"""Plan 6 C7: the worker's periodic step closes a workflow run its worker lost (`running` set, nothing queued or going),
so the workflow never stays "running" after a crash; a workflow whose run is really going is left alone."""

from sqlalchemy import text

from di import worker
from di.core import state
from di.core.db import SessionLocal
from tests import starting


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


def _wf(wid: str) -> dict:
    with SessionLocal() as s:
        return state.get(s, "workflows", wid)


def test_a_lost_run_is_closed_and_a_live_one_is_not():
    with SessionLocal() as s:
        lost = state.get(s, "workflows", "WF-103")
        lost["running"] = True
        state.put(s, "workflows", "WF-103", lost)
        run = {"id": "RUN-LOST1", "wf": "WF-103", "name": lost["name"], "ts": lost["last"]["ts"], "trig": "Manual",
               "dur": None, "rows": None, "state": "running", "note": ""}  # fmt: skip
        state.add(s, "workflow_runs", "RUN-LOST1", run)
        live = state.get(s, "workflows", "WF-110")
        live["running"] = True
        state.put(s, "workflows", "WF-110", live)
        s.execute(
            # a job a worker has just claimed (a longer run is seen by the run lock it holds)
            text(
                "INSERT INTO job (kind, payload, status, locked_at)"
                " VALUES ('workflow.run', CAST(:p AS jsonb), 'running', now())"
            ),
            {"p": '{"wf": "WF-110", "run": "RUN-LIVE1"}'},
        )
        s.commit()
    try:
        worker.reap_lost_runs()
        w = _wf("WF-103")
        assert w["running"] is False and w["last"]["note"] == "Failed: worker lost"
        with SessionLocal() as s:
            assert state.get(s, "workflow_runs", "RUN-LOST1")["state"] == "failed"
        assert _wf("WF-110")["running"] is True  # its job is still going
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM job WHERE kind = 'workflow.run' AND payload->>'run' = 'RUN-LIVE1'"))
            s.commit()
