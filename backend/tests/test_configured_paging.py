"""P9-8.5 (story: enabler, D 1.2): the configured adapter reads dlt-style paging and selectors.

Served by an in-process fake (httpx.MockTransport), so no source-sim is needed. Covers header_link, json_link,
header_cursor, single_page, data_selector, dependent resources and the repeat guard.
"""

import json
from collections.abc import Callable

import httpx
import pytest

from di.connectors.configured import ConfiguredAdapter
from di.connectors.connection import Connection
from di.connectors.http import Auth, SourceClient, SourceError
from di.core.db import SessionLocal

BASE = "http://fake.test/api"


def _client(handler: Callable[[httpx.Request], httpx.Response], session) -> SourceClient:
    c = SourceClient("fake", BASE, Auth(), session)
    c.http = httpx.Client(transport=httpx.MockTransport(handler))
    return c


def _read(paging: dict, resource: dict, handler, resources: list[dict] | None = None) -> list[dict]:
    conn = Connection("fake", BASE, "rest", "none", {}, paging, resources or [resource])
    a = ConfiguredAdapter(conn)
    with SessionLocal() as s:
        client = _client(handler, s)
        try:
            return [row for row, _ in a.pages(client, resource, None)]
        finally:
            client.close()
            s.rollback()


def _pages(n: int, per: int = 2) -> list[list[dict]]:
    return [[{"id": f"r{p}-{i}"} for i in range(per)] for p in range(n)]


def test_paging_header_link_reads_all():
    pages = _pages(3)

    def handler(req: httpx.Request) -> httpx.Response:
        p = int(req.url.params.get("p", "0"))
        headers = {"Link": f'<{BASE}/items?p={p + 1}>; rel="next", <{BASE}/items?p=0>; rel="first"'} if p < 2 else {}
        return httpx.Response(200, json=pages[p], headers=headers)

    rows = _read({"type": "header_link"}, {"name": "items", "path": "/items", "id_field": "id"}, handler)
    assert [r["id"] for r in rows] == [r["id"] for pg in pages for r in pg]


def test_paging_header_link_resolves_relative_link():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.params.get("p") == "1":
            return httpx.Response(200, json=[{"id": "b"}])
        return httpx.Response(200, json=[{"id": "a"}], headers={"Link": '</api/items?p=1>; rel="next"'})

    rows = _read({"type": "header_link"}, {"name": "items", "path": "/items"}, handler)
    assert [r["id"] for r in rows] == ["a", "b"]


def test_paging_json_link_reads_all_and_stops_on_null():
    pages = _pages(3)

    def handler(req: httpx.Request) -> httpx.Response:
        p = int(req.url.params.get("p", "0"))
        nxt = f"{BASE}/items?p={p + 1}" if p < 2 else None
        return httpx.Response(200, json={"items": pages[p], "meta": {"next": nxt}})

    rows = _read({"type": "json_link", "next_url_path": "meta.next"}, {"name": "items", "path": "/items"}, handler)
    assert len(rows) == 6


def test_paging_header_cursor_reads_all():
    seen: list[str | None] = []

    def handler(req: httpx.Request) -> httpx.Response:
        cur = req.url.params.get("after")
        seen.append(cur)
        nxt = {None: "c1", "c1": "c2"}.get(cur)
        return httpx.Response(200, json=[{"id": f"x{len(seen)}"}], headers={"X-Next": nxt} if nxt else {})

    paging = {"type": "header_cursor", "cursor_path": "X-Next", "cursor_param": "after"}
    rows = _read(paging, {"name": "items", "path": "/items"}, handler)
    assert seen == [None, "c1", "c2"] and len(rows) == 3


def test_paging_single_page_reads_once():
    calls: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=[{"id": "a"}, {"id": "b"}], headers={"Link": f'<{BASE}/items?p=1>; rel="next"'})

    rows = _read({"type": "single_page"}, {"name": "items", "path": "/items"}, handler)
    assert len(rows) == 2 and len(calls) == 1


def test_data_selector_nested():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"items": [{"id": "a"}, {"id": "b"}]}, "items": [{"id": "wrong"}]})

    res = {"name": "items", "path": "/items", "data_selector": "data.items"}
    assert [r["id"] for r in _read({"type": "single_page"}, res, handler)] == ["a", "b"]


def test_items_key_still_means_the_same():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rows": [{"id": "a"}]})

    assert len(_read({"type": "single_page", "items_key": "rows"}, {"name": "items", "path": "/items"}, handler)) == 1


def test_page_style_is_read_as_page_number():
    def handler(req: httpx.Request) -> httpx.Response:
        p = int(req.url.params["page"])
        return httpx.Response(200, json={"items": [{"id": f"p{p}"}] * (2 if p < 3 else 1)})

    rows = _read({"style": "page", "max_size": 2}, {"name": "items", "path": "/items"}, handler)
    assert len(rows) == 5
    rows = _read({"type": "page_number", "max_size": 2}, {"name": "items", "path": "/items"}, handler)
    assert len(rows) == 5


def test_dependent_resource_reads_children():
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/orders":
            return httpx.Response(200, json=[{"id": "o1"}, {"id": "o2"}])
        oid = path.split("/")[3]
        return httpx.Response(200, json=[{"line": f"{oid}-{i}"} for i in range(3)])

    orders = {"name": "orders", "path": "/orders", "id_field": "id"}
    lines = {"name": "lines", "path": "/orders/{resources.orders.id}/lines", "include_from_parent": ["id"]}
    rows = _read({"type": "single_page"}, lines, handler, [orders, lines])
    assert len(rows) == 6
    assert {r["_parent_id"] for r in rows} == {"o1", "o2"}
    assert all(r["line"].startswith(r["_parent_id"]) for r in rows)
    assert all(r["_orders_id"] == r["_parent_id"] for r in rows)


def test_dependent_resource_without_parent_fails():
    lines = {"name": "lines", "path": "/orders/{resources.orders.id}/lines"}
    with pytest.raises(SourceError, match="orders"):
        _read({"type": "single_page"}, lines, lambda req: httpx.Response(200, json=[]), [lines])


def test_paging_stops_on_repeat():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps({"items": [{"id": "a"}], "next": f"{BASE}/items?p=1"}),
            headers={"content-type": "application/json"},
        )

    with pytest.raises(SourceError, match="loop"):
        _read({"type": "json_link", "next_url_path": "next"}, {"name": "items", "path": "/items"}, handler)


def test_cursor_repeat_stops():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [{"id": "a"}], "next_cursor": "same"})

    with pytest.raises(SourceError, match="loop"):
        _read({"type": "cursor", "cursor_path": "next_cursor"}, {"name": "items", "path": "/items"}, handler)


def test_unknown_paging_type_is_a_client_error():
    with pytest.raises(SourceError, match="paging type"):
        _read({"type": "bogus"}, {"name": "items", "path": "/items"}, lambda req: httpx.Response(200, json=[]))
