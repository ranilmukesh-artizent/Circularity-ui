"""Plan 9, P9-5.6 (story CR-06): test the proposal's levers before publishing a new threshold.

`refresh.whatIf` runs a contract refresh again on a copy of the market's `refresh_tool_action` table with the swap threshold
(10 to 50% of life left) and the upgrade row moved, through the same pricing the decision is made of
(`refresh_decision.quote`, never a second decider, R19). It is a read: nothing is stored, journaled, sent or reserved.
No model step (R16): the tool choice, fee and renewal figures are all computed, and the note is a template over them (R8:
what it was before and what it would be). A new threshold goes live only through the table's maker-checker (P9-4.2).
R21: the case's tenant boundary holds, a person or an agent may read it, and it joins no forbidden list (it approves nothing).

It starts and ends with the demo reset.
"""

import json
from datetime import date

import pytest
from sqlalchemy import text

from di.core import policy
from di.core.db import SessionLocal, engine
from di.repositories import unit_reservations
from di.services.actions.registry import ACTIONS
from di.services.agents import catalog
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.cases import refresh_intake, store, tool_queue
from di.services.instructions import writers
from tests import starting
from tests.helpers import call, client, h

ORG = "tool-fleet-a"
CID = "FC-30117"
ACTION = "refresh.whatIf"
pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
MONTHS = {"CMH-A1": 5, "CMH-A2": 14, "CMH-A3": 22, "CMH-A4": 28, "CMH-A5": 33, "CMH-A6": 41}  # a spread of remaining life
EOP = (date(2027, 3, 31), "TF-CRH2")  # parts of the CRH end before the next term does: upgrade


def _facts() -> list[canonical.Fact]:
    c = {"contract_id": CID, "customer": "Brightline Mechanical", "market": "US", "start_date": "2024-01-05",
         "end_date": "2027-01-05", "term_months": 36, "status": "active"}  # fmt: skip
    out = [canonical.Fact("contract", CID, k, v, resource="contracts") for k, v in c.items()]
    lines = [(s, "CMH", m) for s, m in MONTHS.items()] + [("CRH-A1", "CRH", 30)]
    for serial, cls, months in lines:
        f = {"contract_id": CID, "serial": serial, "tool_class": cls, "model": f"{cls}-12 Pro", "fee_month": 55.0,
             "months_on_contract": months, "status": "on_contract", "line_id": "FL-" + serial}  # fmt: skip
        out += [canonical.Fact("contract_line", serial, k, v, resource="lines") for k, v in f.items()]
    return out


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('contract', 'contract_line')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract', 'contract_line')"))
        conn.execute(text("DELETE FROM job WHERE kind IN ('refresh.scan', 'work.sla', 'case.replan')"))
        conn.execute(text("DELETE FROM case_record WHERE owner = :o"), {"o": ORG})
        conn.execute(text("DELETE FROM work_item WHERE org_unit_id = :o"), {"o": ORG})
        conn.execute(text("DELETE FROM unit_reservation WHERE org_unit_id = :o"), {"o": ORG})


@pytest.fixture
def refresh_case(monkeypatch):
    starting.reset()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    _forget()
    monkeypatch.setattr(
        unit_reservations, "stock", lambda s: [{"id": f"RU-{i}", "cls": "CMH", "rul": 50 + i, "grade": "A"} for i in range(8)]
    )
    real = tool_queue.plm.end_of_parts
    monkeypatch.setattr(tool_queue.plm, "end_of_parts", lambda s, o, k: EOP if k == "CRH" else real(s, o, k))
    with SessionLocal() as s:
        canonical.apply(s, "fleet", _facts())
        s.commit()
    with SessionLocal() as s:
        ids = refresh_intake.scan(s, ORG, date(2026, 10, 7))
        s.commit()
    assert len(ids) == 1
    yield ids[0]
    _forget()
    starting.reset()


def _panel(cid: str) -> dict:
    return client.get(f"/api/screens/refresh/{cid}", headers=h("admin")).json()


def _what(cid: str, user: str = "admin", **levers) -> dict:
    r = call(ACTION, {"case_id": cid, **levers}, user)
    assert r["ok"] is True, r
    return r["output"]


def test_cr_06_threshold_lever_changes_tools(refresh_case):
    base = {t["serial"]: t for t in _panel(refresh_case)["tools"]}
    moving = sorted(s for s, t in base.items() if t["action"] == "keep" and 25 <= t["rul_pct"] < 40)
    assert moving, base  # the fixture has tools between 25% and 40%
    out = _what(refresh_case, swap_threshold=40)
    assert sorted((c["serial"], c["from"], c["to"]) for c in out["changed"]) == [(s, "keep", "swap") for s in moving]
    assert out["split"]["swap"] == out["before"]["swap"] + len(moving)
    assert out["split"]["keep"] == out["before"]["keep"] - len(moving)
    assert isinstance(out["fee_delta"], float) and out["fee_delta"] != 0  # a swap moves to the refurbished-unit fee
    assert isinstance(out["renewal_delta"], float) and isinstance(out["flips_route"], bool) and out["credit_total"] >= 0
    assert "Before" in out["note"] and f"{len(moving)} tool" in out["note"]  # R8: what it was and what it would be
    assert _what(refresh_case, swap_threshold=25)["changed"] == []  # the table's own value changes nothing


def test_cr_06_upgrades_off(refresh_case):
    base = {t["serial"]: t for t in _panel(refresh_case)["tools"]}
    up = sorted(s for s, t in base.items() if t["action"] == "upgrade")
    assert up == ["CRH-A1"], base
    out = _what(refresh_case, upgrades=False)
    assert out["split"]["upgrade"] == 0 and out["before"]["upgrade"] == 1
    (row,) = [c for c in out["changed"] if c["serial"] == "CRH-A1"]
    assert row["from"] == "upgrade" and row["to"] == ("swap" if base["CRH-A1"]["rul_pct"] < 25 else "keep")
    assert out["credit_total"] == 0  # no upgrade, no credit


def _state(cid: str) -> dict:
    with SessionLocal() as s:
        q = lambda sql: s.execute(text(sql)).scalar()  # noqa: E731
        return {
            "case": json.dumps(store.get(s, cid), sort_keys=True, default=str),
            "journal": q("SELECT count(*) FROM action_journal"),
            "reservations": q("SELECT count(*) FROM unit_reservation"),
            "jobs": q("SELECT count(*) FROM job"),
            "instructions": q("SELECT count(*) FROM instruction"),
            "tables": q("SELECT count(*) FROM market_table"),
        }


def test_cr_06_nothing_sent_or_stored(refresh_case, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("a what-if must not call a source")

    monkeypatch.setattr(writers, "client", boom)  # the fleet mock: any write or read through a writer fails
    before = _state(refresh_case)
    for kw in ({"swap_threshold": 40}, {"upgrades": False}, {"swap_threshold": 10, "upgrades": False}, {}):
        _what(refresh_case, **kw)
    assert _state(refresh_case) == before


def test_cr_06_out_of_range_and_unknown_refused(refresh_case):
    for kw in ({"swap_threshold": 9}, {"swap_threshold": 51}, {"swap_threshold": 25.5}, {"upgrades": "no"}):
        r = call(ACTION, {"case_id": refresh_case, **kw}, "admin")
        assert r["ok"] is False and r["error"]["code"] == "validation_error", (kw, r)
    r = call(ACTION, {"case_id": "RT-1048", "swap_threshold": 40}, "admin")  # a case that is not a contract refresh
    assert r["ok"] is False and r["error"]["code"] == "not_found", r
    assert call(ACTION, {"case_id": "NOPE-1"}, "admin")["error"]["code"] == "not_found"


def test_cr_06_security_read_only_tenant_boundary_agent(refresh_case, monkeypatch):
    a = ACTIONS[ACTION]
    assert a.risk == "read" and not forbidden(ACTION) and catalog.agent_allowed(a)  # a read: an agent may prepare it
    agent = {"id": "ext-whatif", "name": "What-if helper", "tools": [ACTION], "autonomy": "act"}
    assert call("agent.register", agent, "admin")["ok"]
    hdr = h("admin") | {"X-Circularity-Preparer": agent["id"], "X-Circularity-Confirmed": "true"}
    r = client.post(f"/api/actions/{ACTION}", json={"case_id": refresh_case, "swap_threshold": 40}, headers=hdr).json()
    assert r["ok"] is True, r
    ok = policy.tenant_ok
    monkeypatch.setattr(policy, "tenant_ok", lambda acct, tenant, ctx=None: tenant != ORG and ok(acct, tenant, ctx))
    r = call(ACTION, {"case_id": refresh_case, "swap_threshold": 40}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", r
