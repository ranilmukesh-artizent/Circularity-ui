"""Plan 9, P9-9.11 (stories UC-11 and UC-12): the best lot after holding costs, and a person approves recon over the limit.

A stored used car is valued on what the systems serve for it (`cases.car_facts`: the lease system's mileage and book value, the
inspection's recon, the dealer system's per-lot sales, the pricing guide, the auction platform's fees), so the case recommends the
channel with the best net after holding; a tie goes to the fewer days. A recon estimate over AP-UC-RECON ($2,500) holds the
decision for the used-car manager (role Approver): an approval item in My work (I-20) with the cause, the figures and the
action; the hold policy (I-10) holds an agent's submit with reason `value`. Approving and overriding are a person's
(`decision.approve` and `decision.override` are in forbidden.py); the standing policy (I-11) never approves a held decision.
Legal note: approval limits are the pack's data; Kinective's Legal team reviews the pack before it is relied on.
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.actions import standing_policy as sp
from di.services.agents import chain
from di.services.agents.forbidden import forbidden
from di.services.cases import decide
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import Pack, load_pack
from di.services.modeler.valuers.tool_fleet import PathValue
from tests import ucfixtures as uc
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

LIMIT = "Recon $2,800 over the $2,500 limit"
ACTION = "Approve and retail if retail gross after recon beats auction gross"


@pytest.fixture(autouse=True)
def fresh():
    uc.start()
    yield
    uc.finish()


def _route(c: dict, rid: str) -> dict:
    return next(r for r in c["routes"] if r["id"] == rid)


def test_uc_11_best_lot_after_holding():
    c = uc.open_car(1)
    rec = c["recommendation"]
    assert (rec["id"], rec["net"]) == ("retail:LOT-S", 21489.50)
    assert (_route(c, "retail:LOT-C")["net"], _route(c, "auction")["net"]) == (21028.00, 20612.00)
    assert rec["plan"] == "Retail lot · South lot" and c["stage"] == "awaiting_approval"
    assert c["evidenceLines"] == [
        "Comparable sales at South lot: 18, average 15 days",
        "Recon $1,200 against the $2,500 limit",
        "Auction $21,500 before fees",
    ]
    assert all(g["passed"] for g in c["gates"])  # the guardrail results: every gate passes for the clean car
    (check,) = c["approvalChecks"]
    assert (check["id"], check["passed"], check["reason"]) == ("AP-UC-RECON", True, "Recon $1,200 within the $2,500 limit")
    assert "approvalHolds" not in c and uc.items(c["id"]) == []  # under the limit: nothing waits for the manager


def test_uc_11_a_tie_goes_to_fewer_days():
    def pv(k: str, net: float, days: int | None) -> PathValue:
        return {"k": k, "ok": True, "net": net, "dest": {"days": days}} | {  # type: ignore[typeddict-item]
            "gross": net, "cost": 0.0, "hold": 0.0, "why": "", "lines": [], "misses": [], "co2": None, "co2Prov": None,
        }  # fmt: skip

    values = [
        pv("retail:LOT-C", 21000.0, 21),
        pv("retail:LOT-S", 21000.0, 15),
        pv("auction", 21000.0, 6),
        pv("dealer_trade", 21000.0, None),
    ]
    assert decide.best_of(values)["k"] == "auction"  # the fewest days; no days at all is not "fewer"
    assert decide.best_of(values[:2])["k"] == "retail:LOT-S"
    assert decide.best_of([pv("a", 1.0, 3), pv("b", 2.0, 30)])["k"] == "b"  # the net comes first
    assert decide.best_of([pv("x", 5.0, None), pv("y", 5.0, None)])["k"] == "x"  # all unknown: the listed order
    assert decide.best_of([]) is None


def test_uc_12_recon_over_limit_goes_to_manager():
    c = uc.open_car(7)
    assert c["stage"] == "awaiting_approval" and c["recommendation"] is not None  # a decision, held for a person
    (hold,) = c["approvalHolds"]
    assert (hold["id"], hold["reason"], hold["kind"], hold["owner"]) == ("AP-UC-RECON", LIMIT, "value", "used_car_manager")
    (item,) = uc.items(c["id"])
    assert (item["kind"], item["status"], item["owner_role"]) == ("step", "open", "Approver")  # shown as an approval below
    assert item["cause"].startswith(LIMIT + ". Retail gross after recon $21,500, auction gross $21,500. Recommended: ")
    assert item["action"] == ACTION and item["title"] == f"{c['id']}: {LIMIT}"
    assert hold["retail_after_recon"] == 21500.0 and hold["auction_gross"] == 21500.0
    # My work lists it for the Approver (I-20), not for a planner
    page = client.get("/api/screens/mywork", headers=h("approver"))
    assert page.status_code == 200, page.text
    mine = [r for r in page.json()["items"] if r["case_id"] == c["id"]]
    assert [(r["kind"], r["cause"], r["action"]) for r in mine] == [("approval", item["cause"], ACTION)]
    other = client.get("/api/screens/mywork", headers=h("planner-a")).json()["items"]
    assert not [r for r in other if r["case_id"] == c["id"] and r["kind"] == "approval"]


def test_uc_12_the_hold_policy_holds_an_agents_submit_for_value():
    over, under = uc.open_car(7), uc.open_car(1)
    with SessionLocal() as s:
        run = chain.run_chain(s, over["id"], account="planner-a")
        s.commit()
    stage = next(r for r in run.stages if r.stage == "disposition")
    assert ("value", LIMIT) in [(x["reason"], x["detail"]) for x in stage.reasons], stage
    assert uc.get(over["id"]).get("submitted") is None  # nothing was submitted: it waits as a proposal for a person
    with SessionLocal() as s:
        run = chain.run_chain(s, under["id"], account="planner-a")
        s.commit()
    stage = next(r for r in run.stages if r.stage == "disposition")
    assert "value" not in [x["reason"] for x in stage.reasons]  # within the limit: no value hold


def test_uc_12_a_standing_policy_does_not_approve_a_held_decision():
    over, under = uc.open_car(7), uc.open_car(1)
    assert sp._guardrail_holds(over) == ["AP-UC-RECON"] and sp._guardrail_holds(under) == []  # the policy reads the same hold
    pid = uc.ok(call("standingPolicy.save", {"pack": "used_cars", "org_unit_id": uc.ORG, "name": "Cars", "owner": "admin",
                                              "rules": {"max_value": 30000, "min_confidence": 0.75}}, "admin"))["id"]  # fmt: skip
    uc.ok(call("standingPolicy.submit", {"id": pid}, "admin"))
    uc.ok(call("standingPolicy.approve", {"id": pid}, "approver"))
    uc.ok(call("decision.submit", {"case_id": over["id"]}, "planner-a"))
    after = uc.get(over["id"])
    assert after["stage"] == "awaiting_approval" and not after.get("approval")  # a person approves it


def test_uc_12_agent_cannot_approve():
    assert forbidden("decision.approve") and forbidden("decision.override")
    c = uc.open_car(7)
    body = {"case_id": c["id"], "reviewed": True, "rationale": "Within the margin."}
    for action in ("decision.approve", "decision.override"):
        for extra in ({}, {"X-Circularity-Confirmed": "true"}):
            hdr = h("approver") | {"X-Circularity-Preparer": chain.AGENT_IDS["disposition"]} | extra
            r = client.post(f"/api/actions/{action}", json=body, headers=hdr)
            assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required", (action, r.json())
    after = uc.get(c["id"])
    assert after["stage"] == "awaiting_approval" and not after.get("approval")
    assert [i["status"] for i in uc.items(c["id"])] == ["open"]  # the manager's item is still waiting


def test_uc_12_a_person_approves_and_the_item_closes():
    c = uc.open_car(7)
    body = {"case_id": c["id"], "reviewed": True, "rationale": "Recon is worth it on this car."}
    r = call("decision.approve", body, "approver")
    assert r["ok"], r
    assert uc.get(c["id"])["approval"]["by"] and uc.get(c["id"])["stage"] == "approved"
    (item,) = uc.items(c["id"])
    assert item["status"] == "done" and item["outcome"].startswith("Approved by ")


def test_uc_12_override_needs_reason():
    c = uc.open_car(1)
    other = _route(c, "retail:LOT-C")["plan"]
    base = {"case_id": c["id"], "reviewed": True, "route": other}
    for rationale in (None, "", "  "):
        r = call("decision.override", base | ({} if rationale is None else {"rationale": rationale}), "approver")
        assert r["ok"] is False, r  # no reason, no override
    assert uc.get(c["id"])["stage"] == "awaiting_approval"
    why = "Central lot has the buyer waiting."
    r = call("decision.override", base | {"rationale": why}, "approver")
    assert r["ok"], r
    got = uc.get(c["id"])
    assert got["override"] == {"rec": c["recommendation"]["plan"], "chosen": other, "reason": why}
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT input, actor FROM action_journal WHERE action = 'decision.override' AND case_id = :c"), {"c": c["id"]}
        ).one()
    assert why in str(row.input) and row.actor == "approver"  # the reason is in the journal


def test_uc_12_the_limit_is_the_packs_parameter():
    """The limit is the guardrail's value, not a constant (a customer may tighten it, down to its minimum)."""
    c = uc.open_car(1)
    doc = load_pack("used_cars").model_dump()
    next(g for g in doc["guardrails"] if g["id"] == "AP-UC-RECON")["param"]["value"] = 1000
    with SessionLocal() as s:
        d = decide.decide_case(c["id"], Pack.model_validate(doc), FlowVersion(None, 0, ()), session=s)
    (check,) = d.approvals
    assert check["passed"] is False and check["reason"] == "Recon $1,200 over the $1,000 limit"
