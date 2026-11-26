"""P9-1.4: the queue planner port (registry I-5) with named demand on live tool-fleet cases.

    QueuePlanner.plan(cases, demand, capacity) -> Plan     HeuristicPlanner wraps tool_fleet.plan_queue (parity)
    named_demand.for_queue(s, org, classes)                canonical `demand` records as the valuer's orders
    replan.on_opened(s, org)                               the org's other open cases valued again (job case.replan)

An order is filled once (Review Focus 8): two open returns that both want it are planned together, one holds it and
the other says why it lost. Every test ends with the starting state.
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.canonical import store as canonical
from di.services.canonical.store import Fact
from di.services.cases import named_demand, replan, store
from di.services.engine.queue import Capacity, HeuristicPlanner, planner_for
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import tool_fleet
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORDER = {"kind": "lease", "id": "L-1", "renew": True, "who": "Acme Rentals", "site": "Houston", "need": 9, "rate": 900,
         "term": 24, "what": "Fleet contract L-1 renews", "when": "renewal confirmed"}  # fmt: skip
NAMED = {
    "SO-T1": {"kind": "so", "cls": "CRH", "who": "Delta Builders", "site": "Atlanta", "need_days": 20, "price": 8000,
              "what": "Sales order SO-T1", "when": "order booked 30 Oct"},
    "PR-T1": {"kind": "proj", "cls": "CRH", "who": "Atlanta tool pool", "site": "Atlanta", "need_days": 9, "rental": 700,
              "what": "Pool request PR-T1", "when": "raised 29 Oct"},
}  # fmt: skip


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    yield
    starting.reset()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM canonical WHERE model = 'demand' AND key IN ('SO-T1', 'PR-T1')"))
        s.execute(text("DELETE FROM provenance WHERE model = 'demand' AND key IN ('SO-T1', 'PR-T1')"))
        s.commit()


def _open(asset: str, grade: str, org: str = "Customer A", user: str = "planner-a", cls: str = "CMH") -> str:
    facts = {"cls": cls, "grade": grade, "ft": "Repair center", "site": "Houston", "rul": 62, "dem": {"lease": [ORDER]}}
    body = {
        "org_unit_id": org,
        "template_key": "tool_fleet",
        "asset_key": asset,
        "reason": "manual",
        "facts": tool_case_facts(asset, facts),
    }
    r = call("case.open", body, user)
    assert r["ok"], r
    return r["output"]["case_id"]


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _dest(cid: str) -> str | None:
    return ((_case(cid)["recommendation"] or {}).get("dest") or {}).get("id")


def _replan(org: str = "Customer A") -> None:
    with SessionLocal() as s:
        replan.on_opened(s, org)
        s.commit()


def _plan(cid: str) -> dict:
    with SessionLocal() as s:
        return replan.queue_plan(s, _case(cid))


def test_heuristic_planner_equals_plan_queue():
    cases = tool_fleet.sample_live_cases()
    cap = Capacity(slots=int(tool_fleet.BASEP["slots"]))
    assert HeuristicPlanner().plan(cases, {}, cap) == tool_fleet.plan_queue(tool_fleet.BASEP, [], queue=cases)
    live = tool_fleet.LIVE_RULES
    assert HeuristicPlanner().plan(cases, {}, cap, rules=live) == tool_fleet.plan_queue(rules=live, queue=cases)


def test_unknown_planner_refused():
    pack = load_pack("tool_fleet")
    assert isinstance(planner_for(pack), HeuristicPlanner)
    odd = pack.model_copy(update={"valuer": pack.valuer.model_copy(update={"params": {**pack.valuer.params, "planner": "milp"}})})
    with pytest.raises(ValueError, match="No queue planner milp"):
        planner_for(odd)


def test_named_demand_from_canonical():
    rows = [
        Fact("demand", k, f, v)
        for k, d in NAMED.items()
        for f, v in (d | {"org_unit": "Customer A", "pack": "tool_fleet"}).items()
    ]
    with SessionLocal() as s:
        canonical.apply(s, "manual", rows)
        s.commit()
        a = named_demand.for_queue(s, "Customer A", ["CRH", "CMH"])
        b = named_demand.for_queue(s, "Customer B", ["CRH"])
    assert [d["id"] for d in a["CRH"]["so"]] == ["SO-T1"] and a["CRH"]["so"][0]["price"] == 8000
    assert a["CRH"]["proj"]["id"] == "PR-T1" and a["CRH"]["proj"]["rental"] == 700
    assert a["CMH"]["so"] == [] and a["CMH"]["proj"] is None
    assert b.get("CRH", {}).get("so", []) == [] and b.get("CRH", {}).get("proj") is None


def test_tf_08_order_filled_once():
    first, second = _open("T-QP-1", "B"), _open("T-QP-2", "A")
    _replan()
    holders = [i for i in (first, second) if _dest(i) == "L-1"]
    assert len(holders) == 1, {i: _dest(i) for i in (first, second)}
    loser = next(i for i in (first, second) if i != holders[0])
    assert [(x["order"], x["to"]) for x in _plan(loser)["lost"]] == [("L-1", holders[0])]
    # the loser never holds L-1; on a synced stack it may hold another live order (a fleet renewal), on a fresh one none
    assert _plan(holders[0])["holds"] == "L-1" and _plan(loser)["holds"] != "L-1"
    page = client.get(f"/api/screens/case/{loser}", headers=h("planner-a")).json()
    assert page["plan"]["lost"][0]["order"] == "L-1"


def test_replan_on_arrival():
    first = _open("T-QP-3", "B")
    assert _dest(first) == "L-1"
    second = _open("T-QP-4", "A")
    _replan()
    assert _dest(second) == "L-1" and _dest(first) != "L-1"
    with SessionLocal() as s:
        rows = s.execute(text("SELECT reason, actor FROM case_stage_log WHERE case_id = :c ORDER BY id"), {"c": first}).all()
    assert any(r[0].startswith("Re-planned: ") and r[1] == "system" for r in rows), rows


def test_replan_keeps_approved_holder():
    first = _open("T-QP-5", "B")
    with SessionLocal() as s:
        c = store.get(s, first, for_update=True)
        assert c is not None
        c["stage"] = "approved"
        store.save(s, c)
        s.commit()
    second = _open("T-QP-6", "A")
    _replan()
    assert _dest(first) == "L-1" and _dest(second) != "L-1"


def test_tf_07_synced_renewal_filled_once():
    """A renewal synced from the fleet source is named demand for every open case of the class: it is filled once, and
    the case that does not hold it keeps its own order (P9-3.12)."""
    row = {"kind": "lease", "need_by": "2027-06-01", "lease_rate": 5000, "term_months": 24, "renew": True, "site": "Houston",
           "tool_class": "CMH", "buyer": "Brightline Mechanical", "contract_ref": "FC-QP"}  # fmt: skip
    with SessionLocal() as s:
        canonical.apply(s, "fleet", [Fact("demand", "FC-QP-R", k, v, resource="demand") for k, v in row.items()])
        s.commit()
    try:
        first, second = _open("T-QP-5", "B"), _open("T-QP-6", "A")
        _replan()
        dests = {i: _dest(i) for i in (first, second)}
        assert list(dests.values()).count("FC-QP-R") <= 1, dests
        assert [_plan(i)["holds"] for i in (first, second)].count("FC-QP-R") == 1, dests
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM canonical WHERE model = 'demand' AND key = 'FC-QP-R'"))
            s.execute(text("DELETE FROM provenance WHERE model = 'demand' AND key = 'FC-QP-R'"))
            s.commit()
