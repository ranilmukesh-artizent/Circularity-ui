"""Plan 9, P9-4.10 (story SD-09): test a credit before offering it.

`serviceDesk.whatIf` runs the options of a ticket again on a copy with the credit, take-up, repair cost or wait moved,
and gives the expected margin over credits 0 to 40%. It is a read: nothing is stored, journaled or sent.
No model step (R16): every number is computed (`p x margin_up + (1 - p) x margin_fix`), so there is no `AgentLoop`
and no model tests. The action approves and releases nothing, so nothing joins FORBIDDEN_ACTIONS; offering a credit
over GR-C1 stays held for a person (P9-4.6 holds).

It starts and ends with the demo reset.
"""

import json
import math
from datetime import date, timedelta
from itertools import pairwise

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import service_tickets
from di.services.agents.forbidden import forbidden
from di.services.cases import store
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers.service_desk import UPGRADE_LIFE
from di.services.service_desk import intake as sd
from tests import starting
from tests.helpers import call, tool_case_facts

ORG = "tool-fleet-a"
ACTION = "serviceDesk.whatIf"
pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
PRIOR = load_pack("tool_fleet").valuer.params["service_desk"]["options"]["take_up_prior"]


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


def _case(cls: str = "CRH", age: int = 18) -> dict:
    """An uncovered tool past 50% of life (a CRH of 18 months) whose repair is estimated at $600."""
    line = {
        "serial": "CRH-46042", "model_class": cls, "age_months": age, "fault_code": "MOT", "fault_text": "Runs hot",
        "cover_type": "none", "cover_until": None,
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
    tool_case_facts("CRH-46042", {"cls": cls})
    with SessionLocal() as s:
        row = next(t for t in service_tickets.pending(s, ORG) if t.number == "CS0010042")
        c = sd.open_from_ticket(s, row, "system")
        ln = c["serviceDesk"]["lines"][0]
        assert ln["life_used_pct"] >= UPGRADE_LIFE
        ln["estimate"] |= {"point": 600.0, "p10": 550.0, "p90": 650.0, "n": 60}
        store.save(s, c)
        s.commit()
        return store.get(s, c["id"])


def _what(c: dict, **kw) -> dict:
    r = call(ACTION, {"case_id": c["id"], **kw}, "engineer")
    assert r["ok"] is True, r
    return r["output"]["lines"][0]


def _p(pct: float) -> float:
    return 1 / (1 + math.exp(-(PRIOR["a"] + PRIOR["b"] * pct)))


def test_sd_09_credit_lever_shows_margin_and_flip():
    _history()
    c = _case()
    low, high = _what(c, credit_pct=0.05), _what(c, credit_pct=0.35)
    assert low["best"] == "upgrade"
    assert high["best"] == "fix" and high["flips"] is True and high["from"] == "upgrade" and high["to"] == "fix"
    fix = next(o for o in high["options"] if o["k"] == "fix")["expected_margin"]
    curve = high["curve"]
    assert [p["credit_pct"] for p in curve] == [round(i * 0.05, 2) for i in range(9)]
    for p in curve:  # every point is p x margin_up + (1 - p) x margin_fix, the take-up rising with the credit
        assert p["take_up"] == pytest.approx(_p(p["credit_pct"]), abs=1e-9)
        assert p["upgrade"] == pytest.approx(p["take_up"] * p["upgrade_margin"] + (1 - p["take_up"]) * fix, abs=0.02)
    assert all(a["upgrade_margin"] > b["upgrade_margin"] for a, b in pairwise(curve))  # falls with credit
    assert all(a["take_up"] < b["take_up"] for a, b in pairwise(curve))
    x = high["crossing"]
    assert (
        x["from"] == "upgrade"
        and x["to"] == "fix"
        and 0 < x["credit_pct"] < 0.35
        and x["next_pct"] == round(x["credit_pct"] + 0.01, 2)
    )
    slope = (curve[2]["upgrade_margin"] - curve[1]["upgrade_margin"]) / 0.05  # margin_up is linear in the credit

    def up(pct: float) -> float:
        m = curve[1]["upgrade_margin"] + slope * (pct - 0.05)
        return _p(pct) * m + (1 - _p(pct)) * fix

    assert up(x["credit_pct"]) >= fix > up(x["next_pct"])
    assert high["peak"]["upgrade"] == max(p["upgrade"] for p in curve)


def test_sd_09_credit_over_gr_c1_is_still_shown():
    _history()
    c = _case("DCD", 120)  # a $2,944 tool: 15% is $441, over the $300 of GR-C1
    r = call(ACTION, {"case_id": c["id"], "credit_pct": 0.15}, "engineer")["output"]
    assert r["gr_c1"] and r["gr_c1"][0]["id"] == "GR-C1", r
    assert call(ACTION, {"case_id": c["id"], "credit_pct": 0.05}, "engineer")["output"]["gr_c1"] == []  # $147


def test_sd_09_the_other_levers_move_the_numbers():
    _history()
    c = _case()
    base = _what(c, credit_pct=0.10)
    dear = _what(c, credit_pct=0.10, repair_cost_pct=150)
    cost = {x: next(o for o in r["options"] if o["k"] == "fix")["cost"] for x, r in (("dear", dear), ("base", base))}
    assert cost["dear"] == pytest.approx(
        cost["base"] * 1.5, abs=0.02
    )  # the repair is billed at cost plus markup, so only the cost moves
    sure = _what(c, credit_pct=0.10, take_up=1)
    assert next(o for o in sure["options"] if o["k"] == "upgrade")["take_up"] == pytest.approx(1, abs=1e-6)
    wait = _what(c, credit_pct=0.10, wait_days=10)
    assert (
        next(o for o in wait["options"] if o["k"] == "fix")["days"]
        == (next(o for o in base["options"] if o["k"] == "fix")["days"] or 0) + 10
    )


def _counts(case_id: str) -> tuple[int, int, str]:
    with engine.connect() as conn:
        j = conn.execute(text("SELECT count(*) FROM action_journal")).scalar()
        i = conn.execute(text("SELECT count(*) FROM instruction")).scalar()
    with SessionLocal() as s:
        return j, i, json.dumps(store.get(s, case_id), sort_keys=True, default=str)


def test_sd_09_nothing_sent():
    _history()
    c = _case()
    before = _counts(c["id"])
    for k in range(10):
        _what(c, credit_pct=round(0.04 * k, 2), take_up=0.5)
    assert _counts(c["id"]) == before
    assert not forbidden(ACTION)


def test_sd_09_out_of_range_refused():
    _history()
    c = _case()
    for kw in ({"repair_cost_pct": 200}, {"credit_pct": 0.5}, {"take_up": 1.5}, {"wait_days": -1}):
        r = call(ACTION, {"case_id": c["id"], **kw}, "engineer")
        assert r["ok"] is False and r["error"]["code"] == "validation_error", (kw, r)
    r = call(ACTION, {"case_id": c["id"], "line": 9}, "engineer")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
