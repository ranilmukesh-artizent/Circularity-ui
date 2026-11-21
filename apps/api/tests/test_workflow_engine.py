"""The workflow engine (plan 6, tasks C5 and C7): a workflow run processes real records.

Most tests feed the engine from a small in-memory adapter (`Feed` with a fake adapter), so the records, and what each
step must do with them, are known; the parity test and the dry-run test read the demo's sources from source-sim.
"""

import copy

import pytest
from sqlalchemy import text

from di.canonical.store import Fact
from di.connectors.base import Record, Resource
from di.db import SessionLocal, engine
from di.workflow import engine as eng
from tests import starting

ROWS = [
    {"id": "A1", "qty": 5, "sku": "MTR"},
    {"id": "A2", "qty": 0, "sku": "MTR"},
    {"id": "A3", "qty": 2, "sku": "PMP"},
    {"id": "A4", "qty": -1, "sku": "PMP"},
]


def _forget_held() -> None:
    with engine.begin() as c:
        c.execute(text("DELETE FROM failed_record WHERE run_id LIKE 'RUN-ENG%'"))


def setup_module():
    starting.reset()
    _forget_held()


def teardown_module():
    starting.reset()
    _forget_held()


class FakeAdapter:
    source_id = "fake"

    def __init__(self, rows=ROWS, boom=0):
        self.rows, self.boom, self.calls = rows, boom, 0

    def resources(self):
        def read(_client, _since):
            self.calls += 1
            if self.calls <= self.boom:
                raise RuntimeError(f"read failed (call {self.calls})")
            for r in self.rows:
                yield Record("items", r["id"], dict(r), None, "2026-10-07T09:00:00+00:00")

        return [Resource("items", read, delta=False)]

    def map(self, rec):
        return [Fact("asset", "ENG-" + rec.ext_id, "qty", rec.payload["qty"])]


def feed(adapter=None) -> dict:
    return {"fake": eng.Feed("fake", adapter or FakeAdapter())}


def N(nid, k, ref, cfg=None, **kw):
    n = {"id": nid, "k": k, "ref": ref, "x": 0, "y": 0} | kw
    if cfg is not None:
        n["cfg"] = cfg
    return n


def E(a, b):
    return {"a": a, "b": b, "locked": False}


def val_graph(rules, err=True) -> dict:
    nodes = [N("r", "conn", "fake"), N("v", "xf", "x_val", {"rules": rules}), N("aud", "xf", "x_audit")]
    edges = [E("r", "v"), E("v", "aud")]
    if err:
        nodes.append(N("err", "xf", "x_err"))
        edges.append(E("v", "err"))
    return {"nodes": nodes, "edges": edges}


def held_for(run_id: str) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(text("SELECT * FROM failed_record WHERE run_id = :r ORDER BY id"), {"r": run_id}).mappings()
        return [dict(r) for r in rows]


WF = {"id": "WF-T", "name": "Engine test", "src": "fake"}


def test_x_val_holds_the_bad_rows_with_their_real_values():
    with SessionLocal() as s:
        r = eng.run_graph(s, WF, val_graph([{"field": "qty", "check": "range", "arg": ">0"}]), trigger="Manual",
                          feeds=feed(), run_id="RUN-ENG1")  # fmt: skip
    assert r.states == {"r": "success", "v": "success", "aud": "success", "err": "success"}
    # the counts are the records that really passed each step
    assert r.counts["r"] == {"in": 4, "out": 4, "rej": 0}
    assert r.counts["v"] == {"in": 4, "out": 2, "rej": 2}
    assert r.counts["aud"] == {"in": 2, "out": 2, "rej": 0}
    assert r.counts["err"]["in"] == 2
    assert r.rows == 4 and r.held == 2 and r.status == "warning"
    held = held_for("RUN-ENG1")
    assert [(h["ext_id"], h["field"], h["value"], h["rule"], h["step"]) for h in held] == [
        ("A2", "qty", 0, "range", "err"),
        ("A4", "qty", -1, "range", "err"),
    ]
    assert held[0]["payload"] == ROWS[1] and held[0]["run_kind"] == "workflow"


def test_rejects_without_an_error_handler_are_held_by_the_engine():
    with SessionLocal() as s:
        r = eng.run_graph(s, WF, val_graph([{"field": "qty", "check": "range", "arg": ">0"}], err=False),
                          trigger="Manual", feeds=feed(), run_id="RUN-ENG2")  # fmt: skip
    assert r.held == 2
    assert [h["step"] for h in held_for("RUN-ENG2")] == ["v", "v"]


def test_a_dry_run_writes_nothing_and_returns_samples():
    with SessionLocal() as s:
        r = eng.run_graph(s, WF, val_graph([{"field": "qty", "check": "range", "arg": ">0"}]), trigger="Test", dry=True,
                          feeds=feed(), run_id="RUN-ENG3")  # fmt: skip
    assert held_for("RUN-ENG3") == []
    assert r.held == 2 and r.counts["v"] == {"in": 4, "out": 2, "rej": 2}
    assert [x["ext_id"] for x in r.samples["v"]["before"]] == ["A1", "A2", "A3"]
    assert [x["ext_id"] for x in r.samples["v"]["after"]] == ["A1", "A3"]


def _fingerprint() -> tuple:
    with engine.connect() as c:
        return tuple(
            c.execute(text(f"SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) FROM {t} t")).one()  # noqa: S608
            for t in ("canonical", "provenance", "raw_record", "sync_cursor", "failed_record")
        )


def test_a_dry_run_of_a_demo_source_leaves_the_store_as_it_was():
    before = _fingerprint()
    with SessionLocal() as s:
        r = eng.run_graph(s, WF | {"src": "erp"}, eng.default_graph("erp"), trigger="Test", dry=True, full=True, sample=25)
    assert _fingerprint() == before
    assert r.status in ("success", "warning"), r.error
    assert 0 < r.rows <= 25
    canon = next(n["id"] for n in eng.default_graph("erp")["nodes"] if n["k"] == "fixed" and n["ref"] != "snap")
    assert r.counts["m"]["out"] == r.rows - r.counts["m"]["rej"]
    assert r.samples["m"]["after"] and "facts" in r.samples["m"]["after"][0]
    assert r.counts[canon]["in"] == r.counts["m"]["out"]


def test_a_failing_step_is_retried_with_backoff_and_shows_its_attempts():
    slept: list[float] = []
    g = val_graph([])
    with SessionLocal() as s:
        r = eng.run_graph(s, WF, g, trigger="Manual", feeds=feed(FakeAdapter(boom=2)), retries=3, sleep=slept.append)
    assert slept == [1.0, 2.0] and r.attempts["r"] == 3 and r.states["r"] == "success"
    slept.clear()
    with SessionLocal() as s:
        r = eng.run_graph(s, WF, g, trigger="Manual", feeds=feed(FakeAdapter(boom=9)), retries=3, sleep=slept.append)
    assert slept == [1.0, 2.0, 4.0] and r.attempts["r"] == 4
    assert r.states == {"r": "failed", "v": "upstream_failed", "aud": "upstream_failed", "err": "upstream_failed"}
    assert r.status == "failed" and "read failed (call 4)" in r.error


def test_the_failure_toggle_fails_the_step_after_its_retries():
    g = val_graph([])
    g["nodes"][1]["fail"] = True
    slept: list[float] = []
    with SessionLocal() as s:
        r = eng.run_graph(s, WF, g, trigger="Manual", feeds=feed(), retries=1, sleep=slept.append)
    assert r.states["v"] == "failed" and r.attempts["v"] == 2 and slept == [1.0]
    assert r.note.startswith("Validation & enrichment failed")


def test_a_branch_sends_the_else_path_to_its_second_step():
    g = {
        "nodes": [N("r", "conn", "fake"), N("b", "xf", "x_branch", {"condition": [{"field": "sku", "op": "==", "value": "MTR"}]}),
                  N("yes", "xf", "x_audit"), N("no", "xf", "x_audit")],
        "edges": [E("r", "b"), E("b", "yes"), E("b", "no")],
    }  # fmt: skip
    with SessionLocal() as s:
        r = eng.run_graph(s, WF, g, trigger="Test", dry=True, feeds=feed())
    assert r.counts["yes"]["in"] == 2 and r.counts["no"]["in"] == 2
    assert [x["ext_id"] for x in r.samples["no"]["before"]] == ["A3", "A4"]


def test_progress_reports_every_state_change_in_order():
    seen: list[dict] = []
    with SessionLocal() as s:
        r = eng.run_graph(s, WF, val_graph([]), trigger="Test", dry=True, feeds=feed(), on_step=seen.append)
    assert [(e["step"], e["state"]) for e in seen] == [
        ("r", "running"), ("r", "success"), ("v", "running"), ("v", "success"),
        ("aud", "running"), ("aud", "success"), ("err", "running"), ("err", "success"),
    ]  # fmt: skip
    assert seen[1]["counts"] == {"r": {"in": 4, "out": 4, "rej": 0}} and r.steps == len(seen)


def test_an_unreadable_source_fails_without_retries():
    g = copy.deepcopy(val_graph([]))
    g["nodes"][0]["ref"] = "nosuch"
    slept: list[float] = []
    with SessionLocal() as s:
        r = eng.run_graph(s, WF, g, trigger="Manual", retries=3, sleep=slept.append)
    assert r.states["r"] == "failed" and r.attempts["r"] == 1 and slept == []
    assert "has no connected feed" in r.note


# ---------------------------------------------------------------- Review Focus 4: one run at a time (C7)
def _run_queued() -> None:
    import di.actions.workflows as wf

    with engine.begin() as c:
        rows = c.execute(text("SELECT id, payload FROM job WHERE kind = 'workflow.run' AND status = 'queued' ORDER BY id")).all()
    for job_id, payload in rows:
        wf.run_job(payload)
        with engine.begin() as c:
            c.execute(text("UPDATE job SET status = 'done' WHERE id = :i"), {"i": job_id})


@pytest.fixture
def studio(monkeypatch):
    import di.actions.workflows as wf
    from di import state

    for k in ("STEP_SECONDS", "QUICK_SECONDS", "BACKOFF_SECONDS"):
        monkeypatch.setattr(wf, k, 0)
    with engine.begin() as c:
        c.execute(text("DELETE FROM job WHERE kind = 'workflow.run'"))
    state.reset(["workflows", "workflow_runs", "notes"])
    yield wf
    with engine.begin() as c:
        c.execute(text("DELETE FROM job WHERE kind = 'workflow.run'"))
    state.reset(["workflows", "workflow_runs", "notes"])


def _wf(wid: str) -> dict:
    from di import state

    with SessionLocal() as s:
        return state.get(s, "workflows", wid)


def _runs(wid: str) -> dict[str, dict]:
    with engine.connect() as c:
        return dict(c.execute(text("SELECT id, data FROM state_item WHERE collection = 'workflow_runs' AND data->>'wf' = :w"),
                              {"w": wid}).all())  # fmt: skip


DEC = "WF-133"  # a decision workflow: no source to read, so its runs are quick


def test_one_run_at_a_time(studio, monkeypatch):
    """Review Focus 4: Run now while a run is queued is refused; a second job of the same workflow (a schedule tick
    during Run now) finds the run lock taken and is dropped, so the run happens once; a run that crashes, and one whose
    worker died, never leave the workflow running."""
    from di import state
    from tests.helpers import call

    wf = studio
    r1 = call("workflow.run", {"id": DEC}, "developer")
    assert r1["ok"], r1
    r2 = call("workflow.run", {"id": DEC}, "developer")
    assert r2["error"]["code"] == "duplicate" and "already running" in r2["error"]["message"]
    key1 = r1["output"]["run"]

    with SessionLocal() as s:  # the tick: a second run record and job
        w = state.get(s, "workflows", DEC, for_update=True)
        key2 = wf.start_run(s, w, "Schedule", wf._now() + 1)
        s.commit()
    with engine.connect() as lk:  # the first run is going: its job holds the run lock
        lk.execute(text("SELECT pg_advisory_xact_lock(:c, hashtext(:k))"), {"c": wf.RUN_LOCK, "k": f"wf:{DEC}"})
        assert wf.run_job({"run": key2, "wf": DEC, "trig": "Schedule"}) == {"run": key2, "skipped": "already_running"}
        with SessionLocal() as s:
            assert wf.run_active(s, DEC)
        lk.rollback()
    assert key2 not in _runs(DEC)
    _run_queued()
    w = _wf(DEC)
    assert w["running"] is False and w["lastRun"]["key"] == key1 and _runs(DEC)[key1]["state"] != "running"
    assert w["runsN"] == 1 + (next(x for x in _starting() if x["id"] == DEC).get("runsN") or 0)

    # a run that crashes is closed as failed, and the workflow can run again
    from di.workflow import engine as engine_mod

    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(engine_mod, "run_graph", boom)
    r = call("workflow.run", {"id": DEC}, "developer")
    out = wf.run_job(_job(r["output"]["run"]))
    assert out["state"] == "failed" and "disk full" in out["error"]
    w = _wf(DEC)
    assert w["running"] is False and w["last"]["state"] == "failed"
    assert _runs(DEC)[r["output"]["run"]]["state"] == "failed"
    monkeypatch.undo()
    for k in ("STEP_SECONDS", "QUICK_SECONDS", "BACKOFF_SECONDS"):
        monkeypatch.setattr(wf, k, 0)

    # a worker that died: `running` set, nothing queued, no lock. Run now closes that run and starts a new one.
    with SessionLocal() as s:
        w = state.get(s, "workflows", DEC, for_update=True)
        lost = wf.start_run(s, w, "Manual", wf._now() + 2, enqueue=False)
        s.commit()
    assert _wf(DEC)["running"] is True
    r = call("workflow.run", {"id": DEC}, "developer")
    assert r["ok"], r
    assert _runs(DEC)[lost]["state"] == "failed" and _runs(DEC)[lost]["note"] == "Failed: worker lost"
    _run_queued()
    assert _wf(DEC)["running"] is False


def _job(key: str) -> dict:
    with engine.begin() as c:
        jid, payload = c.execute(text("SELECT id, payload FROM job WHERE kind = 'workflow.run' AND payload->>'run' = :r"),
                                 {"r": key}).one()  # fmt: skip
        c.execute(text("UPDATE job SET status = 'done' WHERE id = :i"), {"i": jid})
    return payload


def _starting() -> list[dict]:
    from di import golden

    return golden.load("screens/workflows")["starting"]


def test_retries_attempts_and_alerts_on_a_real_run(studio):
    """C7: a step that keeps failing is tried Retries + 1 times; the run records the tries per step (the Try column)
    and the alert rule fires on the real failure."""
    from tests.helpers import call

    wf = studio
    w = _wf(DEC)
    g = w["graph"]
    step = next(n["id"] for n in g["nodes"] if n["k"] == "fixed" and n["ref"] == "gates")
    for n in g["nodes"]:
        if n["id"] == step:
            n["fail"] = True
    body = {"id": DEC, "name": w["name"], "owner": w["owner"], "trig": w["trig"], "graph": g, "retries": 3}
    assert call("workflow.save", body, "developer")["ok"]
    assert call("workflow.publish", {"id": DEC}, "developer")["ok"]  # the published version is the one that runs
    r = call("workflow.run", {"id": DEC}, "developer")
    assert r["ok"], r
    _run_queued()
    w = _wf(DEC)
    lr = w["lastRun"]
    assert lr["status"] == "failed" and lr["states"][step] == "failed"
    assert lr["attempts"][step] == 4 and lr["retries"] == 3
    assert all(lr["states"][d] == "upstream_failed" for d in lr["order"][lr["order"].index(step) + 1:]
               if d in {e["b"] for e in g["edges"] if e["a"] == step})  # fmt: skip
    with engine.connect() as c:
        notes = list(c.execute(text("SELECT data FROM state_item WHERE collection = 'notes' AND data->>'exId' = :x"),
                               {"x": f"wf:{DEC}"}).scalars())  # fmt: skip
    assert len(notes) == 1 and f"run {lr['id']} failed." in notes[0]["msg"]
    assert wf.BACKOFF_SECONDS == 0


# ---------------------------------------------------------------- Review Focus 1: the sync through the engine
_KEPT = ("canonical", "provenance", "conflict", "sync_cursor")
_SRC_COLS = "status, last_sync_at, last_success_at, completeness, fail_streak, next_retry_at, updated_at"


def _legacy_sync(sid: str) -> None:
    """Today's run_sync (before plan 6 C5), its data path only: read every resource in full through the adapter, map
    with the saved field mapping over it, hold facts that do not fit their model, apply the rest per record."""
    from di.canonical import store
    from di.canonical.schema import split_facts
    from di.connectors import connection, mapping
    from di.connectors.registry import ADAPTERS, adapter_for

    with SessionLocal() as s:
        adapter = adapter_for(s, sid)
        conf = s.execute(text("SELECT confidence FROM source_system WHERE id = :i"), {"i": sid}).scalar()
        conf = float(conf) if conf is not None else None
        client = connection.client_for(s, sid, adapter, None)
        remap = mapping.mapper(s, sid, sid in ADAPTERS)
        try:
            for res in adapter.resources():
                for rec in res.read(client, None):
                    with s.begin_nested():
                        facts = [
                            f if f.resource else type(f)(**{**f.__dict__, "resource": rec.resource, "ext_id": rec.ext_id})
                            for f in (remap(rec, adapter.map(rec)) if remap else adapter.map(rec))
                        ]
                        facts, _bad = split_facts(facts)
                        store.apply(s, sid, facts, conf)
                s.commit()
        finally:
            client.close()


def _snapshot() -> tuple[list, list, int]:
    with engine.connect() as c:
        canon = [tuple(r) for r in c.execute(text("SELECT model, key, data FROM canonical ORDER BY model, key"))]
        prov = [
            tuple(r)
            for r in c.execute(
                text(
                    "SELECT model, key, field, source_id, value, source_field, source_value, transform, resource, ext_id, "
                    "confidence FROM provenance ORDER BY model, key, field, source_id"
                )
            )
        ]
        conflicts = c.execute(text("SELECT count(*) FROM conflict")).scalar_one()
    return canon, prov, conflicts


def _clear_store() -> None:
    with engine.begin() as c:
        for t in ("conflict", "provenance", "canonical"):
            c.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names


def test_engine_parity_canonical():
    """Review Focus 1: after a full sync of every demo source through the engine (run_sync, the default ingest graph),
    the canonical and provenance tables equal those of today's run_sync, from an empty store each time. The store is
    put back as it was afterwards."""
    from di.connectors import sync
    from di.connectors.registry import ADAPTERS

    with engine.begin() as c:
        for t in (*_KEPT, "src"):
            c.execute(text(f"DROP TABLE IF EXISTS parity_bk_{t}"))
        for t in _KEPT:
            c.execute(text(f"CREATE TABLE parity_bk_{t} AS SELECT * FROM {t}"))  # noqa: S608
        c.execute(text(f"CREATE TABLE parity_bk_src AS SELECT id, {_SRC_COLS} FROM source_system"))  # noqa: S608
        sids = [r for r in c.execute(text("SELECT id FROM source_system WHERE status NOT IN ('paused', 'disconnected', "
                                          "'unavailable') ORDER BY id")).scalars() if r in ADAPTERS]  # fmt: skip
    try:
        assert len(sids) >= 20, sids
        _clear_store()
        for sid in sids:
            _legacy_sync(sid)
        want = _snapshot()
        _clear_store()
        for sid in sids:
            out = sync.run_sync(sid, "manual", True)
            assert out["status"] in ("ok", "partial"), out
        got = _snapshot()
        assert len(got[0]) == len(want[0]) and len(got[1]) == len(want[1]), (len(got[0]), len(want[0]), len(got[1]), len(want[1]))
        assert got[0] == want[0], "canonical differs"
        assert got[1] == want[1], "provenance differs"
        assert got[2] == want[2], "conflicts differ"
        assert want[0] and want[1]
    finally:
        with engine.begin() as c:
            for t in ("conflict", "provenance", "canonical", "sync_cursor"):
                c.execute(text(f"DELETE FROM {t}"))  # noqa: S608
            for t in ("canonical", "provenance", "conflict", "sync_cursor"):
                c.execute(text(f"INSERT INTO {t} OVERRIDING SYSTEM VALUE SELECT * FROM parity_bk_{t}"))  # noqa: S608
                c.execute(text(f"DROP TABLE parity_bk_{t}"))
            sets = ", ".join(f"{k.strip()} = b.{k.strip()}" for k in _SRC_COLS.split(","))
            c.execute(text(f"UPDATE source_system s SET {sets} FROM parity_bk_src b WHERE b.id = s.id"))  # noqa: S608
            c.execute(text("DROP TABLE parity_bk_src"))


def test_a_published_ingest_workflow_is_what_its_source_syncs_with():
    """The binding (source_config.workflow): set when an ingest workflow is published here, cleared when it is
    unpublished; the seeded published workflow of the same source (WF-101, never published here) is not bound, so the
    source syncs with the default graph again."""
    from di import state
    from di.actions import workflows as wf
    from di.workflow import binding
    from tests.helpers import call

    r = call("workflow.create", {"type": "ingest", "src": "crm"}, "developer")
    wid = r["output"]["id"]
    try:
        assert call("workflow.publish", {"id": wid}, "developer")["ok"]
        with SessionLocal() as s:
            assert (state.get(s, "source_config", "crm") or {}).get("workflow") == wid
            w, g = binding.bound(s, "crm")
            assert w["id"] == wid and g == wf.graph_for_run(w)
        assert call("workflow.setStatus", {"id": wid, "status": "draft"}, "developer")["ok"]
        with SessionLocal() as s:
            assert "workflow" not in (state.get(s, "source_config", "crm") or {})
            w, g = binding.bound(s, "crm")
            assert w["id"] is None and g == eng.default_graph("crm")
    finally:
        call("workflow.delete", {"id": wid}, "developer")
        starting.reset()


@pytest.mark.parametrize("sid", ["erp", "crm"])
def test_the_default_graph_is_the_minimal_ingest_graph(sid):
    g = eng.default_graph(sid)
    kinds = [n["k"] for n in g["nodes"]]
    assert kinds[0] == "conn" and "map" in kinds and any(n["k"] == "fixed" for n in g["nodes"])
    assert eng.default_graph("made-by-hand")["nodes"][0] == {"id": "r", "k": "conn", "ref": "made-by-hand", "x": 24, "y": 170}


# ---------------------------------------------------------------- plan 6 follow-up: Wait, Call workflow, audit log
def _jobs(kind: str) -> list[tuple[int, dict, float]]:
    with engine.connect() as c:
        q = text("SELECT id, payload, EXTRACT(EPOCH FROM run_after - now()) FROM job WHERE kind = :k AND status = 'queued' "
                 "ORDER BY id")  # fmt: skip
        return [(r[0], r[1], float(r[2])) for r in c.execute(q, {"k": kind}).all()]


def _waits() -> list[dict]:
    from di import state
    from di.workflow import waits

    with SessionLocal() as s:
        return state.items(s, waits.COLLECTION)


def _as_wait_workflow(graph: dict) -> dict:
    """WF-133 (a published decision workflow, no source) with `graph` as the graph that runs."""
    from di import state

    with SessionLocal() as s:
        w = state.get(s, "workflows", DEC)
        w["graph"] = graph
        w.pop("pub", None)
        state.put(s, "workflows", DEC, w)
        s.commit()
    return w


@pytest.fixture
def waiting(studio, monkeypatch):
    from di.workflow import waits  # noqa: F401 - registers the collection, so the resets clear it

    monkeypatch.setattr(studio, "errors", lambda g, kind, s=None: [])  # the test graphs are not complete workflows
    with engine.begin() as c:
        c.execute(text("DELETE FROM job WHERE kind = 'workflow.resume'"))
        c.execute(text("DELETE FROM state_item WHERE collection = 'workflow_waits'"))
        c.execute(text("DELETE FROM failed_record WHERE source_id = 'fake'"))  # run keys repeat on the pinned clock
    yield studio
    with engine.begin() as c:
        c.execute(text("DELETE FROM job WHERE kind = 'workflow.resume'"))
        c.execute(text("DELETE FROM state_item WHERE collection = 'workflow_waits'"))
        c.execute(text("DELETE FROM failed_record WHERE source_id = 'fake'"))
        c.execute(text("DELETE FROM raw_record WHERE source_id = 'fake'"))


def wait_graph(cfg: dict) -> dict:
    nodes = [N("r", "conn", "fake"), N("wt", "xf", "x_wait", cfg), N("v", "xf", "x_val", {"rules": [
        {"field": "qty", "check": "range", "arg": ">0"}]}), N("aud", "xf", "x_audit")]  # fmt: skip
    return {"nodes": nodes, "edges": [E("r", "wt"), E("wt", "v"), E("v", "aud")]}


def test_a_wait_duration_parks_the_records_and_the_run_comes_back_for_them(waiting):
    from di.workflow import waits

    w = _as_wait_workflow(wait_graph({"duration_min": 30}))
    with SessionLocal() as s:
        r = eng.run_graph(s, w, wait_graph({"duration_min": 30}), trigger="Manual", feeds=feed(), run_id="RUN-ENGW1")
    assert r.states == {"r": "success", "wt": "waiting", "v": "waiting", "aud": "waiting"}
    assert r.counts["wt"] == {"in": 4, "out": 0, "rej": 0} and r.note == "4 records waiting at Wait"
    [item] = _waits()
    assert item["wf"] == DEC and item["node"] == "wt" and item["run"] == "RUN-ENGW1"
    assert [x["ext_id"] for x in item["records"]] == ["A1", "A2", "A3", "A4"]
    [(_jid, payload, due_in)] = _jobs("workflow.resume")
    assert payload == {"wait": item["id"], "wf": DEC} and 1700 < due_in <= 1800  # due 30 min later (wall clock)
    # a test run parks nothing
    with SessionLocal() as s:
        eng.run_graph(s, w, wait_graph({"duration_min": 30}), trigger="Test", dry=True, feeds=feed())
    assert len(_waits()) == 1

    out = waits.resume(payload)
    assert out["state"] == "warning" and _waits() == []
    lr = _wf(DEC)["lastRun"]
    assert lr["trig"] == "Resume" and lr["states"] == {"r": "skipped", "wt": "success", "v": "success", "aud": "success"}
    assert lr["counts"]["wt"] == {"in": 4, "out": 4, "rej": 0} and lr["counts"]["v"] == {"in": 4, "out": 2, "rej": 2}
    assert _runs(DEC)[out["run"]]["trig"] == "Resume"
    assert [h["ext_id"] for h in held_for(out["run"])] == ["A2", "A4"]
    assert waits.resume(payload) == {"wait": item["id"], "skipped": "gone"}


def test_a_wait_until_checks_the_newest_landed_records_again(waiting):
    from di.workflow import waits

    cfg = {"until": "qty > 0", "duration_min": 10}
    w = _as_wait_workflow(wait_graph(cfg))
    with SessionLocal() as s:
        r = eng.run_graph(s, w, wait_graph(cfg), trigger="Manual", feeds=feed(), run_id="RUN-ENGW2")
    assert r.counts["wt"] == {"in": 4, "out": 2, "rej": 0} and r.states["v"] == "success"
    [item] = _waits()
    assert [x["ext_id"] for x in item["records"]] == ["A2", "A4"]
    with engine.begin() as c:  # A2 is corrected at the source and lands again
        c.execute(text("UPDATE raw_record SET payload = jsonb_set(payload, '{qty}', '3') "
                       "WHERE source_id = 'fake' AND ext_id = 'A2'"))  # fmt: skip
    out = waits.resume(_jobs("workflow.resume")[0][1])
    lr = _wf(DEC)["lastRun"]
    assert lr["counts"]["wt"] == {"in": 2, "out": 1, "rej": 0} and lr["counts"]["v"] == {"in": 1, "out": 1, "rej": 0}
    assert out["state"] == "success" and lr["note"] == "1 record waiting at Wait"
    [again] = _waits()  # A4 still does not meet Until: parked again, from when it first waited
    assert again["id"] != item["id"] and [x["ext_id"] for x in again["records"]] == ["A4"]
    assert again["records"][0]["meta"]["wait_since"] == item["records"][1]["meta"]["wait_since"]


def test_a_wait_step_no_longer_in_the_workflow_holds_its_records(waiting):
    from di.workflow import waits

    w = _as_wait_workflow(wait_graph({"duration_min": 5}))
    with SessionLocal() as s:
        eng.run_graph(s, w, wait_graph({"duration_min": 5}), trigger="Manual", feeds=feed(), run_id="RUN-ENGW3")
    _as_wait_workflow(val_graph([{"field": "qty", "check": "present"}]))
    assert waits.resume(_jobs("workflow.resume")[0][1])["held"] == 4
    assert [(h["rule"], h["step"]) for h in held_for("RUN-ENGW3")] == [("wait", "wt")] * 4 and _waits() == []


def call_graph(target: str) -> dict:
    return {"nodes": [N("r", "conn", "fake"), N("c", "xf", "x_call", {"workflow": target})], "edges": [E("r", "c")]}


def test_call_workflow_starts_the_other_workflow(studio, monkeypatch):
    from di import state

    monkeypatch.setenv("DI_WORKFLOW_TRIGGERS", "true")
    from tests.helpers import publish_seeded_here

    publish_seeded_here()  # a called workflow starts only when it is published in the app
    me = {"id": "WF-134", "name": "Caller"}
    with SessionLocal() as s:
        r = eng.run_graph(s, me, call_graph(DEC), trigger="Test", dry=True, feeds=feed())
    assert r.states["c"] == "success" and _jobs("workflow.run") == []  # a test run starts nothing
    with SessionLocal() as s:
        r = eng.run_graph(s, me, call_graph(DEC), trigger="Manual", feeds=feed(), run_id="RUN-ENGC1")
    assert r.states["c"] == "success" and r.counts["c"] == {"in": 4, "out": 4, "rej": 0}
    assert [p for _i, p, _a in _jobs("workflow.run")] == [{"wf": DEC, "trig": "Workflow"}]
    # once queued it is not queued twice
    with SessionLocal() as s:
        eng.run_graph(s, me, call_graph(DEC), trigger="Manual", feeds=feed(), run_id="RUN-ENGC2")
    [(jid, payload, _due)] = _jobs("workflow.run")
    from di.worker import _workflow_run  # as the worker takes a triggered run: its run record is made now

    _workflow_run(payload)
    with engine.begin() as c:
        c.execute(text("UPDATE job SET status = 'done' WHERE id = :i"), {"i": jid})
    assert _wf(DEC)["lastRun"]["trig"] == "Workflow"

    # a workflow that does not exist, and one that calls the caller back, fail the step
    with SessionLocal() as s:
        r = eng.run_graph(s, me, call_graph("WF-NOPE"), trigger="Manual", feeds=feed(), run_id="RUN-ENGC3")
    assert r.states["c"] == "failed" and "there is no workflow WF-NOPE" in r.note
    with SessionLocal() as s:
        w = state.get(s, "workflows", DEC)
        g = copy.deepcopy(studio.graph_for_run(w))
        g["nodes"].append(N("back", "xf", "x_call", {"workflow": "WF-134"}))
        (w["pub"] if w.get("pub") else w)["graph"] = g
        state.put(s, "workflows", DEC, w)
        s.commit()
    with SessionLocal() as s:
        r = eng.run_graph(s, me, call_graph(DEC), trigger="Manual", feeds=feed(), run_id="RUN-ENGC4")
    assert r.states["c"] == "failed" and "calls WF-134 back" in r.note


def test_the_audit_log_step_writes_one_entry_per_run():
    from di import state

    def entries(run_id: str) -> list[dict]:
        with SessionLocal() as s:
            return [e for e in state.items(s, "events") if e.get("run") == run_id]

    g = val_graph([{"field": "qty", "check": "range", "arg": ">0"}])
    with SessionLocal() as s:
        eng.run_graph(s, WF, g, trigger="Manual", feeds=feed(), run_id="RUN-ENGA1")
        eng.run_graph(s, WF, g, trigger="Test", dry=True, feeds=feed(), run_id="RUN-ENGA2")
    [e] = entries("RUN-ENGA1")
    assert e["type"] == "workflow.audit" and e["records"] == 2 and e["level"] == "info" and e["step"] == "aud"
    assert e["note"] == "WF-T · run RUN-ENGA1 · step Write to audit log: 2 records (info)"
    assert entries("RUN-ENGA2") == []
