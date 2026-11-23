"""Plan 8 MVP-10.3: pilot mode per org unit, and the pilot report.

An org unit in pilot mode (state collection `org_settings`, org.setPilot) is a read-only testbed: an instruction for a
case whose owner, or an ancestor of it, is in pilot mode is never sent. It is held with the note "Pilot mode: not sent
to <target>" and acknowledged later by the simulated adapter, as a step without a mock write is. org.pilotReport sums
what the org's subtree did.

RT-1048 (Customer A) is submitted and approved with sending off (the test suite's default), then its first step
(the Sterling order allocation) is queued and sent in-process, its job removed in the same transaction so the running
worker never picks it up. The module starts and ends with the demo reset and resets the Sterling mock (oms).
"""

import httpx
import pytest
from sqlalchemy import text

from di.core import golden
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.actions import org_pilot
from di.services.cases import store
from di.services.instructions import queue
from di.services.instructions import send as instruction_send
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url.rstrip("/")
CASE = "RT-1048"


def _sim_reset_oms() -> None:
    httpx.post(SIM + "/_sim/reset", params={"system": "oms"}, timeout=60).raise_for_status()


def setup_module():
    starting.reset()
    _sim_reset_oms()


def teardown_module():
    starting.reset()
    _sim_reset_oms()


@pytest.fixture
def approved():
    """RT-1048 approved again (from the starting state), its pilot settings cleared afterwards."""
    starting.reset()
    approve = next(s for s in golden.load("actions")["steps"] if s["action"] == "decision.approve" and s["result"].get("ok"))
    assert call("decision.submit", {"case_id": CASE}, "planner-a")["ok"]
    r = call("decision.approve", approve["input"], "approver")
    assert r["ok"], r
    yield r["output"]["ref"]
    starting.reset()


def queue_first_step() -> int:
    """The approval's first instruction row, without its send job (sent in-process below)."""
    with SessionLocal() as s:
        c = store.get(s, CASE)
        iid = queue.queue(s, c, 0)
        assert iid is not None
        s.execute(text("DELETE FROM job WHERE kind = 'instruction.send'"))
        s.commit()
    return iid


def oms_posts() -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM fetch_log WHERE source_id = 'oms' AND method = 'POST'")).scalar_one()


def row(iid: int) -> dict:
    with SessionLocal() as s:
        got = queue.get(s, iid)
    assert got is not None
    return got


def set_pilot(org: str, on: bool) -> dict:
    r = call("org.setPilot", {"org_unit_id": org, "on": on}, "admin")
    assert r["ok"], r
    return r["output"]


@pytest.mark.usefixtures("approved")
def test_pilot_holds_instructions():
    assert set_pilot("Customer A", True) == {"org_unit_id": "Customer A", "pilot": True}
    iid = queue_first_step()
    before = oms_posts()
    assert instruction_send.send(iid) == "held"
    assert oms_posts() == before  # no write reached Sterling (source-sim has no new record)
    ins = row(iid)
    assert (ins["status"], ins["simulated"], ins["doc_ref"]) == ("sent", True, None)
    assert ins["detail"]["held"] is True
    assert ins["detail"]["note"] == "Pilot mode: not sent to IBM Sterling OMS"
    assert ins["due_at"] is not None  # the simulated adapter acknowledges it, so the run goes on


@pytest.mark.usefixtures("approved")
def test_pilot_off_sends():
    set_pilot("Customer A", True)
    assert set_pilot("Customer A", False)["pilot"] is False
    iid = queue_first_step()
    before = oms_posts()
    assert instruction_send.send(iid) == "sent"
    assert oms_posts() > before  # the allocation reached Sterling (each try has its own fetch-log row)
    ins = row(iid)
    assert ins["simulated"] is False and "held" not in ins["detail"] and ins["doc_ref"]


def test_child_of_pilot_org_is_pilot():
    set_pilot("workspace", True)
    try:
        with SessionLocal() as s:
            assert org_pilot.is_pilot(s, "Customer A") and org_pilot.is_pilot(s, "Customer C")
        set_pilot("workspace", False)
        with SessionLocal() as s:
            assert not org_pilot.is_pilot(s, "Customer A")
    finally:
        starting.reset()


def test_set_pilot_needs_manage_orgs():
    r = call("org.setPilot", {"org_unit_id": "Customer A", "on": True}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope", r
    r = call("org.setPilot", {"org_unit_id": "t-no-such-unit", "on": True}, "admin")
    assert r["error"] == {"code": "not_found", "message": "No org unit t-no-such-unit."}


def _expected(owners: set[str]) -> dict:
    with SessionLocal() as s:
        cases = [c for c in store.all_cases(s) if c["owner"] in owners]
    recs = [c["recommendation"] for c in cases if c.get("recommendation")]
    by_route: dict[str, int] = {}
    for r in recs:
        by_route[r["id"]] = by_route.get(r["id"], 0) + 1
    return {
        "cases_opened": len(cases),
        "decisions_submitted": sum(1 for c in cases if c["stage"] in org_pilot.SUBMITTED),
        "decisions_approved": sum(1 for c in cases if c["stage"] in org_pilot.APPROVED),
        "recommended_net_total": round(sum(r["net"] for r in recs), 2),
        "rules_applied_count": sum(1 for c in cases if c.get("rulesApplied")),
        "by_route": by_route,
    }


@pytest.mark.usefixtures("approved")
def test_pilot_report_counts():
    set_pilot("Customer A", True)
    instruction_send.send(queue_first_step())
    a = call("org.pilotReport", {"org_unit_id": "Customer A"}, "admin")
    assert a["ok"], a
    out = a["output"]
    assert out == _expected({"Customer A"}) | {"org_unit_id": "Customer A", "instructions_held": 1}
    assert out["decisions_approved"] >= 1 and out["cases_opened"] > 0
    whole = call("org.pilotReport", {"org_unit_id": "workspace"}, "approver")["output"]
    assert whole == _expected({"Customer A", "Customer B", "Customer C"}) | {"org_unit_id": "workspace", "instructions_held": 1}
    refused = call("org.pilotReport", {"org_unit_id": "Customer A"}, "planner-a")
    assert refused["ok"] is False and refused["error"]["code"] == "out_of_scope", refused
