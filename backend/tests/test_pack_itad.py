"""P9-12.2: the ITAD pack data file (`packs/itad.json`, I-1). Data only: the tests read the pack through `load_pack` and check
it against the gate catalogue, the role policy and the spec's texts (story NS-IT-01). Synthetic data throughout. Where the pack
format has no named field for a spec part, the data sits in the nearest free-form field (gate `params`, `data.record_match`,
`replay.example`); each such place is named in the test that reads it. Legal: the gates summarise NIST SP 800-88 Rev. 2, IEEE
2883, lease contract terms, R2v3, e-Stewards and WEEE; Kinective's Legal team must review them before they are relied on.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from di.services.modeler.pack import Pack, PackError, load_pack, parse_pack

BACKEND = Path(__file__).resolve().parents[1]
PACK_FILE = BACKEND / "di" / "services" / "modeler" / "packs" / "itad.json"
CATALOGUE = BACKEND / "di" / "services" / "modeler" / "packs" / "gates.catalogue.json"
POLICY = BACKEND.parent / "fixtures" / "golden" / "policy.json"

LEGAL_NOTE = "Research summary, not legal advice. Kinective's Legal team must review this gate before the pack ships."
GATES = {"G-DATA-1", "G-DATA-2", "G-CON-1", "G-DS-1", "G-WEEE-2"}


def _doc() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(PACK_FILE.read_text(encoding="utf-8"))
    return doc


def test_itad_pack_validates():
    p = load_pack("itad")
    assert isinstance(p, Pack) and p.key == "itad"
    assert (p.version, p.unit, p.prefix, p.author_role) == ("1.0.0", "assets", "IT", "itad_manager")
    assert p.name == "IT asset disposition · IT lease end"
    assert (p.regions, p.legal_review.status) == (["US", "EU"], "pending")
    assert [s.label for s in p.stages] == [
        "Decommission or lease end", "Reconcile the manifest", "Sanitise and test", "Value each route", "Decide the route",
        "Execute", "Close and settle",
    ]  # fmt: skip
    assert [r.id for r in p.routes] == ["redeploy", "return_to_lessor", "resell", "harvest", "recycle"]
    assert p.stories == ["NS-IT-01", "NS-IT-02", "NS-IT-03"]
    doc = _doc()
    del doc["customer_layer"]
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert (e.value.key, e.value.version, e.value.part, e.value.part_name) == ("itad", "1.0.0", 7, "customer_layer")


def test_itad_owners_resolve():
    p = load_pack("itad")
    named = {r.owner for r in p.routes} | {p.author_role}
    named |= {g.owner for g in p.guardrails} | {a for g in p.guardrails for a in g.approvers}
    named |= {e.owner_role for e in p.runtime.exception_types}
    assert named - set(p.roles) == set()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["role_policy"]
    assert set(p.roles.values()) <= set(policy)
    assert p.roles == {
        "itad_manager": "Planner", "logistics_lead": "Warehouse Manager", "compliance": "Approver", "finance": "Finance",
    }  # fmt: skip


def test_itad_gates_from_catalogue():
    """Legal note on G-DATA-1/2, G-CON-1, G-DS-1, G-WEEE-2: it sits in each gate's params (GateRef has no field)."""
    p = load_pack("itad")
    catalogue = {g["id"]: g for g in json.loads(CATALOGUE.read_text(encoding="utf-8"))}
    assert {g.id for g in p.gates} == GATES and set(catalogue) >= GATES
    assert all("itad" in catalogue[g]["packs"] for g in GATES)  # the catalogue lists the pack it serves
    assert {g.id for g in p.guardrails} == GATES and {g.id for g in p.guardrails if g.locked} == {"G-DATA-1"}
    params = {g.id: g.params for g in p.gates}
    assert all(v["legal_review"] == LEGAL_NOTE for v in params.values())
    assert (params["G-DATA-1"]["stage"], params["G-DATA-1"]["locked"]) == (3, True)
    assert params["G-DATA-2"]["stage"] == 3 and params["G-CON-1"]["stage"] == 2
    assert (params["G-DS-1"]["stage"], params["G-DS-1"]["routes"]) == (6, ["recycle", "harvest"])
    assert (params["G-WEEE-2"]["stage"], params["G-WEEE-2"]["regions"]) == (6, ["EU"])
    assert set(p.customer_layer.editable) == GATES - {"G-DATA-1"}  # a locked gate is not editable


def test_itad_valuer_exceptions_and_record_match():
    p = load_pack("itad")
    assert p.valuer.kind == "standard"
    vp = p.valuer.params["params"]
    assert vp["residual_start"] == {"laptop": 0.35, "desktop": 0.20, "server": 0.30, "network": 0.25}
    got = (vp["residual_monthly_decay"], vp["resell_fee_pct"], vp["logistics_per_unit"], vp["recycle_fee"])
    assert got == (0.03, 0.12, 18, 6)
    assert vp["carbon_d"]["redeploy"] == 1 and vp["carbon_d"]["against"] == "a named request"
    ex = {e.id: (e.label, e.owner_role) for e in p.runtime.exception_types}
    assert ex == {
        "EX-IT-MISSING": ("Serial on the manifest not received", "logistics_lead"),
        "EX-IT-EXTRA": ("Serial received but not on the manifest", "logistics_lead"),
    }
    rm = p.data.record_match
    assert rm is not None and (rm["source_type"], rm["field"], rm["mode"]) == ("it_logistics", "asset.pickup", "exception")
    assert (rm["missing_type"], rm["extra_type"], rm["critical"]) == ("EX-IT-MISSING", "EX-IT-EXTRA", ["EX-IT-MISSING"])
    systems = {s.type: s.system_of_record for s in p.data.systems}
    assert systems == {"it_cmdb": True, "it_logistics": False, "erp": False}
    assert all(s.adapter == "registry" for s in p.data.systems)


def test_itad_kpis_questions_samples():
    p = load_pack("itad")
    assert [k.id for k in p.kpis] == [
        "recovery_per_asset", "days_to_settle", "redeploy_rate", "straight_through_pct", "sanitisation_exceptions",
        "manifest_mismatches",
    ]  # fmt: skip
    assert [a.question for a in p.analytics] == [
        "Which customers' pickups have the most missing serials?",
        "How fast does residual value fall by class?",
    ]
    ex = p.replay.example
    assert ex is not None and [s["id"] for s in ex["samples"]] == [f"IT-S{n}" for n in range(1, 9)]
    by = {s["id"]: s["facts"] for s in ex["samples"]}
    assert by["IT-S2"]["condition.erasures"][0]["method"] == "clear" and by["IT-S2"]["asset.media"][0]["type"] == "ssd"
    assert by["IT-S3"]["condition.erasures"][0]["verification"] == "failed"
    assert by["IT-S4"]["asset.lessor_return_required"] is True and by["IT-S4"]["asset.consent_to_resell"] is False
    assert by["IT-S1"]["market.new_price"] == 1400
