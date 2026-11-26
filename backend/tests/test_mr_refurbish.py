"""Plan 9, P9-11.10 (story MR-16): the refurbish stays servicing gate G-MED-REFURB, and the device facts of a real rental case.

`refurbish` needs the biomedical system's servicing assessment; a result of remanufacturing or full refurbishment fails it
unless the case's market is in the pack's `manufacturer_status_markets`. The gate is Compliance, so locked: an overlay cannot
remove or widen it. The last test opens a case from canonical facts only (no `facts` but the tag) and checks that the
valuer's device facts (`cls`, `age_years`, `book_value`, `residual_sale_value`, `repair_estimate`) came from the canonical
records (the gap found in P9-11.9). Facts are written by the real adapters' mapping on literal records (no source-sim). Legal
note: Kinective's Legal team reviews the wording of this gate before it is relied on.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key, tag_key
from di.services.canonical.store import Fact
from di.services.cases import store as cases
from di.services.engine.routes import mk_route
from di.services.modeler.gates import apply_gate_results, evaluate_gates, pack_gates
from di.services.modeler.overlay import OverlayError, Tighten, apply_overlay
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import call

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "medical_rental.json"
IN = "2026-11-17T06:00:00+00:00"
AFTER = "2026-11-17T09:30:00+00:00"
FULL_TEXT = "Would be remanufacturing or full refurbishment: needs manufacturer status in this market"
GATE = "G-MED-REFURB"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SYN-MR-%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYN-MR-%"})


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.3"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        for sid in ("mr_rental", "mr_decon", "mr_biomed", "mr_assets"):
            extra.register(s, sid, ORG)
        s.commit()
    yield
    _clean()
    starting.reset()


def _write(source: str, resource: str, payload: dict[str, Any]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, ADAPTERS[source].map(Record(resource, "x", payload)))
        s.commit()


def _tag(n: int) -> str:
    return f"SYN-MR-EB-{n:04d}"


def _return(tag: str, assessment: str | None) -> dict:
    """A bed's return with its decontamination, register and service records, then its case opened from canonical facts."""
    _write("mr_assets", "devices", {
        "tag": tag, "deviceClass": "electric_bed", "model": "EB-9", "serial": 9000, "inServiceDate": "2018-01-01",
        "bookValue": 800, "residualSaleValue": 500, "org_unit_id": ORG,
    })  # fmt: skip
    _write("mr_biomed", "service", {
        "tag": tag, "model": "EB-9", "serialNo": 9000, "pmDue": "2027-02-15", "pmCode": "PM-12M", "lastPm": "2026-02-15",
        "certificationExpiry": "2027-03-31", "functionalTest": {"result": "pass", "at": "2026-11-10"},
        "electricalSafety": {"standard": "IEC 62353", "result": "pass", "at": "2026-11-10"}, "notes": [], "repairEstimate": 120,
        "faults": [], "notice": None, "org_unit_id": ORG,
    })  # fmt: skip
    if assessment:
        _write("mr_biomed", "assessments", {"tag": tag, "result": assessment, "org_unit_id": ORG})
    _write("mr_rental", "returns", {
        "returnId": "RET-EB", "tag": tag, "hospitalId": "HOSP-D", "ward": "Ward 3", "wardType": "general", "depot": "EAST",
        "checkedInAt": IN, "previousRentalEnd": "2026-11-16", "org_unit_id": ORG,
    })  # fmt: skip
    _write("mr_decon", "cycles", {
        "cycleId": "DC-EB", "tag": tag, "method": "standard", "enhanced": False, "cycleStartedAt": "2026-11-17T04:00:00+00:00",
        "cycleEndedAt": AFTER, "operatorRef": "OP-01", "result": "pass", "org_unit_id": ORG,
    })  # fmt: skip
    key = tag_key(ORG, tag)
    row = {"asset_key": key, "type": "field_safety_status", "result": "pass", "ref": "R-1", "at": "2026-11-01T00:00:00+00:00",
           "value": {}}  # fmt: skip
    with SessionLocal() as s:
        facts = [Fact("compliance", compliance_key(key, "field_safety_status"), f, v) for f, v in row.items()]
        canonical.apply(s, "manual", facts)
        s.commit()
    body = {
        "org_unit_id": ORG,
        "template_key": "medical_rental",
        "asset_key": key,
        "reason": "rental_return",
        "facts": {"tag": tag},
    }  # only the tag: every other fact comes from canonical
    cid = _ok(call("case.open", body, "planner-a"))["case_id"]
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _gate(c: dict) -> dict:
    return next(g for g in c["gates"] if g["id"] == GATE)


def _failed(c: dict, pack=None) -> dict[str, str]:
    pack = pack or load_pack("medical_rental")
    routes = [mk_route({"id": r.id, "plan": r.id, "terms": []}) for r in pack.routes]
    apply_gate_results(routes, evaluate_gates(c, pack))
    return {r["id"]: r["failReason"] for r in routes if r["excluded"]}


def test_mr_16_refurbish_needs_assessment():
    c = _return(_tag(39), None)
    g = _gate(c)
    assert not g["passed"] and g["missingTypes"] == ["servicing_assessment"] and g["routes"] == ["refurbish"]
    assert _failed(c)["refurbish"] == "Refurbish stays servicing: Servicing assessment required"
    assert not c.get("gateHold")  # only the refurbish route is stopped


def test_mr_16_servicing_passes():
    c = _return(_tag(40), "servicing")  # SYN-MR-EB-0040
    assert _gate(c)["passed"] and "refurbish" not in _failed(c)


def test_mr_16_full_refurbishment_blocked():
    c = _return(_tag(41), "full_refurbishment")  # SYN-MR-EB-0041
    g = _gate(c)
    assert not g["passed"] and g["reason"] == FULL_TEXT and g["routes"] == ["refurbish"]
    assert _failed(c)["refurbish"] == f"Refurbish stays servicing: {FULL_TEXT}"
    assert "retire" not in _failed(c)


def test_mr_16_remanufacturing_blocked():
    assert _gate(_return(_tag(42), "remanufacturing"))["reason"] == FULL_TEXT


def test_mr_16_manufacturer_status_market_allows():
    c = _return(_tag(41), "full_refurbishment") | {"market": "EU"}
    base = load_pack("medical_rental")
    assert not next(g for g in pack_gates(base) if g.id == GATE).params["manufacturer_status_markets"]
    assert "refurbish" in _failed(c, base)  # the market is not in the default list
    refs = [
        r.model_copy(update={"params": {**r.params, "manufacturer_status_markets": ["EU"]}}) if r.id == GATE else r
        for r in base.gates
    ]
    allowed = base.model_copy(update={"gates": refs})
    assert [r.passed for r in evaluate_gates(c, allowed) if r.gate_id == GATE] == [True]
    assert "refurbish" not in _failed(c, allowed)
    assert "refurbish" in _failed(c | {"market": "US"}, allowed)  # another market stays blocked
    # a tighten-only overlay never takes the gate away or widens its markets: its guardrail takes no such operation
    op = Tighten(id="op-1", op="tighten", target=GATE, field="manufacturer_status_markets", value=1, seen=0)
    with pytest.raises(OverlayError) as e:
        apply_overlay(base, [op])
    assert e.value.code in ("locked", "not_editable")
    assert next(g for g in pack_gates(base) if g.id == GATE).locked  # Compliance: a customer may only tighten it


def test_mr_16_device_facts_come_from_canonical():
    """The gap of P9-11.9: a case opened with only the tag is priced on the device facts canonical holds."""
    c = _return(_tag(40), "servicing")
    v = c["valuer"]
    assert (v["cls"], v["book_value"], v["residual_sale_value"], v["repair_estimate"]) == ("electric_bed", 800, 500, 120)
    assert v["age_years"] >= 8 and c["cls"] == "electric_bed"
    assert {r["id"] for r in c["routes"]} >= {"refurbish", "retire"}
    refurbish = next(r for r in c["routes"] if r["id"] == "refurbish")
    assert not refurbish["excluded"], refurbish.get("failReason")
