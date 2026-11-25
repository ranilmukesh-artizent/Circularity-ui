"""P9-8.3 (story: enabler, 01 section 2; R21): discovery reads a sample of up to 500 records per resource from a TEST
connection into the raw store, marked dry, and writes no canonical fact.

Served by an in-process fake (httpx.MockTransport): no source-sim is needed. The connection is a generic REST
connection in the test environment; the fake plays its host.
"""
# ruff: noqa: E501 - long lines in the SQL and the call bodies

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text

from di.connectors import connection, discover
from di.connectors.http import Auth, SourceClient, SourceError
from di.core.db import SessionLocal, engine
from tests import starting
from tests.helpers import call

BASE = "http://fake.test/api"
SID = "t83sample"
OFFSET = {"type": "offset", "limit_param": "limit", "offset_param": "offset", "total_key": "total", "max_size": 100}


def _clean() -> None:
    with engine.begin() as c:
        for t in ("fetch_log", "raw_record", "source_connection", "source_secret", "field_mapping"):
            c.execute(text(f"DELETE FROM {t} WHERE source_id = :i"), {"i": SID})  # noqa: S608 - fixed names
        c.execute(text("DELETE FROM source_system WHERE id = :i"), {"i": SID})


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    _clean()
    starting.reset()


def _source(environment: str = "test", paging: dict | None = None, resources: list[dict] | None = None) -> None:
    with SessionLocal() as s:
        s.execute(
            text(
                "INSERT INTO source_system (id, vendor, type, status, interval_min, authority, owner, org_unit_id) "
                "VALUES (:i, 'Parts API', 'erp', 'live', 30, '{}', 'Integration Engineering', 'Customer A')"
            ),
            {"i": SID},
        )
        connection.save_connection(
            s, SID, "test", base_url=BASE, auth_kind="none", paging=paging if paging is not None else OFFSET,
            resources=resources or [{"name": "parts", "path": "/parts", "id_field": "id"}],
        )  # fmt: skip
        connection.tag(s, SID, environment=environment, system_owner="approver", registry_id="generic-rest", registry_version=1)
        s.commit()


def _client(handler: Callable[[httpx.Request], httpx.Response], s) -> SourceClient:
    c = SourceClient(SID, BASE, Auth(), s)
    c.http = httpx.Client(transport=httpx.MockTransport(handler))
    return c


def _offset_server(
    n: int, calls: list[httpx.Request] | None = None, total: bool = True
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(req: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(req)
        q = req.url.params
        off, lim = int(q.get("offset", 0)), int(q.get("limit", 100))
        items = [{"id": f"r{i:04d}", "name": f"Part {i}", "serial": f"SN-{i}"} for i in range(off, min(off + lim, n))]
        return httpx.Response(200, json={"items": items} | ({"total": n} if total else {}))

    return handler


def _landed() -> list[tuple[str, str | None]]:
    with engine.begin() as c:
        return [
            (r[0], r[1])
            for r in c.execute(text("SELECT ext_id, request FROM raw_record WHERE source_id = :i ORDER BY ext_id"), {"i": SID})
        ]


def _facts() -> int:
    with engine.begin() as c:
        n = c.execute(text("SELECT count(*) FROM provenance WHERE source_id = :i"), {"i": SID}).scalar() or 0
        return int(n)


def test_discover_reads_500_from_test():
    _source()
    with SessionLocal() as s:
        client = _client(_offset_server(1200), s)
        report = discover.sample_report(s, SID, client=client)
        s.commit()
    assert report["parts"] == {"read": 500, "spread": True}
    ids = [int(e[1:]) for e, _ in _landed()]
    assert len(ids) == 500
    head = [i for i in ids if i < 250]
    assert len(head) == 250  # the newest pages: the first 250, whole
    rest = sorted(i for i in ids if i >= 250)
    assert len(rest) == 250 and rest[0] < 600 and rest[-1] > 900  # spread over the window, not a second block
    assert len({i // 316 for i in rest}) >= 3
    assert all((req or "").startswith(discover.DRY) for _, req in _landed())  # marked dry
    assert _facts() == 0  # nothing canonical


def test_discover_sample_test_returns_counts_per_resource():
    _source()
    with SessionLocal() as s:
        assert discover.sample_test(s, SID, client=_client(_offset_server(1200), s)) == {"parts": 500}
        s.rollback()


def test_discover_small_resource_is_read_whole():
    _source()
    with SessionLocal() as s:
        report = discover.sample_report(s, SID, client=_client(_offset_server(130), s))
        s.commit()
    assert report["parts"]["read"] == 130 and len(_landed()) == 130


def test_discover_without_a_total_reads_the_newest_500_and_says_no_spread():
    _source()
    with SessionLocal() as s:
        report = discover.sample_report(s, SID, client=_client(_offset_server(1200, total=False), s))
        s.commit()
    assert report["parts"] == {"read": 500, "spread": False}
    assert sorted(int(e[1:]) for e, _ in _landed()) == list(range(500))


def test_discover_page_cap_and_limit():
    _source()
    calls: list[httpx.Request] = []
    with SessionLocal() as s:
        report = discover.sample_report(s, SID, limit=120, client=_client(_offset_server(5000, calls), s))
        s.rollback()
    assert report["parts"]["read"] == 120 and len(calls) <= discover.PAGE_CAP


def test_discover_time_budget_stops_the_read():
    _source()
    with SessionLocal() as s:
        report = discover.sample_report(s, SID, time_budget_s=0, client=_client(_offset_server(1200), s))
        s.rollback()
    assert report["parts"]["read"] < 500


def test_discover_only_calls_connection_host():
    _source(paging={"type": "json_link", "next_url_path": "next"})
    hosts: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        hosts.append(req.url.host)
        if req.url.host == "fake.test":
            return httpx.Response(200, json={"items": [{"id": "a"}], "next": "http://elsewhere.test/api/parts?p=2"})
        return httpx.Response(200, json={"items": [{"id": "b"}]})

    with SessionLocal() as s:
        with pytest.raises(SourceError) as e:
            discover.sample_report(s, SID, client=_client(handler, s))
        s.rollback()
    assert "elsewhere.test" in str(e.value) and hosts == ["fake.test"]


def test_discover_refused_on_production():
    _source(environment="production")
    out = call("connection.discover", {"source_id": SID}, "developer")
    assert out["ok"] is False and out["error"]["code"] == "conflict"
    assert out["error"]["message"] == "Samples are read from the test connection only."
    assert _landed() == []


def test_discover_action_reads_a_sample(monkeypatch):
    _source()
    monkeypatch.setattr(discover, "open_client", lambda s, sid, adapter: _client(_offset_server(1200), s))
    out = call("connection.discover", {"source_id": SID}, "developer")
    assert out["ok"], out
    assert out["output"]["counts"] == {"parts": 500} and out["output"]["spread"] == {"parts": True}
    assert len(_landed()) == 500 and _facts() == 0
    # the stored sample is what Suggest mappings and Source Tables read
    with SessionLocal() as s:
        assert len(discover._samples(s, SID)["parts"]) == 500
        s.rollback()


def test_discover_action_needs_manage_integrations_and_a_known_source():
    _source()
    assert call("connection.discover", {"source_id": SID}, "planner.a")["error"]["code"] in (
        "forbidden",
        "out_of_scope",
        "permission_denied",
    )
    assert call("connection.discover", {"source_id": "nope"}, "developer")["error"]["code"] == "not_found"


def test_discover_action_reports_a_failing_system(monkeypatch):
    _source()

    def down(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    monkeypatch.setattr(discover, "open_client", lambda s, sid, adapter: _client(down, s))
    monkeypatch.setattr("di.connectors.http._sleep", lambda _s: None)
    out = call("connection.discover", {"source_id": SID}, "developer")
    assert out["ok"] is False and "503" in out["error"]["message"]
