"""Workflow settings and triggers that were accepted but unused (plan 6 follow-up, G3b).

- File arrival: a sync of a file source (the Sims SFTP drop) that read new files runs the source's file-triggered
  workflows; Case request: a case that needs a new decision (it moves to re-evaluation) runs the case-triggered ones.
  A trigger that fails never breaks the sync or the action.
- Scheduler and Event trigger blocks: a graph with one sets the workflow's trigger (interval / event type), on save
  and when the triggers read it.
- Delivery method Timeout and Retries, write connector Target operation: an instruction for a target whose outbound
  workflow is published here uses them; with none (the demo) or with the defaults nothing changes.
- Field mapping version: a run maps with the chosen version ("latest": the saved mapping).
"""

import copy
import hashlib
import hmac
import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

import di.actions.workflows as wf
from di import clock, state, worker
from di.cases import lifecycle as case_lifecycle
from di.cases import store as case_store
from di.config import get_settings
from di.connectors import mapping
from di.connectors.http import SourceError
from di.connectors.sync import ensure_sources
from di.db import SessionLocal, engine
from di.instructions import outbound, send, writers
from di.reads.common import ms
from di.workflow import blocks, triggers
from di.workflow import engine as eng
from tests.helpers import call, client

GLOBAL = get_settings().webhook_secret.get_secret_value()


def queued() -> list[dict]:
    with SessionLocal() as s:
        return list(
            s.execute(
                text("SELECT payload FROM job WHERE kind = 'workflow.run' AND status IN ('queued','running') ORDER BY id")
            ).scalars()
        )


def patch_wf(wid: str, **kw) -> dict:
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid, for_update=True)
        w.update(kw)
        state.put(s, "workflows", wid, w)
        s.commit()
        return w


def graph_with(wid: str, node: dict) -> dict:
    with SessionLocal() as s:
        g = copy.deepcopy(wf.graph_of(state.get(s, "workflows", wid)))
    g["nodes"].append(node)
    return g


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("DI_WORKFLOW_TRIGGERS", "true")  # the suite turns triggers off (conftest.py)
    with SessionLocal() as s:
        ensure_sources(s)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind IN ('workflow.run', 'sync.source')"))
    state.reset(["workflows", "workflow_runs", "notes", "source_config"])
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind IN ('workflow.run', 'sync.source')"))
        conn.execute(text("DELETE FROM webhook_event WHERE event_id LIKE 'wir-%'"))
    state.reset(["workflows", "workflow_runs", "notes", "source_config"])


# ---------------------------------------------------------------- 1. file arrival and case request
def _sync_returns(monkeypatch, read: int, status: str = "ok"):
    import di.connectors.sync as sync

    monkeypatch.setattr(sync, "run_sync", lambda sid, *a, **k: {"source_id": sid, "status": status, "records_read": read})


def test_a_sync_that_read_new_files_runs_the_file_workflows(monkeypatch):
    _sync_returns(monkeypatch, 2)
    worker.HANDLERS["sync.source"]({"source_id": "rcy", "trigger": "schedule"})
    assert {"wf": "WF-120", "trig": "File"} in queued()


def test_no_new_files_or_a_failed_sync_runs_nothing(monkeypatch):
    _sync_returns(monkeypatch, 0)
    worker.HANDLERS["sync.source"]({"source_id": "rcy"})
    _sync_returns(monkeypatch, 3, "failed")
    worker.HANDLERS["sync.source"]({"source_id": "rcy"})
    assert queued() == []


def test_a_sync_of_a_source_that_delivers_no_files_runs_no_file_workflow(monkeypatch):
    patch_wf("WF-105", trig={"t": "file"})  # proc delivers by API: its syncs are no file arrival
    _sync_returns(monkeypatch, 5)
    worker.HANDLERS["sync.source"]({"source_id": "proc"})
    assert queued() == []


def test_a_file_source_made_in_the_app_counts_as_a_file_source(monkeypatch):
    """delivers_files reads the sources as they are now: a file drop connected from the catalogue or made by hand
    (here: a copy of the demo's file source under a new id) fires File triggers too; unknown ids do not."""
    from di.reads.common import SOURCES
    from di.workflow import live

    made = {**SOURCES["rcy"], "id": "drop2"}
    real = live.sources
    monkeypatch.setattr(live, "sources", lambda s: {**real(s), "drop2": made})
    with SessionLocal() as s:
        assert triggers.delivers_files("drop2", s) is True
        assert triggers.delivers_files("proc", s) is False
        assert triggers.delivers_files("nope", s) is False
    assert triggers.delivers_files("drop2") is False  # without a session: the demo's reference only


def test_a_file_trigger_error_never_breaks_the_sync(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("trigger down")

    _sync_returns(monkeypatch, 2)
    monkeypatch.setattr(triggers, "on_file", boom)
    worker.HANDLERS["sync.source"]({"source_id": "rcy"})  # does not raise
    assert queued() == []


def _a_case_awaiting_approval(s):
    return next(c for c in case_store.all_cases(s) if c["stage"] == "awaiting_approval")


def test_a_case_that_needs_a_new_decision_runs_the_case_workflows():
    with SessionLocal() as s:
        c = case_store.get(s, _a_case_awaiting_approval(s)["id"], for_update=True)
        case_lifecycle.move(s, c, "reeval", "Declined", "approver")
        got = list(s.execute(text("SELECT payload FROM job WHERE kind = 'workflow.run'")).scalars())
        s.rollback()  # nothing kept
    assert {(p["wf"], p["trig"]) for p in got} == {("WF-133", "Case"), ("WF-134", "Case"), ("WF-135", "Case")}


def test_other_stage_moves_and_a_failing_trigger_leave_the_case_alone(monkeypatch):
    with SessionLocal() as s:
        c = case_store.get(s, _a_case_awaiting_approval(s)["id"], for_update=True)
        case_lifecycle.move(s, c, "approved", "Approved", "approver")
        assert s.execute(text("SELECT count(*) FROM job WHERE kind = 'workflow.run'")).scalar() == 0
        s.rollback()

    def boom(*_a, **_k):
        raise RuntimeError("trigger down")

    monkeypatch.setattr(triggers, "on_case", boom)
    with SessionLocal() as s:
        c = case_store.get(s, _a_case_awaiting_approval(s)["id"], for_update=True)
        case_lifecycle.move(s, c, "reeval", "Declined", "approver")  # does not raise
        assert case_store.get(s, c["id"])["stage"] == "reeval"
        s.rollback()


# ---------------------------------------------------------------- 2. Scheduler and Event trigger blocks
SCHED = {"id": "sch", "k": "xf", "ref": "x_sched", "x": 0, "y": 0}
EVTRIG = {"id": "evt", "k": "xf", "ref": "x_evtrig", "x": 0, "y": 0}


def test_the_trigger_a_graph_sets():
    assert triggers.from_graph({"nodes": [SCHED], "edges": []}) == {"t": "schedule", "min": 60}
    assert triggers.from_graph({"nodes": [SCHED | {"cfg": {"interval_min": 45}}]}) == {"t": "schedule", "min": 45}
    assert triggers.from_graph({"nodes": [EVTRIG]}) == {"t": "event"}
    assert triggers.from_graph({"nodes": [EVTRIG | {"cfg": {"event_type": "offer.created"}}]}) == {
        "t": "event", "type": "offer.created"
    }  # fmt: skip
    assert triggers.from_graph({"nodes": [{"id": "u", "k": "xf", "ref": "x_utc"}]}) is None
    assert triggers.from_graph(None) is None


def test_a_scheduler_block_sets_the_interval():
    t0 = ms(clock.now().isoformat())
    g = graph_with("WF-105", SCHED | {"cfg": {"interval_min": 10}})  # its Settings tab says every 30 min
    patch_wf("WF-105", graph=g, last={"ts": t0, "state": "success", "dur": 1, "rows": 1, "note": ""}, updated=t0 - 3600_000)
    with SessionLocal() as s:
        assert ("WF-105", "Schedule") not in triggers.due(s, clock.now() + timedelta(minutes=9))
        assert ("WF-105", "Schedule") in triggers.due(s, clock.now() + timedelta(minutes=10))


def test_a_scheduler_block_makes_an_event_workflow_scheduled():
    t0 = ms(clock.now().isoformat())
    patch_wf("WF-119", graph=graph_with("WF-119", SCHED | {"cfg": {"interval_min": 5}}), last={"ts": t0}, updated=t0)
    with SessionLocal() as s:
        assert ("WF-119", "Schedule") in triggers.due(s, clock.now() + timedelta(minutes=5))
        assert triggers.on_event(s, "dlr") == []  # no longer event-triggered


def _post(sid: str, ev_type: str):
    ev = {"specversion": "1.0", "id": f"wir-{uuid.uuid4()}", "source": f"/vendor/{sid}", "type": ev_type,
          "time": clock.now().isoformat().replace("+00:00", "Z")}  # fmt: skip
    body = json.dumps(ev).encode()
    sig = "sha256=" + hmac.new(GLOBAL.encode(), body, hashlib.sha256).hexdigest()
    return client.post(f"/api/webhooks/{sid}", content=body, headers={"x-signature": sig, "content-type": "application/json"})


def test_an_event_trigger_block_runs_only_on_its_event_type():
    patch_wf("WF-119", graph=graph_with("WF-119", EVTRIG | {"cfg": {"event_type": "offer.created"}}))
    assert _post("dlr", "offer.updated").status_code == 202
    assert queued() == []
    assert _post("dlr", "offer.created").status_code == 202
    assert {"wf": "WF-119", "trig": "Event"} in queued()


def test_an_event_type_pattern_and_no_type():
    pattern, any_event = graph_with("WF-119", EVTRIG | {"cfg": {"event_type": "offer.*"}}), graph_with("WF-119", EVTRIG)
    with SessionLocal() as s:
        patch_wf("WF-119", graph=pattern)
        assert triggers.on_event(s, "dlr", "listing.updated") == []
        assert triggers.on_event(s, "dlr", "offer.withdrawn") == ["WF-119"]
        s.rollback()
        patch_wf("WF-119", graph=any_event)
        assert triggers.on_event(s, "dlr", "anything") == ["WF-119"]
        s.rollback()


def test_save_keeps_the_trigger_in_step_with_the_block():
    r = call("workflow.create", {"type": "ingest", "src": "proc"}, "developer")
    assert r["ok"], r
    wid = r["output"]["id"]
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid)
    g = copy.deepcopy(wf.graph_of(w))
    g["nodes"].append(SCHED | {"cfg": {"interval_min": 20}})
    body = {"id": wid, "name": w["name"], "owner": w["owner"], "trig": {"t": "manual"}, "graph": g}
    assert call("workflow.save", body, "developer")["ok"]
    with SessionLocal() as s:
        assert state.get(s, "workflows", wid)["trig"] == {"t": "schedule", "min": 20}
    g["nodes"] = [n for n in g["nodes"] if n["id"] != "sch"]  # the block removed: the Settings tab's trigger again
    assert call("workflow.save", body | {"graph": g, "trig": {"t": "event"}}, "developer")["ok"]
    with SessionLocal() as s:
        assert state.get(s, "workflows", wid)["trig"] == {"t": "event"}


# ---------------------------------------------------------------- 3. delivery method and write connector settings
def _publish_outbound(sid: str, act_cfg: dict | None, wconn_cfg: dict | None) -> str:
    r = call("workflow.create", {"type": "out", "src": sid}, "developer")
    assert r["ok"], r
    wid = r["output"]["id"]
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid)
    g = copy.deepcopy(wf.graph_of(w))
    for n in g["nodes"]:
        if n["k"] == "act" and act_cfg:
            n["cfg"] = act_cfg
        if n["k"] == "wconn" and wconn_cfg:
            n["cfg"] = wconn_cfg
    g = blocks.compact_graph(g)
    patch_wf(wid, graph=g, status="published", pub={"ver": w["ver"], "graph": g, "settings": {}}, updated=w["updated"] + 1)
    return wid


def test_no_bound_outbound_workflow_means_the_demos_sends():
    with SessionLocal() as s:
        assert outbound.settings(s, "oms") == {}  # WF-125 is seeded as published but never published here
    _publish_outbound("oms", None, None)  # published here with the defaults: still nothing changes
    with SessionLocal() as s:
        assert outbound.settings(s, "oms") == {}


def test_the_bound_outbound_workflow_gives_its_changed_settings():
    _publish_outbound("repair", {"timeout_s": 5, "retries": 1}, {"operation": "teardown"})
    with SessionLocal() as s:
        assert outbound.settings(s, "repair") == {"timeout_s": 5, "retries": 1, "operation": "teardown"}
        assert outbound.settings(s, "oms") == {}


def test_target_operation_is_checked_against_the_targets_writes():
    n = {"id": "w", "k": "wconn", "ref": "repair", "cfg": {"operation": "teardown"}}
    assert blocks.cfg_errors(n, {"label": "Depot Repair"}) == []
    assert blocks.cfg_errors(n | {"cfg": {"operation": "order"}}, {"label": "Depot Repair"}) == [
        "Depot Repair: Target operation order is not a write of this system (repair, teardown)."
    ]
    assert writers.operations("oms") == ["order", "pod"] and writers.operations("lease") == []


def test_a_write_uses_the_timeout():
    with SessionLocal() as s:
        cl = writers.client(s, "oms")
        assert cl.http.timeout.read == 20  # the client's own default
        cl.close()
        with writers.timeout(5):
            cl = writers.client(s, "oms")
            assert cl.http.timeout.read == 5
            cl.close()


@pytest.fixture
def instruction():
    """An instruction row for a case's current approval (a repair step), removed afterwards."""
    with SessionLocal() as s:
        c = next(x for x in case_store.all_cases(s) if x.get("exec"))
        ref = c["exec"]["ref"]
        step = len(c["exec"]["steps"]) + 50  # no real step has this number
        iid = s.execute(
            text(
                "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, match_refs, queued_at) "
                "VALUES (:c, :r, :n, 'repair', 'repair', :k, '[]'::jsonb, now()) RETURNING id"
            ),
            {"c": c["id"], "r": ref, "n": step, "k": f"{ref}.{step}.repair"},
        ).scalar_one()
        s.commit()
    yield iid
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM instruction WHERE id = :i"), {"i": iid})


def _fake_writer(seen: list, fail: Exception | None = None):
    def w(s, ins, c, prev):  # a writer's signature
        seen.append({"kind": ins["kind"], "timeout": writers.current_timeout()})
        if fail is not None:
            raise fail
        return writers.Sent([{"call": "fake", "body": {}}], "DOC-1")

    return w


def test_send_uses_the_bound_settings(monkeypatch, instruction):
    seen: list = []
    monkeypatch.setitem(writers.WRITERS, "repair", _fake_writer(seen))
    monkeypatch.setitem(writers.WRITERS, "teardown", writers.WRITERS["repair"])
    monkeypatch.setattr(outbound, "settings", lambda s, system: {"timeout_s": 7, "operation": "teardown"})
    assert send.send(instruction) == "sent"
    assert seen == [{"kind": "teardown", "timeout": 7}]


def test_send_without_settings_is_unchanged(monkeypatch, instruction):
    seen: list = []
    monkeypatch.setitem(writers.WRITERS, "repair", _fake_writer(seen))
    assert send.send(instruction) == "sent"
    assert seen == [{"kind": "repair", "timeout": None}]


def test_retries_limit_the_attempts_on_a_system_that_is_down(monkeypatch, instruction):
    seen: list = []
    monkeypatch.setitem(writers.WRITERS, "repair", _fake_writer(seen, SourceError("unavailable", "repair: down")))
    with pytest.raises(SourceError):
        send.send(instruction)
    with SessionLocal() as s:
        assert send.queue.get(s, instruction)["status"] == "queued"  # retried by the job queue, as before
    monkeypatch.setattr(outbound, "settings", lambda s, system: {"retries": 1})
    with pytest.raises(SourceError):
        send.send(instruction)  # the second try: no retries left
    with SessionLocal() as s:
        row = send.queue.get(s, instruction)
    assert row["status"] == "failed" and "down" in row["last_error"]


# ---------------------------------------------------------------- 4. field mapping version
SID = "insp"


@pytest.fixture
def two_versions():
    """insp with v1 (the demo's mapping) and v2 (every row removed: the builtin fields are dropped)."""
    with engine.begin() as conn:  # the starting state: no saved version
        conn.execute(text("DELETE FROM field_mapping WHERE source_id = :s"), {"s": SID})
    with SessionLocal() as s:
        assert mapping.save_version(s, SID, [], "developer", "Nothing mapped") == 2
        s.commit()
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM field_mapping WHERE source_id = :s"), {"s": SID})


def _mapped(version) -> eng.RunResult:
    g = {
        "nodes": [
            {"id": "r", "k": "conn", "ref": SID, "x": 0, "y": 0, "cfg": {"mode": "full"}},
            {"id": "m", "k": "map", "ref": SID, "x": 0, "y": 0} | ({"cfg": {"version": version}} if version != "latest" else {}),
        ],
        "edges": [{"id": "e0", "a": "r", "b": "m", "locked": False}],
    }
    with SessionLocal() as s:
        return eng.run_graph(s, {"id": "WF-T"}, g, trigger="Test", dry=True, sample=5)


def _fields(res: eng.RunResult) -> set[tuple[str, str]]:
    return {(f["model"], f["field"]) for r in res.samples["m"]["after"] for f in r.get("facts") or []}


def test_a_run_maps_with_the_chosen_version(two_versions):  # the fixture saves the versions
    base = mapping.builtin(SID)
    v1, latest = _mapped(1), _mapped("latest")
    assert v1.states["m"] == "success" and latest.states["m"] == "success"
    assert _fields(v1) & base  # the demo's mapping: the builtin fields are there
    assert not _fields(latest) & base  # v2, the saved one: dropped
    assert _fields(_mapped(2)) == _fields(latest)


def test_a_version_that_does_not_exist_fails_the_step(two_versions):  # the fixture saves the versions
    res = _mapped(9)
    assert res.states["m"] == "failed" and "no field mapping version 9" in (res.error or "")
