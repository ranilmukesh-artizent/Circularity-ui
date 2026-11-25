"""P9-6.7 (R20, story DV-04): for a received device the order is gates, locked compliance guardrails, business rules, then
valuation, ranking and the hold. A device with a registry hit, no wipe certificate, a stale price and a business rule `require
buynow` stays blocked on every channel: the rule never brings back a route a gate excluded, and both gates speak."""

from di.core import clock
from di.services.cases import intake
from di.services.cases.decide import Decision, decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import load_pack

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
    assert all(r["excluded"] for r in d.routes)
    assert d.hold is not None and d.hold["gates"] == ["G-DEV-WIPE"]  # the hold follows the gates, last
