"""A bound ingest workflow narrows nothing (plan 6 follow-up): a source's sync runs its bound published ingest workflow
for the resources that workflow's connector reads, and the default graph (the adapter's standard mapping) for every
other resource of the source, in the same sync_run. So publishing the tutorial's SAP workflow (it reads only
purchase_order) does not stop the journal entries RT-1048 reconciles against from syncing.
"""

from sqlalchemy import text

from di.connectors import sync
from di.core.db import SessionLocal, engine
from di.workflow import binding
from di.workflow import engine as eng
from tests import starting
from tests.helpers import call

SID = "erp"
RESOURCES = ("product", "stock", "purchase_order", "journal_entry_item")
SERVICES = ("API_PRODUCT_SRV", "API_MATERIAL_STOCK_SRV", "API_PURCHASEORDER_PROCESS_SRV", "API_JOURNALENTRYITEMBASIC_SRV")


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


def _newest(table: str) -> dict[str, object]:
    with engine.connect() as c:
        return dict(c.execute(text(f"SELECT resource, max(fetched_at) FROM {table} WHERE source_id = :s GROUP BY 1"),  # noqa: S608
                              {"s": SID}).all())  # fmt: skip


def test_rest_of_a_graph():
    g = eng.default_graph(SID)
    assert binding.unread(g, SID, list(RESOURCES)) == []  # no resource ticked: every resource
    conn = next(n for n in g["nodes"] if n["k"] == "conn")
    conn["cfg"] = {"resources": ["purchase_order"]}
    assert binding.unread(g, SID, list(RESOURCES)) == ["product", "stock", "journal_entry_item"]
    rest = binding.rest_graph(SID, ["stock"])
    assert next(n for n in rest["nodes"] if n["k"] == "conn")["cfg"]["resources"] == ["stock"]


def test_a_workflow_reading_one_resource_leaves_the_others_syncing():
    r = call("workflow.create", {"type": "ingest", "src": SID}, "developer")
    assert r["ok"], r
    wid = r["output"]["id"]
    try:
        with SessionLocal() as s:
            from di.core import state

            w = state.get(s, "workflows", wid)
        g = w["graph"]
        for n in g["nodes"]:
            if n["k"] == "conn":
                n["cfg"] = {**(n.get("cfg") or {}), "resources": ["purchase_order"]}
        body = {"id": wid, "name": w["name"], "owner": w["owner"], "trig": w["trig"], "graph": g}
        assert call("workflow.save", body, "developer")["ok"]
        assert call("workflow.publish", {"id": wid}, "developer")["ok"]
        with SessionLocal() as s:
            assert binding.bound(s, SID)[0]["id"] == wid

        raw0, prov0 = _newest("raw_record"), _newest("provenance")
        out = sync.run_sync(SID, "manual", True)
        assert out["status"] in ("ok", "partial"), out
        raw1, prov1 = _newest("raw_record"), _newest("provenance")
        with engine.connect() as c:  # every resource's service was asked, in this one run
            urls = list(c.execute(text("SELECT url FROM fetch_log WHERE run_id = :r"), {"r": out["run_id"]}).scalars())
        for svc in SERVICES:
            assert any(svc in u for u in urls), svc
        # the resources with records (the simulator's journal has none until a decision posts one) were read again,
        # and their canonical facts written again
        fresh = {res for res in RESOURCES if res in raw0 and raw1[res] > raw0[res]}
        assert {"product", "stock", "purchase_order"} <= fresh, fresh
        for res in fresh & set(prov0):
            assert prov1[res] > prov0[res], res
        with engine.connect() as c:
            runs = c.execute(text("SELECT count(*) FROM sync_run WHERE source_id = :s AND id >= :i"),
                             {"s": SID, "i": out["run_id"]}).scalar_one()  # fmt: skip
            fresh = c.execute(text("SELECT count(*) FROM raw_record WHERE source_id = :s AND fetched_at > :t"),
                              {"s": SID, "t": max(raw0.values())}).scalar_one()  # fmt: skip
        assert runs == 1  # one sync_run for both parts, counting the records of both
        assert out["records_read"] == fresh > 0
    finally:
        call("workflow.delete", {"id": wid}, "developer")
        starting.reset()
