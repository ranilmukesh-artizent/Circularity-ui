"""Plan 9, P9-11.9 (stories MR-09 and MR-10): the nearest next hospital and the repair approval, through `decide_case`.

Among the requests the service window covers (the unit's certification and preventive maintenance in date for the whole
rental) the best value wins, then the least travel; the route is `rerent:<request>` and its four evidence lines are the plain
facts behind it. A repair estimate over the AP-MR-REPAIR limit holds the decision for the fleet manager, with the modelled
rental income over the next period and the alternative, retire. Numbers come from code (the valuer); no model is involved.
Gates and business rules on `rerent` / `service_rerent` apply to the `rerent:<request>` routes too (the base id). Pure: facts in,
a decision out. Legal note: the wording of the service gates needs review by Kinective's Legal team before it is relied on.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from di.services.cases.decide import Decision, decide_case, write_back
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.gate_checks import medical
from di.services.modeler.pack import Diversion, Pack, load_pack, parse_pack
from di.services.modeler.valuers import VALUERS, medical_rental

AS_OF = datetime(2026, 11, 17, 12, tzinfo=UTC)
CHECKED_IN = datetime(2026, 11, 17, 6, tzinfo=UTC)
DECON_ENDED = datetime(2026, 11, 17, 9, 30, tzinfo=UTC)
PACK_FILE = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "medical_rental.json"


def _req(n: int, hospital: str, miles: int, days: int = 30, start: str = "2026-11-27") -> dict[str, Any]:
    first = datetime.fromisoformat(start)
    return {
        "req_id": f"REQ-{n}", "hospital_id": hospital, "hospital": hospital, "start_date": start, "days": days,
        "ends": (first + timedelta(days=days)).date().isoformat(), "distance_miles": miles,
        "requested_at": "2026-11-26T08:00:00+00:00",
    }  # fmt: skip


def _facts(**over: Any) -> dict[str, Any]:
    """MR-S1: pump `SYN-MR-IP-0001`, 3 years old, book value 1,150, residual sale value 1,100, with its decontamination record,
    its service record (certification to 31 Mar 2027, preventive maintenance due 15 Feb 2027) and three open requests."""
    cert, pm = "2027-03-31", "2027-02-15"
    reqs = over.pop("rentalRequests", None) or [_req(1, "HOSP-A", 12), _req(2, "HOSP-B", 5), _req(3, "HOSP-C", 48)]
    cert, pm = over.pop("certificationExpiry", cert), over.pop("pmDue", pm)
    value = {"certification_expiry": cert, "pm_due": pm, "failed": []}
    facts: dict[str, Any] = {
        "id": "MR-9001", "template": "medical_rental", "owner": "Customer A", "assetId": "Customer A:SYN-MR-IP-0001",
        "cls": "infusion_pump", "age_years": 3, "book_value": 1150, "residual_sale_value": 1100, "repair_estimate": 0,
        "rentalRequests": reqs, "serviceRead": {"pmDue": pm, "certificationExpiry": cert},
        "serviceCheck": {"requests": medical.request_checks(value, reqs), "proposed": None},
        "evidenceRecords": [
            {"type": "decontamination", "source": "mr_decon", "at": DECON_ENDED.isoformat(), "result": "pass",
             "value": {"checked_in_at": CHECKED_IN.isoformat()}},
            {"type": "service_record", "source": "mr_biomed", "at": "2026-11-10T00:00:00+00:00", "result": "pass",
             "value": value},
            {"type": "field_safety_status", "source": "mr_biomed", "at": "2026-11-10T00:00:00+00:00", "result": "pass",
             "value": {"notice_id": None, "correction_ref": None}},
            {"type": "refurb_assessment", "source": "manual", "at": "2026-11-01T00:00:00+00:00", "result": "pass", "value": {}},
        ],
    }  # fmt: skip
    return facts | over


def _decide(facts: dict[str, Any], pack: Pack | None = None, *rules: CompiledRule) -> Decision:
    return decide_case(facts, pack or load_pack("medical_rental"), FlowVersion(None, 3, tuple(rules)), AS_OF)


def _route(d: Decision, rid: str) -> dict[str, Any]:
    return next(r for r in d.routes if r["id"] == rid)


def _best(facts: dict[str, Any], pack: Pack, route: str | None) -> Any:
    return next((v for v in VALUERS["medical_rental"](facts, pack, AS_OF) if v["k"] == route), None)


def test_mr_09_nearest_next_hospital():
    pack, facts = load_pack("medical_rental"), _facts()
    d = _decide(facts, pack)
    assert d.route == "rerent:REQ-2" and d.recommendation is not None
    assert round(d.net, 2) == 498.00  # 18 x 30 - 5 miles x 1.40 - 35
    assert d.recommendation["dest"]["name"] == "Re-rent · HOSP-B" and d.recommendation["dest"]["distance"] == 5
    assert medical_rental.evidence_lines(facts, _best(facts, pack, d.route), pack, AS_OF) == [
        "HOSP-B 5 miles, request date 2026-11-26",
        "Service due 2027-02-15, after the rental ends 2026-12-27",
        "Certification to 2027-03-31",
        "Decontaminated 2.5 h ago",
    ]


def test_mr_09_service_window_excludes_request():
    """REQ-2 pays most (90 days) but ends 25 Feb 2027, after the preventive maintenance due 15 Feb: it is not chosen."""
    pack = load_pack("medical_rental")
    long = _req(2, "HOSP-B", 5, days=90)
    facts = _facts(rentalRequests=[_req(1, "HOSP-A", 12), long, _req(3, "HOSP-C", 48)])
    free = VALUERS["medical_rental"]({**facts, "serviceCheck": {"requests": []}}, pack, AS_OF)
    assert max((v for v in free if v["ok"]), key=lambda v: v["net"])["k"] == "rerent:REQ-2"  # without the window it would win
    d = _decide(facts, pack)
    assert d.route == "rerent:REQ-1"
    out = _route(d, "rerent:REQ-2")
    assert out["excluded"] and "Preventive maintenance due 2027-02-15, before the rental ends 2027-02-25" in out["failReason"]
    best = _best(facts, pack, "rerent:REQ-1")
    assert medical_rental.evidence_lines(facts, best, pack, AS_OF)[0] == "HOSP-A 12 miles, request date 2026-11-26"


def test_mr_09_service_then_rerent_serves_a_request_the_window_covers():
    short = _facts(rentalRequests=[_req(1, "HOSP-A", 12), _req(2, "HOSP-B", 5, days=90)])
    by = {v["k"]: v for v in VALUERS["medical_rental"](short, load_pack("medical_rental"), AS_OF)}
    assert by["service_rerent"]["dest"]["name"] == "Service then Re-rent · HOSP-A"


def test_mr_09_least_travel_after_value():
    facts = _facts(rentalRequests=[_req(1, "HOSP-A", 20), _req(2, "HOSP-B", 8)])
    keys = [v["k"] for v in VALUERS["medical_rental"](facts, load_pack("medical_rental"), AS_OF)]
    assert keys[:2] == ["rerent:REQ-2", "rerent:REQ-1"]  # same days: the nearer one is worth more and wins


def test_mr_09_evidence_lines_leave_out_what_is_missing():
    pack, facts = load_pack("medical_rental"), _facts()
    best = _best(facts, pack, "rerent:REQ-2")
    bare = {k: v for k, v in facts.items() if k not in ("serviceRead", "evidenceRecords")}
    assert medical_rental.evidence_lines(bare, best, pack, AS_OF) == ["HOSP-B 5 miles, request date 2026-11-26"]
    assert len(medical_rental.evidence_lines(facts, best, pack)) == 3  # no clock given: no "hours ago" line
    assert medical_rental.evidence_lines(facts, _best(facts, pack, "retire"), pack, AS_OF) == []


def test_mr_09_rules_and_gates_on_rerent_apply_to_every_request_route():
    """The routes are `rerent:<request>`: a business rule or a gate that names `rerent` reaches them (base-id matching)."""
    pack = load_pack("medical_rental")
    d = _decide(_facts(), pack, CompiledRule("BR-1", {}, "exclude", "rerent", "no re-rent"))
    rerents = [r for r in d.routes if r["id"].startswith("rerent:")]
    assert len(rerents) == 3 and all(r["excluded"] and "Excluded by business rule BR-1" in r["failReason"] for r in rerents)
    assert d.route == "service_rerent" or d.route in ("refurbish", "retire")
    short = _facts(certificationExpiry="2026-12-07")  # certification ends before every rental ends: G-MED-SVC fails rerent
    g = _decide(short, pack)
    rerents = [r for r in g.routes if r["id"].startswith("rerent:")]
    assert all(r["excluded"] and "Certification ends 2026-12-07, before the rental ends" in r["failReason"] for r in rerents)
    assert _route(g, "service_rerent")["excluded"] and g.route in ("refurbish", "retire")


def test_mr_09_same_hospital_shortcut_takes_the_best_rerent_route():
    """DV-MR-SAME (shortcut to `rerent`) reaches the best eligible `rerent:<request>`, after the gates and the valuation."""
    doc = json.loads(PACK_FILE.read_text(encoding="utf-8"))
    pack = parse_pack(doc)
    same = Diversion(op_id="DV-MR-SAME", stage="decide", kind="shortcut", to="rerent",
                     when=[{"fact": "request.same_hospital_within_24h", "op": "eq", "value": True}])  # fmt: skip
    pack = pack.model_copy(update={"diversions": [same]})
    d = _decide(_facts(request={"same_hospital_within_24h": True}), pack)
    assert d.route == "rerent:REQ-2" and d.preferred == "rerent:REQ-2" and d.diversions == ["DV-MR-SAME"]
    off = _decide(_facts(request={"same_hospital_within_24h": False}), pack)
    assert off.diversions == [] and off.preferred is None


# ---------------------------------------------------------------- MR-10: a repair over the limit
def _s5(**over: Any) -> dict[str, Any]:
    """MR-S5: a patient monitor (24 a day) with a repair estimate of 1,350."""
    base = {"cls": "patient_monitor", "age_years": 4, "book_value": 600, "residual_sale_value": 900, "repair_estimate": 1350}
    return _facts(**(base | over))


def test_mr_10_repair_over_limit_to_fleet_manager():
    pack = load_pack("medical_rental")
    facts = _s5()
    d = _decide(facts, pack)
    assert len(d.approval_holds) == 1
    item = d.approval_holds[0]
    assert item["id"] == "AP-MR-REPAIR" and item["owner"] == "fleet_manager"
    assert item["repairEstimate"] == 1350.0 and item["limit"] == 1000.0
    assert item["income"] == 1512.00  # 90 days x 0.7 x 24 a day
    assert item["incomeBasis"] == "90 days at 70% utilisation at 24 a day"
    retire = _best(facts, pack, "retire")
    assert item["alternative"] == {"route": "retire", "net": round(retire["net"], 2)} and round(retire["net"], 2) == 495.00
    assert "$1,350.00 is over the $1,000 limit" in item["reason"] and "fleet manager approves" in item["reason"]
    assert item["route"] == d.route  # what the person approves: the recommendation
    case = dict(facts)
    write_back(case, d)
    assert [h["id"] for h in case["approvalHolds"]] == ["AP-MR-REPAIR"]  # the case carries it for I-10 and I-11


def test_mr_10_within_the_limit_or_no_estimate_holds_nothing():
    assert _decide(_s5(repair_estimate=1000)).approval_holds == []  # the limit is "over", not "at"
    assert _decide(_facts()).approval_holds == []
    plain = {k: v for k, v in _facts().items() if k != "repair_estimate"}
    assert _decide(plain).approval_holds == []
    case = _s5()
    write_back(case, _decide(case))
    case["repair_estimate"] = 400
    write_back(case, _decide(case))
    assert "approvalHolds" not in case  # a later decision with a smaller estimate clears the hold


def test_mr_10_the_customers_stricter_limit_holds_a_smaller_repair():
    base = load_pack("medical_rental")
    stricter = [
        g.model_copy(update={"param": g.param.model_copy(update={"value": 500})}) if g.id == "AP-MR-REPAIR" and g.param else g
        for g in base.guardrails
    ]  # the customer layer's stricter value (the limit may go as low as 250)
    pack = base.model_copy(update={"guardrails": stricter})
    held = _decide(_facts(repair_estimate=600), pack).approval_holds
    assert [h["id"] for h in held] == ["AP-MR-REPAIR"] and held[0]["limit"] == 500.0
    assert _decide(_facts(repair_estimate=600)).approval_holds == []  # the pack's own limit (1,000) is untouched


def test_mr_10_the_hold_reaches_the_hold_policy_as_a_guardrail_hold():
    """I-10: an agent's write on a case with the approval hold is held with the reason `risk`, naming the guardrail."""
    from di.services.actions import hold
    from di.services.actions.registry import ACTIONS
    from di.services.agents import chain

    case = _s5()
    write_back(case, _decide(case))
    mod = next(m for m in chain.CHAIN if m.ID == "disposition")
    defn = next(d for d in chain.stage_defs(load_pack("medical_rental")) if d.id == "disposition")
    ctx = chain.stage_context(defn, mod, {}, case)
    assert ctx.guardrail_holds == ["AP-MR-REPAIR"]
    reasons = hold.evaluate_hold(
        action=ACTIONS["decision.submit"], autonomy="limits", confidence=0.9, value=None, bulk=1, open_exception=False,
        conflict=False, guardrail_holds=ctx.guardrail_holds, taint=False, policy=hold.HoldPolicy(None, None, 0.75),
    )  # fmt: skip
    assert [(r.reason, r.detail) for r in reasons] == [("risk", "Guardrail AP-MR-REPAIR needs a person")]
