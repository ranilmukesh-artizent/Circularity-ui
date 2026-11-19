"""The HTTP side of a connector: authentication, retries and the fetch log (docs/BACKEND_STEPS.md, B9).

Every call is written to `fetch_log` (Audit › Fetch log): method, URL, status, record count, duration.
Auth strategies:
    Basic(user, password)                         Authorization: Basic …
    ApiKey(header, key, prefix="")                <header>: <prefix><key>
    OAuthClientCredentials(token_url, client_id, client_secret, form=False, extra={})
        POST token_url grant_type=client_credentials (client in Basic auth, or in the form when form=True);
        the token is cached until it expires and fetched again once on a 401.
    Static(headers)                               fixed headers (e.g. a bearer token issued elsewhere)
Strategies combine: Combined(ApiKey(...), OAuthClientCredentials(...)) for Ariba's apiKey + bearer.
"""

import base64
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session


class SourceError(Exception):
    """A source call failed. `kind`: auth (401/403), unavailable (5xx, network), client (other 4xx)."""

    def __init__(self, kind: str, message: str, status: int | None = None):
        super().__init__(message)
        self.kind, self.status = kind, status


class Auth:
    def headers(self, client: "SourceClient", force_refresh: bool = False) -> dict[str, str]:
        return {}


@dataclass
class Basic(Auth):
    user: str
    password: str

    def headers(self, client, force_refresh=False):
        return {"Authorization": "Basic " + base64.b64encode(f"{self.user}:{self.password}".encode()).decode()}


@dataclass
class ApiKey(Auth):
    header: str
    key: str
    prefix: str = ""

    def headers(self, client, force_refresh=False):
        return {self.header: self.prefix + self.key}


@dataclass
class Static(Auth):
    values: dict[str, str]

    def headers(self, client, force_refresh=False):
        return dict(self.values)


@dataclass
class OAuthClientCredentials(Auth):
    token_url: str  # relative to the source's base URL host (e.g. "/sap/bc/sec/oauth2/token")
    client_id: str
    client_secret: str
    form: bool = False  # send the client in the form body instead of Basic auth
    extra: dict[str, str] = field(default_factory=dict)  # extra form fields
    _token: str | None = None
    _expires: float = 0

    def headers(self, client, force_refresh=False):
        if force_refresh or not self._token or self._expires < time.time() + 30:
            data = {"grant_type": "client_credentials", **self.extra}
            auth = None
            if self.form:
                data |= {"client_id": self.client_id, "client_secret": self.client_secret}
            else:
                auth = (self.client_id, self.client_secret)
            r = client.raw("POST", self.token_url, data=data, auth=auth, log_records=False)
            if r.status_code != 200:
                raise SourceError("auth", f"Token request failed: HTTP {r.status_code}", r.status_code)
            body = r.json()
            self._token = body["access_token"]
            self._expires = time.time() + float(body.get("expires_in", 3600))
        return {"Authorization": "Bearer " + self._token}


@dataclass
class Combined(Auth):
    parts: list[Auth]

    def headers(self, client, force_refresh=False):
        out: dict[str, str] = {}
        for p in self.parts:
            out |= p.headers(client, force_refresh)
        return out


class SourceClient:
    """One source's HTTP client for one sync run."""

    def __init__(
        self, source_id: str, base_url: str, auth: Auth, session: Session, run_id: int | None = None, timeout: float = 20
    ):
        self.source_id, self.base_url, self.auth = source_id, base_url.rstrip("/"), auth
        self.session, self.run_id = session, run_id
        self.http = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self.http.close()

    def url(self, path: str) -> str:
        return path if path.startswith("http") else self.base_url + path

    def raw(self, method: str, path: str, log_records: bool = True, **kw) -> httpx.Response:
        """One HTTP call, logged. No auth headers added (used by token endpoints and by `request`)."""
        url = self.url(path)
        t0 = time.perf_counter()
        err = None
        try:
            r = self.http.request(method, url, **kw)
        except httpx.HTTPError as e:
            err = f"{type(e).__name__}: {e}"
            self._log(method, str(httpx.URL(url, params=kw.get("params"))), None, None, t0, err)
            raise SourceError("unavailable", err) from e
        self._log(method, str(r.request.url), r.status_code, None, t0, None if r.status_code < 400 else r.text[:300])
        return r

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        """An authenticated call; refreshes OAuth once on a 401. Raises SourceError for failures."""
        headers = kw.pop("headers", {})
        r = self.raw(method, path, headers=self.auth.headers(self) | headers, **kw)
        if r.status_code == 401:
            r = self.raw(method, path, headers=self.auth.headers(self, force_refresh=True) | headers, **kw)
        if r.status_code in (401, 403):
            raise SourceError("auth", f"{self.source_id}: HTTP {r.status_code} {r.text[:200]}", r.status_code)
        if r.status_code >= 500:
            raise SourceError("unavailable", f"{self.source_id}: HTTP {r.status_code}", r.status_code)
        if r.status_code >= 400:
            raise SourceError("client", f"{self.source_id}: HTTP {r.status_code} {r.text[:300]}", r.status_code)
        return r

    def get_json(self, path: str, **kw) -> Any:
        return self.request("GET", path, **kw).json()

    def note_records(self, n: int) -> None:
        """Attach a record count to the most recent fetch-log entry of this run."""
        self.session.execute(
            text("UPDATE fetch_log SET records = :n WHERE id = (SELECT max(id) FROM fetch_log WHERE source_id = :s)"),
            {"n": n, "s": self.source_id},
        )

    def _log(self, method, url, status, records, t0, error) -> None:
        self.session.execute(
            text(
                "INSERT INTO fetch_log (run_id, source_id, method, url, status, records, duration_ms, error) "
                "VALUES (:r, :s, :m, :u, :st, :n, :d, :e)"
            ),
            {
                "r": self.run_id,
                "s": self.source_id,
                "m": method,
                "u": url[:2000],
                "st": status,
                "n": records,
                "d": int((time.perf_counter() - t0) * 1000),
                "e": error,
            },
        )
