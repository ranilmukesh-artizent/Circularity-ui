"""P9-9.1: the used-car pack data file (`packs/used_cars.json`, I-1). Data only: the tests read the pack through
`load_pack` and check it against the gate catalogue, the role policy and the spec's texts. Synthetic data throughout.

Where the pack format (P9-1.1) has no named field for a spec part, the data sits in the nearest free-form field (gate
`params`, `data.mappings`, `runtime.suggestion_rules`, `replay.example`); each such place is named in the test that reads it.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from di.services.modeler.pack import Pack, PackError, load_pack, parse_pack

BACKEND = Path(__file__).resolve().parents[1]
PACK_FILE = BACKEND / "di" / "services" / "modeler" / "packs" / "used_cars.json"
CATALOGUE = BACKEND / "di" / "services" / "modeler" / "packs" / "gates.catalogue.json"
POLICY = BACKEND.parent / "fixtures" / "golden" / "policy.json"

LEGAL_NOTE = "Research summary, not legal advice. Kinective's Legal team must review this gate before the pack ships."
LOCKED = {"G-VEH-TITLE", "G-VEH-ODO", "G-VEH-RECALL"}
GATES = LOCKED | {"G-VEH-BRAND", "G-VEH-SALV"}


def _doc() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(PACK_FILE.read_text(encoding="utf-8"))
    return doc


def test_used_cars_pack_validates():
    p = load_pack("used_cars")
    assert isinstance(p, Pack) and p.key == "used_cars"
    doc = _doc()
    del doc["customer_layer"]
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert (e.value.key, e.value.version, e.value.part, e.value.part_name) == ("used_cars", "1.9.0", 7, "customer_layer")


def test_used_cars_identity_and_stages():
    p = load_pack("used_cars")
    assert (p.version, p.unit, p.prefix, p.author_role) == ("1.9.0", "cars", "UC", "remarketing_director")
    assert p.name == "Used vehicles · lease and trade-in returns"
    assert (p.industry, p.regions, p.legal_review.status) == ("Automotive remarketing", ["US"], "pending")
    assert p.data_licence == "synthetic, no third-party data"
    assert [s.label for s in p.stages] == [
        "Car returned", "Title and finance", "Inspect and estimate", "Price by channel", "Decide the channel",
        "Recondition and list", "Sold and learn",
    ]  # fmt: skip
    assert {s.agent: s.autonomy for s in p.stages} == {
        "intake": "alone", "condition": "limits", "valuation": "alone", "routing": "limits",
        "follow-through": "limits", "analytics": "alone",
    }  # fmt: skip
    assert {s.confidence for s in p.stages} == {0.75}
    assert [r.id for r in p.routes] == ["retail", "auction", "dealer_trade", "salvage"]
    assert p.prompts[0].startswith("Lease returns to best channel: when a leased car or a trade-in comes back,")
    assert p.prompts[0].endswith("Reconditioning over $2,500 needs the used-car manager.")
    assert (p.prompts[1], p.prompts[2]) == ("Trade-ins: retail or wholesale", "Move ageing stock between lots")
    assert [c.id for c in p.classes] == ["car_ice", "car_ev"]
    assert (p.grades.graded_by, p.grades.scale) == ("read", ["A", "B", "C", "D"])
    assert p.grades.map_from == {"5": "A", "4": "B", "3": "C", "2": "D", "1": "D"}


def test_used_cars_gates_from_catalogue():
    p = load_pack("used_cars")
    catalogue = {g["id"]: g for g in json.loads(CATALOGUE.read_text(encoding="utf-8"))}
    assert {g.id for g in p.gates} == GATES
    assert set(catalogue) >= GATES
    assert {g.id for g in p.guardrails if g.locked} == LOCKED
    assert {g.id for g in p.guardrails} == GATES | {"AP-UC-RECON"}
    for g in p.gates:
        assert g.params["legal_review"] == LEGAL_NOTE, g.id  # the Legal note sits in the gate's params (GateRef has no field)
    assert {g.id for g in p.gates if g.params.get("research_addition")} == {"G-VEH-ODO", "G-VEH-BRAND", "G-VEH-SALV"}
    params = {g.id: g.params for g in p.gates}
    assert params["G-VEH-ODO"]["tolerance_miles"] == 500
    assert params["G-VEH-RECALL"]["check_max_age_days"] == 30
    ap = next(g for g in p.guardrails if g.id == "AP-UC-RECON")
    assert (ap.type, ap.stage, ap.param.field, ap.param.value) == ("Approval", "decide", "condition.recon_estimate", 2500)  # type: ignore[union-attr]


def test_used_cars_systems_kpis_questions():
    p = load_pack("used_cars")
    assert len(p.data.systems) == 8
    adapter = {s.type: s.adapter for s in p.data.systems}
    assert sum(a == "registry" for a in adapter.values()) == 7
    assert adapter["uc_bodyshop"] == "needs_connector"
    assert len(p.kpis) == 6 and len(p.analytics) == 2
    assert p.clarify is not None and len(p.clarify.options) == 2
    assert sum(1 for g in p.gates if g.params.get("research_addition")) == 3


def test_used_cars_owners_resolve():
    p = load_pack("used_cars")
    named = {r.owner for r in p.routes} | {p.author_role}
    named |= {g.owner for g in p.guardrails} | {a for g in p.guardrails for a in g.approvers}
    named |= {e.owner_role for e in p.runtime.exception_types}
    named |= {str(r["owner"]) for r in p.runtime.suggestion_rules if "owner" in r}
    assert named - set(p.roles) == set()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["role_policy"]
    assert set(p.roles.values()) <= set(policy)
    assert p.roles["used_car_manager"] == "Approver" and p.roles["lot_manager"] == "Planner"


def test_used_cars_samples_present():
    ex = load_pack("used_cars").replay.example
    assert ex is not None and ex["case"] == "UC-S1"
    samples = {s["id"]: s for s in ex["samples"]}
    assert list(samples) == [f"UC-S{n}" for n in range(1, 9)]
    s4 = samples["UC-S4"]["facts"]
    assert (s4["asset.mileage_at_return"], s4["asset.mileage_lease_record"]) == (61240, 46240)
    assert samples["UC-S1"]["vin"] == "SYNUC000000000001" and samples["UC-S6"]["vin"] == "SYNUC000000000044"
    assert all(len(s["vin"]) == 17 and s["vin"].startswith("SYNUC") for s in samples.values())
