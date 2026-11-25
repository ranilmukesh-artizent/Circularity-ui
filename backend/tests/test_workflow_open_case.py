"""MVP-8.2: the Open case workflow block (x_case): a published ingest workflow opens a case for each record passing
the block, through di.services.cases.intake, as the system with the workflow's publisher as `by`.

The source is Optoro (rl): its receipts carry the returned asset's key (`sku`) and the return reason. Only if
`return_reason=early return` picks some of them; each opens an industrial case for Customer A. A re-sync opens none
again (the intake's dedupe), and a dry run opens nothing and says how many it would. Needs source-sim; rl is read in
full, and the starting state is put back afterwards.
"""

import pytest
from sqlalchemy import text

from di.connectors import sync
from di.core import state
from di.core.db import SessionLocal, engine
from di.workflow import blocks
from di.workflow import engine as eng
from tests import starting
from tests.helpers import call, client, h

SID = "rl"
ONLY = ("return_reason", "early return")
CFG = {"template": "industrial", "reason": "rma", "asset_field": "sku", "org_unit_id": "Customer A",
       "only_if": f"{ONLY[0]}={ONLY[1]}"}  # fmt: skip


@pytest.fixture(scope="module", autouse=True)
def live_rl():
    starting.reset()
    with engine.begin() as c:
        c.execute(text("UPDATE source_system SET status = 'live' WHERE id = :s"), {"s": SID})
    yield
    starting.reset()


def _graph_with_case(wid: str, cfg: dict) -> dict:
    """The workflow's graph with an Open case step right after its connector (reading receipts only)."""
    with SessionLocal() as s:
        g = state.get(s, "workflows", wid)["graph"]
    conn = next(n for n in g["nodes"] if n["k"] == "conn")
    conn["cfg"] = {**(conn.get("cfg") or {}), "resources": ["receipts"]}
    g["nodes"].append({"id": "case", "k": "xf", "ref": "x_case", "x": conn["x"] + 120, "y": conn["y"] + 170, "cfg": cfg})
    for e in g["edges"]:
        if e["a"] == conn["id"]:
            e["a"] = "case"
    g["edges"].append({"id": f"{conn['id']}>case", "a": conn["id"], "b": "case", "locked": False})
    return g


@pytest.fixture
def workflow():
    r = call("workflow.create", {"type": "ingest", "src": SID}, "developer")
    assert r["ok"], r
    wid = r["output"]["id"]
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid)
    body = {"id": wid, "name": w["name"], "owner": w["owner"], "trig": w["trig"], "graph": _graph_with_case(wid, CFG)}
    assert call("workflow.save", body, "developer")["ok"]
    yield wid
    call("workflow.delete", {"id": wid}, "developer")
    starting.reset()


def _passing() -> set[str]:
    """The asset keys of the receipts Only if lets through (what the sync reads in full)."""
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT DISTINCT payload->>'sku' FROM raw_record WHERE source_id = :s AND resource = 'receipts' "
                 "AND payload->>:f = :v"),
            {"s": SID, "f": ONLY[0], "v": ONLY[1]},
        )  # fmt: skip
        return set(rows.scalars())


def _opened() -> list[dict]:
    with engine.connect() as c:
        return list(c.execute(text("SELECT data FROM case_record WHERE jsonb_exists(data, 'intake') ORDER BY id")).scalars())


def test_the_block_is_in_the_catalogue_and_the_palette():
    assert blocks.default_cfg("x_case") == {"template": "industrial", "reason": "rma", "asset_field": "",
                                            "org_unit_id": "", "only_if": "", "reason_field": "", "facts": []}  # fmt: skip
    body = client.get("/api/screens/workflows/blocks", headers=h("developer")).json()
    assert [p["id"] for p in body["palette"]] == ["x_case"] and body["palette"][0]["label"] == "Open case"
    assert set(blocks.CASE_REASONS) == {"rma", "lease_end", "trade_in", "contract_end", "iot_alarm", "manual", "swap",
                                        "service_order", "pool_excess"}  # fmt: skip


def test_published_ingest_with_open_case_opens_cases(workflow):
    assert call("workflow.publish", {"id": workflow}, "developer")["ok"]
    out = sync.run_sync(SID, "manual", True)
    assert out["status"] in ("ok", "partial"), out
    want = _passing()
    assert want, "the Optoro mock has early returns"
    opened = _opened()
    assert sorted(c["assetId"] for c in opened) == sorted(want)
    assert {(c["owner"], c["template"], c["intake"]["reason"]) for c in opened} == {("Customer A", "industrial", "rma")}
    with SessionLocal() as s:
        publisher = state.get(s, "workflows", workflow)["hist"][0]["by"]
    assert publisher and {c["intake"]["by"] for c in opened} == {publisher}
    with engine.connect() as c:
        actors = set(c.execute(text("SELECT actor FROM case_stage_log WHERE reason = 'Case opened from rma'")).scalars())
    assert actors == {"system"}


def test_resync_opens_no_duplicates(workflow):
    assert call("workflow.publish", {"id": workflow}, "developer")["ok"]
    sync.run_sync(SID, "manual", True)
    first = [c["id"] for c in _opened()]
    assert first
    out = sync.run_sync(SID, "manual", True)
    assert out["status"] in ("ok", "partial"), out
    assert [c["id"] for c in _opened()] == first


def test_dry_run_opens_nothing(workflow):
    with SessionLocal() as s:
        w = state.get(s, "workflows", workflow)
        r = eng.run_graph(s, w, w["graph"], trigger="Test", dry=True, full=True)
    assert r.status == "success", (r.error, r.note)
    assert r.note.startswith("Would open ") and r.note.endswith(" cases")
    assert int(r.note.split()[2]) > 0
    assert _opened() == []
