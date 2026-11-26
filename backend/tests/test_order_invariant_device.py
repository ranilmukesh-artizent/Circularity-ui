"""P9-6.7 (R20, story DV-04): for a received device the order is gates, locked compliance guardrails, business rules, then
valuation, ranking and the hold. A device with a registry hit, no wipe certificate, a stale price and a business rule `require
buynow` stays blocked on every channel: the rule never brings back a route a gate excluded, and both gates speak."""

from di.core import clock
from di.services.cases import intake
from di.services.cases.decide import Decision, decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import device_price

ORDER = ("gates", "valuation", "queue_plan", "rules", "rank")
NOW = clock.now().isoformat()


def _device_case() -> dict:
    lot = intake.device_lot("D-9001", {"grade": "B", "band": "25-48m", "ref": 300, "qty": 1})
    lot |= {"imei": "359990000099001", "sku_key": "iPhone 14|128", "storage_gb": 128, "quote": {"amount": 410}}
    lot["inputs"] = {
        "feed_price": 300.0, "feed_stale": True,  # a low price confidence: the feed's week is old
        "registry": {"state": "hit", "status": "reported stolen", "hits": ["reported stolen"], "checked_at": NOW[:10]},
        "wipe": {"state": "none", "certificate": None},
    }  # fmt: skip
    return {"id": "D-9001", "valuer": lot}


def _decide(*rules: CompiledRule) -> Decision:
    return decide_case(_device_case(), load_pack("device"), FlowVersion(None, 3, tuple(rules)))


def test_order_invariant_device():
    d = _decide(CompiledRule("DR-9", {}, "require", "buynow", "send every device to Buy Now"))
    assert d.trace == ORDER
    assert [g.gate_id for g in d.gates if not g.passed] == ["G-DEV-WIPE", "G-DEV-LOCK"]  # gates first, in catalogue order
    buynow = next(r for r in d.routes if r["id"] == "buynow")
    assert buynow["excluded"] and "GR-D1" in buynow["failReason"]  # the first failed gate's reason stays
    assert d.rules_applied == [] and d.recommendation is None and d.route is None  # the rule never re-enables a gated channel
    assert all(r["excluded"] for r in d.routes if r["id"] != "recycle")  # both gates keep recycle open (P9-6.15)
    assert d.hold is not None and d.hold["gates"] == ["G-DEV-WIPE"]  # the hold follows the gates, last


def test_order_invariant_device_price_holds_come_after_valuation_and_ranking():
    """P9-6.10 (R20): the floor and confidence holds judge the route that was finally recommended, after the gates, the rules,
    the valuation and the ranking; a rule that requires a channel changes the route the floor is read on."""
    lot = _device_case()["valuer"]
    lot["ref"] = 200
    lot["inputs"] = {
        "feed_price": 200.0, "feed_stale": False, "sales_90d": 50,
        "registry": {"state": "clear", "status": "clear", "hits": [], "checked_at": NOW[:10], "checked_ts": NOW, "age_days": 1.0},
        "wipe": {"state": "ok", "certificate": {"certificate_id": "WC-1", "method": "Purge", "tool_version": "4.2",
                                                 "verification": "pass", "operator": "OP-1", "at": NOW}, "missing": []},
        "bands": {k: {"p10": 60.0, "p50": 60.0, "p90": 60.0, "model_id": None, "feed_week": "2026-10-05"}
                  for k in ("buynow", "offers", "auction", "wholesale")},
    }  # fmt: skip
    rule = CompiledRule("DR-9", {}, "require", "buynow", "Buy Now only")
    d = decide_case({"id": "D-9001", "valuer": lot}, load_pack("device"), FlowVersion(None, 3, (rule,)))
    assert d.trace == ORDER and d.rules_applied == ["DR-9"] and d.route == "buynow"
    assert d.approval is not None and [h["id"] for h in d.approval["holds"]] == ["GR-D2"]
    cash = next(r for r in d.routes if r["id"] == "buynow")
    assert device_price.usd(d.extra["cash"]) in d.approval["holds"][0]["reason"] and cash["net"] == d.net


def test_order_invariant_device_a_shortcut_never_bypasses_the_gates():
    """P9-6.14 (R20): the grade C shortcut to wholesale runs after the gates; a reported-stolen device with no wipe certificate
    still has no route, and both gates speak."""
    from di.services.modeler.overlay import apply_overlay, parse_ops

    op = next(s.op for s in load_pack("device").customer_layer.sample_diversions if s.op.get("to") == "wholesale")
    pack = apply_overlay(load_pack("device"), parse_ops([{**op, "id": "op-1"}]))
    case = _device_case()
    case["valuer"] |= {"grade": "C"}
    case["valuer"]["inputs"]["model_age_months"] = 40.0
    d = decide_case(case, pack, FlowVersion(None, 3, ()))
    assert d.diversions == ["op-1"] and d.route is None and d.recommendation is None
    assert all(r["excluded"] for r in d.routes if r["id"] != "recycle")  # both gates keep recycle open (P9-6.15)
    assert {g.gate_id for g in d.gates if not g.passed} >= {"G-DEV-WIPE", "G-DEV-LOCK"}
