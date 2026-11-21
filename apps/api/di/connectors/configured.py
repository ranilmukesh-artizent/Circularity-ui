"""An adapter for any spec-shaped HTTP API, configured by its connection row (plan 6, task A3).

    ConfiguredAdapter(conn, rows)   conn: di.connectors.connection.Connection; rows: the source's MapRows (A4)

A source connected from the catalogue or set up by hand has no Python adapter. Its `source_connection` row says
everything this adapter needs (the same keys as source-sim's `sim.generic.spec`):
- resources: [{name, path, id_field, delta_param?, changed_field?}], paths relative to base_url;
- paging: {style: offset | page | cursor, limit_param, offset_param, page_param, size_param, cursor_param, items_key,
  next_key, total_key, max_size}. Without a next value in the body, offset and page paging move on by the page's
  length and stop at `total` or at a short page;
- auth_kind: none | api_key (header, prefix) | bearer | basic (user) | oauth_cc (token_path relative to base_url,
  client_id, form); the secret is the stored one (di.connectors.secrets).
Records are mapped with the source's field mapping (di.connectors.mapping.apply_rows): a row whose source field is
missing fails that record ("missing field …"), counted by the sync, not fatal.

Delta reads: a resource with `delta_param` is read with `?{delta_param}=<cursor>` after its first full read. The cursor
is the source's clock at the start of the read when the system is source-sim (its documents change on the simulated
clock), else the record's `changed_field` when the resource names one; without either the resource is read in full.
"""

import hashlib
import json
from collections.abc import Iterator
from typing import Any

import httpx

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.connection import Connection
from di.connectors.generic import source_clock
from di.connectors.http import ApiKey, Auth, Basic, OAuthClientCredentials, SourceClient, SourceError

DEFAULT_PAGING: dict[str, Any] = {"style": "offset", "limit_param": "limit", "offset_param": "offset", "page_param": "page",
                  "size_param": "page_size", "cursor_param": "cursor", "items_key": "items", "next_key": "next",
                  "total_key": "total", "max_size": 100}  # fmt: skip


class NoCredential(Auth):
    """A connection that needs a secret but has none stored: the first call fails as an auth error."""

    def __init__(self, source_id: str):
        self.source_id = source_id

    def headers(self, client, force_refresh=False):  # noqa: ARG002 - the Auth interface
        raise SourceError("auth", f"{self.source_id}: no credential is stored for this connection")


class ConfiguredAdapter(Adapter):
    def __init__(self, conn: Connection, rows: list | None = None):
        self.conn = conn
        self.source_id = conn.source_id
        self.rows = list(rows or [])
        self.paging = DEFAULT_PAGING | dict(conn.paging or {})

    # ------------------------------------------------------------- signing in
    def auth(self, conn: Connection | None = None, secret: str | None = None) -> Auth:
        c = conn or self.conn
        p, kind = c.auth_params or {}, c.auth_kind
        if kind in ("none", "builtin"):
            return Auth()
        if not secret:
            return NoCredential(self.source_id)
        if kind == "api_key":
            return ApiKey(p.get("header") or "x-api-key", secret, p.get("prefix") or "")
        if kind == "bearer":
            return ApiKey("Authorization", secret, "Bearer ")
        if kind == "basic":
            return Basic(p.get("user") or "di-connector", secret)
        if kind == "oauth_cc":
            return OAuthClientCredentials(p.get("token_path") or "/oauth/token", p.get("client_id") or "di-connector", secret,
                                          form=bool(p.get("form")))  # fmt: skip
        raise SourceError("client", f"{self.source_id}: unknown authentication kind {kind}")

    # ------------------------------------------------------------- reading
    def resources(self) -> list[Resource]:
        out = []
        for r in self.conn.resources or []:
            if not r.get("name") or not r.get("path"):
                continue
            delta = bool(r.get("delta_param")) and (self.conn.simulated or bool(r.get("changed_field")))
            out.append(Resource(str(r["name"]), self._reader(r), delta))
        return out

    def _reader(self, r: dict[str, Any]):
        def read(client: SourceClient, since: str | None) -> Iterator[Record]:
            now = source_clock(client) if self.conn.simulated else None
            for row, url in self.pages(client, r, since):
                yield Record(r["name"], self._ext_id(row, r.get("id_field")), row, url, now or _changed(row, r))

        return read

    @staticmethod
    def _ext_id(row: dict, id_field: str | None) -> str:
        v = row.get(id_field) if id_field else None
        if v is None:  # no id: a stable one from the content, so a re-read updates the same raw record
            return "sha1:" + hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()[:20]  # noqa: S324
        return str(v)

    def pages(self, client: SourceClient, r: dict[str, Any], since: str | None) -> Iterator[tuple[dict, str]]:
        """Every row of one resource, following the paging to the end. Yields (row, request URL)."""
        p = self.paging
        style, size = p["style"], int(p.get("max_size") or 100)
        nxt: Any = None
        offset, page = 0, 1
        for _ in range(100000):
            q: dict[str, Any] = {}
            if style == "page":
                q[p["size_param"]] = size
                q[p["page_param"]] = nxt if nxt is not None else page
            else:
                q[p["limit_param"]] = size
                if style == "cursor":
                    if nxt is not None:
                        q[p["cursor_param"]] = nxt
                else:
                    q[p["offset_param"]] = nxt if nxt is not None else offset
            if since and r.get("delta_param"):
                q[r["delta_param"]] = since.replace("+00:00", "Z")
            body = client.get_json(r["path"], params=q)
            rows = (body.get(p["items_key"]) if isinstance(body, dict) else body) or []
            client.note_records(len(rows))
            url = str(httpx.URL(client.url(r["path"]), params=q))
            for row in rows:
                if isinstance(row, dict):
                    yield row, url
            if not rows:
                return
            nk = p.get("next_key")
            if nk and isinstance(body, dict) and nk in body:
                nxt = body.get(nk)
                if nxt is None:
                    return
                continue
            if style == "cursor":
                return  # no next cursor: one page
            offset, page = offset + len(rows), page + 1
            total = body.get(p["total_key"]) if p.get("total_key") and isinstance(body, dict) else None
            if (total is not None and offset >= int(total)) or len(rows) < size:
                return
        raise SourceError("client", f"{self.source_id}: paging did not end for {r['path']}")

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        try:
            from di.connectors.mapping import apply_rows  # plan 6 A4
        except ImportError:  # before A4: no mapping, no facts (the records are still stored raw)
            return []
        return apply_rows(self.rows, record)


def active_rows(s, source_id: str) -> list:
    """The source's field mapping rows (di.connectors.mapping, plan 6 A4); [] before that module exists."""
    try:
        from di.connectors import mapping
    except ImportError:
        return []
    return mapping.active_rows(s, source_id)


def _changed(row: dict, r: dict) -> str | None:
    f = r.get("changed_field")
    v = row.get(f) if f else None
    return str(v) if v else None
