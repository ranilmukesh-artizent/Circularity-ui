"""Plan 9, P9-9.10 (story UC-10): the used-car channel valuer values every channel net of what it costs.

Sample UC-S1 (SUV, 38,000 miles, grade B, recon 1,200, book value 19,500) is valued on the inputs the mocks serve: the dealer
system's per-lot sales history and bid, the pricing guide and the auction platform's fees (P9-9.6). Every number is a parameter
of the pack, so a pack copy with another holding cost moves the net. Pure: no database, no source-sim.
"""

import copy
from typing import Any

from di.services.cases.decide import decide_case
from di.services.modeler.compile import FlowVersion
from di.services.modeler.gates import GateEffect, GateResult, apply_gate_results
from di.services.modeler.pack import Pack, load_pack
from di.services.modeler.templates import load_template
from di.services.modeler.valuers import VALUERS, used_cars
from di.services.modeler.valuers.routes_adapter import to_routes
from di.services.modeler.valuers.tool_fleet import PathValue, ValueLine

PACK = load_pack("used_cars")
LIMIT = "Not considered: recon under 60% of retail value"


def facts_s1(**over: Any) -> dict[str, Any]:
    """UC-S1 with the market the mocks serve for VIN ...001 (retail guide 24,000, wholesale 21,500, three lots)."""
    f: dict[str, Any] = {
        "asset": {"mileage_at_return": 38000, "book_value": 19500},
        "condition": {"condition_score": 4, "recon_estimate": 1200},
        "grade": "B",
        "market": {
            "lot_avg_price": {"LOT-N": 23600, "LOT-C": 24000, "LOT-S": 24300},
            "lot_days_to_sale": {"LOT-N": 34, "LOT-C": 21, "LOT-S": 15},
            "lot_spread": {"LOT-N": 1500, "LOT-C": 1300, "LOT-S": 1200},
            "lot_comparables": {"LOT-N": 12, "LOT-C": 22, "LOT-S": 18},
            "lot_distance_miles": {"LOT-N": 12, "LOT-C": 40, "LOT-S": 95},
            "lot_names": {"LOT-N": "North lot", "LOT-C": "Central lot", "LOT-S": "South lot"},
            "retail_guide_price": 24000,
            "wholesale_guide_price": 21500,
            "auction_sell_fee": 325,
            "auction_transport": 120,
            "auction_next_sale_days": 6,
            "dealer_bid": 20900,
            "salvage_bid": 2100,
        },
    }
    return f | over


def by_id(values: list[PathValue]) -> dict[str, PathValue]:
    return {v["k"]: v for v in values}


def test_uc_10_every_channel_valued_net():
    v = by_id(used_cars.value_routes(facts_s1(), PACK, None))
    assert list(v) == ["retail:LOT-C", "retail:LOT-N", "retail:LOT-S", "auction", "dealer_trade", "salvage"]
    assert [v[k]["net"] for k in ("retail:LOT-N", "retail:LOT-C", "retail:LOT-S")] == [20172.80, 21028.00, 21489.50]
    assert (v["auction"]["net"], v["dealer_trade"]["net"]) == (20612.00, 20665.00)
    assert (v["salvage"]["ok"], v["salvage"]["why"]) == (False, LIMIT)
    assert all(x["ok"] for k, x in v.items() if k != "salvage")
    south = v["retail:LOT-S"]
    assert (south["dest"]["days"], south["dest"]["confidence"], south["dest"]["name"]) == (15, 0.95, "Retail lot · South lot")
    assert south["gross"] == 24300 and south["cost"] == 1200 + 104.5 + 450 + 486 and south["hold"] == 570
    assert {x["kind"] for r in v.values() for x in r["lines"]} <= {"sale", "prep", "fees", "risk"}
    for k in ("retail:LOT-N", "retail:LOT-C", "auction"):
        assert "days" in v[k]["dest"] and "confidence" in v[k]["dest"]


def test_uc_10_gross_vs_book():
    v = by_id(used_cars.value_routes(facts_s1(), PACK, None))
    assert v["retail:LOT-S"]["dest"]["gross_vs_book"] == 1989.50
    assert v["dealer_trade"]["dest"]["gross_vs_book"] == 20665 - 19500


def test_uc_10_few_comparables_use_the_guide_and_scale_confidence():
    f = facts_s1()
    f["market"]["lot_comparables"]["LOT-S"] = 4
    s = by_id(used_cars.value_routes(f, PACK, None))["retail:LOT-S"]
    assert s["gross"] == 24000  # the guide's retail value, not the lot's average
    assert s["dest"]["confidence"] == round(round(1 - 1200 / 24000, 2) * 0.8, 2)


def test_uc_10_salvage_considered_when_recon_high():
    f = facts_s1(condition={"condition_score": 2, "recon_estimate": 16500}, grade="D")
    f["market"] |= {"salvage_bid": 3900, "retail_guide_price": 21000}
    f["market"]["lot_avg_price"] = {"LOT-C": 21000}
    f["market"]["lot_days_to_sale"] = {"LOT-C": 21}
    v = by_id(used_cars.value_routes(f, PACK, None))
    assert (v["salvage"]["ok"], v["salvage"]["net"]) == (True, 3720.00)
    assert [(x["label"], x["amt"]) for x in v["salvage"]["lines"]][1:] == [("Tow", 120.0), ("Title brand administration", 60.0)]


def test_uc_10_params_come_from_pack():
    doc = copy.deepcopy(PACK.model_dump())
    doc["valuer"]["params"]["params"]["holding_cost_per_day"] = 40
    pack = Pack.model_validate(doc)
    v = by_id(used_cars.value_routes(facts_s1(), pack, None))
    assert v["retail:LOT-S"]["net"] == 21459.50
    assert v["auction"]["net"] == 20612.00 - 6 * 2  # six days of holding at the new rate


def test_uc_10_auction_mileage_and_grade_adjust_the_price():
    f = facts_s1(grade="C")
    f["asset"]["mileage_at_return"] = 133000  # 13,000 miles past the last band
    a = by_id(used_cars.value_routes(f, PACK, None))["auction"]
    assert a["gross"] == round(21500 * 0.94 * (1 - 0.015 * 1.3), 2)


def test_uc_10_missing_inputs_are_named_not_made_up():
    f = facts_s1()
    for k in ("dealer_bid", "wholesale_guide_price"):
        del f["market"][k]
    del f["condition"]["recon_estimate"]
    v = by_id(used_cars.value_routes(f, PACK, None))
    assert (v["dealer_trade"]["ok"], v["dealer_trade"]["why"]) == (False, "No partner bid")
    assert v["auction"]["ok"] is False and v["auction"]["misses"] == ["market.wholesale_guide_price"]
    assert not any(v[k]["ok"] for k in v if k.startswith("retail:"))


def test_uc_10_flat_dotted_facts_read_like_nested():
    flat = {"asset.mileage_at_return": 38000, "asset.book_value": 19500, "condition.recon_estimate": 1200, "grade": "B"}
    flat |= {f"market.{k}": x for k, x in facts_s1()["market"].items()}
    assert used_cars.value_routes(flat, PACK, None) == used_cars.value_routes(facts_s1(), PACK, None)


def test_uc_10_evidence_lines():
    best = by_id(used_cars.value_routes(facts_s1(), PACK, None))["retail:LOT-S"]
    assert used_cars.evidence_lines(facts_s1(), best, PACK) == [
        "Comparable sales at South lot: 18, average 15 days",
        "Recon $1,200 against the $2,500 limit",
        "Auction $21,500 before fees",
    ]


def test_uc_10_registered_and_decide_case_recommends_the_best_channel():
    assert VALUERS["used_cars"] is used_cars.value_routes
    case = {"id": "UC-S1", "template": "used_cars", "valuer": facts_s1(), "assetId": "asset.Customer A:SYNUC000000000001"}
    d = decide_case(case, PACK, FlowVersion(None, 0, ()))
    named = {r["id"]: r for r in d.routes}
    assert named["retail:LOT-S"]["plan"] == "Retail lot · South lot" and named["retail:LOT-S"]["dest"]["days"] == 15
    assert [r["net"] for r in d.routes if r["id"].startswith("retail:")] == [21028.0, 20172.8, 21489.5]


def test_uc_10_a_gate_that_blocks_retail_fails_every_retail_lot():
    t = load_template("used_cars")
    values = used_cars.value_routes(facts_s1(), PACK, None)
    routes = to_routes(t, values)
    res = GateResult("G-VEH-RECALL", False, GateEffect("block", ("retail",), False, None), (), "open recall")
    apply_gate_results(routes, [res])
    assert {r["id"]: r["excluded"] for r in routes if r["id"].startswith("retail:")} == {
        "retail:LOT-C": True, "retail:LOT-N": True, "retail:LOT-S": True,
    }  # fmt: skip
    assert not [r for r in routes if r["id"] in ("auction", "dealer_trade") and r["excluded"]]


def test_routes_adapter_uses_line_kind():
    line: ValueLine = {"type": "c", "label": "Ship to the buyer", "basis": "", "amt": 10.0, "kind": "risk"}
    pv: PathValue = {
        "k": "resell", "ok": True, "gross": 0.0, "cost": 10.0, "hold": 0.0, "net": -10.0, "why": "", "lines": [line],
        "dest": {"name": "Named by the valuer"}, "misses": [], "co2": None, "co2Prov": None,
    }  # fmt: skip
    (r,) = to_routes(load_template("tool_fleet"), [pv])  # `_KINDS` says "fees" for a "Ship to" cost; the line says risk
    assert [t["kind"] for t in r["terms"]] == ["risk"] and r["plan"] == "Named by the valuer"


def test_uc_10_no_lot_history_keeps_a_retail_channel_not_valued():
    f = facts_s1()
    for k in ("lot_avg_price", "lot_days_to_sale", "lot_spread", "lot_comparables", "lot_distance_miles"):
        del f["market"][k]
    v = by_id(used_cars.value_routes(f, PACK, None))
    assert list(v) == ["retail", "auction", "dealer_trade", "salvage"]
    assert (v["retail"]["ok"], v["retail"]["why"]) == (False, "No lot has comparable sales yet")


def _compiled(action: str) -> Any:
    from di.services.modeler.compile import CompiledRule

    return CompiledRule("BR-UC-T", {}, action, "retail", "retail rule")


def _routes() -> list[Any]:
    return to_routes(load_template("used_cars"), used_cars.value_routes(facts_s1(), PACK, None))


def test_uc_10_business_rules_on_retail_apply_to_every_lot():
    from di.services.modeler.apply import apply_rules

    t = load_template("used_cars")
    routes = _routes()
    out = apply_rules({}, routes, [_compiled("exclude")], t)
    assert out.ids == ["BR-UC-T"] and not out.waived
    assert {r["id"] for r in routes if r["excluded"]} == {
        "retail:LOT-C",
        "retail:LOT-N",
        "retail:LOT-S",
        "salvage",
    }  # salvage: not valued
    routes = _routes()
    apply_rules({}, routes, [_compiled("require")], t)
    assert {r["id"] for r in routes if not r["excluded"]} == {"retail:LOT-C", "retail:LOT-N", "retail:LOT-S"}
    routes = _routes()
    assert apply_rules({}, routes, [_compiled("prefer")], t).preferred == "retail:LOT-S"  # the lot with the best net
