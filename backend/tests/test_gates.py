"""P9-1.2 (I-2, I-3): the gate catalogue (43 gates: B section 5, G-CON-2, G-DEV-QUOTE), evidence records and the pure evaluation
of a case's gates. The hold and the release on evidence are in test_gate_hold.py."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from di.services.cases import gate_hold
from di.services.engine.routes import POLICY, mk_route, term
from di.services.modeler.evidence import EVIDENCE_TYPES, Evidence, evidence_of
from di.services.modeler.gates import (
    GateDef,
    GateEffect,
    GateResult,
    apply_gate_results,
    catalogue,
    evaluate_gates,
    pack_gates,
)
from di.services.modeler.pack import GateRef, Pack, load_pack, pack_keys, parse_pack

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "packs" / "evidence_test.json"
T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)

# research B sections 5.2 to 5.6, in order
B5_IDS = [
    "G-TOOL-REC", "G-TOOL-TEL", "G-DEV-WIPE", "G-DEV-LOCK", "G-DEV-QUOTE", "G-VEH-TITLE", "G-VEH-ODO", "G-VEH-RECALL",
    "G-VEH-BRAND",
    "G-VEH-SALV", "G-NET-INV", "G-NET-CFG", "G-NET-EXP", "G-NET-COV", "G-MED-DECON", "G-MED-SVC", "G-MED-FSN",
    "G-MED-REFURB",
    "G-DATA-1", "G-DATA-2", "G-DATA-3", "G-DS-1", "G-DS-2", "G-WEEE-1", "G-WEEE-2", "G-WASTE-1", "G-WASTE-2",
    "G-BAT-1", "G-BAT-2", "G-BAT-3", "G-BAT-4", "G-BAT-5",
    "G-MED-1", "G-MED-2", "G-MED-3", "G-ESPR-1", "G-DPP-1", "G-CON-1", "G-CON-2", "G-SAFE-1",
    "G-REP-1", "G-REP-2", "G-REP-3",
]  # fmt: skip


def _fixture_pack() -> Pack:
    return parse_pack(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _with_gates(key: str, *ids: str) -> Pack:
    p = load_pack(key)
    return p.model_copy(update={"gates": [GateRef(id=i) for i in ids]})


def _rec(type: str, result: str = "pass", at: datetime = T0, **over: Any) -> dict[str, Any]:
    return {"type": type, "source": "wipe-tool", "at": at.isoformat(), "result": result, "value": {}} | over


def _case(*records: dict[str, Any], **over: Any) -> dict[str, Any]:
    return {"id": "RT-9001", "cls": "phone", "template": "device", "evidenceRecords": list(records)} | over


def _routes() -> list[dict[str, Any]]:
    return [
        mk_route({"id": i, "plan": i, "terms": [term("Sale", 100, "gain")]}) for i in ("buynow", "offers", "auction", "market")
    ]


def test_x_03_gate_has_typed_fields():
    cat = catalogue()
    assert len(cat) == 43  # 41 of research B section 5, G-CON-2 (P9-3.6) and G-DEV-QUOTE (P9-6.5)
    assert list(cat) == B5_IDS
    for g in cat.values():
        assert (
            g.type
            and g.stage
            and g.trigger is not None
            and (g.evidence or g.id == "G-DEV-QUOTE")
            and g.effect.kind
            and g.owner
            and g.citation
        ), g.id
        assert g.legal_review == "pending"
        assert all(e in EVIDENCE_TYPES for e in g.evidence), g.id
    assert {g.type for g in cat.values()} == {"Compliance", "Data quality"}
    # the two entries the spec fixes
    wipe = cat["G-DEV-WIPE"]
    assert (wipe.stage, wipe.trigger.routes, wipe.trigger.when, wipe.evidence, wipe.owner) == (
        "condition",
        ["sale"],
        [],
        ["data_wipe"],
        "Compliance",
    )
    assert (wipe.effect.kind, wipe.effect.hold_until_evidence, wipe.effect.on_fail.step) == (
        "block", True, "Re-run the wipe or destroy the storage"
    )  # fmt: skip
    rec = cat["G-TOOL-REC"]
    assert (rec.stage, rec.trigger.routes, rec.evidence, rec.owner) == (
        "match",
        ["release", "reuse", "sale", "parts"],
        ["recall_check"],
        "Quality",
    )
    assert (rec.effect.kind, rec.effect.hold_until_evidence, rec.effect.step) == ("block", False, "Quarantine")
    # stage ranges take their last stage; reporting gates sit at close and block it
    assert cat["G-VEH-ODO"].stage == "condition" and cat["G-VEH-SALV"].stage == "execute"
    assert {g.stage for g in cat.values() if g.id.startswith("G-REP")} == {"close"}
    assert {g.effect.kind for g in cat.values() if g.id.startswith("G-REP")} == {"close_block"}


def test_x_03_compliance_gates_locked():
    cat = catalogue()
    compliance = [g.id for g in cat.values() if g.type == "Compliance"]
    assert len(compliance) == 40
    gates = pack_gates(_with_gates("tool_fleet", *compliance))
    assert [g.id for g in gates] == compliance and all(g.locked for g in gates)
    assert not cat["G-NET-INV"].locked and not cat["G-TOOL-TEL"].locked  # Data quality gates are editable


def test_pack_gates_merges_params_in_catalogue_order():
    p = load_pack("device").model_copy(update={"gates": [
        GateRef(id="G-DEV-LOCK", params={"max_age_days": 3}), GateRef(id="G-DEV-WIPE"), GateRef(id="G-DATA-1", active=False),
    ]})  # fmt: skip
    got = pack_gates(p)
    assert [g.id for g in got] == ["G-DEV-WIPE", "G-DEV-LOCK"]  # catalogue order, the inactive ref left out
    assert got[1].params == {"max_age_days": 3} and isinstance(got[0], GateDef)
    with pytest.raises(ValueError, match="G-NOPE"):
        pack_gates(p.model_copy(update={"gates": [GateRef(id="G-NOPE")]}))


def test_x_07_no_wipe_blocks_release_routes():
    p = _fixture_pack()
    case = _case()
    (res,) = evaluate_gates(case, p)
    assert res == GateResult(
        "G-DEV-WIPE", False, GateEffect("block", ("buynow", "offers", "auction", "market"), True, None),
        ("data_wipe",), "Data-wipe certificate missing",
    )  # fmt: skip
    routes = _routes()
    apply_gate_results(routes, [res])
    assert all(r["excluded"] and r["failGate"] == POLICY for r in routes)
    assert {r["failReason"] for r in routes} == {"Data-wipe certificate: Data-wipe certificate missing"}
    assert gate_hold.hold(case, [res]) is True
    assert case["gateHold"]["gates"] == ["G-DEV-WIPE"] and case["recommendation"] is None and case["stage"] == "none"


def test_x_07_pass_record_clears_the_gate():
    p = _fixture_pack()
    (res,) = evaluate_gates(_case(_rec("data_wipe")), p)
    assert res.passed and res.evidence_missing == () and res.reason == "Data-wipe certificate on file"
    routes = _routes()
    apply_gate_results(routes, [res])
    assert not any(r["excluded"] for r in routes)
    case = _case(_rec("data_wipe"), gateHold={"gates": ["G-DEV-WIPE"], "since": "x", "batch": None})
    assert gate_hold.hold(case, [res]) is False and case["gateHold"] is None


def test_x_07_failed_wipe_adds_step():
    p = _fixture_pack()
    case = _case(_rec("data_wipe", "fail"))
    (res,) = evaluate_gates(case, p)
    assert not res.passed and res.reason == "Data-wipe certificate failed verification"
    assert res.effect.step == "Re-run the wipe or destroy the storage" and res.evidence_missing == ()
    assert gate_hold.hold(case, [res]) is True
    assert case["requiredSteps"] == [
        {"gate": "G-DEV-WIPE", "step": "Re-run the wipe or destroy the storage", "owner": "Compliance"}
    ]
    # a later pass supersedes the failed record
    (again,) = evaluate_gates(_case(_rec("data_wipe", "fail"), _rec("data_wipe", at=T0 + timedelta(hours=1))), p)
    assert again.passed


def test_x_03_tool_recall_blocks_four_routes_with_quarantine_step():
    p = _with_gates("tool_fleet", "G-TOOL-REC")
    (res,) = evaluate_gates({"id": "RT-9002", "cls": "CMH", "evidenceRecords": []}, p)
    assert res.effect == GateEffect("block", ("release", "redeploy", "resell", "harvest"), False, "Quarantine")
    assert res.reason == "Recall check missing"
    case: dict[str, Any] = {}
    assert gate_hold.hold(case, [res]) is False  # no hold, but the step is required
    assert case["requiredSteps"] == [{"gate": "G-TOOL-REC", "step": "Quarantine", "owner": "Quality"}]


def test_x_03_trigger_facts_and_classes():
    p = _with_gates("device", "G-DATA-1", "G-DATA-3", "G-DATA-2", "G-REP-3")
    # phone has storage media and no patient data; the other gates need facts the case lacks
    assert [r.gate_id for r in evaluate_gates(_case(), p)] == ["G-DATA-1"]
    got = evaluate_gates(_case(media={"sanitisable": False}, carbon=12.5), p)
    assert [r.gate_id for r in got] == ["G-DATA-1", "G-DATA-2", "G-REP-3"]
    assert got[1].effect.kind == "require_step" and got[1].effect.step == "Destroy the media"
    assert got[2].effect.kind == "close_block" and got[2].effect.routes == ("buynow", "offers", "auction", "market")
    # a gate whose route classes the pack has no route for is not listed (the device pack sells only)
    assert evaluate_gates(_case(), _with_gates("device", "G-MED-REFURB")) == []


def test_x_03_other_kinds_are_not_applied_to_routes():
    p = _with_gates("device", "G-DATA-2", "G-REP-3")
    results = evaluate_gates(_case(media={"sanitisable": False}, carbon=1), p)
    assert [r.passed for r in results] == [False, False]
    routes = _routes()
    apply_gate_results(routes, results)  # require_step and close_block never fail a route
    assert not any(r["excluded"] for r in routes)


def test_evidence_as_of_ignores_later_records():
    case = _case(_rec("data_wipe", at=T0), _rec("data_wipe", "fail", at=T0 + timedelta(days=2)))
    assert evidence_of(case, "data_wipe") == Evidence("data_wipe", "wipe-tool", T0 + timedelta(days=2), "fail", {}, None)
    got = evidence_of(case, "data_wipe", T0 + timedelta(days=1))
    assert got is not None and got.result == "pass" and got.at == T0
    assert evidence_of(case, "data_wipe", T0 - timedelta(seconds=1)) is None
    assert evidence_of(case, "recall_check") is None
    p = _fixture_pack()
    assert evaluate_gates(case, p, T0 + timedelta(days=1))[0].passed
    assert not evaluate_gates(case, p, T0 + timedelta(days=3))[0].passed


def test_evidence_expiry():
    until = T0 + timedelta(days=5)
    case = _case(_rec("data_wipe", valid_until=until.isoformat()))
    assert evidence_of(case, "data_wipe", T0 + timedelta(days=4)) is not None
    assert evidence_of(case, "data_wipe", until) is None  # expired at its valid_until
    assert evidence_of(case, "data_wipe", until + timedelta(days=1)) is None
    # a record that does not parse is ignored
    assert evidence_of(_case({"type": "data_wipe", "result": "maybe", "at": "x"}), "data_wipe") is None


def test_shipped_packs_have_only_the_gates_a_phase_switched_on():
    """A parity guard (plan 9): the pack phases flip it as they switch gates on. P9-1.11 switched G-CON-1 on in the tool-fleet
    pack; it triggers only on a restricting contract record, so a case without one is not gated. P9-3.6 switched G-CON-2 on,
    P9-6.5 G-DEV-QUOTE, P9-6.6 G-DEV-LOCK and P9-6.7 G-DEV-WIPE (a received device only)."""
    for k in pack_keys():
        assert [g.id for g in load_pack(k).gates] == {
            "tool_fleet": ["G-CON-1", "G-CON-2"],
            "device": ["G-DEV-WIPE", "G-DEV-LOCK", "G-DEV-QUOTE"],
        }.get(k, []), k
        got = evaluate_gates({"cls": "x"}, load_pack(k))
        # the tool fleet's contract right (P9-3.6) applies to every case: with no contract line it fails
        assert [(r.gate_id, r.passed) for r in got] == ([("G-CON-2", False)] if k == "tool_fleet" else []), k


def test_catalogue_file_is_the_catalogue():
    path = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "gates.catalogue.json"
    assert [g["id"] for g in json.loads(path.read_text(encoding="utf-8"))] == B5_IDS
    assert "gates.catalogue" not in pack_keys()
