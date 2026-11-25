"""An adapter for any spec-shaped HTTP API, configured by its connection row (plan 6, task A3).

    ConfiguredAdapter(conn, rows)   conn: di.connectors.connection.Connection; rows: the source's MapRows (A4)

A source connected from the catalogue or set up by hand has no Python adapter. Its `source_connection` row says
everything this adapter needs (the same keys as source-sim's `sim.generic.spec`):
- resources: [{name, path, id_field, delta_param?, changed_field?}], paths relative to base_url;
- paging: {style: offset | page | cursor, limit_param, offset_param, page_param, size_param, cursor_param, items_key,
  next_key, total_key, max_size}. Without a next value in the body, offset and page paging move on by the page's
  length and stop at `total` or at a short page;
  P9-8.5 adds dlt `rest_api` vocabulary (a pattern, not the dlt package): `paging.type` is offset | page_number
  (`page` and `style` stay accepted) | cursor | header_link (`Link: <url>; rel="next"`) | json_link (a next URL in the
  body at `next_url_path`) | header_cursor (a response header named by `cursor_path`, sent back as `cursor_param`) |
  single_page. A resource's `data_selector` (dotted path, "data.items") says where its records are; `items_key` means
  the same. A link or cursor already read stops the read with an error naming the loop.
  Dependent resources: `path: "/orders/{resources.orders.id}/lines"` (+ `include_from_parent: ["id"]`) reads the
  parent first and calls the path once per parent record; each child gets `_parent_id` and `_orders_id`.
  Owns: reading one resource. Never does: writing, mapping, or storing.
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
import re
from collections.abc import Iterator
from typing import Any

import httpx

from di.connectors.base import Adapter, Record, Resource
from di.connectors.connection import Connection
from di.connectors.generic import source_clock
from di.connectors.http import ApiKey, Auth, Basic, OAuthClientCredentials, SourceClient, SourceError
from di.services.canonical.store import Fact

PAGING_TYPES = ("offset", "page_number", "cursor", "header_link", "json_link", "header_cursor", "single_page")
MAX_PAGES = 100000  # the cap on requests of one resource (a dependent resource counts one per parent record)
_PARENT_REF = re.compile(r"\{resources\.([A-Za-z0-9_-]+)\.([^}]+)\}")
_LINK = re.compile(r"<([^>]*)>([^<]*)")

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
        self.stored = dict(conn.paging or {})
        self.paging = DEFAULT_PAGING | self.stored
        kind = str(self.stored.get("type") or self.stored.get("style") or "offset")
        self.kind = "page_number" if kind == "page" else kind  # `page` is the old name of page_number

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
        """Every row of one resource, following the paging to the end. Yields (row, request URL).

        A path with `{resources.<parent>.<field>}` is a dependent resource: the parent is read first, the path is
        called once per parent record, and each child row is tagged `_parent_id` and `_<parent>_<field>`.
        """
        if _PARENT_REF.search(str(r["path"])):
            yield from self._children(client, r, since, ())
        else:
            yield from self._read(client, str(r["path"]), r, since)

    def _children(
        self, client: SourceClient, r: dict[str, Any], since: str | None, chain: tuple[str, ...]
    ) -> Iterator[tuple[dict, str]]:
        template, name = str(r["path"]), str(r.get("name"))
        ref = _PARENT_REF.findall(template)[0]
        parent_name = ref[0]
        parent = next((x for x in self.conn.resources or [] if x.get("name") == parent_name), None)
        if parent is None or parent_name in (*chain, name):
            raise SourceError("client", f"{self.source_id}: {name} needs the resource {parent_name}, which is not configured")
        include = [str(f) for f in r.get("include_from_parent") or [ref[1]]]
        if _PARENT_REF.search(str(parent["path"])):
            parents = self._children(client, parent, None, (*chain, name))
        else:
            parents = self._read(client, str(parent["path"]), parent, None)
        for calls, (prow, _) in enumerate(parents, 1):
            if calls > MAX_PAGES:
                raise SourceError("client", f"{self.source_id}: {name} would call more than {MAX_PAGES} times")
            path = _fill(template, prow)
            for row, url in self._read(client, path, r, since):
                tags = {f"_{parent_name}_{f}": _dig(prow, f) for f in include}
                yield {**row, "_parent_id": _dig(prow, include[0]), **tags}, url

    def _read(self, client: SourceClient, path: str, r: dict[str, Any], since: str | None) -> Iterator[tuple[dict, str]]:
        """One list, page by page, by the connection's paging type (module docstring)."""
        p, kind = self.paging, self.kind
        if kind not in PAGING_TYPES:
            raise SourceError("client", f"{self.source_id}: unknown paging type {kind!r} (one of {', '.join(PAGING_TYPES)})")
        size = int(p.get("max_size") or 100)
        selector = str(r.get("data_selector") or p["items_key"])
        links = kind in ("header_link", "json_link", "single_page")
        nxt: Any = None  # the next cursor, or the next value the body names (offset, page number)
        next_url: str | None = None
        offset, page = 0, 1
        seen: set[str] = set()
        for _ in range(MAX_PAGES):
            if next_url:
                resp = client.request("GET", next_url)
            else:
                q: dict[str, Any] = {}
                if kind == "page_number":
                    q[p["size_param"]] = size
                    q[p["page_param"]] = nxt if nxt is not None else page
                elif kind in ("cursor", "header_cursor"):
                    q[p["limit_param"]] = size
                    if nxt is not None:
                        q[p["cursor_param"]] = nxt
                elif kind == "offset":
                    q[p["limit_param"]] = size
                    q[p["offset_param"]] = nxt if nxt is not None else offset
                elif "limit_param" in self.stored:  # link paging sends a page size only when asked to
                    q[p["limit_param"]] = size
                if since and r.get("delta_param"):
                    q[r["delta_param"]] = since.replace("+00:00", "Z")
                resp = client.request("GET", path, params=q)
            url = str(resp.request.url)
            body = resp.json()
            rows = _dig(body, selector) if isinstance(body, dict) else body
            rows = rows if isinstance(rows, list) else []
            client.note_records(len(rows))
            for row in rows:
                if isinstance(row, dict):
                    yield row, url
            if not rows or kind == "single_page":
                return
            if links:
                found = _next_link(resp, body, kind, p)
                if not found:
                    return
                next_url = str(resp.request.url.join(found))
                self._guard(seen, url, next_url, path)
                continue
            if kind in ("cursor", "header_cursor"):
                nxt = _next_cursor(resp, body, kind, p)
                if nxt is None:
                    return
                self._guard(seen, "", str(nxt), path)
                continue
            nk = p.get("next_key")
            if nk and isinstance(body, dict) and nk in body:
                nxt = body.get(nk)
                if nxt is None:
                    return
                continue
            offset, page = offset + len(rows), page + 1
            total = body.get(p["total_key"]) if p.get("total_key") and isinstance(body, dict) else None
            if (total is not None and offset >= int(total)) or len(rows) < size:
                return
        raise SourceError("client", f"{self.source_id}: paging did not end for {path}")

    def _guard(self, seen: set[str], current: str, nxt: str, path: str) -> None:
        """A next link or cursor read before means the server repeats itself: stop with an error naming the loop."""
        seen.add(current)
        if nxt in seen:
            raise SourceError("client", f"{self.source_id}: paging loop for {path}: {nxt} was already read")
        seen.add(nxt)

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


def _fill(template: str, parent: dict) -> str:
    """The dependent path with each {resources.<parent>.<field>} replaced by that field of the parent record."""
    return _PARENT_REF.sub(lambda m: str(_dig(parent, m.group(2))), template)


def _dig(value: Any, path: str) -> Any:
    """A dotted path into a body ("data.items", "$.meta.next", "rows.0"); None when any step is missing."""
    for step in path.removeprefix("$.").removeprefix("$").removesuffix("[*]").split("."):
        if not step:
            continue
        if isinstance(value, dict):
            value = value.get(step)
        elif isinstance(value, list) and step.isdigit() and int(step) < len(value):
            value = value[int(step)]
        else:
            return None
    return value


def _next_link(resp: httpx.Response, body: Any, kind: str, p: dict[str, Any]) -> str | None:
    """The next page's URL: the `Link` header's rel="next" (header_link), or the body at next_url_path (json_link)."""
    if kind == "json_link":
        v = _dig(body, str(p.get("next_url_path") or p.get("next_key") or "next"))
        return str(v) if v else None
    for url, params in _LINK.findall(resp.headers.get("link", "")):
        if re.search(r'rel\s*=\s*"?[^";,]*\bnext\b', params):
            return url.strip()
    return None


def _next_cursor(resp: httpx.Response, body: Any, kind: str, p: dict[str, Any]) -> Any:
    """The next cursor: a response header (header_cursor) or the body at cursor_path (cursor, default next_key)."""
    if kind == "header_cursor":
        return resp.headers.get(str(p.get("cursor_path") or "next")) or None
    return _dig(body, str(p.get("cursor_path") or p.get("next_key") or "next")) if isinstance(body, dict) else None
