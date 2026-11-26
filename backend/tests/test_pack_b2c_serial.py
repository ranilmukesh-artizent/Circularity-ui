"""P9-12.10 (stories NS-B2C-01, NS-B2C-02): the serialised retail returns pack data file (`packs/b2c_serial.json`, I-1). It reuses
the device pack's valuer and its two device gates, and adds the destruction ban of unsold apparel and footwear. Synthetic data.
Legal: G-ESPR-1 summarises Regulation (EU) 2024/1781 (large companies from 19 Jul 2026) and the device gates summarise data-wipe
and registry practice; Kinective's Legal team must review them before they are relied on."""

import json
from pathlib import Path
from typing import Any

from di.services.modeler.pack import Pack, load_pack

BACKEND = Path(__file__).resolve().parents[1]
CATALOGUE = BACKEND / "di" / "services" / "modeler" / "packs" / "gates.catalogue.json"
POLICY = BACKEND.parent / "fixtures" / "golden" / "policy.json"


def test_b2c_serial_pack_validates():
    p = load_pack("b2c_serial")
    assert isinstance(p, Pack) and p.key == "b2c_serial"
    assert (p.name, p.version, p.unit, p.prefix) == ("Serialised retail returns", "1.0.0", "items", "B2C")
    assert p.valuer.kind == "standard" and p.valuer.params["params"]["plugin"] == "b2c_serial"
    device = load_pack("device")
    sale = [
        "buynow",
        "offers",
        "auction",
        "market",
        "wholesale",
    ]  # the device pack's channels; its repair_sell, parts and replacement are not offered
    assert [r.id for r in p.routes] == [*sale, "donate", "recycle", "exit"]
    assert [r.classes for r in p.routes[:5]] == [
        r.classes for r in device.routes if r.id in sale
    ]  # the device pack's channels, unchanged
    assert [g.id for g in p.gates] == ["G-DEV-WIPE", "G-DEV-LOCK", "G-ESPR-1"]
    by = {g.id: g for g in p.gates}
    dev = {g.id: g for g in device.gates}

    # the device gates' params except `locked_routes` (lane B: parts and recycle; b2c locks none)
    def same(a, b):
        return {k: v for k, v in a.params.items() if k != "locked_routes"} == {
            k: v for k, v in b.params.items() if k != "locked_routes"
        }

    assert same(by["G-DEV-WIPE"], dev["G-DEV-WIPE"]) and same(by["G-DEV-LOCK"], dev["G-DEV-LOCK"])
    assert by["G-ESPR-1"].params["stage"] == 5 and by["G-ESPR-1"].params["classes"] == ["apparel", "footwear"]
    assert by["G-ESPR-1"].params["routes"] == ["exit"] and by["G-ESPR-1"].params["allowed_exceptions"]
    assert "Legal team must review" in by["G-ESPR-1"].params["legal_review"]
    assert {c.id for c in p.classes} == {"phone", "tablet", "apparel", "footwear"}
    assert p.stories == ["NS-B2C-01", "NS-B2C-02"]


def test_b2c_serial_gates_are_in_the_catalogue():
    p = load_pack("b2c_serial")
    catalogue = {g["id"]: g for g in json.loads(CATALOGUE.read_text(encoding="utf-8"))}
    assert all("b2c_serial" in catalogue[g.id]["packs"] for g in p.gates)
    assert {g.id for g in p.guardrails} >= {"G-ESPR-1"}


def test_b2c_serial_owners_resolve():
    p = load_pack("b2c_serial")
    named = {r.owner for r in p.routes} | {p.author_role}
    named |= {g.owner for g in p.guardrails} | {a for g in p.guardrails for a in g.approvers}
    named |= {e.owner_role for e in p.runtime.exception_types}
    assert named - set(p.roles) == set()
    policy: dict[str, Any] = json.loads(POLICY.read_text(encoding="utf-8"))["role_policy"]
    assert set(p.roles.values()) <= set(policy)
