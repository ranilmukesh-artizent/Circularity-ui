"""P9-11.1: the medical rental pack data file (`packs/medical_rental.json`, I-1). Data only: the tests read the pack through
`load_pack` and check it against the gate catalogue, the role policy and the spec's texts. Synthetic data throughout.

Where the pack format (P9-1.1) has no named field for a spec part, the data sits in the nearest free-form field (gate
`params`, `data.mappings`, `runtime.suggestion_rules`, `replay.example`, a diversion's `op`); each such place is named in
the test that reads it.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from di.services.modeler.pack import Pack, PackError, load_pack, parse_pack

BACKEND = Path(__file__).resolve().parents[1]
PACK_FILE = BACKEND / "di" / "services" / "modeler" / "packs" / "medical_rental.json"
CATALOGUE = BACKEND / "di" / "services" / "modeler" / "packs" / "gates.catalogue.json"
POLICY = BACKEND.parent / "fixtures" / "golden" / "policy.json"

LEGAL_NOTE = "Research summary, not legal advice. Kinective's Legal team must review this gate before the pack ships."
PACK_NOTE = (
    "Decontamination, maintenance-duty, recall and remanufacturing rules summarised; several wordings unconfirmed. "
    "Kinective's Legal team must review before shipping."
)
LOCKED = {"G-MED-DECON", "G-MED-SVC"}
GATES = LOCKED | {"G-MED-FSN", "G-MED-REFURB", "G-DATA-3"}


def _doc() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(PACK_FILE.read_text(encoding="utf-8"))
    return doc


def test_medical_rental_pack_validates():
    p = load_pack("medical_rental")
    assert isinstance(p, Pack) and p.key == "medical_rental"
    doc = _doc()
    del doc["customer_layer"]
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert (e.value.key, e.value.version, e.value.part, e.value.part_name) == ("medical_rental", "1.6.0", 7, "customer_layer")


def test_medical_rental_identity_and_stages():
    p = load_pack("medical_rental")
    assert (p.version, p.unit, p.prefix, p.author_role) == ("1.6.0", "devices", "MR", "rental_fleet_director")
    assert p.name == "Medical rental · hospital equipment"
    assert (p.industry, p.regions, p.legal_review.status) == ("Medical equipment rental", ["US", "UK"], "pending")
    ex = p.replay.example or {}
    assert ex["legal_review_note"] == PACK_NOTE  # LegalReview has no note field: the note sits in replay.example
    assert [s.label for s in p.stages] == [
        "Device returned", "Decontamination", "Inspect and test", "Value each route", "Decide the route", "Execute",
        "Close and learn",
    ]  # fmt: skip
    assert {s.agent: s.autonomy for s in p.stages} == {
        "intake": "alone", "condition": "limits", "valuation": "alone", "routing": "limits",
        "follow-through": "limits", "analytics": "alone",
    }  # fmt: skip
    assert {s.confidence for s in p.stages} == {0.75}
    assert [r.id for r in p.routes] == ["rerent", "service_rerent", "refurbish", "retire"]
    assert {r.id: (r.app, r.owner, r.lead_days) for r in p.routes} == {
        "rerent": ("mr_rental", "operations_manager", 1),
        "service_rerent": ("mr_biomed", "biomedical_engineer", 2),
        "refurbish": ("mr_biomed", "clinical_engineering", 10),
        "retire": ("mr_disposal", "fleet_manager", 7),
    }
    assert {r.id: r.instructions for r in p.routes}["retire"] == ["data_sanitisation", "disposal_collection", "write_off"]
    assert p.prompts[0].startswith("Return to re-rent: when a pump, monitor, bed or other rental device comes back")
    assert p.prompts[0].endswith("A repair over $1,000 needs the fleet manager.")
    assert p.prompts[1:] == ["Plan servicing around demand", "Retire or refurbish ageing devices"]
    assert ex["asset_fields"] == ["model", "service interval", "certification", "decontamination"]  # no pack field for it
    assert [c.id for c in p.classes] == [
        "infusion_pump", "patient_monitor", "electric_bed", "syringe_driver", "transport_ventilator", "pulse_oximeter",
    ]  # fmt: skip
    assert all(c.attrs.regulated and c.attrs.serialised for c in p.classes)
    assert {c.id for c in p.classes if c.attrs.patient_data} == {"patient_monitor"}
    assert p.grades.graded_by == "read"  # condition comes from the biomedical service system; no grade is computed


def test_medical_rental_clarify_rule_options():
    p = load_pack("medical_rental")
    assert p.clarify is not None
    assert p.clarify.question == "Should servicing be brought forward when it falls due within the next rental?"
    assert [o.label for o in p.clarify.options] == ["Yes, always service first", "Only if the rental is longer than 30 days"]
    always, longer = (json.loads(o.adds)[0] for o in p.clarify.options)
    for op in (always, longer):
        assert (op["id"], op["op"], op["stage"]) == ("BR-MR-SVC", "business_rule", "decide")
        assert op["text"] == "service due within the next rental → service then re-rent"
    assert "request.days" not in always["scope"] and longer["scope"].endswith("request.days > 30")


def test_medical_rental_gates():
    p = load_pack("medical_rental")
    catalogue = {g["id"]: g for g in json.loads(CATALOGUE.read_text(encoding="utf-8"))}
    assert {g.id for g in p.gates} == GATES
    assert set(catalogue) >= GATES
    assert {g.id for g in p.guardrails if g.locked} == LOCKED
    assert {g.id for g in p.guardrails} == GATES | {"AP-MR-REPAIR"}
    for g in p.gates:
        assert g.params["legal_review"] == LEGAL_NOTE, g.id  # the Legal note sits in the gate's params (GateRef has no field)
    assert {g.id for g in p.gates if g.params.get("research_addition")} == {"G-MED-FSN", "G-MED-REFURB", "G-DATA-3"}
    params = {g.id: g.params for g in p.gates}
    assert params["G-MED-DECON"]["stage"] == 2 and params["G-MED-DECON"]["routes"] == "all"
    assert params["G-MED-DECON"]["record_must_end_after_checkin"] is True and params["G-MED-DECON"]["locked"] is True
    assert (params["G-MED-SVC"]["stage"], params["G-MED-SVC"]["routes"]) == (3, ["rerent", "service_rerent"])
    assert (params["G-MED-REFURB"]["stage"], params["G-MED-REFURB"]["manufacturer_status_markets"]) == (5, [])
    assert params["G-DATA-3"]["classes"] == ["patient_monitor"] and params["G-DATA-3"]["routes"] == ["retire"]
    ap = next(g for g in p.guardrails if g.id == "AP-MR-REPAIR")
    assert ap.text == "Repair over $1,000 → fleet manager"
    assert (ap.type, ap.stage, ap.param.field, ap.param.value) == ("Approval", "decide", "intervention.repair_estimate", 1000)  # type: ignore[union-attr]
    assert ap.approvers == ["fleet_manager"]
    rule = next(r for r in p.runtime.suggestion_rules if r["id"] == "AP-MR-REPAIR")  # the op "gt" has no GuardParam field
    assert (rule["op"], rule["field"], rule["value"], rule["owner"]) == ("gt", "intervention.repair_estimate", 1000, "fleet_manager")
    cl = p.customer_layer
    assert set(cl.editable) == {"G-MED-FSN", "G-MED-REFURB", "G-DATA-3", "AP-MR-REPAIR"}  # the locked two are not editable
    ops = {d.op["id"]: d for d in cl.sample_diversions}
    assert {k: v.op["op"] for k, v in ops.items()} == {"DV-MR-ISO": "add_step", "DV-MR-SAME": "shortcut", "DV-MR-SKIP": "shortcut"}
    assert [d.blocked for d in ops.values()] == [False, False, True]
    assert ops["DV-MR-SKIP"].op["blocked_suggestion"] == "dispatch an already decontaminated unit from the nearest depot"
    assert "G-MED-DECON" in ops["DV-MR-SKIP"].reason


def test_medical_rental_systems_kpis_questions():
    p = load_pack("medical_rental")
    assert [s.type for s in p.data.systems] == [
        "mr_rental", "mr_assets", "mr_decon", "mr_biomed", "crm", "erp", "mr_parts", "mr_disposal",
    ]  # fmt: skip
    assert all(s.adapter == "registry" for s in p.data.systems)  # the spec's "adapter: true"
    assert [e.name for e in p.data.entities] == [
        "Device", "Return event", "Test result", "Compliance record", "Demand signal", "Cost rate", "Location",
    ]  # fmt: skip
    hints = {m["field"]: m for m in p.data.mappings if m["kind"] == "hint"}
    assert (hints["cycleEndedAt"]["canonical"], hints["cycleEndedAt"]["confidence"]) == ("condition.decon_ended_at", 0.79)
    assert hints["cycleEndedAt"]["reason"] == "two timestamps; the end of the cycle was chosen"
    assert (hints["pmCode"]["canonical"], hints["pmCode"]["confidence"]) == ("condition.pm_code", 0.73)
    assert hints["pmCode"]["reason"] == "meaning taken from the service manual"
    trig = next(m for m in p.data.mappings if m["kind"] == "intake_trigger")
    assert (trig["source"], trig["resource"], trig["reason"], trig["key"]) == ("mr_rental", "returns", "rental_return", "asset_tag")
    ev = {m["evidence_type"]: m["source"] for m in p.data.mappings if m["kind"] == "evidence"}
    assert set(ev) == {
        "decon_record", "pm_record", "electrical_safety", "certification", "correction_status", "servicing_assessment",
        "sanitisation_record",
    }  # fmt: skip
    assert (ev["decon_record"], ev["servicing_assessment"], ev["sanitisation_record"]) == ("mr_decon", "mr_biomed", "mr_disposal")
    assert [k.id for k in p.kpis] == [
        "fleet_utilisation", "turnaround_days", "rerented_within_48h", "straight_through_pct", "compliance_exceptions",
        "repairs_over_limit",
    ]  # fmt: skip
    assert "2.9" in p.kpis[1].definition and "1.6" in p.kpis[1].definition and "modelled" in p.kpis[1].definition
    assert len(p.analytics) == 2
    wq = (p.replay.example or {})["worked_questions"]  # AnalyticsQuestion has no id field
    assert wq == {"WQ-MR-1": "Why did turnaround slip at the East depot?", "WQ-MR-2": "Which device models are retired earliest?"}
    assert [a.question for a in p.analytics] == list(wq.values())
    assert p.clarify is not None and len(p.clarify.options) == 2
    assert sum(1 for g in p.gates if g.params.get("research_addition")) == 3
    v = p.valuer
    assert (v.kind, v.carbon.d_rule) == ("standard", "transport_only")
    vp = v.params["params"]
    assert vp["plugin"] == "medical_rental" and vp["daily_rate"]["transport_ventilator"] == 55
    assert (vp["transport_per_mile"], vp["refurb_min_age_years"], vp["utilisation_rate"]) == (1.40, 6, 0.7)
    rep = (p.replay.example or {})["modelled"]
    assert p.replay.dataset == "medical_rental"
    assert (rep["devices"], rep["straight_through_pct"], rep["approvals_per_day"], rep["exceptions_per_day"]) == (1880, 83, 7, 5)
    assert rep["utilisation_points"] == 6
    ex = {e.id: (e.owner_role, e.label) for e in p.runtime.exception_types}
    assert ex["EX-MR-DECON"] == ("decontamination_lead", "No decontamination record")
    assert ex["EX-MR-CERT"] == ("biomedical_engineer", "Certification expires during the rental")
    alert = next(r for r in p.runtime.suggestion_rules if r["id"] == "AL-MR-TURNAROUND")
    assert alert["params"] == {"avg_turnaround_days_gt": 2.5, "window_days": 14} and alert["owner"] == "operations_manager"
    assert any(r["id"] == "SR-MR-SVCWEEK" for r in p.runtime.suggestion_rules)
    assert p.stories == [f"MR-{n:02d}" for n in range(1, 24)]


def test_medical_rental_owners_resolve():
    p = load_pack("medical_rental")
    named = {r.owner for r in p.routes} | {p.author_role}
    named |= {g.owner for g in p.guardrails} | {a for g in p.guardrails for a in g.approvers}
    named |= {e.owner_role for e in p.runtime.exception_types}
    named |= {str(r["owner"]) for r in p.runtime.suggestion_rules if "owner" in r}
    assert named - set(p.roles) == set()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["role_policy"]
    assert set(p.roles.values()) <= set(policy)
    assert p.roles == {
        "rental_fleet_director": "Planner", "operations_director": "Approver", "fleet_manager": "Approver",
        "clinical_engineering": "Approver", "biomedical_engineer": "Engineer", "decontamination_lead": "Warehouse Manager",
        "operations_manager": "Planner",
    }  # fmt: skip


def test_medical_rental_samples_present():
    ex = load_pack("medical_rental").replay.example
    assert ex is not None and ex["case"] == "MR-S1"
    samples = {s["id"]: s for s in ex["samples"]}
    assert list(samples) == [f"MR-S{n}" for n in range(1, 9)]
    assert samples["MR-S1"]["serial"] == "SYN-MR-IP-0001"
    assert all(s["serial"].startswith("SYN-MR-") for s in samples.values())
    f = {k: v["facts"] for k, v in samples.items()}
    assert f["MR-S2"]["condition.certification_days_left"] == 12
    assert f["MR-S3"]["condition.decon_record"] is False
    assert f["MR-S4"]["condition.decon_ended_at"] < f["MR-S4"]["asset.checked_in_at"]
    assert f["MR-S5"]["asset.class"] == "patient_monitor" and f["MR-S5"]["intervention.repair_estimate"] == 1350
    assert f["MR-S6"]["condition.field_safety_notice_open"] is True
    assert f["MR-S7"]["asset.class"] == "electric_bed" and f["MR-S7"]["asset.age_years"] == 7
    assert f["MR-S8"]["asset.class"] == "patient_monitor" and f["MR-S8"]["asset.age_years"] == 4
    assert f["MR-S8"]["intervention.repair_estimate"] > f["MR-S8"]["asset.residual_value"]
