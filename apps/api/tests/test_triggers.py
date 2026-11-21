"""Plan 6 C6: workflows run on their trigger (di/workflow/triggers.py).

A published, not paused workflow whose source is not paused runs on its trigger: a schedule every `min` minutes after
its last run or its publish (whichever is later, on the workspace clock), an event (a webhook for its source), an
approval (an instruction queued for its target system). A trigger queues one `workflow.run` job ({wf, trig}, no run
record yet); the worker makes the run record when it takes the job, so the record's `trig` says what started it. A
workflow already running, or with a run already queued, gets no second one.
"""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import di.actions.workflows as wf
from di import clock, state, worker
from di.config import get_settings
from di.connectors.sync import ensure_sources
from di.db import SessionLocal, engine
from di.reads.common import ms
from di.workflow import triggers
from tests.helpers import client, publish_seeded_here

GLOBAL = get_settings().webhook_secret.get_secret_value()
MIN = 60_000


def now_ms() -> int:
    return ms(clock.now().isoformat())


def run_jobs() -> list[dict]:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, payload FROM job WHERE kind = 'workflow.run' AND status = 'queued' ORDER BY id")
        ).all()
    for job_id, payload in rows:
        worker.HANDLERS["workflow.run"](payload)
        with engine.begin() as conn:
            conn.execute(text("UPDATE job SET status = 'done' WHERE id = :i"), {"i": job_id})
    return [p for _, p in rows]


def queued() -> list[dict]:
    with SessionLocal() as s:
        return list(
            s.execute(
                text("SELECT payload FROM job WHERE kind = 'workflow.run' AND status IN ('queued','running') ORDER BY id")
            ).scalars()
        )


def patch_wf(wid: str, **kw) -> None:
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid, for_update=True)
        w.update(kw)
        state.put(s, "workflows", wid, w)
        s.commit()


def test_seeded_workflows_not_published_in_the_app_fire_on_no_trigger():
    """The demo's seeded "published" workflows are illustrations: until a person publishes one in the app (it then
    has `pub`), no schedule, event, file, approval or case starts it (they would flood the worker)."""
    state.reset(["workflows"])  # back to the seeded workflows, without the fixture's pub
    with SessionLocal() as s:
        w = next(x for x in state.items(s, "workflows") if x.get("status") == "published")
        assert not triggers.published_here(w) and not triggers.may_run(s, w)
        assert triggers.fire(s, w["id"], "Event") is None
        assert triggers.due(s, datetime(2099, 1, 1, tzinfo=UTC)) == []
        s.rollback()


def source_status(sid: str, status: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE source_system SET status = :st WHERE id = :i"), {"st": status, "i": sid})


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("DI_WORKFLOW_TRIGGERS", "true")  # the suite turns triggers off (conftest.py)
    monkeypatch.setattr(wf, "STEP_SECONDS", 0)
    monkeypatch.setattr(wf, "QUICK_SECONDS", 0)
    with SessionLocal() as s:
        ensure_sources(s)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind IN ('workflow.run', 'sync.source')"))
        was = dict(conn.execute(text("SELECT id, status FROM source_system WHERE id IN ('proc', 'dlr')")).all())
    state.reset(["workflows", "workflow_runs", "notes", "source_config"])
    publish_seeded_here()  # triggers fire only for workflows published in the app
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind IN ('workflow.run', 'sync.source')"))
        conn.execute(text("DELETE FROM webhook_event WHERE event_id LIKE 'trg-%'"))
    for sid, st in was.items():
        source_status(sid, st)
    state.reset(["workflows", "workflow_runs", "notes", "source_config"])


# ---------------------------------------------------------------- schedule
def test_nothing_is_due_at_the_demo_as_of_time():
    """Golden parity: on the suite's pinned clock the seeded schedules have all run recently, so none is due."""
    with SessionLocal() as s:
        assert triggers.due(s, clock.now()) == []


def test_a_30_minute_schedule_runs_at_30_minutes_not_before():
    t0 = now_ms()
    patch_wf("WF-105", last={"ts": t0, "state": "success", "dur": 1, "rows": 1, "note": ""}, updated=t0 - 3600 * 1000)
    assert ("WF-105", "Schedule") not in triggers.due(SessionLocal(), clock.now() + timedelta(minutes=29, seconds=59))
    with SessionLocal() as s:
        assert ("WF-105", "Schedule") in triggers.due(s, clock.now() + timedelta(minutes=30))
        assert "WF-105" in triggers.tick(s, clock.now() + timedelta(minutes=30))
        s.commit()
    assert [p for p in queued() if p["wf"] == "WF-105"] == [{"wf": "WF-105", "trig": "Schedule"}]
    run_jobs()
    runs = [r for r in state.items(SessionLocal(), "workflow_runs", newest_first=True) if r["wf"] == "WF-105"]
    assert runs[0]["trig"] == "Schedule" and runs[0]["state"] != "running"
    assert state.get(SessionLocal(), "workflows", "WF-105")["lastRun"]["trig"] == "Schedule"


def test_the_schedule_counts_from_the_publish_when_that_is_later():
    t0 = now_ms()
    patch_wf("WF-105", last={"ts": t0 - 3600 * 1000, "state": "success", "dur": 1, "rows": 1, "note": ""}, updated=t0)
    with SessionLocal() as s:
        assert ("WF-105", "Schedule") not in triggers.due(s, clock.now() + timedelta(minutes=10))
        assert ("WF-105", "Schedule") in triggers.due(s, clock.now() + timedelta(minutes=30))


def test_paused_workflows_and_workflows_of_a_paused_source_do_not_run():
    t0 = now_ms()
    patch_wf("WF-105", last={"ts": t0, "state": "success", "dur": 1, "rows": 1, "note": ""}, updated=t0, status="paused")
    later = clock.now() + timedelta(hours=2)
    with SessionLocal() as s:
        assert "WF-105" not in [w for w, _ in triggers.due(s, later)]
    patch_wf("WF-105", status="published")
    source_status("proc", "paused")
    with SessionLocal() as s:
        assert "WF-105" not in [w for w, _ in triggers.due(s, later)]
        assert triggers.fire(s, "WF-105", "Schedule") is None
        s.commit()
    assert queued() == []


# ---------------------------------------------------------------- event (webhook)
def _post(sid: str, ev_type: str = "offer.updated"):
    ev = {
        "specversion": "1.0",
        "id": f"trg-{uuid.uuid4()}",
        "source": f"/vendor/{sid}",
        "type": ev_type,
        "time": clock.now().isoformat().replace("+00:00", "Z"),
    }
    body = json.dumps(ev).encode()
    sig = "sha256=" + hmac.new(GLOBAL.encode(), body, hashlib.sha256).hexdigest()
    return client.post(f"/api/webhooks/{sid}", content=body, headers={"x-signature": sig, "content-type": "application/json"})


def test_a_webhook_runs_the_bound_workflow_with_trigger_event():
    r = _post("dlr")  # WF-119, Ingest Â· dealer network, trigger "On event"
    assert r.status_code == 202, r.text
    assert {"wf": "WF-119", "trig": "Event"} in queued()
    run_jobs()
    with SessionLocal() as s:
        run = next(x for x in state.items(s, "workflow_runs", newest_first=True) if x["wf"] == "WF-119")
        w = state.get(s, "workflows", "WF-119")
    assert run["trig"] == "Event" and run["state"] in ("success", "warning", "failed")
    assert w["lastRun"]["trig"] == "Event" and not w["running"]


def test_a_webhook_for_a_paused_workflow_runs_nothing():
    patch_wf("WF-119", status="paused")
    assert _post("dlr").status_code == 202
    assert queued() == []


def test_triggers_switched_off_queue_nothing(monkeypatch):
    monkeypatch.setenv("DI_WORKFLOW_TRIGGERS", "false")
    assert _post("dlr").status_code == 202
    with SessionLocal() as s:
        assert triggers.fire(s, "WF-119", "Event") is None
        assert triggers.on_approval(s, "oms") == []
    assert queued() == []


def test_a_trigger_error_never_breaks_the_webhook(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("trigger down")

    monkeypatch.setattr(triggers, "on_event", boom)
    r = _post("dlr")
    assert r.status_code == 202 and r.json()["queued_job"], r.text


# ---------------------------------------------------------------- no duplicates
def test_no_second_run_while_one_is_queued_or_running():
    with SessionLocal() as s:
        assert triggers.fire(s, "WF-119", "Event") is not None
        assert triggers.fire(s, "WF-119", "Event") is None
        s.commit()
    assert len(queued()) == 1
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'workflow.run'"))
    patch_wf("WF-119", running=True)
    with SessionLocal() as s:
        assert triggers.fire(s, "WF-119", "Event") is None
    # a manual run already queued counts too
    patch_wf("WF-119", running=False)
    with SessionLocal() as s:
        s.execute(
            text("INSERT INTO job (kind, payload) VALUES ('workflow.run', CAST(:p AS jsonb))"),
            {"p": json.dumps({"run": "RUN-X", "wf": "WF-119", "trig": "Manual"})},
        )
        assert triggers.fire(s, "WF-119", "Event") is None


def test_a_job_whose_workflow_started_meanwhile_makes_no_second_run():
    with SessionLocal() as s:
        triggers.fire(s, "WF-119", "Event")
        s.commit()
    patch_wf("WF-119", running=True)
    before = len(state.items(SessionLocal(), "workflow_runs"))
    with engine.connect() as lk:  # the run that started meanwhile is going: its job holds the run lock (plan 6 C7)
        lk.execute(text("SELECT pg_advisory_xact_lock(:c, hashtext(:k))"), {"c": wf.RUN_LOCK, "k": "wf:WF-119"})
        run_jobs()
        lk.rollback()
    assert len(state.items(SessionLocal(), "workflow_runs")) == before


def test_a_triggered_run_closes_a_run_its_worker_lost_and_runs():
    """Plan 6 C7: `running` left by a dead worker (no lock, no other job) does not block the trigger for ever: the
    triggered run closes the lost run as "Failed: worker lost" and runs."""
    with SessionLocal() as s:
        w = state.get(s, "workflows", "WF-119", for_update=True)
        lost = wf.start_run(s, w, "Event", now_ms() - 1, enqueue=False)
        s.commit()
    with SessionLocal() as s:
        s.execute(
            text("INSERT INTO job (kind, payload) VALUES ('workflow.run', CAST(:p AS jsonb))"),
            {"p": json.dumps({"wf": "WF-119", "trig": "Event"})},
        )
        s.commit()
    run_jobs()
    with SessionLocal() as s:
        assert state.get(s, "workflow_runs", lost)["note"] == "Failed: worker lost"
        w = state.get(s, "workflows", "WF-119")
    assert not w["running"] and w["lastRun"]["trig"] == "Event"


def test_a_webhook_does_not_also_trigger_the_workflow_its_source_syncs_with():
    """Plan 6 C5: once WF-119 is published here it is the dealer source's sync workflow (source_config.workflow); the
    webhook queues the sync, which runs it, so the event trigger does not run it a second time."""
    from tests.helpers import call

    for st in ("draft", "published"):  # published again here (the seeded one is published already)
        r = call("workflow.setStatus", {"id": "WF-119", "status": st}, "developer")
        assert r["ok"], r
    with SessionLocal() as s:
        assert (state.get(s, "source_config", "dlr") or {}).get("workflow") == "WF-119"
    r = _post("dlr")
    assert r.status_code == 202 and r.json()["queued_job"], r.text
    assert [p for p in queued() if p.get("wf") == "WF-119"] == []


# ---------------------------------------------------------------- approval, file, case
def test_an_instruction_for_a_target_runs_its_outbound_workflow_with_trigger_approval():
    with SessionLocal() as s:
        assert triggers.on_approval(s, "oms") == ["WF-125"]  # Outbound Â· Sterling OMS
        s.commit()
    run_jobs()
    run = next(x for x in state.items(SessionLocal(), "workflow_runs", newest_first=True) if x["wf"] == "WF-125")
    assert run["trig"] == "Approval"


def test_file_and_case_triggers():
    with SessionLocal() as s:
        assert triggers.on_file(s, "rcy") == ["WF-120"]
        assert set(triggers.on_case(s, "RT-1048")) == {"WF-133", "WF-134", "WF-135"}
        s.commit()
    assert {(p["wf"], p["trig"]) for p in queued()} == {
        ("WF-120", "File"),
        ("WF-133", "Case"),
        ("WF-134", "Case"),
        ("WF-135", "Case"),
    }


def test_a_manual_run_still_says_manual():
    from tests.helpers import call

    r = call("workflow.run", {"id": "WF-119"}, "developer")
    assert r["ok"], r
    run_jobs()
    run = next(x for x in state.items(SessionLocal(), "workflow_runs", newest_first=True) if x["wf"] == "WF-119")
    assert run["trig"] == "Manual"
