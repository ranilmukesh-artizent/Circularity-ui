"""Plan 9, P9-4.7 (story SD-06): the fault is posted on a draft line and the options run again.

`serviceDesk.postFault` sets the line's fault code, keeps the ticket's text, estimates the line again (P9-4.4), decides the case
again through the one decider (`intake.revalue`, I-6, R19), closes the line's technician-check item and journals it.
No model step (R16): the fault is a code picked from a list and nothing reads free text, so there are no model tests. The action
needs `assess`, an agent's call is held for a person (HELD_FOR_PERSON, I-10) and nothing joins FORBIDDEN_ACTIONS: it approves
and releases nothing.

It starts and ends with the demo reset.
"""

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import service_tickets
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, forbidden, held_for_person
from di.services.cases import store
from di.services.service_desk import intake as sd
from tests import starting
from tests.helpers import call, tool_case_facts

ORG = "tool-fleet-a"
ACTION = "serviceDesk.postFault"
pytestmark = pytest.mark.usefixtures("no_synced_conflicts")


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('contract_line', 'contract', 'recall')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract_line', 'contract', 'recall')"))
        for t in ("service_ticket", "repair_history", "refurb_unit", "upgrade_offer"):
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    yield
    starting.reset()
    _clean()


def _history(n: int = 60) -> None:
    rows = [{"id": f"RH-{i}", "closed": date(2023, 10, 7) + timedelta(days=i * 5)} for i in range(n)]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO repair_history (id, org_unit_id, serial, model_class, age_months, fault_code, market, parts, "
                "labour_hours, test_fee, turnaround_days, actual_cost, currency, closed_on, source) VALUES (:id, :org, NULL, "
                "'CRH', 18, 'MOT', 'US', CAST('[{\"PART_NUMBER\": \"CRH-0\", \"QUANTITY\": 1}]' AS jsonb), 2.0, false, 5, 0, "
                "'USD', :closed, 'rephist')"
            ),
            [{"org": ORG, **r} for r in rows],
        )


def _draft_case(fault: str | None = None) -> dict:
    """A ticket of one CRH whose fault is unclear (the technician's text only), opened as a case."""
    line = {
        "serial": "CRH-46042", "model_class": "CRH", "age_months": 18, "fault_code": fault, "fault_text": "Runs hot, smells",
        "cover_type": "fleet", "cover_until": "2027-06-30",
    }  # fmt: skip
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO service_ticket (number, org_unit_id, account, market, site, batch_id, lines, requester_role, "
                "loaner_promised, opened_at, source) VALUES ('CS0010042', :o, 'ACC-US-0042', 'US', 'Austin', NULL, "
                "CAST(:l AS jsonb), 'Site manager', false, '2026-10-07T09:00:00+00:00', 'sdesk')"
            ),
            {"o": ORG, "l": json.dumps([line])},
        )
    tool_case_facts("CRH-46042", {"cls": "CRH"})
    with SessionLocal() as s:
        row = next(t for t in service_tickets.pending(s, ORG) if t.number == "CS0010042")
        c = sd.open_from_ticket(s, row, "system")
        s.commit()
    with SessionLocal() as s:
        return store.get(s, c["id"])


def _case(case_id: str) -> dict:
    with SessionLocal() as s:
        return store.get(s, case_id)


def _checks(case_id: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT status, outcome FROM work_item WHERE case_id = :c AND type = 'technician_check'"), {"c": case_id}
        )
        return [dict(r._mapping) for r in rows]


def _journal(case_id: str) -> int:
    with engine.connect() as conn:
        q = text("SELECT count(*) FROM action_journal WHERE action = :a AND case_id = :c")
        return conn.execute(q, {"a": ACTION, "c": case_id}).scalar()


def test_sd_06_fault_post_reruns_options():
    _history()
    c = _draft_case()
    ln = c["serviceDesk"]["lines"][0]
    assert ln["fault_code"] is None and ln["estimate"]["auto"] is False and ln["estimate"]["n"] == 0
    assert [o["k"] for o in (ln.get("options") or []) if o["eligible"] and o["customer_price"]] == []
    assert [x["status"] for x in _checks(c["id"])] == ["open"]
    r = call(ACTION, {"case_id": c["id"], "line": 1, "fault_code": "MOT"}, "engineer")
    assert r["ok"] is True, r
    after = _case(c["id"])["serviceDesk"]["lines"][0]
    assert after["fault_code"] == "MOT" and after["fault_text"] == "Runs hot, smells"  # the ticket's text is kept
    e = after["estimate"]
    assert e["n"] >= 50 and e["key_used"] == "class_fault_age" and e["auto"] is True and e["item"] is None
    assert e["point"] > 0 and {o["k"] for o in after["options"]} == {"fix", "swap", "upgrade"}
    fix = next(o for o in after["options"] if o["k"] == "fix")
    assert fix["eligible"] and fix["cost"] and any(x["cites"].startswith("US labour rates") for x in fix["lines"])
    assert _checks(c["id"])[0]["status"] == "done"
    assert len(_checks(c["id"])) == 1  # closed, not booked again
    assert _journal(c["id"]) == 1


def test_sd_06_the_journal_says_which_fault_and_that_the_options_re_ran():
    _history()
    c = _draft_case()
    r = call(ACTION, {"case_id": c["id"], "line": 1, "fault_code": "MOT"}, "engineer")
    assert r["ok"] is True, r
    assert r["output"]["log"] == "Fault posted for CRH-46042: MOT; options re-run"


def test_sd_06_unknown_code_and_unknown_line_are_refused():
    _history()
    c = _draft_case()
    r = call(ACTION, {"case_id": c["id"], "line": 1, "fault_code": "XYZ"}, "engineer")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    r = call(ACTION, {"case_id": c["id"], "line": 9, "fault_code": "MOT"}, "engineer")
    assert r["ok"] is False and r["error"]["code"] in ("validation_error", "not_found")
    assert _case(c["id"])["serviceDesk"]["lines"][0]["fault_code"] is None


def test_sd_06_the_same_fault_twice_is_a_conflict():
    _history()
    c = _draft_case()
    assert call(ACTION, {"case_id": c["id"], "line": 1, "fault_code": "MOT"}, "engineer")["ok"] is True
    r = call(ACTION, {"case_id": c["id"], "line": 1, "fault_code": "MOT"}, "engineer")
    assert r["ok"] is False and r["error"]["code"] == "conflict" and r["error"]["message"] == "This fault is already posted."


def test_post_fault_needs_assess():
    _history()
    c = _draft_case()
    r = call(ACTION, {"case_id": c["id"], "line": 1, "fault_code": "MOT"}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope", r  # the pipeline's refusal of a role without `assess`
    assert _case(c["id"])["serviceDesk"]["lines"][0]["fault_code"] is None


def test_post_fault_agent_is_held():
    from tests.helpers import client, h

    _history()
    c = _draft_case()
    assert held_for_person(ACTION) and not forbidden(ACTION) and not ACTION.startswith(FORBIDDEN_ACTIONS)
    hdr = h("engineer") | {"X-Circularity-Preparer": "coordinator"}
    r = client.post(f"/api/actions/{ACTION}", json={"case_id": c["id"], "line": 1, "fault_code": "MOT"}, headers=hdr).json()
    assert r["ok"] is True and "held" in r["output"], r
    assert _case(c["id"])["serviceDesk"]["lines"][0]["fault_code"] is None
