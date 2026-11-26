"""P9-12.7: the battery pack data file (`packs/battery.json`, I-1; stories NS-BAT-01, NS-BAT-02, NS-BAT-03). The tests read the
pack through `load_pack` and check it against the gate catalogue, the role policy and the spec's parameters. Synthetic data
throughout. Legal: the gates summarise Reg. (EU) 2023/1542 (battery passport, due diligence, recyclers) and ADR/IATA
dangerous-goods rules, some provisions unconfirmed; Kinective's Legal team must review them before they are relied on.
"""

import json
from pathlib import Path
from typing import Any

from di.services.modeler.pack import Pack, load_pack

BACKEND = Path(__file__).resolve().parents[1]
CATALOGUE = BACKEND / "di" / "services" / "modeler" / "packs" / "gates.catalogue.json"
POLICY = BACKEND.parent / "fixtures" / "golden" / "policy.json"
GATES = {"G-BAT-1", "G-BAT-2", "G-BAT-3", "G-BAT-4", "G-BAT-5"}
LEGAL_NOTE = "Research summary, not legal advice. Kinective's Legal team must review this gate before the pack ships."


def test_battery_pack_validates():
    p = load_pack("battery")
    assert isinstance(p, Pack) and p.key == "battery"
    assert (p.name, p.version, p.unit, p.prefix) == ("EV and industrial batteries", "1.0.0", "packs", "BAT")
    assert p.regions == ["EU", "US"] and p.valuer.kind == "standard"
    assert [r.id for r in p.routes] == ["reuse", "remanufacture", "repurpose", "recycle"]
    assert p.stories == ["NS-BAT-01", "NS-BAT-02", "NS-BAT-03"]
    assert {g.id for g in p.gates} == GATES


def test_battery_owners_resolve():
    p = load_pack("battery")
    named = {r.owner for r in p.routes} | {p.author_role}
    named |= {g.owner for g in p.guardrails} | {a for g in p.guardrails for a in g.approvers}
    named |= {e.owner_role for e in p.runtime.exception_types}
    assert named - set(p.roles) == set()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["role_policy"]
    assert set(p.roles.values()) <= set(policy)
    assert {k: v for k, v in p.roles.items() if k in ("battery_lead", "compliance", "sustainability_lead")} == {
        "battery_lead": "Engineer", "compliance": "Approver", "sustainability_lead": "Engineer",
    }  # fmt: skip


def test_battery_gates_from_catalogue_with_the_spec_params():
    """Stages and params sit in each gate ref's `params` (GateRef has no field); every gate carries the Legal note."""
    p = load_pack("battery")
    catalogue = {g["id"]: g for g in json.loads(CATALOGUE.read_text(encoding="utf-8"))}
    assert set(catalogue) >= GATES and all("battery" in catalogue[g]["packs"] for g in GATES)
    params: dict[str, dict[str, Any]] = {g.id: g.params for g in p.gates}
    assert all(v["legal_review"] == LEGAL_NOTE for v in params.values())
    assert [params[g]["stage"] for g in sorted(GATES)] == [3, 4, 6, 6, 6]
    assert params["G-BAT-3"]["passport_from"] == "2027-02-18"
    assert params["G-BAT-3"]["routes"] == ["repurpose", "remanufacture"] and params["G-BAT-3"]["markets"] == ["EU"]
    assert params["G-BAT-1"]["routes"] == ["reuse", "remanufacture", "repurpose"]  # without a reading only recycle is left
    assert params["G-BAT-2"]["routes"] == ["repurpose"] and params["G-BAT-5"]["routes"] == ["recycle"]
    assert {g.id for g in p.guardrails} == GATES
    note = next(g for g in p.gates if g.id == "G-BAT-3").params["note"]
    assert "indicative" in note and "18 Aug 2027" in note  # due diligence moved by Reg. 2025/1561; ELV changes unconfirmed


def test_battery_valuer_and_samples():
    p = load_pack("battery")
    vp = p.valuer.params
    assert {ln["route"] for ln in vp["lines"]} == {"reuse", "remanufacture", "repurpose", "recycle"}
    ex = p.replay.example
    assert ex is not None and [s["id"] for s in ex["samples"]] == [f"BAT-S{n}" for n in range(1, 5)]
    by = {s["id"]: s["facts"] for s in ex["samples"]}
    assert by["BAT-S3"]["battery.damaged"] is True and by["BAT-S1"]["battery.soh_pct"] == 86
