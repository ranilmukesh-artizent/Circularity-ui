"""Plan 9 phase 5 review findings (M1 to M7; H1 is in test_cr_window.py): contract refresh, the cases that follow the review.

M1 an approved refresh case leaves the like-life match, and a unit it holds is offered to no other case; M2 held units are freed
when the decision goes back, when the parts system refuses the reserve and when the renewal lapses (consumed when it renews);
M3 an on-time submit closes the `refresh_late` item; M4 and M5 the routed role is checked on the chosen route's own credits (a
Planner cannot approve what GR-C1 routes to Sales, also by an override to `upgrade_all`); M6 the renewal outcome lands on the term
it belongs to; M7 a gate that blocks after the case opened keeps the holds and the approval says why. Computed facts only (R16:
no model step). Every test starts and ends with the demo reset.
"""

from datetime import date

import pytest
from sqlalchemy import text

from di.connectors.http import SourceError
from di.core import policy
from di.core.db import SessionLocal
from di.repositories import unit_reservations
from di.services import refresh_decision, refresh_outcome
from di.services.canonical import store as canonical
from di.services.cases import refresh_intake, tool_queue
from di.services.modeler.valuers import tool_approval
from tests import refreshkit, starting
from tests.helpers import call
from tests.test_cr_execution import (  # noqa: F401 - the fixtures and helpers of the execution tests
    UNITS,
    _approve,
    _case,
    _drive,
    _held,
    _submit,
    sending,
    world,
)
from tests.test_cr_tool_action import ORG, refresh_case  # noqa: F401


def _hold_units(cid: str) -> list[str]:
    """What the unit-reserve writer does for the approved plan: hold the units of the sent proposal."""
    units = ((_case(cid)["exec"] or {}).get("proposal") or {}).get("units") or []
    with SessionLocal() as s:
        for u in units:
            unit_reservations.hold(s, u["unit_id"], cid, u["need_id"], "approver", ORG)
        s.commit()
    return [u["unit_id"] for u in units]


# ------------------------------------------------------------------ M1
def test_cr_03_an_approved_case_leaves_the_match_and_its_units_are_no_ones_else(monkeypatch):
    try:
        by = refreshkit.world(monkeypatch)
        a = by["FC-30117"]
        assert call("decision.submit", {"case_id": a}, "admin")["ok"]
        assert _approve(a)["ok"]
        mine = _hold_units(a)
        assert mine
        with SessionLocal() as s:
            m = tool_queue.refresh_match(s, refreshkit.ORG)
            shown = tool_queue.case_match(s, _case(a))
        assert a not in m  # it no longer takes units from the cases that still wait
        assert not ({r["unit_id"] for rows in m.values() for r in rows} & set(mine))
        assert [r["unit_id"] for r in shown] == mine  # its panel shows the units it holds
    finally:
        refreshkit.forget()  # the held units reference the org unit the reset removes
        starting.reset()


# ------------------------------------------------------------------ M2
def test_cr_03_a_decision_sent_back_frees_its_units(world):  # noqa: F811
    cid, _ = world
    _submit(cid)
    assert _approve(cid)["ok"]
    assert _hold_units(cid) and _held(cid)
    with SessionLocal() as s:
        refresh_decision.send_back(s, cid, "A unit was taken meanwhile.")
        s.commit()
    assert _held(cid) == []


def test_cr_03_a_refused_reserve_frees_its_units(world):  # noqa: F811
    cid, mock = world
    _submit(cid)
    assert _approve(cid)["ok"]

    def refuse(method, path, json=None, **_):
        if method == "PATCH":
            raise SourceError("client", "the parts system refused the reservation", status=409)
        return type("R", (), {"json": staticmethod(lambda: dict(json or {}))})()

    mock.request = refuse  # the proposal and the lines go out; the PATCH of the unit is refused
    from di.services.instructions import writers

    with pytest.raises(writers.Refused):
        _drive(cid)
    assert _held(cid) == []


def _status(status: str, end: str | None = None) -> None:
    facts = [canonical.Fact("contract", "FC-30140", "renewal_status", status, resource="contracts")]
    if end:
        facts.append(canonical.Fact("contract", "FC-30140", "end_date", end, resource="contracts"))
    with SessionLocal() as s:
        canonical.apply(s, "fleet", facts)
        s.commit()


def _record() -> list[str]:
    with SessionLocal() as s:
        out = refresh_outcome.record(s)
        s.commit()
    return out


def test_cr_07_a_lapse_frees_the_units_and_a_renewal_consumes_them(world):  # noqa: F811
    cid, _ = world
    _submit(cid)
    assert _approve(cid)["ok"]
    assert _hold_units(cid)
    _status("lapsed")
    assert _record() == [cid] and _held(cid) == []
    with SessionLocal() as s:
        assert s.execute(text("SELECT status FROM unit_reservation WHERE case_id = :c"), {"c": cid}).scalar() == "released"


def test_cr_07_a_renewal_consumes_the_units(world):  # noqa: F811
    cid, _ = world
    _submit(cid)
    assert _approve(cid)["ok"]
    assert _hold_units(cid)
    _status("renewed")
    assert _record() == [cid] and _held(cid) == []
    with SessionLocal() as s:
        assert s.execute(text("SELECT status FROM unit_reservation WHERE case_id = :c"), {"c": cid}).scalar() == "consumed"


# ------------------------------------------------------------------ M3
def _late_items(cid: str) -> list[str]:
    with SessionLocal() as s:
        rows = s.execute(text("SELECT status FROM work_item WHERE case_id = :c AND type = 'refresh_late'"), {"c": cid}).scalars()
        return sorted(rows)


def test_cr_01_an_on_time_submit_closes_the_late_item(world):  # noqa: F811
    cid, _ = world
    assert _late_items(cid) == ["open"]
    _submit(cid)
    assert _late_items(cid) == ["done"]  # nothing is left for the timer to escalate


# ------------------------------------------------------------------ M4 and M5
def _planner_may_approve(monkeypatch) -> None:
    """A Planner whose limit Admin raised can approve decisions; tenant scope is not what these tests are about."""
    assert call("access.setLimit", {"role": "Planner", "amount": 1000000}, "admin")["ok"]
    ok = policy.tenant_ok
    monkeypatch.setattr(policy, "tenant_ok", lambda a, tenant, ctx=None: True if tenant == ORG else ok(a, tenant, ctx))


def _credit_limit(monkeypatch, usd: float) -> None:
    real = tool_approval._param
    monkeypatch.setattr(tool_approval, "_param", lambda pack, g: usd if g == tool_approval.CREDIT_GUARD else real(pack, g))


def test_cr_04_credits_over_the_limit_wait_for_an_approver_not_a_planner(world, monkeypatch):  # noqa: F811
    cid, _ = world
    _credit_limit(monkeypatch, -1.0)  # every proposal is over the limit: GR-C1 routes it to Sales
    _planner_may_approve(monkeypatch)
    c = _submit(cid)
    assert c["approvalRoute"]["role"] == "Sales"
    r = _approve(cid, "proposal", "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope" and "Sales" in r["error"]["message"], r
    assert _case(cid)["stage"] == "awaiting_approval"
    assert _approve(cid, "proposal", "approver")["ok"]  # the routed role may


def test_cr_04_an_override_to_upgrade_all_is_routed_on_its_own_credits(world, monkeypatch):  # noqa: F811
    cid, _ = world
    c = _submit(cid)
    docs = c["refreshProposal"]
    up, own = docs["upgrade_all"]["credit_total"], docs["proposal"]["credit_total"]
    assert docs["upgrade_all"]["currency"] == "USD" and up > own  # upgrading every tool credits every old tool
    _credit_limit(monkeypatch, (up + own) / 2)  # the proposal is under the limit, upgrade_all is over it
    _planner_may_approve(monkeypatch)
    assert c["approvalRoute"]["role"] == "Fleet desk"
    r = _approve(cid, "upgrade_all", "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope" and "Sales" in r["error"]["message"], r
    assert _approve(cid, "upgrade_all", "approver")["ok"]


# ------------------------------------------------------------------ M7
def test_cr_09_a_gate_that_blocks_after_the_case_opened_keeps_the_holds(world):  # noqa: F811
    cid, _ = world
    _submit(cid)  # priced and held for a person; then declined back and valued again, as a person sends it back
    for action, data in (("decision.decline", {"reason": "Check again."}), ("case.reevaluate", {})):
        assert call(action, {"case_id": cid, **data}, "admin")["ok"]
    before = _case(cid)
    assert before["approvalHolds"] and before["routes"] and before["stage"] == "awaiting_approval"
    with SessionLocal() as s:  # a damage charge appears on a line between open and submit (GR-07)
        f = {"damage_charge_open": True, "charge_ref": "DC-5801"}
        facts = [canonical.Fact("contract_line", "FC-30140-S00", k, v, resource="lines") for k, v in f.items()]
        canonical.apply(s, "fleet", facts)
        s.commit()
    c = _submit(cid)
    assert "G-CON-2" in c["refreshBlock"]["gate"] + c["refreshBlock"]["reason"]
    assert c["approvalHolds"] == before["approvalHolds"]  # the standing policy cannot cover it
    r = _approve(cid)
    assert r["ok"] is False and r["error"]["code"] == "conflict" and "DC-5801" in r["error"]["message"], r
    assert "refreshProposal" not in c  # nothing priced is left to send


# ------------------------------------------------------------------ M6
def test_cr_07_the_next_terms_case_does_not_take_the_status_of_the_last(refresh_case):  # noqa: F811
    _status("renewed")
    assert _record() == [refresh_case]
    _status("renewed", "2028-01-05")  # the contract runs to the next term and the source still says renewed
    with SessionLocal() as s:
        (nxt,) = refresh_intake.scan(s, ORG, date(2027, 10, 7))
        s.commit()
    assert _record() == []  # a status the last term already carried is not the next term's
    assert "renewalOutcome" not in _case(nxt)
    _status("renewed", "2029-01-05")  # the next term was renewed too
    assert _record() == [nxt]
