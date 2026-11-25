"""P9-1.5 (R20): for every case the order is gates, locked compliance guardrails, business rules and diversions, then
valuation and ranking. A business rule never brings back a route a gate or a guardrail excluded, and its waiver restores
only what was eligible after the gates."""

import json
from pathlib import Path

from di.services.cases import intake
from di.services.cases.decide import Decision, decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import Pack, load_pack, parse_pack

RECALL = Path(__file__).resolve().parent / "fixtures" / "packs" / "recall_test.json"
ORDER = ("gates", "valuation", "queue_plan", "rules", "rank")


def _decide(case: dict, pack: Pack, *rules: CompiledRule) -> Decision:
    return decide_case(case, pack, FlowVersion(None, 3, tuple(rules)))


def _route(d: Decision, rid: str) -> dict:
    return next(r for r in d.routes if r["id"] == rid)


def test_order_invariant_tool_fleet():
    pack = parse_pack(json.loads(RECALL.read_text(encoding="utf-8")))  # G-TOOL-REC active: no recall check, no resell
    case = intake.tool_fleet_case("RT-9001", {"cls": "CMH", "grade": "B", "rul": 60})
    require = CompiledRule("R-1", {}, "require", "resell", "send every return to resale")
    d = _decide(case, pack, require)
    assert d.trace == ORDER
    resell = _route(d, "resell")
    assert resell["excluded"] and d.gates[0].reason in resell["failReason"] and resell["failReason"].startswith("Safety recall")
    assert d.waived is False and d.rules_applied == [] and d.recommendation is not None and d.route != "resell"

    open_ids = [r["id"] for r in _decide(case, pack).routes if not r["excluded"]]
    exclude = [CompiledRule(f"R-{i}", {}, "exclude", k, "no") for i, k in enumerate(open_ids)]
    w = _decide(case, pack, *exclude)  # the rules would leave nothing eligible: waived, and only the gates' view returns
    assert w.waived is True and w.rules_applied == []
    assert [r["id"] for r in w.routes if not r["excluded"]] == open_ids
    assert _route(w, "resell")["excluded"] and w.gates[0].reason in _route(w, "resell")["failReason"]


def test_order_invariant_device():
    pack = load_pack("device")
    lot = intake.device_lot("L-9001", {"grade": "D", "band": "25-48m", "ref": 300, "qty": 20})
    d = _decide(lot, pack, CompiledRule("DR-9", {}, "prefer", "buynow", "prefer buy now"))
    assert d.trace == ORDER
    assert _route(d, "buynow")["excluded"]  # GR-D3: a grade D lot never goes to Buy Now
    assert d.recommendation is not None and d.route != "buynow" and d.preferred is None
