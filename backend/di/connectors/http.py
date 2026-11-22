"""The HTTP side of a connector: authentication, retries and the fetch log (docs/backend-steps.md, B9).

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
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core.config import get_settings


class SourceError(Exception):
    """A source call failed. `kind`: auth (401/403), unavailable (5xx, network), client (other 4xx)."""

    def __init__(self, kind: str, message: str, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.kind, self.status = kind, status
        self.retry_after = retry_after  # seconds, from the answer's Retry-After header (429, 503)


class Auth:
    def headers(self, client: "SourceClient", force_refresh: bool = False) -> dict[str, str]:  # noqa: ARG002 - the Auth interface (OAuth uses both)
        return {}


@dataclass
class Basic(Auth):
    user: str
    password: str

    def headers(self, client, force_refresh=False):  # noqa: ARG002 - the Auth interface (OAuth uses both)
        return {"Authorization": "Basic " + base64.b64encode(f"{self.user}:{self.password}".encode()).decode()}


@dataclass
class ApiKey(Auth):
    header: str
    key: str
    prefix: str = ""

    def headers(self, client, force_refresh=False):  # noqa: ARG002 - the Auth interface (OAuth uses both)
        return {self.header: self.prefix + self.key}


@dataclass
class Static(Auth):
    values: dict[str, str]

    def headers(self, client, force_refresh=False):  # noqa: ARG002 - the Auth interface (OAuth uses both)
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


# ---------------------------------------------------------------- retries (plan 6 A6)
RETRIES = 3  # after the first try
RETRY_AFTER_MAX = 30.0  # seconds: a longer Retry-After is cut to this
_TIMEOUTS = (httpx.ConnectTimeout, httpx.ReadTimeout)


def _sleep(seconds: float) -> None:
    """The backoff wait (a module function, so tests can record the waits instead of sleeping)."""
    time.sleep(seconds)


def _retryable(e: SourceError) -> bool:
    if e.status is not None:
        return e.status == 429 or e.status >= 500
    return isinstance(e.__cause__, _TIMEOUTS)  # a refused connection or an unknown host fails at once


def _retry_after(value: str | None) -> float | None:
    """Retry-After in seconds (a number or an HTTP date), or None when absent or unreadable."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def _wait(e: SourceError, attempt: int) -> float:
    if e.retry_after is not None:
        return min(e.retry_after, RETRY_AFTER_MAX)
    return get_settings().source_retry_base_seconds * 2**attempt


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
        """One HTTP call, logged. No auth headers added (used by token endpoints and by `request`).

        Every call gets a fetch-log row. A failed call's row carries the start of the response body, unless
        `log_records=False` (token and session calls): their bodies can hold credentials, so only the status is kept.
        """
        url = self.url(path)
        t0 = time.perf_counter()
        err = None
        try:
            r = self.http.request(method, url, **kw)
        except httpx.HTTPError as e:
            err = f"{type(e).__name__}: {httpx.URL(url).host}: {e}"  # the host, so a wrong URL shows (plan 6 A2)
            self._log(method, str(httpx.URL(url, params=kw.get("params"))), None, None, t0, err)
            raise SourceError("unavailable", err) from e
        error = None
        if r.status_code >= 400:
            error = r.text[:300] if log_records else f"HTTP {r.status_code}"
        self._log(method, str(r.request.url), r.status_code, None, t0, error)
        return r

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        """An authenticated call; refreshes OAuth once on a 401. Raises SourceError for failures.

        A GET (plan 6 A6) is tried again up to RETRIES times on 429, 5xx and connect or read timeouts, after the
        configured base wait doubled per retry (0.5 s, 1 s, 2 s), or after the answer's Retry-After (at most 30 s).
        Every try has its own fetch-log row. Writes are never repeated here: a repeated POST could act twice.
        """
        attempt = 0
        while True:
            try:
                return self._request_once(method, path, **kw)
            except SourceError as e:
                if method.upper() != "GET" or attempt >= RETRIES or not _retryable(e):
                    raise
                _sleep(_wait(e, attempt))
                attempt += 1

    def _request_once(self, method: str, path: str, **kw) -> httpx.Response:
        headers = kw.pop("headers", {})
        r = self.raw(method, path, headers=self.auth.headers(self) | headers, **kw)
        if r.status_code == 401:
            r = self.raw(method, path, headers=self.auth.headers(self, force_refresh=True) | headers, **kw)
        if r.status_code in (401, 403):
            raise SourceError("auth", f"{self.source_id}: HTTP {r.status_code} {r.text[:200]}", r.status_code)
        after = _retry_after(r.headers.get("retry-after"))
        if r.status_code >= 500:
            raise SourceError("unavailable", f"{self.source_id}: HTTP {r.status_code}", r.status_code, after)
        if r.status_code >= 400:
            raise SourceError("client", f"{self.source_id}: HTTP {r.status_code} {r.text[:300]}", r.status_code, after)
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
