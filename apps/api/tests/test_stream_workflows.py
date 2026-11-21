"""B15 part 2: a workflow run reports its progress over the live-update stream (kind `workflow`, migration 0009).

As in test_stream.py, the streams are real HTTP connections to the api server in this container (port 8000). The run
is started through that server; its `workflow.run` job then runs here, in-process (the worker is stopped for the test
run), and every step it writes into the run record must reach the Workflow Studio's accounts as one `workflow` event,
in order, while accounts without the studio receive none.
"""

import itertools
import time

import httpx
import pytest
from sqlalchemy import text

import di.actions.workflows as wf
from di.db import engine
from tests import starting
from tests.test_stream import API, Listener, token


def act(user: str, action: str, body: dict) -> dict:
    r = httpx.post(f"{API}/api/actions/{action}", json=body, headers={"Authorization": f"Bearer {token(user)}"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(wf, "STEP_SECONDS", 0.02)
    monkeypatch.setattr(wf, "QUICK_SECONDS", 0)
    starting.reset()
    yield
    starting.reset()


def _job(run_key: str) -> dict:
    with engine.begin() as conn:
        job_id, payload = conn.execute(
            text("SELECT id, payload FROM job WHERE kind = 'workflow.run' AND payload->>'run' = :r"), {"r": run_key}
        ).one()
        conn.execute(text("UPDATE job SET status = 'done' WHERE id = :i"), {"i": job_id})
    return payload


def _run_events(listener: Listener, run_key: str) -> list[dict]:
    return [
        d["payload"]
        for _, kind, d, _ in listener.events
        if kind == "workflow" and d["payload"]["collection"] == "workflow_runs" and d["payload"]["id"] == run_key
    ]


def test_a_run_streams_one_event_per_step_change_to_the_studio_only():
    dev, admin, planner, engineer = Listener("developer"), Listener("admin"), Listener("planner-a"), Listener("engineer")
    try:
        out = act("developer", "workflow.run", {"id": "WF-101"})["output"]
        key = out["run"]
        assert out["id"] == "WF-101"
        # queued: the run record (running) and the workflow (running) are on the stream already
        assert dev.wait_for(lambda k, d: k == "workflow" and d["payload"]["id"] == key and d["payload"]["op"] == "insert")
        assert dev.wait_for(
            lambda k, d: k == "workflow" and d["payload"]["collection"] == "workflows" and d["payload"]["data"]["running"] is True
        )

        result = wf.run_job(_job(key))
        assert result["state"] == "success"
        final = dev.wait_for(
            lambda k, d: k == "workflow" and d["payload"]["id"] == key and d["payload"]["data"]["state"] != "running", timeout=10
        )
        assert final is not None, "the finished run did not arrive"
        time.sleep(0.3)

        evs = _run_events(dev, key)
        assert evs[0]["op"] == "insert" and evs[0]["data"]["state"] == "running" and "states" not in evs[0]["data"]
        steps = [e["data"] for e in evs[1:-1]]
        assert len(steps) == result["steps"], "one event per step change"
        assert all(e["op"] == "update" for e in evs[1:])
        # every step goes queued -> running -> its state, in the run order, and the states only move forward
        order = steps[0]["order"]
        seen = [(s["step"], s["step_state"]) for s in steps]
        assert [x for x in seen if x[1] != "running"] == [(i, steps[-1]["states"][i]) for i in order]
        for a, b in itertools.pairwise(steps):
            changed = [i for i in order if a["states"][i] != b["states"][i]]
            assert changed == [b["step"]], (a["step"], b["step"], changed)
        # the records in and out of each finished step come with it: what the run really read (plan 6 C5; a delta read
        # of the source, so as many as changed since its cursor)
        assert set(steps[-1]["counts"]) == set(order)
        assert steps[-1]["counts"]["r"]["in"] == steps[-1]["counts"]["r"]["out"] == result["rows"] >= 0
        # the last event is the demo's run record
        assert set(evs[-1]["data"]) == {"id", "wf", "name", "ts", "trig", "dur", "rows", "state", "note"}
        assert evs[-1]["data"]["state"] == "success"
        # and the workflow's own change (running off, its last run) follows
        assert dev.wait_for(
            lambda k, d: k == "workflow"
            and d["payload"]["collection"] == "workflows"
            and d["payload"]["id"] == "WF-101"
            and d["payload"]["data"]["running"] is False
            and "graph" not in d["payload"]["data"]
        )
        assert len(_run_events(admin, key)) == len(evs)

        # accounts that may not open the Workflow Studio see none of it
        assert not [e for e in planner.events if e[1] == "workflow"]
        assert not [e for e in engineer.events if e[1] == "workflow"]
    finally:
        for s in (dev, admin, planner, engineer):
            s.close()


def test_workflow_changes_reach_the_studio():
    dev = Listener("developer")
    try:
        act("developer", "workflow.setStatus", {"id": "WF-101", "status": "paused"})
        hit = dev.wait_for(
            lambda k, d: k == "workflow" and d["payload"]["id"] == "WF-101" and d["payload"]["data"]["status"] == "paused"
        )
        assert hit is not None and hit[2]["payload"]["op"] == "update"
        made = act("developer", "workflow.create", {"type": "dec"})["output"]["id"]
        assert dev.wait_for(lambda k, d: k == "workflow" and d["payload"]["id"] == made and d["payload"]["op"] == "insert")
    finally:
        dev.close()
