"""MVP-3.3 and 3.4: a re-evaluation applies the business rules of the case's published flow, and records the flow
version; publishing never rewrites a decision already made or submitted (Review Focus 4)."""

import pytest
from sqlalchemy import text

from di.core import state
from di.core.db import SessionLocal, engine
from di.services.cases import store
from di.services.engine import book
from tests import flowkit
from tests.flowkit import ok
from tests.helpers import call

SCOPE_A_C = {"grade": ["C"], "owner": ["Customer A"]}


@pytest.fixture(autouse=True)
def fresh():
    """The demo's starting cases and an empty journal (as tests/test_writes_decisions.py), the seeded flows."""

    def reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("UPDATE delegation SET enabled = true"))
            conn.execute(text("DELETE FROM tenant_grant"))
            conn.execute(text("DELETE FROM domain_event"))
            conn.execute(text("DELETE FROM case_stage_log WHERE seq IS NOT NULL"))
            conn.execute(text("DELETE FROM action_journal"))
        store.reset()
        state.reset()
        flowkit.reset_flows()

    reset()
    yield
    reset()


def _case(case_id: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, case_id)
    assert c is not None
    return c


def _reevaluate(case_id: str) -> dict:
    ok(call("decision.decline", {"case_id": case_id, "reason": "Re-check with the new policy."}, "admin"))
    return ok(call("case.reevaluate", {"case_id": case_id}, "admin"))


def _route(c: dict, rid: str) -> dict:
    return next(r for r in c["routes"] if r["id"] == rid)


def test_published_rule_excludes_on_reevaluate():
    flowkit.fork_and_publish("Customer A", [("IR-01", "exclude", "material", SCOPE_A_C)])
    _reevaluate("RT-1065")
    c = _case("RT-1065")
    m = _route(c, "material")
    assert (m["excluded"], m["failGate"]) == (True, 2)
    assert m["failReason"] == "Excluded by business rule IR-01: grade C, for Customer A: never material recovery"
    assert (c["rulesApplied"], c["flowVer"]) == (["IR-01"], 2)
    assert c["recommendation"]["id"] != "material"


def test_other_org_unaffected():
    flowkit.fork_and_publish("Customer A", [("IR-01", "exclude", "material", {"grade": ["C"]})])
    _reevaluate("RT-1001")  # Customer B, grade C: its flow is the workspace default
    c = _case("RT-1001")
    assert not _route(c, "material")["excluded"]
    assert "rulesApplied" not in c and c["flowVer"] == 1


def test_default_flows_change_nothing():
    """RT-1048 (hand-modelled) and a formula-valued case re-evaluate as before with only the seeded flows; the
    formula values themselves are pinned by tests/test_writes_decisions.py::test_formula_cases_rebuild_as_the_demo."""
    want = book.get("RT-1048")
    out = _reevaluate("RT-1048")
    c = _case("RT-1048")
    assert out == {"case_id": "RT-1048", "was": want["recommendation"]["plan"], "now": want["recommendation"]["plan"],
                   "net": want["recommendation"]["net"]}  # fmt: skip
    assert c["routes"] == want["routes"]
    assert c["flowVer"] == 1
    assert not {"rulesApplied", "rulesWaived", "preferred"} & c.keys()


def test_rule_on_hand_modelled_case_and_rollback():
    """A hand-modelled case keeps its route terms; the rules apply on top and leave with the rollback."""
    want = book.get("RT-1048")
    fid = flowkit.fork_and_publish("Customer A", [("IR-01", "exclude", "redeploy", {})])
    _reevaluate("RT-1048")
    c = _case("RT-1048")
    rd = _route(c, "redeploy")
    assert (rd["excluded"], rd["failGate"]) == (True, 2)
    assert rd["failReason"] == "Excluded by business rule IR-01: every return: never redeploy"
    assert c["recommendation"]["id"] != "redeploy" and c["rulesApplied"] == ["IR-01"]
    ok(call("flow.rollback", {"flow_id": fid}, "approver"))
    _reevaluate("RT-1048")
    c = _case("RT-1048")
    assert c["routes"] == want["routes"] and c["flowVer"] == 1
    assert not {"rulesApplied", "rulesWaived", "preferred"} & c.keys()
