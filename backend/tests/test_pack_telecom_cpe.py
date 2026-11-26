"""P9-12.6: the telecom CPE pack data file (`packs/telecom_cpe.json`, I-1). Data only: the tests read the pack through `load_pack`
and check it against the gate catalogue, the role policy and the spec's texts (stories NS-CPE-01 to NS-CPE-03). Synthetic data
throughout; the carbon factors are placeholders. Where the pack format has no named field for a spec part, the data sits in the
nearest free-form field (gate `params`, `valuer.params.params`, `replay.example`); each such place is named in the test that reads
it. Legal: the gates summarise NIST SP 800-88 Rev. 2, R2v3, e-Stewards and WEEE; Kinective's Legal team must review them before
they are relied on.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from di.services.modeler.pack import Pack, PackError, load_pack, parse_pack

BACKEND = Path(__file__).resolve().parents[1]
PACK_FILE = BACKEND / "di" / "services" / "modeler" / "packs" / "telecom_cpe.json"
CATALOGUE = BACKEND / "di" / "services" / "modeler" / "packs" / "gates.catalogue.json"
POLICY = BACKEND.parent / "fixtures" / "golden" / "policy.json"

LEGAL_NOTE = "Research summary, not legal advice. Kinective's Legal team must review this gate before the pack ships."
GATES = {"G-DATA-1", "G-DS-1", "G-WEEE-2"}


def _doc() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(PACK_FILE.read_text(encoding="utf-8"))
    return doc


def test_telecom_cpe_pack_validates():
    p = load_pack("telecom_cpe")
    assert isinstance(p, Pack) and p.key == "telecom_cpe"
    assert (p.version, p.unit, p.prefix) == ("1.0.0", "devices", "CPE")
    assert p.name == "Telecom CPE · home routers and set-top boxes"
    assert p.valuer.kind == "standard" and p.valuer.params["params"]["decision_unit"] == "lot"
    assert [r.id for r in p.routes] == ["refurbish_redeploy", "broker", "harvest", "recycle"]
    assert p.stories == ["NS-CPE-01", "NS-CPE-02", "NS-CPE-03"]
    assert p.valuer.carbon.set == "cpe_gsma_2025"
    doc = _doc()
    del doc["customer_layer"]
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert (e.value.key, e.value.version, e.value.part, e.value.part_name) == ("telecom_cpe", "1.0.0", 7, "customer_layer")


def test_telecom_cpe_owners_resolve():
    p = load_pack("telecom_cpe")
    named = {r.owner for r in p.routes} | {p.author_role}
    named |= {g.owner for g in p.guardrails} | {a for g in p.guardrails for a in g.approvers}
    named |= {e.owner_role for e in p.runtime.exception_types}
    assert named - set(p.roles) == set()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["role_policy"]
    assert set(p.roles.values()) <= set(policy)
    assert p.roles["cpe_operations_lead"] == "Planner" and p.author_role == "cpe_operations_lead"
    sample = (p.replay.example or {})["standing_policy"]  # the sample of I-11, owned by the operations lead
    assert sample["text"] == "lots under $20,000 are approved by policy" and sample["owner_role"] == "cpe_operations_lead"
    assert (sample["max_value"], sample["min_confidence"]) == (20000, 0.75)


def test_telecom_cpe_gates_from_catalogue():
    """Legal note on G-DATA-1, G-DS-1, G-WEEE-2: it sits in each gate's params (GateRef has no field)."""
    p = load_pack("telecom_cpe")
    catalogue = {g["id"]: g for g in json.loads(CATALOGUE.read_text(encoding="utf-8"))}
    assert {g.id for g in p.gates} == GATES and set(catalogue) >= GATES
    assert all("telecom_cpe" in catalogue[g]["packs"] for g in GATES)  # the catalogue lists the pack it serves
    assert {g.id for g in p.guardrails} == GATES and {g.id for g in p.guardrails if g.locked} == {"G-DATA-1"}
    params = {g.id: g.params for g in p.gates}
    assert all(v["legal_review"] == LEGAL_NOTE for v in params.values())
    assert (params["G-DATA-1"]["stage"], params["G-DATA-1"]["locked"]) == (3, True)
    assert params["G-DATA-1"]["accept_methods_for_redeploy"] == ["clear"]  # a factory reset counts as "clear"
    assert params["G-DS-1"]["stage"] == 6 and params["G-DS-1"]["routes"] == ["recycle", "harvest"]
    assert (params["G-WEEE-2"]["stage"], params["G-WEEE-2"]["regions"]) == (6, ["EU"])
    assert set(p.customer_layer.editable) == GATES - {"G-DATA-1"}  # a locked gate is not editable


def test_telecom_cpe_valuer_data_and_sources():
    p = load_pack("telecom_cpe")
    systems = {s.type: s.system_of_record for s in p.data.systems}
    assert systems == {"cpe_bss": True, "erp": False}
    assert [k.id for k in p.kpis][:2] == ["recovery_per_device", "redeploy_rate"] and len(p.kpis) == 6
    assert len(p.analytics) == 2
    ex = p.replay.example
    assert ex is not None and [s["id"] for s in ex["samples"]] == [f"CPE-S{n}" for n in range(1, 5)]
