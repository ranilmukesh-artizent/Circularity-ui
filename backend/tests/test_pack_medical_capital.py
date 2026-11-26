"""P9-12.9: the medical capital equipment pack data file (`packs/medical_capital.json`, I-1; stories NS-MED-01 to NS-MED-03). The
tests read the pack through `load_pack` and check it against the gate catalogue and the role policy. Where the pack format has no
named field for a spec part, the data sits in the nearest free-form field (gate `params`); the Legal note is in each gate's
`params.legal_review`. Synthetic data throughout. Legal: the gates summarise FDA remanufacturing guidance (May 2024), EU MDR
Art. 17, MDR economic operators and UDI, and HIPAA and GDPR sanitisation; Kinective's Legal team must review them before they
are relied on.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from di.services.modeler.pack import Pack, PackError, load_pack, parse_pack

BACKEND = Path(__file__).resolve().parents[1]
PACK_FILE = BACKEND / "di" / "services" / "modeler" / "packs" / "medical_capital.json"
CATALOGUE = BACKEND / "di" / "services" / "modeler" / "packs" / "gates.catalogue.json"
POLICY = BACKEND.parent / "fixtures" / "golden" / "policy.json"

LEGAL_NOTE = "Research summary, not legal advice. Kinective's Legal team must review this gate before the pack ships."
GATES = {"G-MED-1", "G-MED-2", "G-MED-3", "G-DATA-3", "G-MED-FSN"}


def _doc() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(PACK_FILE.read_text(encoding="utf-8"))
    return doc


def test_medical_capital_pack_validates():
    p = load_pack("medical_capital")
    assert isinstance(p, Pack) and p.key == "medical_capital"
    assert (p.version, p.unit, p.prefix, p.regions) == ("1.0.0", "devices", "MC", ["US", "EU"])
    assert p.name == "Medical capital equipment · trade-in, refurbish, resale"
    assert [r.id for r in p.routes] == ["refurbish_resell", "resell_as_is", "harvest", "recycle"]
    assert p.valuer.kind == "standard" and p.legal_review.status == "pending"
    assert p.stories == ["NS-MED-01", "NS-MED-02", "NS-MED-03"]
    assert {c.id for c in p.classes if c.attrs.patient_data} == {"imaging_system", "patient_monitor"}
    doc = _doc()
    del doc["customer_layer"]
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert (e.value.key, e.value.version, e.value.part_name) == ("medical_capital", "1.0.0", "customer_layer")


def test_medical_capital_owners_resolve():
    p = load_pack("medical_capital")
    named = {r.owner for r in p.routes} | {p.author_role}
    named |= {g.owner for g in p.guardrails} | {a for g in p.guardrails for a in g.approvers}
    named |= {e.owner_role for e in p.runtime.exception_types}
    assert named - set(p.roles) == set()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["role_policy"]
    assert set(p.roles.values()) <= set(policy)
    assert p.roles == {"refurbishment_lead": "Planner", "clinical_engineering": "Approver", "regulatory": "Approver"}


def test_medical_capital_gates_from_catalogue():
    """Legal note on G-MED-1, G-MED-2, G-MED-3, G-DATA-3 and G-MED-FSN: it sits in each gate's params (GateRef has no field)."""
    p = load_pack("medical_capital")
    catalogue = {g["id"]: g for g in json.loads(CATALOGUE.read_text(encoding="utf-8"))}
    assert {g.id for g in p.gates} == GATES and set(catalogue) >= GATES
    assert all("medical_capital" in catalogue[g]["packs"] for g in GATES)
    params = {g.id: g.params for g in p.gates}
    assert all(v["legal_review"] == LEGAL_NOTE for v in params.values())
    stages = {g: v["stage"] for g, v in params.items()}
    assert stages == {"G-MED-1": 5, "G-MED-2": 2, "G-MED-3": 4, "G-DATA-3": 6, "G-MED-FSN": 3}
    assert params["G-MED-1"]["manufacturer_status_markets"] == []
    assert set(params["G-DATA-3"]["routes"]) == {"refurbish_resell", "resell_as_is", "harvest", "recycle"}
    assert {g.id for g in p.guardrails} == GATES
