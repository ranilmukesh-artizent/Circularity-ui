"""P9-8.15: a test run can start from pinned records (D section 8, input and output previews per node).

The pinned node takes those records as its input; only it and its descendants run, everything else is `skipped`. It is
a dry run: nothing is written, and pins live in the person's draft only."""

import copy

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.workflow.engine import run_graph
from tests import starting
from tests.helpers import call, client, h


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


@pytest.fixture
def wf():
    r = call("workflow.create", {"type": "ingest", "src": "erp"}, "developer")
    assert r["ok"], r
    d = client.get(f"/api/screens/workflows/{r['output']['id']}", headers=h("developer")).json()
    yield d["workflow"]
    call("workflow.delete", {"id": r["output"]["id"]}, "developer")


def _fingerprint() -> tuple:
    with engine.connect() as c:
        return tuple(
            c.execute(text(f"SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) FROM {t} t")).one()  # noqa: S608
            for t in ("canonical", "provenance", "raw_record", "sync_cursor", "failed_record", "action_journal")
        )


def _ids(g: dict) -> tuple[str, str]:
    conn = next(n["id"] for n in g["nodes"] if n["k"] == "conn")
    mp = next(n["id"] for n in g["nodes"] if n["k"] == "map")
    return conn, mp


def _first_records(w: dict, node: str, n: int = 2) -> list[dict]:
    r = call("workflow.testRun", {"id": w["id"], "sample": 5}, "developer")
    assert r["ok"], r
    recs = r["output"]["samples"][node]["before"][:n]
    assert len(recs) == n
    return recs


def test_testrun_pinned_runs_descendants_only(wf):
    conn, mp = _ids(wf["graph"])
    recs = _first_records(wf, mp)
    r = call("workflow.testRun", {"id": wf["id"], "pinned": {"node_id": mp, "records": recs}}, "developer")
    assert r["ok"], r
    o = r["output"]
    assert o["dry"] is True
    assert o["states"][conn] == "skipped"
    assert conn not in o["samples"]
    assert o["samples"][mp]["before"] == recs
    after_map = {e["b"] for e in wf["graph"]["edges"] if e["a"] == mp}
    down = [n["id"] for n in wf["graph"]["nodes"] if n["k"] == "fixed" and n["id"] in after_map]
    assert down, "the mapping is followed by its canonical step"
    for d in down:
        assert o["states"][d] == "success"
        assert {x["ext_id"] for x in o["samples"][d]["before"]} <= {x["ext_id"] for x in recs}


def test_testrun_pinned_writes_nothing(wf):
    _, mp = _ids(wf["graph"])
    recs = _first_records(wf, mp)
    before = _fingerprint()
    r = call("workflow.testRun", {"id": wf["id"], "pinned": {"node_id": mp, "records": recs}}, "developer")
    assert r["ok"], r
    assert _fingerprint() == before


def test_testrun_pinned_caps_records(wf):
    _, mp = _ids(wf["graph"])
    recs = [{"ext_id": f"X{i}", "resource": "x", "data": {"n": i}} for i in range(21)]
    r = call("workflow.testRun", {"id": wf["id"], "pinned": {"node_id": mp, "records": recs}}, "developer")
    assert not r["ok"] and r["error"]["code"] == "validation_error"
    assert r["error"]["message"] == "Pin at most 20 records."


def test_testrun_pinned_refuses_a_connector_or_unknown_node(wf):
    conn, _ = _ids(wf["graph"])
    rec = [{"ext_id": "X1", "resource": "x", "data": {}}]
    for node in (conn, "nope"):
        r = call("workflow.testRun", {"id": wf["id"], "pinned": {"node_id": node, "records": rec}}, "developer")
        assert not r["ok"] and r["error"]["code"] == "validation_error", r


def test_testrun_samples_are_masked(wf):
    _, mp = _ids(wf["graph"])
    rec = [{"ext_id": "X1", "resource": "x", "data": {"contact": "jane.doe@example.com", "qty": 3}}]
    r = call("workflow.testRun", {"id": wf["id"], "pinned": {"node_id": mp, "records": rec}}, "developer")
    assert r["ok"], r
    shown = r["output"]["samples"][mp]["before"][0]["data"]
    assert shown["contact"] == "«masked»" and shown["qty"] == 3


def test_a_draft_keeps_its_pins_and_the_engine_pins_only_dry(wf):
    _, mp = _ids(wf["graph"])
    pins = {mp: [{"ext_id": "X1", "resource": "x", "data": {"n": 1}}]}
    body = {"id": wf["id"], "graph": copy.deepcopy(wf["graph"]), "name": wf["name"], "pins": pins}
    assert call("workflow.draft.save", body, "developer")["ok"]
    d = client.get(f"/api/screens/workflows/{wf['id']}", headers=h("developer")).json()["draft"]
    assert d["pins"] == pins
    with SessionLocal() as s, pytest.raises(ValueError, match="dry"):
        run_graph(s, {}, {}, trigger="Manual", pinned=(mp, []))
