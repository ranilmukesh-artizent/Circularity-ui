"""P9-12.4: the rental fleet pack data file (`packs/rental_fleet.json`, I-1). Data only: the tests read the pack through
`load_pack` and check it against the gate catalogue, the role policy and the spec's texts (story NS-RC-01). Synthetic data
throughout. Where the pack format has no named field for a spec part, the data sits in the nearest free-form field (gate
`params`, `replay.example`). Legal: G-SAFE-1 and G-DS-1 summarise lifting and access equipment safety certification and
downstream vendor certification; Kinective's Legal team must review them before they are relied on.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from di.services.modeler.pack import Pack, PackError, load_pack, parse_pack
from di.services.modeler.valuers import standard

BACKEND = Path(__file__).resolve().parents[1]
PACK_FILE = BACKEND / "di" / "services" / "modeler" / "packs" / "rental_fleet.json"
CATALOGUE = BACKEND / "di" / "services" / "modeler" / "packs" / "gates.catalogue.json"
POLICY = BACKEND.parent / "fixtures" / "golden" / "policy.json"

LEGAL_NOTE = "Research summary, not legal advice. Kinective's Legal team must review this gate before the pack ships."


def _doc() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(PACK_FILE.read_text(encoding="utf-8"))
    return doc


def test_rental_fleet_pack_validates():
    p = load_pack("rental_fleet")
    assert isinstance(p, Pack) and p.key == "rental_fleet"
    assert (p.version, p.unit, p.prefix, p.regions) == ("1.0.0", "machines", "RF", ["US"])
    assert p.name == "Rental and construction fleets"
    assert [s.label for s in p.stages] == [
        "Off-rent return", "Check-in inspection", "Hours and condition", "Value each route", "Decide the route", "Execute",
        "Close and learn",
    ]  # fmt: skip
    assert [r.id for r in p.routes] == [
        "rerent", "rebuild", "transfer_branch", "retail", "auction", "dealer", "parts", "scrap",
    ]
    assert p.valuer.kind == "standard" and standard.validate_valuer(p) == []
    assert "NS-RC-01" in p.stories
    doc = _doc()
    del doc["customer_layer"]
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert (e.value.key, e.value.version, e.value.part_name) == ("rental_fleet", "1.0.0", "customer_layer")


def test_rental_fleet_owners_resolve():
    p = load_pack("rental_fleet")
    named = {r.owner for r in p.routes} | {p.author_role}
    named |= {g.owner for g in p.guardrails} | {a for g in p.guardrails for a in g.approvers}
    named |= {e.owner_role for e in p.runtime.exception_types}
    assert named - set(p.roles) == set()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["role_policy"]
    assert set(p.roles.values()) <= set(policy)
    assert p.roles == {
        "fleet_director": "Planner", "branch_manager": "Planner", "approver": "Approver", "finance": "Finance",
    }  # fmt: skip


def test_rental_fleet_gates_from_catalogue():
    """Legal note on G-SAFE-1 and G-DS-1: it sits in each gate's params (GateRef has no field)."""
    p = load_pack("rental_fleet")
    catalogue = {g["id"]: g for g in json.loads(CATALOGUE.read_text(encoding="utf-8"))}
    assert {g.id for g in p.gates} == {"G-SAFE-1", "G-DS-1"}
    assert all("rental_fleet" in catalogue[g.id]["packs"] for g in p.gates)
    params = {g.id: g.params for g in p.gates}
    assert all(v["legal_review"] == LEGAL_NOTE for v in params.values())
    assert params["G-SAFE-1"]["stage"] == 3 and set(params["G-SAFE-1"]["classes"]) == {"scissor_lift", "telehandler"}
    assert (params["G-DS-1"]["stage"], params["G-DS-1"]["routes"]) == (6, ["scrap"])
    assert {g.id for g in p.guardrails} == {"G-SAFE-1", "G-DS-1"}


def test_rental_fleet_valuer_params_kpis_samples():
    p = load_pack("rental_fleet")
    vp = p.valuer.params["params"]
    got = (vp["horizon_months"], vp["prep_cost"], vp["maintenance_per_hour"], vp["expected_hours"])
    assert got == (6, 1200, 4, 900)
    assert (vp["rebuild_min_age_years"], vp["rebuild_extra_years"], vp["rebuild_downtime_months"]) == (7, 3, 2)
    assert (vp["retail_cost_pct"], vp["transport_cost"], vp["auction_factor"], vp["auction_fees"]) == (0.03, 900, 0.88, 1800)
    tables = p.valuer.params["tables"]
    assert tables["monthly_rate"]["excavator_20t"] == 7500 and tables["annual_margin"]["excavator_20t"] == 14000
    assert tables["rebuild_cost"]["excavator_20t"] == 38000
    assert len(p.kpis) == 6 and len(p.analytics) == 2
    ex = p.replay.example
    assert ex is not None and [s["id"] for s in ex["samples"]] == [f"RF-S{n}" for n in range(1, 9)]
    s1 = ex["samples"][0]["facts"]
    assert (s1["asset.hours"], s1["asset.age_years"], s1["asset.book_value"], s1["demand.branch_utilisation"]) == (
        6200, 8, 52000, 0.72,
    )
