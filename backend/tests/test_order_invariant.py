"""P9-1.5 (R20): for every case the order is gates, locked compliance guardrails, business rules and diversions, then
valuation and ranking. A business rule never brings back a route a gate or a guardrail excluded, and its waiver restores
only what was eligible after the gates."""

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories.live_rules import live_pack
from di.services.canonical import store as canonical
from di.services.cases import intake
from di.services.cases.decide import Decision, decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import Pack, load_pack, parse_pack
from tests import starting
from tests.helpers import tool_case_facts

REPAIR = {"recall_id": "RC-2026-017", "tool_class": "BRK", "serial_from": "BRK-51000", "serial_to": "BRK-51999",
          "remedy": "repair", "affected_parts": ["Impact mechanism"], "status": "active"}  # fmt: skip
RECALL = Path(__file__).resolve().parent / "fixtures" / "packs" / "recall_test.json"
ORDER = ("gates", "valuation", "queue_plan", "rules", "rank")


def _decide(case: dict, pack: Pack, *rules: CompiledRule) -> Decision:
    return decide_case(case, pack, FlowVersion(None, 3, tuple(rules)))


def _route(d: Decision, rid: str) -> dict:
    return next(r for r in d.routes if r["id"] == rid)


def test_order_invariant_tool_fleet():
    pack = parse_pack(json.loads(RECALL.read_text(encoding="utf-8")))  # G-TOOL-REC active (GR-12)
    case = intake.tool_fleet_case("RT-9001", {"cls": "BRK", "grade": "B", "rul": 60, "serial": "BRK-51007"})
    case["evidenceRecords"] = [
        {
            "type": "recall_check",
            "source": "register",
            "at": "2026-11-01T00:00:00+00:00",
            "result": "pass",
            "value": {"recalls": [REPAIR], "released": None},
        }
    ]  # a repair recall names this serial
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


# ---------------------------------------------------------------------------------------------------------------------
# P9-3.21 (R20, TF-04, TF-12): the order for the tool-fleet returns flow on stored cases: gates (the recall, the contract),
# then the business rules, then valuation and ranking, then the approval holds, which come last.
# ---------------------------------------------------------------------------------------------------------------------
KEY_CONTRACT = "FC-TFOI-KEY"
RECALLED = "BRK-51007"
OI_KEYS = [RECALLED, "FC-TEST", KEY_CONTRACT, "RC-2026-017", "DR-OI-1"]
ORG = "Customer A"


def _clean_canonical() -> None:
    with engine.begin() as conn:
        for m in ("contract_line", "contract", "condition", "recall"):
            for t in ("provenance", "canonical", "conflict"):
                conn.execute(text(f"DELETE FROM {t} WHERE model = :m AND key = ANY(:k)"), {"m": m, "k": OI_KEYS})  # noqa: S608


@pytest.fixture
def stored_world(no_synced_demand):
    starting.reset()
    _clean_canonical()
    yield
    starting.reset()
    _clean_canonical()


def _write(source: str, facts: list[canonical.Fact]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, facts)
        s.commit()


def _open_key_account(line: dict | None = None) -> dict:
    """A breaker of a key-account contract (Westmark Supply) with fresh telematics and an inspection grade A, opened from data."""
    _write("recall", [canonical.Fact("recall", REPAIR["recall_id"], k, v, resource="notices") for k, v in REPAIR.items()])
    _write("fleet", [
        canonical.Fact("contract", KEY_CONTRACT, "customer", "Westmark Supply", resource="contracts"),
        canonical.Fact("contract", KEY_CONTRACT, "key_account", True, resource="contracts"),
        canonical.Fact("condition", RECALLED, "run_hours", 820.0, resource="tools"),
        canonical.Fact("condition", RECALLED, "high_load_share", 0.3, resource="tools"),
        canonical.Fact("condition", RECALLED, "event_counts", {"overheat": 0, "drop": 0, "overload": 0}, resource="tools"),
        canonical.Fact("condition", RECALLED, "telemetry_coverage_pct", 95, resource="tools"),
    ])  # fmt: skip
    grade = {"grade": "A", "test_result": "pass", "inspection_ref": "DR-OI-1", "graded_at": "2026-10-07T03:00:00Z"}
    _write("repairlog", [canonical.Fact("condition", RECALLED, k, v, resource="orders") for k, v in grade.items()])
    facts = tool_case_facts(RECALLED, {"cls": "BRK", "grade": "A", "ft": "Repair center", "site": "Houston", "rul": 75},
                            line={"contract_id": KEY_CONTRACT, **(line or {})})  # fmt: skip
    with SessionLocal() as s:
        c = intake.open_case(s, {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": RECALLED, "reason": "manual",
                                 "facts": facts}, "system")  # fmt: skip
        s.commit()
    return c


def test_order_invariant_tool_fleet_recalled_key_account_with_a_resell_rule(stored_world):
    # Story: a recalled key-account breaker, and a business rule that prefers resell. GR-12 (the gate) blocks resell first, so the
    # rule meets a route that is already out: it is reported as not applied, and the approval review comes after the ranking.
    c = _open_key_account()
    prefer = CompiledRule("R-1", {}, "prefer", "resell", "prefer resale")
    with SessionLocal() as s:
        d = decide_case(c, live_pack(s, c), FlowVersion(None, 3, (prefer,)), session=s)
    assert d.trace == ORDER  # gates, valuation, queue plan, rules, rank: the approval holds are not a step before them
    resell = _route(d, "resell")
    assert resell["excluded"] and "Safety recall RC-2026-017 (repair)" in resell["failReason"]
    assert d.rules_applied == [] and d.preferred is None and d.route not in (None, "resell")
    holds = [x["id"] for x in d.approval["holds"]]
    assert holds and holds[-1] == "TF-KEY"  # the account manager's review is added last, after the gates' own


def test_order_invariant_tool_fleet_contract_block_hides_the_key_account_review(stored_world):
    # Story: the same key account, but its line has an open damage charge (G-CON-2): every route is blocked before anything
    # else runs, so there is no ranking and no review to wait for; the gate shows, not the account manager.
    c = _open_key_account({"damage_charge_open": True, "charge_ref": "CHG-4412"})
    assert c["recommendation"] is None and c["gateHold"]["gates"] == ["G-CON-2"]
    assert all(r["excluded"] for r in c["routes"])
    assert not any(x.get("id") == "TF-KEY" for x in c.get("approvalHolds") or [])
    prefer = CompiledRule("R-1", {}, "prefer", "resell", "prefer resale")
    with SessionLocal() as s:
        d = decide_case(c, live_pack(s, c), FlowVersion(None, 3, (prefer,)), session=s)
    assert d.route is None and d.rules_applied == [] and d.preferred is None
    assert not any(x["id"] == "TF-KEY" for x in (d.approval or {}).get("holds") or [])
