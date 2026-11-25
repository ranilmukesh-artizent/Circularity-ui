"""P9-1.11 (X-11): the contract entitlement gate G-CON-1 in the tool-fleet pack. A case with a restricting contract clause
blocks the routes of the restricted classes until a consent record is on file; a case with no clause is not gated. Contract
and consent wording is product text, not legal advice: Kinective's Legal team reviews it before it is relied on."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key
from di.services.canonical.store import Fact
from di.services.cases import gate_hold
from di.services.engine.routes import mk_route, term
from di.services.modeler.gates import catalogue, evaluate_gates
from di.services.modeler.pack import load_pack
from tests import starting

AT = "2026-10-01T08:00:00+00:00"
ROUTE_IDS = ["release", "refurb", "redeploy", "resell", "harvest", "exit"]
CLAUSE = {"contract_id": "LS-5412", "clause": "7.2", "text": "No resale without consent", "restricts": ["sale"]}
BLOCKED = "Contract LS-5412 clause 7.2: No resale without consent. Customer consent not on file."


def _rec(type: str, value: dict[str, Any], source: str = "lease-system", at: str = AT) -> dict[str, Any]:
    return {"type": type, "source": source, "at": at, "result": "pass", "value": value}


def _case(*records: dict[str, Any]) -> dict[str, Any]:
    return {"id": "RT-9011", "cls": "CMH", "template": "tool_fleet", "evidenceRecords": list(records)}


def _routes() -> list[dict[str, Any]]:
    return [mk_route({"id": i, "plan": i, "terms": [term("Sale", 100, "gain")]}) for i in ROUTE_IDS]


def _apply(case: dict[str, Any]) -> list[dict[str, Any]]:
    routes = _routes()
    gate_hold.apply(case, routes, load_pack("tool_fleet"), datetime(2026, 10, 2, tzinfo=UTC))
    return routes


@pytest.fixture(autouse=True)
def fresh():
    _clean()
    yield
    _clean()
    starting.reset()


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM provenance WHERE key LIKE 'T-CON%'"))
        s.execute(text("DELETE FROM canonical WHERE key LIKE 'T-CON%'"))
        s.commit()


def test_x_11_gate_is_in_the_pack_and_catalogue_as_specified():
    g = catalogue()["G-CON-1"]
    assert g.trigger.routes == "any" and g.owner == "Customer operations"
    assert [(c.fact, c.op) for c in g.trigger.when] == [("evidence.contract_clause.restricts", "exists")]
    assert g.evidence == ["customer_consent"] and g.effect.kind == "block" and g.effect.hold_until_evidence is False
    assert [r.id for r in load_pack("tool_fleet").gates if r.active] == ["G-CON-1"]


def test_x_11_clause_and_source_on_case():
    case = _case(_rec("contract_clause", CLAUSE, source="lease-system"))
    _apply(case)
    (row,) = case["gates"]
    assert row["id"] == "G-CON-1" and row["passed"] is False and row["reason"] == BLOCKED
    (clause,) = row["evidence"]
    assert clause["type"] == "contract_clause" and clause["source"] == "lease-system" and clause["at"] == AT
    assert clause["value"] == CLAUSE


def test_x_11_restricted_routes_fail():
    case = _case(_rec("contract_clause", CLAUSE))
    routes = _apply(case)
    by = {r["id"]: r for r in routes}
    assert by["resell"]["excluded"] is True and by["resell"]["failReason"] == "Contract entitlement: " + BLOCKED
    assert all(not by[i]["excluded"] for i in ROUTE_IDS if i != "resell")
    assert case["gates"][0]["routes"] == ["resell"] and case.get("gateHold") is None


def test_x_11_restricts_every_class_it_names():
    case = _case(_rec("contract_clause", CLAUSE | {"restricts": ["sale", "refurbish"]}))
    by = {r["id"]: r for r in _apply(case)}
    assert {i for i, r in by.items() if r["excluded"]} == {"resell", "refurb"}


def test_x_11_consent_passes_with_reference():
    case = _case(_rec("contract_clause", CLAUSE), _rec("customer_consent", {"ref": "CONS-88"}, source="crm"))
    routes = _apply(case)
    (row,) = case["gates"]
    assert row["passed"] is True and row["reason"] == "Consent on file: CONS-88."
    assert {e["type"] for e in row["evidence"]} == {"contract_clause", "customer_consent"}
    assert all(not r["excluded"] for r in routes)  # resell is eligible


def test_x_11_clause_without_restricted_class_blocks_nothing():
    case = _case(_rec("contract_clause", CLAUSE | {"restricts": []}))
    routes = _apply(case)
    assert all(not r["excluded"] for r in routes) and not case.get("gates")


def test_x_11_clause_after_as_of_does_not_gate():
    case = _case(_rec("contract_clause", CLAUSE, at="2026-12-01T00:00:00+00:00"))
    routes = _apply(case)
    assert all(not r["excluded"] for r in routes) and not case.get("gates")


def test_x_11_no_clause_no_change():
    case = _case()
    routes = _apply(case)
    assert all(not r["excluded"] for r in routes)
    assert not {"gates", "gateHold", "requiredSteps", "evidence"} & set(case)
    assert evaluate_gates({"cls": "CMH"}, load_pack("tool_fleet")) == []


def _facts(key: str, type: str, value: dict[str, Any]) -> list[Fact]:
    row = {"asset_key": key, "type": type, "result": "pass", "at": AT, "value": value}
    return [Fact("compliance", compliance_key(key, type), f, v) for f, v in row.items()]


def test_x_11_attach_evidence_builds_clause_and_consent_with_lease():
    key = "T-CON1"
    with SessionLocal() as s:
        lease = [Fact("asset", key, "lease_ref", "LS-5412"), Fact("asset", key, "contract_end", "2027-03-31")]
        canonical.apply(s, "lease-system", lease)
        canonical.apply(s, "lease-system", _facts(key, "contract_clause", CLAUSE))
        canonical.apply(s, "crm", _facts(key, "customer_consent", {"ref": "CONS-88"}))
        s.commit()
        case: dict[str, Any] = {"id": "RT-9012", "assetId": key, "cls": "CMH", "template": "tool_fleet"}
        gate_hold.attach_evidence(s, case)
    by = {r["type"]: r for r in case["evidenceRecords"]}
    assert by["contract_clause"]["value"] == CLAUSE | {"lease_ref": "LS-5412", "contract_end": "2027-03-31"}
    assert by["contract_clause"]["source"] == "lease-system"
    assert by["customer_consent"]["value"] == {"ref": "CONS-88"}
    _apply(case)
    assert case["gates"][0]["reason"] == "Consent on file: CONS-88."
