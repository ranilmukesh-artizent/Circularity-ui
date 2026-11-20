"""Helpers shared by the adapters of source-sim's generic, spec-driven mocks (docs/backend-steps.md, B5 and B9).

Moved here from manhattan.py and oracle_lease.py so those adapters can be replaced without breaking the others:
- `GenericAdapter`: the base for a generic-mock adapter (spec demo credentials, the spec's paging, `?updated_since=` deltas)
- `generic_pages`, `source_clock`, `utc`: the same building blocks as functions
- `to_usd` (83.5 INR/USD, 0.92 EUR/USD), `tenant_name`, `keep`, `iso_z`
"""

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from di.canonical.store import Fact
from di.config import get_settings
from di.connectors.base import Adapter, Record
from di.connectors.http import ApiKey, Basic, OAuthClientCredentials, SourceClient

PAGE = 200


# ------------------------------------------------------------------ shared by the generic-mock adapters
def utc(v: str | None) -> str | None:
    """Any ISO 8601 timestamp with an offset → UTC with a Z ("2026-10-05T10:11:00-04:00" → "2026-10-05T14:11:00Z")."""
    if not v:
        return None
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def source_clock(client: SourceClient) -> str | None:
    """The source's current time (ISO UTC), taken before a read: the delta cursor of every record of that read.

    The generic mocks keep a change stamp per document (filtered by ?updated_since=) but do not return it, and they
    stamp changes with the simulated clock, so the clock is the only way to know "now" in the source's time.
    Without it (a real system), records carry no cursor and resources are read in full.
    """
    try:
        r = client.http.get(get_settings().source_sim_url.rstrip("/") + "/_sim/clock")
        return datetime.fromisoformat(r.json()["now"]).astimezone(UTC).isoformat()
    except Exception:  # noqa: BLE001 - no clock: full reads
        return None


def generic_pages(
    client: SourceClient,
    path: str,
    since: str | None,
    *,
    items_key: str,
    next_key: str,
    next_param: str,
    size_param: str,
    since_param: str = "updated_since",
    params: dict[str, Any] | None = None,
) -> Iterator[tuple[dict, str]]:
    """Every document of a generic-mock list, following the `next` value (page number, offset or cursor) to the end."""
    base = dict(params or {}) | {size_param: PAGE}
    if since:
        base[since_param] = since
    nxt = None
    while True:
        r = client.request("GET", path, params=base | ({next_param: nxt} if nxt is not None else {}))
        body = r.json()
        items = body.get(items_key) or []
        client.note_records(len(items))
        for it in items:
            yield it, str(r.request.url)
        nxt = body.get(next_key)
        if nxt is None or not items:
            return


INR_PER_USD = Decimal("83.5")
EUR_PER_USD = Decimal("0.92")
FX_NOTE = {"INR": "83.5 INR/USD", "EUR": "0.92 EUR/USD"}


def to_usd(amount, currency: str | None) -> float:
    """Money to USD at the demo's dated rates (83.5 INR/USD, 0.92 EUR/USD), to the cent."""
    a = Decimal(str(amount))
    cur = (currency or "USD").upper()
    if cur == "INR":
        a = a / INR_PER_USD
    elif cur == "EUR":
        a = a / EUR_PER_USD
    elif cur != "USD":
        raise ValueError(f"no rate for {cur}")
    return float(a.quantize(Decimal("0.01")))


def tenant_name(key: str | None) -> str | None:
    """Tenant key → name: CUSTOMER_A → Customer A."""
    if not key:
        return None
    return " ".join(w if len(w) == 1 else w.capitalize() for w in re.split(r"[_\s]+", key.strip()) if w)


def keep(facts: list[Fact]) -> list[Fact]:
    """Drop facts the source left empty."""
    return [f for f in facts if f.value is not None]


def iso_z(ts: str) -> str:
    return ts.replace("+00:00", "Z")


class GenericAdapter(Adapter):
    """An adapter for one of source-sim's generic mocks (apps/source-sim/sim/generic)."""

    auth_kind: str = "oauth"  # oauth | api_key | basic
    api_key_header: str = "x-api-key"
    token_path: str = "/oauth/token"  # noqa: S105 - a URL path, not a secret (relative to base_path)
    items_key: str = "items"
    next_key: str = "next"  # the body key that holds the next page / offset / cursor
    next_param: str = "offset"  # the query parameter that takes it
    size_param: str = "limit"
    page_size: int = 200
    since_param: str = "updated_since"

    def auth(self):
        sid = self.source_id
        if self.auth_kind == "api_key":
            return ApiKey(self.api_key_header, f"{sid}-demo-key")
        if self.auth_kind == "basic":
            return Basic("di-connector", f"{sid}-demo")
        return OAuthClientCredentials(self.token_path, "di-connector", f"{sid}-demo-secret")

    # ------------------------------------------------------------- reading
    def pages(self, client: SourceClient, path: str, since: str | None = None, **params) -> Iterator[tuple[dict, str]]:
        """Every row of a list, following the paging to the end. Yields (row, request URL)."""
        nxt = None
        while True:
            q = {**params, self.size_param: str(self.page_size)}
            if since:
                q[self.since_param] = iso_z(since)
            if nxt is not None:
                q[self.next_param] = str(nxt)
            body = client.get_json(path, params=q)
            rows = body[self.items_key]
            client.note_records(len(rows))
            url = str(httpx.URL(client.url(path), params=q))
            for row in rows:
                yield row, url
            nxt = body.get(self.next_key)
            if nxt is None or not rows:
                return

    def read_all(self, client: SourceClient, path: str, **params) -> list[dict]:
        return [row for row, _ in self.pages(client, path, **params)]

    def source_now(self, client: SourceClient) -> str | None:
        """The source's clock (source-sim's simulated time), used as the delta cursor of a read that starts now."""
        try:
            r = client.http.get(get_settings().source_sim_url.rstrip("/") + "/_sim/clock")
            return r.json()["now"] if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError, KeyError):
            return None

    def flat(self, client: SourceClient, name: str, path: str, id_field: str, since: str | None) -> Iterator[Record]:
        """One record per document."""
        now = self.source_now(client)
        for row, url in self.pages(client, path, since):
            yield Record(name, str(row[id_field]), row, url, now)

    def grouped(
        self, client: SourceClient, name: str, path: str, group_field: str, since: str | None, extra=None
    ) -> Iterator[Record]:
        """One record per group (e.g. every certificate of one asset). On a delta read, each group with a change is
        read again in full (filtered by the group field), so the record always holds the whole group."""
        now = self.source_now(client)
        groups: dict[str, list[dict]] = {}
        urls: dict[str, str] = {}
        for row, url in self.pages(client, path, since):
            key = row.get(group_field)
            if key is None:
                continue
            groups.setdefault(str(key), []).append(row)
            urls.setdefault(str(key), url)
        for key in sorted(groups):
            rows = groups[key]
            url = urls[key]
            if since:
                rows = self.read_all(client, path, **{group_field: key})
                url = str(httpx.URL(client.url(path), params={group_field: key}))
            payload = {group_field: key, "items": rows}
            if extra:
                payload |= extra(client)
            yield Record(name, key, payload, url, now)
