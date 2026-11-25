"""P9-10.1: the telecom network pack data file (`packs/telecom_network.json`, I-1). Data only: the tests read the pack through
`load_pack` and check it against the gate catalogue, the role policy and the spec's texts. Synthetic data throughout.

Where the pack format (P9-1.1) has no named field for a spec part, the data sits in the nearest free-form field (gate
`params`, `data.mappings`, `runtime.suggestion_rules`, `replay.example`, an overlay op's `note`); each such place is named
in the test that reads it. Same approach as `test_pack_used_cars.py`.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from di.services.modeler.overlay import parse_ops
from di.services.modeler.pack import Pack, PackError, load_pack, parse_pack

BACKEND = Path(__file__).resolve().parents[1]
PACK_FILE = BACKEND / "di" / "services" / "modeler" / "packs" / "telecom_network.json"
CATALOGUE = BACKEND / "di" / "services" / "modeler" / "packs" / "gates.catalogue.json"
POLICY = BACKEND.parent / "fixtures" / "golden" / "policy.json"

LEGAL_NOTE = (
    "Export control (US EAR, EU dual-use list) and US covered-equipment rules summarised; classification is always a "
    "person's. Kinective's Legal team must review before shipping."
)
LOCKED = {"G-NET-INV", "G-NET-CFG"}
GATES = LOCKED | {"G-NET-EXP", "G-NET-COV", "G-BAT-4", "G-DS-1", "G-WEEE-2"}


def _doc() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(PACK_FILE.read_text(encoding="utf-8"))
    return doc


def test_telecom_network_pack_validates():
    p = load_pack("telecom_network")
    assert isinstance(p, Pack) and p.key == "telecom_network"
    doc = _doc()
    del doc["customer_layer"]
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert (e.value.key, e.value.version, e.value.part, e.value.part_name) == ("telecom_network", "1.4.0", 7, "customer_layer")


def test_telecom_network_identity_and_stages():
    p = load_pack("telecom_network")
    assert (p.version, p.unit, p.prefix, p.author_role) == ("1.4.0", "units", "TN", "network_asset_manager")
    assert p.name == "Telecom network equipment"
    assert (p.industry, p.regions, p.legal_review.status) == ("Telecommunications networks", ["US", "EU"], "pending")
    # LegalReview has no note field: the pack-level note sits in replay.example and on every gate's params
    assert p.replay.example is not None and p.replay.example["legal_review_note"] == LEGAL_NOTE
    assert [s.label for s in p.stages] == [
        "Decommission notified", "Match to inventory", "Wipe and test", "Value each route", "Decide the route",
        "Execute", "Close and learn",
    ]  # fmt: skip
    assert {s.agent: s.autonomy for s in p.stages} == {
        "intake": "alone", "condition": "limits", "valuation": "alone", "routing": "limits",
        "follow-through": "limits", "analytics": "alone",
    }  # fmt: skip
    assert {s.confidence for s in p.stages} == {0.75}
    assert [(r.id, r.name, r.app, r.owner, r.lead_days, r.instructions) for r in p.routes] == [
        ("redeploy", "Redeploy to a site", "tn_inv", "network_asset_manager", 5, ["firmware_upgrade", "site_transfer"]),
        ("spare", "Refurbish as a spare", "tn_bench", "spares_planner", 7, ["refurb_order", "spares_transfer"]),
        ("resell", "Resell to a broker", "tn_broker", "network_asset_manager", 14, ["broker_listing"]),
        ("harvest", "Harvest boards", "tn_bench", "test_bench_lead", 4, ["teardown"]),
        ("recycle", "Recycle", "tn_recycler", "sustainability_lead", 10, ["recycler_pickup"]),
    ]  # fmt: skip
    assert p.prompts[0].startswith("Decommissioned network kit: when radios, baseband units, routers,")
    assert p.prompts[0].endswith("Export-control check before any resale.")
    assert (p.prompts[1], p.prompts[2]) == ("Site-swap returns to open site demand", "Spares before new purchases")
    assert [c.id for c in p.classes] == ["radio", "baseband", "router", "line_card", "power_unit", "microwave_link"]
    assert [c.id for c in p.classes if c.attrs.hazardous] == ["power_unit"]  # has_battery: the format's `hazardous`
    assert (p.grades.graded_by, p.grades.scale) == ("read", ["A", "B", "C", "D"])
    assert p.grades.map_from["A"] == "all tests passed and firmware current"
    assert p.grades.map_from["D"] == "failed"


def test_telecom_network_clarify_options_parse_as_overlay_ops():
    p = load_pack("telecom_network")
    assert p.clarify is not None
    assert p.clarify.question == "Should units with firmware two or more major versions behind be upgraded before redeployment?"
    assert [o.label for o in p.clarify.options] == ["Yes, always upgrade first", "Only for core sites"]
    # no business-rule action "upgrade first" in the format: each option is an add_step op (as device does), rule id in `note`
    always, core = (parse_ops(json.loads(o.adds)) for o in p.clarify.options)
    assert [(o.stage, o.step) for o in always + core] == [("decide", "Upgrade firmware before redeploy")] * 2
    assert "BR-TN-FW" in always[0].note and "BR-TN-FW" in core[0].note
    assert len(always[0].when) == 1 and {c.fact for c in core[0].when} == {"asset.firmware_major_gap", "asset.site_kind"}
    assert 'asset.site_kind == "core"' in core[0].note


def test_telecom_network_gates():
    p = load_pack("telecom_network")
    catalogue = {g["id"]: g for g in json.loads(CATALOGUE.read_text(encoding="utf-8"))}
    assert {g.id for g in p.gates} == GATES
    assert set(catalogue) >= GATES
    assert {g.id for g in p.guardrails if g.locked} == LOCKED
    assert {g.id for g in p.guardrails} == GATES
    for g in p.gates:
        assert g.params["legal_review"] == LEGAL_NOTE, g.id  # the Legal note sits in the gate's params (GateRef has no field)
    assert {g.id for g in p.gates if g.params.get("research_addition")} == {"G-NET-COV", "G-BAT-4"}
    assert {g.id for g in p.gates if g.params.get("locked")} == LOCKED
    params = {g.id: g.params for g in p.gates}
    assert params["G-NET-INV"]["stage"] == 2 and params["G-NET-CFG"]["stage"] == 3 and params["G-NET-CFG"]["fail_limit"] == 2
    exp = params["G-NET-EXP"]
    assert (exp["stage"], exp["routes"], exp["controlled_classes"]) == (4, ["resell"], ["5A002", "5A992", "5A991"])
    assert (exp["inferred_counts_as_missing"], exp["approver"]) == (True, "trade_compliance")
    cov = params["G-NET-COV"]
    assert (cov["regions"], cov["programme"]) == (["US"], "reimbursement_programme")
    assert cov["covered_manufacturers"] == ["MFR-COV-1", "MFR-COV-2"]
    assert cov["blocks"] == ["redeploy", "spare", "resell", "harvest"]
    assert params["G-BAT-4"]["classes"] == ["power_unit"] and params["G-BAT-4"]["stage"] == 6
    assert params["G-DS-1"]["routes"] == ["recycle"] and params["G-WEEE-2"]["regions"] == ["EU"]
    guards = {g.id: g for g in p.guardrails}
    assert guards["G-NET-INV"].type == "Data quality" and guards["G-NET-EXP"].approvers == ["trade_compliance"]
    assert set(p.customer_layer.editable) == GATES - LOCKED  # a locked gate is never editable


def test_telecom_network_customer_layer_and_diversions():
    cl = load_pack("telecom_network").customer_layer
    by_id = {d.op["id"]: d for d in cl.sample_diversions}
    assert list(by_id) == ["DV-TN-CORE", "DV-TN-FW", "DV-TN-SKIP"]
    assert by_id["DV-TN-CORE"].text == "unit from a core site → security inspection"
    assert by_id["DV-TN-FW"].text == "firmware behind → upgrade step"
    assert [by_id[k].op["op"] for k in by_id] == ["add_step", "add_step", "shortcut"]
    assert by_id["DV-TN-CORE"].op["stage"] == by_id["DV-TN-FW"].op["stage"] == "condition"  # stage 3
    assert [by_id[k].blocked for k in by_id] == [False, False, True]
    skip = by_id["DV-TN-SKIP"]
    assert skip.text == "urgent site outage: skip the configuration wipe"
    # no blocked_suggestion field in SampleDiversion: the suggestion ends the reason
    assert skip.reason.endswith("send an already wiped spare from the nearest pool.") and "G-NET-CFG" in skip.reason


def test_telecom_network_systems_kpis_questions():
    p = load_pack("telecom_network")
    assert [s.type for s in p.data.systems] == [
        "tn_inv", "tn_decom", "erp", "fsm", "tn_bench", "tn_spares", "tn_broker", "tn_recycler",
    ]  # fmt: skip
    assert len(p.data.systems) == 8 and all(s.adapter == "registry" for s in p.data.systems)  # adapter: true
    assert [e.name for e in p.data.entities] == [
        "Network element", "Return event", "Test result", "Compliance record", "Demand signal", "Market price", "Cost rate",
    ]  # fmt: skip
    hints = {m["field"]: m for m in p.data.mappings if m.get("kind") == "hint"}
    assert (hints["hwRevision"]["canonical"], hints["hwRevision"]["confidence"]) == ("asset.hw_revision", 0.74)
    assert hints["hwRevision"]["reason"] == "revision codes differ by vendor; needs a conversion table"
    inferred = hints["exportClassInferred"]
    assert (inferred["canonical"], inferred["confidence"], inferred["owner"]) == ("asset.export_class", 0.70, "trade_compliance")
    assert inferred["allowed_choices"] == ["ask_system_owner", "confirmed_source_field"]
    trig = next(m for m in p.data.mappings if m.get("kind") == "intake_trigger")
    assert (trig["source"], trig["resource"]) == ("tn_decom", "removal-jobs")
    assert (trig["key"], trig["reason"]) == ("serial", "decommission")
    evidence = {m["evidence_type"]: m["source"] for m in p.data.mappings if m.get("kind") == "evidence"}
    assert evidence == {
        "inventory_match": "tn_inv", "removal_job": "tn_decom", "wipe_certificate": "tn_bench", "bench_result": "tn_bench",
        "firmware": "tn_bench", "export_class": "tn_inv", "destination_screening": "tn_broker", "disposal_record": "tn_recycler",
    }  # fmt: skip
    # the export class is read only from the confirmed field, never mapped from a part number
    ec = next(m for m in p.data.mappings if m.get("evidence_type") == "export_class")
    assert ec["fields"] == ["exportClassConfirmed"]
    assert [k.id for k in p.kpis] == [
        "new_spend_avoided", "reuse_rate", "spares_filled_from_returns", "straight_through_pct", "days_to_redeploy",
        "export_holds",
    ]  # fmt: skip
    assert "21 to 12" in next(k for k in p.kpis if k.id == "days_to_redeploy").definition
    assert [a.question for a in p.analytics] == [
        "Why are we still buying new power units when returns are coming in?", "Which regions hold the most idle spares?",
    ]  # fmt: skip
    assert p.clarify is not None and len(p.clarify.options) == 2
    assert p.stories == [f"TN-{n:02d}" for n in range(1, 25)]


def test_telecom_network_valuer_replay_runtime():
    p = load_pack("telecom_network")
    assert p.valuer.carbon.d_rule == "demand"
    vp = p.valuer.params["params"]
    assert vp["plugin"] == "telecom_network"
    assert {k: vp[k] for k in vp if k not in ("plugin", "carbon_d")} == {
        "test_cost": 85, "firmware_upgrade_cost": 140, "logistics_per_unit": 60, "install_job": 220, "refurb_cost": 180,
        "spare_holding_per_month": 6, "spare_horizon_months": 12, "broker_fee_pct": 0.08, "export_compliance_cost": 150,
        "teardown_cost": 90, "board_test_cost": 25, "recycle_fee": 15, "material_per_kg": 1.8,
        "resale_needs_horizon_months": 6, "firmware_major_gap_for_upgrade": 2,
    }  # fmt: skip
    assert (vp["carbon_d"]["redeploy"], vp["carbon_d"]["spare"]) == (1, 1)
    assert p.replay.dataset == "telecom_network"
    assert p.replay.example is not None and p.replay.example["modelled"] == {
        "units": 1260, "straight_through_pct": 84, "approvals_per_day": 6, "exceptions_per_day": 4, "new_spend_avoided": 1100000,
    }  # fmt: skip
    ex = {e.id: e for e in p.runtime.exception_types}
    assert (ex["EX-TN-INV"].label, ex["EX-TN-INV"].owner_role, ex["EX-TN-INV"].action) == (
        "Unit not in network inventory",
        "inventory_lead",
        "Field team to confirm serial and site",
    )
    assert (ex["EX-TN-CFG"].label, ex["EX-TN-CFG"].owner_role, ex["EX-TN-CFG"].action) == (
        "Configuration wipe failed",
        "test_bench_lead",
        "Re-run the wipe; units held",
    )
    rules = {r["id"]: r for r in p.runtime.suggestion_rules}
    assert rules["AP-TN-EXP"]["owner"] == "trade_compliance" and rules["AP-TN-EXP"]["label"].startswith("Export control: units")
    assert rules["AL-TN-XREGION"]["params"] == {"idle_days_gt": 30} and rules["AL-TN-XREGION"]["owner"] == "spares_planner"
    assert rules["SR-TN-XREGION"]["label"] == "offer surplus across regions before a new purchase order"


def test_telecom_network_owners_resolve():
    p = load_pack("telecom_network")
    named = {r.owner for r in p.routes} | {p.author_role}
    named |= {g.owner for g in p.guardrails} | {a for g in p.guardrails for a in g.approvers}
    named |= {e.owner_role for e in p.runtime.exception_types}
    named |= {str(r["owner"]) for r in p.runtime.suggestion_rules if "owner" in r}
    named |= {str(m["owner"]) for m in p.data.mappings if "owner" in m}
    named |= {str(g.params["approver"]) for g in p.gates if "approver" in g.params}
    named |= {str(d.op["owner_role"]) for d in p.customer_layer.sample_diversions if "owner_role" in d.op}
    assert named - set(p.roles) == set()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["role_policy"]
    assert set(p.roles.values()) <= set(policy)
    assert p.roles == {
        "network_asset_manager": "Planner", "operations_director": "Approver", "trade_compliance": "Approver",
        "network_planning": "Approver", "spares_planner": "Planner", "test_bench_lead": "Engineer",
        "inventory_lead": "Warehouse Manager", "sustainability_lead": "Engineer",
    }  # fmt: skip


def test_telecom_network_samples_present():
    ex = load_pack("telecom_network").replay.example
    assert ex is not None and ex["case"] == "TN-S1"
    samples = {s["id"]: s for s in ex["samples"]}
    assert list(samples) == [f"TN-S{n}" for n in range(1, 9)]
    assert samples["TN-S1"]["facts"]["asset.model"] == "RRU-4410" and samples["TN-S1"]["facts"]["demand.open_site_demand"] is True
    s2 = samples["TN-S2"]["facts"]
    assert s2["asset.model"] == "RRU-4410" and s2["demand.open_site_demand"] is False
    assert samples["TN-S3"]["facts"]["asset.model"] == "BBU-2200"
    assert samples["TN-S4"]["facts"]["inventory.match"] is False
    assert samples["TN-S5"]["facts"]["config.wipe_fail_count"] == 2
    assert samples["TN-S6"]["facts"]["asset.manufacturer"] in {"MFR-COV-1", "MFR-COV-2"}
    s7 = samples["TN-S7"]["facts"]
    assert s7["asset.model"] == "RAD-7700" and s7["market.bid_destination"] == "overseas"
    assert s7["compliance.export_class_confirmed"] is False  # a part number never gives a class
    s8 = samples["TN-S8"]["facts"]
    assert (s8["asset.model"], s8["asset.firmware"], s8["demand.firmware_min_major"]) == ("RTR-880", "5.2", 7)
    assert all(s["serial"].startswith("SYNTN") for s in samples.values())
    assert len({s["serial"] for s in samples.values()}) == 8
