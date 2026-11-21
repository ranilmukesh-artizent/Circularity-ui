"""Plan 6 follow-up: the last gaps around sources made in the Connection Fabric, and the cursor of a triggered workflow.

1. A source connected from the catalogue (or made by hand) is named by its real name wherever a run or a screen names
   it: the engine's run notes, Run now (whose checks read the sources as they are now, so it is not refused as "deleted
   from the Source map"), the Monitor's step labels and the History tab's Compare. Before, every label outside the
   checks read the demo's SOURCES and said "Deleted source".
2. The workflow list's search by vendor and its attention list read the live sources: a catalogue source's workflow is
   found by its system's vendor, and an expired catalogue source is listed (the demo's own answers are unchanged:
   tests/test_screens_workflows.py).
5. A workflow that is not its source's bound sync workflow (an Event, File or Case-triggered one, or a Run now of an
   unbound one) reads the source with a cursor of its own (sync_cursor resource `wf:<workflow id>:<resource>`), so a
   sync that ran first does not leave it 0 new records; its second run reads only what is new. The bound workflow (and
   the default graph a sync runs) keep the source's own cursor.
"""

import copy

import pytest
from sqlalchemy import text

from di import state
from di.connectors import catalog
from di.db import SessionLocal, engine
from tests import starting
from tests.helpers import call, client, h

CAT = "postgres"
DEV = "developer"
DELTA = "rl"  # Optoro: delta resources (returns, receipts ...)
TABLES = ("sync_run", "fetch_log", "raw_record", "sync_cursor", "failed_record", "webhook_event")


def setup_module():
    starting.reset()


def teardown_module():
    with engine.begin() as c:
        c.execute(text("DELETE FROM job WHERE kind IN ('sync.source', 'workflow.run')"))
        for t in (*TABLES, "field_mapping", "source_connection", "source_secret"):
            c.execute(text(f"DELETE FROM {t} WHERE source_id = :i"), {"i": CAT})  # noqa: S608 - fixed names
        c.execute(text("DELETE FROM sync_cursor WHERE resource LIKE 'wf:%'"))
        c.execute(text("DELETE FROM failed_record WHERE run_id LIKE 'RUN-GAPS%'"))
    starting.reset()


def _connect() -> None:
    with engine.connect() as c:
        there = c.execute(text("SELECT 1 FROM source_system WHERE id = :i"), {"i": CAT}).first()
    if there is not None:
        return
    maps = call("mapping.catalogSuggest", {"catalog_id": CAT}, DEV)["output"]["rows"]
    body = {"mode": "catalog", "id": "", "d": {"catalog": CAT, "auth": "key", "scopes": ["read"]}, "maps": maps, "ops": {},
            "secret": catalog.template(CAT)["demo_secret"]}  # fmt: skip
    r = call("source.update", body, DEV)
    assert r["ok"], r


def _source() -> dict:
    srcs = client.get("/api/screens/integration/sources", headers=h(DEV)).json()["sources"]
    return next(x for x in srcs if x["id"] == CAT)


@pytest.fixture
def cat_wf(monkeypatch):
    """An ingest workflow for the catalogue source (a draft), removed afterwards."""
    import di.actions.workflows as wf

    for k in ("STEP_SECONDS", "QUICK_SECONDS", "BACKOFF_SECONDS"):
        monkeypatch.setattr(wf, k, 0)
    _connect()
    r = call("workflow.create", {"type": "ingest", "src": CAT}, DEV)
    assert r["ok"], r
    wid = r["output"]["id"]
    yield wid
    call("workflow.delete", {"id": wid}, DEV)


def _wf(wid: str) -> dict:
    with SessionLocal() as s:
        return state.get(s, "workflows", wid)


def _run_queued() -> None:
    import di.actions.workflows as wf

    with engine.begin() as c:
        rows = c.execute(text("SELECT id, payload FROM job WHERE kind = 'workflow.run' AND status = 'queued' ORDER BY id")).all()
    for job_id, payload in rows:
        wf.run_job(payload)
        with engine.begin() as c:
            c.execute(text("UPDATE job SET status = 'done' WHERE id = :i"), {"i": job_id})


# ---------------------------------------------------------------- 1. the real name in runs and screens
def test_a_run_names_a_catalogue_source_by_its_name(cat_wf):
    from di.actions.workflows import graph_for_run
    from di.workflow import engine as eng

    name = _source()["name"]
    w = _wf(cat_wf)
    g = copy.deepcopy(graph_for_run(w))
    conn = next(n for n in g["nodes"] if n["k"] == "conn")
    conn["fail"] = True  # the canvas' failure toggle: the step raises "<label> failed"
    with SessionLocal() as s:
        r = eng.run_graph(s, w, g, trigger="Manual", dry=True)
    assert r.status == "failed" and r.note.startswith(f"{name} failed"), r.note
    assert "Deleted source" not in r.note


def test_run_now_of_a_catalogue_workflow_runs_and_labels_its_steps(cat_wf):
    name = _source()["name"]
    r = call("workflow.run", {"id": cat_wf}, DEV)
    assert r["ok"], r
    key = r["output"]["run"]
    _run_queued()
    lr = _wf(cat_wf)["lastRun"]
    # checked against the sources as they are now: not refused as "deleted from the Source map"
    assert "Source map" not in (lr["note"] or ""), lr
    assert lr["states"]["r"] == "success", lr
    with SessionLocal() as s:
        stats = state.get(s, "workflow_run_stats", key)
    assert stats["labels"]["r"] == name, stats["labels"]


def test_compare_names_a_catalogue_source(cat_wf):
    name = _source()["name"]
    w = _wf(cat_wf)
    g = copy.deepcopy(w["graph"])
    conn = next(n for n in g["nodes"] if n["k"] == "conn")
    conn["cfg"] = {"lookback_days": 3}
    r = call("workflow.save", {"id": cat_wf, "name": w["name"], "owner": w["owner"], "trig": w["trig"], "graph": g}, DEV)
    assert r["ok"], r
    d = client.get(f"/api/screens/workflows/{cat_wf}/compare", params={"a": w["ver"]}, headers=h(DEV)).json()
    changed = {x["id"]: x["label"] for x in d["blocks"]["changed"]}
    assert changed.get("r") == name, d


# ---------------------------------------------------------------- 2. the list reads the live sources
def test_the_list_finds_a_catalogue_workflow_by_its_vendor(cat_wf):
    vendor = _source()["vendor"]
    w = _wf(cat_wf)
    r = call("workflow.save", {"id": cat_wf, "name": "Nightly feed", "owner": w["owner"], "trig": w["trig"], "graph": w["graph"]},
             DEV)  # fmt: skip
    assert r["ok"], r
    assert vendor.lower() not in f"Nightly feed {cat_wf} {w['owner']}".lower()
    found = client.get("/api/screens/workflows", params={"q": vendor}, headers=h(DEV)).json()["workflows"]
    assert cat_wf in [x["id"] for x in found], (vendor, [x["id"] for x in found])


def test_the_attention_list_names_an_expired_catalogue_source():
    _connect()
    vendor = _source()["vendor"]
    with engine.begin() as c:
        c.execute(text("UPDATE source_system SET status = 'auth_expired' WHERE id = :i"), {"i": CAT})
    try:
        att = client.get("/api/screens/workflows", headers=h(DEV)).json()["attention"]
        mine = [a for a in att if a.get("arg") == "source|" + CAT]
        assert len(mine) == 1 and mine[0]["t"] == vendor and mine[0]["s"].startswith("Authentication expired"), att
    finally:
        with engine.begin() as c:
            c.execute(text("UPDATE source_system SET status = 'live' WHERE id = :i"), {"i": CAT})


def test_the_overlay_tells_the_browser_a_catalogue_sources_target_and_delivery():
    """The browser's checks read MAP_TARGET and DELIVER, which know only the demo's sources: the list's `live` overlay
    gives a source made here the target its mapping feeds and how it accepts instructions (the server's map_target and
    deliver), and nothing more for the demo's sources."""
    _connect()
    lv = client.get("/api/screens/workflows", headers=h(DEV)).json()["live"]
    assert lv[CAT]["target"] in ("Asset & component", "Condition & eligibility", "Demand opportunity", "Outcome")
    assert lv[CAT]["deliver"] == []  # read only
    assert "target" not in lv["erp"] and "deliver" not in lv["erp"]


# ---------------------------------------------------------------- 5. a triggered workflow's own cursor
def _cursors(sid: str) -> dict[str, str]:
    with engine.connect() as c:
        return dict(c.execute(text("SELECT resource, cursor FROM sync_cursor WHERE source_id = :s"), {"s": sid}).tuples().all())


def _read(w: dict, run_id: str) -> int:
    from di.actions.workflows import graph_for_run
    from di.workflow import engine as eng

    g = copy.deepcopy(graph_for_run(w))
    with SessionLocal() as s:
        r = eng.run_graph(s, w, g, trigger="Event", run_id=run_id)
    assert r.status != "failed", r.note
    conn = next(n["id"] for n in g["nodes"] if n["k"] == "conn")
    return r.counts[conn]["out"]


def test_a_triggered_workflow_reads_with_its_own_cursor():
    from di.connectors import sync

    out = sync.run_sync(DELTA, "manual")
    assert out["status"] in ("ok", "partial"), out
    own = {k: v for k, v in _cursors(DELTA).items() if not k.startswith("wf:")}
    assert own, "the sync sets the source's cursors"
    r = call("workflow.create", {"type": "ingest", "src": DELTA}, DEV)
    assert r["ok"], r
    wid = r["output"]["id"]
    try:
        first = _read(_wf(wid), "RUN-GAPS1")
        assert first > 0, "the sync ran first, but the workflow reads the records once with a cursor of its own"
        cur = _cursors(DELTA)
        mine = {k: v for k, v in cur.items() if k.startswith(f"wf:{wid}:")}
        assert mine and {k.split(":", 2)[2] for k in mine} <= set(own), cur
        assert {k: v for k, v in cur.items() if not k.startswith("wf:")} == own  # the sync's cursors are untouched
        assert _read(_wf(wid), "RUN-GAPS2") == 0  # the second run: only what is new (nothing)

        # published here, it is the source's bound sync workflow: it reads with the source's own cursor
        assert call("workflow.publish", {"id": wid}, DEV)["ok"]
        with engine.begin() as c:
            c.execute(text("DELETE FROM sync_cursor WHERE resource LIKE :p"), {"p": f"wf:{wid}:%"})
        assert _read(_wf(wid), "RUN-GAPS3") == 0
        assert not any(k.startswith(f"wf:{wid}:") for k in _cursors(DELTA))
    finally:
        call("workflow.delete", {"id": wid}, DEV)


# ---------------------------------------------------------------- G3b: the Target operation's choices
def test_the_block_catalogue_lists_each_targets_operations():
    """A write connector's Target operation is checked against the writes its target takes (blocks.cfg_errors); the
    catalogue serves those choices per system, so the inspector offers them and the browser's checks agree."""
    from di.instructions.writers import SYSTEM_OF, operations

    ops = client.get("/api/screens/workflows/blocks", headers=h(DEV)).json()["operations"]
    assert ops == {sid: operations(sid) for sid in dict.fromkeys(SYSTEM_OF.values())}
    assert ops["repair"] == ["repair", "teardown"]
