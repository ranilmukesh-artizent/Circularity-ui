"""P9-12.8: the automotive cores pack data file (`packs/auto_core.json`, I-1; stories NS-CORE-01 and NS-CORE-03). Data only: the
tests read the pack through `load_pack` and check it against the gate catalogue, the role policy and the spec's texts. Where the
pack format has no named field for a spec part, the data sits in the nearest free-form field (the acceptance criteria in the
gate's `params`, the fraud rules in the pack's `fraud` part); each such place is named in the test that reads it. Legal: core
credit and fraud rules are commercial and consumer-protection matters; Kinective's Legal team must review them before use.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from di.services.modeler.gates import catalogue, pack_gates
from di.services.modeler.pack import Pack, PackError, load_pack, parse_pack

BACKEND = Path(__file__).resolve().parents[1]
PACK_FILE = BACKEND / "di" / "services" / "modeler" / "packs" / "auto_core.json"
POLICY = BACKEND.parent / "fixtures" / "golden" / "policy.json"


def _doc() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(PACK_FILE.read_text(encoding="utf-8"))
    return doc


def test_auto_core_pack_validates():
    p = load_pack("auto_core")
    assert isinstance(p, Pack) and p.key == "auto_core"
    assert (p.version, p.unit, p.prefix) == ("1.0.0", "cores", "CORE")
    assert p.name == "Automotive cores · remanufacturing"
    assert [r.id for r in p.routes] == ["reman", "harvest", "broker", "scrap"]
    assert p.valuer.kind == "standard"
    assert p.stories == ["NS-CORE-01", "NS-CORE-03"]
    doc = _doc()
    del doc["customer_layer"]
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert (e.value.key, e.value.version, e.value.part, e.value.part_name) == ("auto_core", "1.0.0", 7, "customer_layer")


def test_auto_core_owners_resolve():
    p = load_pack("auto_core")
    named = {r.owner for r in p.routes} | {p.author_role}
    named |= {g.owner for g in p.guardrails} | {a for g in p.guardrails for a in g.approvers}
    named |= {e.owner_role for e in p.runtime.exception_types}
    assert named - set(p.roles) == set()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["role_policy"]
    assert set(p.roles.values()) <= set(policy)


def test_auto_core_acceptance_is_data_on_the_gate():
    """Part 6: the acceptance criteria per part number are the `acceptance` parameter of the pack gate CORE-ACCEPT (Threshold)."""
    p = load_pack("auto_core")
    [gate] = pack_gates(p)
    assert gate.id == "CORE-ACCEPT" and gate.type == "Threshold" and "auto_core" in catalogue()["CORE-ACCEPT"].packs
    acc = gate.params["acceptance"]
    assert acc["ALT-1450"] == {
        "required": ["housing_intact", "no_cracks", "complete", "family_match"],
        "partial_allowed": ["complete"],
    }
    assert gate.params["partial_pct"] == 50
    assert [g.id for g in p.guardrails] == ["CORE-ACCEPT"] and p.guardrails[0].type == "Threshold"


def test_auto_core_fraud_rules_are_pack_data():
    """The X-15 rules as data (`Pack.fraud`): the signal ids are the rule ids, the source is the core returns system."""
    p = load_pack("auto_core")
    assert p.fraud is not None and p.fraud.version
    rules = {r.id: r for r in p.fraud.rules}
    assert set(rules) == {"part_family_mismatch", "repeat_returner"}
    assert rules["part_family_mismatch"].signal == "quote_mismatch"
    assert (rules["repeat_returner"].signal, rules["repeat_returner"].params) == ("dealer_rejects", {"n": 3, "days": 90})
    assert {r.source for r in p.fraud.rules} == {"core_ret"}
    assert all(r.weight >= p.fraud.threshold for r in p.fraud.rules)  # one signal alone holds the case for a person


def test_auto_core_data_system_and_valuer_lines():
    p = load_pack("auto_core")
    assert {s.type for s in p.data.systems} >= {"core_ret"}
    routes = {ln["route"] for ln in p.valuer.params["lines"]}
    assert routes == {"reman", "harvest", "broker", "scrap"}
