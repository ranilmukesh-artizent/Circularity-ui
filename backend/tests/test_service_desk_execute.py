"""Plan 9, P9-4.9 (story SD-05): the approved option runs on market terms through the one execution plan.

An approved fix, covered swap, upgrade or batch split becomes the existing execution plan (`steps_for`, `instructions.queue`):
the route carries its step kinds and the lines each covers, the instructions go out in order, every one carries the market terms
(`detail.terms`: market, the table versions, `valid_until` = approval date + 14 days), a swap reserves its refurbished unit at
approval, and the acknowledgement of `takeback` opens the old tool's Returns case (once) and lets the credit go. A split has one
sale order for its upgrade lines, one service reference for its fix lines and one delivery to the site.

No model step (R16): no model tests. No new action, so nothing joins FORBIDDEN_ACTIONS; a person (or the standing policy)
approves,
and the test asserts that agents still cannot. The writers are driven with a fake client (no source-sim call).

It starts and ends with the demo reset.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from di.core import clock
from di.core.config import get_settings
from di.core.db import SessionLocal
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.agents.forbidden import forbidden
from di.services.cases import store
from di.services.execution.steps import STEP_TPL
from di.services.instructions import queue, writers
from di.services.modeler.valuers.service_desk import OPTION_KINDS
from di.services.service_desk import follow_through
from tests.helpers import call
from tests.test_service_desk_batch import _open_batch
from tests.test_service_desk_options import _history, _line, _open, _stock, _ticket, fresh  # noqa: F401 - `fresh` is the fixture

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")


@pytest.fixture(autouse=True)
def sending(monkeypatch):
    """Instructions on for the test (the suite turns them off), so an approval queues its first step."""
    monkeypatch.setattr(get_settings(), "instructions", True)


def _approve(c: dict, route: str) -> dict:
    """A person approves the route (the recommendation, else an override) as the maker-checker pair the pipeline asks for."""
    assert call("decision.submit", {"case_id": c["id"]}, "admin")["ok"]
    rec = c["recommendation"]["id"]
    r = next(x for x in c["routes"] if x["id"] == route)
    body = {"case_id": c["id"], "reviewed": True, "rationale": "Service desk end to end.", "route": r["plan"]}
    out = call("decision.approve" if rec == route else "decision.override", body, "approver")
    assert out["ok"], out
    with SessionLocal() as s:
        return store.get(s, c["id"])


def _ack(case_id: str, n: int = 1) -> None:
    for _ in range(n):
        with SessionLocal() as s:
            r = invoke("adapter.acknowledge", {"case_id": case_id, "simulated": True}, CallContext(actor=SYSTEM, session=s))
            assert r["ok"], r
            s.commit()


def _rows(case_id: str) -> list[dict]:
    with SessionLocal() as s:
        return queue.for_case(s, case_id)


def _case(case_id: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, case_id)
    assert c is not None
    return c


def _kinds(c: dict) -> list[str]:
    return [s["k"] for s in c["exec"]["steps"]]


def _fix_case() -> dict:
    _history()
    _ticket("CS0010042", [_line(age=10, cover="none")])  # no cover, 28% of life: a fix is the only option
    return _open("CS0010042")


def _upgrade_case() -> dict:
    _history()
    _ticket("CS0010042", [_line("CRH-46077", age=33, cover="none")])  # 92% of life: an upgrade is offered
    return _open("CS0010042")


def test_sd_05_the_option_plans_are_the_valuers():
    assert {k: tuple(STEP_TPL[k]) for k in OPTION_KINDS} == OPTION_KINDS
    assert STEP_TPL["all_fix"] == STEP_TPL["fix"] and STEP_TPL["all_upgrade"] == STEP_TPL["upgrade"]


def test_sd_05_fix_creates_service_order(monkeypatch):
    c = _approve(_fix_case(), "fix")
    assert _kinds(c) == ["repair", "transport", "finance"]
    assert c["exec"]["steps"][1]["to"] == "Austin"  # the transport goes back to the site
    sent: list[dict] = []

    class Fake:
        def request(self, method, path, json=None, **_):
            sent.append(json)
            ok = {"OutputParameters": {"X_RETURN_STATUS": "S", "X_REPAIR_NUMBER": "WO-1", "X_REPAIR_LINE_ID": 1}}
            return SimpleNamespace(json=lambda: ok)

        def close(self):
            pass

    monkeypatch.setattr(writers, "client", lambda *_: Fake())
    rows = _rows(c["id"])
    assert [r["kind"] for r in rows] == ["repair"]  # the first step goes out; the rest wait for its acknowledgement
    with SessionLocal() as s:
        writers.repair(s, rows[0], c, {})
    rec = sent[0]["CREATE_REPAIR_ORDER_Input"]["InputParameters"]["P_REPLN_REC"]
    assert rec["REPAIR_TYPE"] == "Repair and Return" and rec["ORIGINAL_SOURCE_REFERENCE"] == c["id"]
    assert rec["SERIAL_NUMBER"] == "CRH-46042"


def test_sd_05_upgrade_sale_and_takeback():
    c = _approve(_upgrade_case(), "upgrade")
    assert _kinds(c) == ["sale", "transport", "takeback", "credit", "finance"]
    _ack(c["id"], 2)  # the sale and the transport are acknowledged: the takeback is queued, the credit is not
    assert [r["kind"] for r in _rows(c["id"])] == ["sale", "transport", "takeback"]


def test_sd_05_credit_released_on_receipt():
    c = _approve(_upgrade_case(), "upgrade")
    _ack(c["id"], 3)  # sale, transport, takeback
    assert [r["kind"] for r in _rows(c["id"])][-1] == "credit"  # the takeback's acknowledgement lets the credit send
    with SessionLocal() as s:
        log = (
            s.execute(text("SELECT reason FROM case_stage_log WHERE case_id = :c AND reason LIKE 'Taken-back%'"), {"c": c["id"]})
            .scalars()
            .all()
        )
    assert (
        len(log) == 1 and log[0].startswith("Taken-back CRH-46077 opened RT-") and log[0].endswith(" in Returns; credit released")
    )


def _returns(serial: str) -> list[dict]:
    with SessionLocal() as s:
        ids = (
            s.execute(text("SELECT id FROM case_record WHERE data->'intake'->>'key' = :k"), {"k": f"{serial}:trade_in"})
            .scalars()
            .all()
        )
        return [store.get(s, i) for i in ids]  # type: ignore[misc]


def test_sd_05_takeback_opens_returns_case():
    c = _approve(_upgrade_case(), "upgrade")
    _ack(c["id"], 3)
    got = _returns("CRH-46077")
    assert len(got) == 1 and got[0]["source_case"] == c["id"] and got[0]["template"] == "tool_fleet"
    with SessionLocal() as s:  # the acknowledgement again (a redelivered event): no second case
        assert follow_through.on_takeback(s, _case(c["id"]), 2) == []
        s.commit()
    assert len(_returns("CRH-46077")) == 1


def test_sd_05_terms_on_every_instruction():
    c = _approve(_upgrade_case(), "upgrade")
    _ack(c["id"], 4)  # every step but the last has been queued and acknowledged; the last is queued
    rows = _rows(c["id"])
    assert [r["kind"] for r in rows] == _kinds(c)
    valid = (clock.now().date() + timedelta(days=14)).isoformat()
    for r in rows:
        t = r["detail"]["terms"]
        assert t["market"] == "US" and t["valid_until"] == valid and len(t["refs"]) == 3
        assert [any(w in ref for ref in t["refs"]) for w in ("parts prices", "labour rates", "credit rules")] == [True] * 3
    assert c["exec"]["terms"]["valid_until"] == valid


def test_sd_05_a_swap_reserves_its_unit_at_approval():
    _history()
    _stock(1)
    _ticket("CS0010042", [_line()])  # fleet cover, 50% of life, a refurbished unit on the shelf
    c = _approve(_open("CS0010042"), "swap")
    assert _kinds(c) == ["reserve", "transport", "takeback", "finance"]
    unit = c["serviceDesk"]["lines"][0]["reserved_unit"]
    with SessionLocal() as s:
        assert s.execute(text("SELECT reserved_case FROM refurb_unit WHERE serial = :u"), {"u": unit}).scalar() == c["id"]


def test_sd_07_one_set_of_orders():
    """A split is one plan: one sale order for its upgrade lines, one service reference for its fix lines, one delivery to the
    site, one takeback for the lines whose old tool comes back."""
    c = _open_batch()
    c = _approve(c, "split")
    lines = c["serviceDesk"]["lines"]
    assert len(set(_kinds(c))) == len(_kinds(c))  # every kind once
    by = {s["k"]: s for s in c["exec"]["steps"]}
    for kind, step in by.items():
        want = [ln["n"] for ln in lines if kind in OPTION_KINDS.get(ln["best"], ())]
        assert step["lines"] == want and want, kind
    assert by["transport"]["to"] == "Denver"


def test_sd_05_agents_cannot_approve_what_the_plan_executes():
    assert forbidden("decision.approve") and forbidden("decision.override")
