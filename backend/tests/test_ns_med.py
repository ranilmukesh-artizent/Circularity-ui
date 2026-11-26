"""P9-12.9 (stories NS-MED-01 to NS-MED-03): the medical capital pack's regulatory gates and the assessment a person records.

`assessment.record` stores the evidence `servicing_assessment` (planned work, result, rationale, the person and the time) on
the case's asset; G-MED-1 reads it: no assessment, or remanufacturing or full refurbishment where the pack lists no
manufacturer-status market, stops `refurbish_resell`. G-MED-2 (single-use), G-MED-3 (cross-market resale: UDI, service
record, recalls) and G-DATA-3 (a sanitisation record for patient data before any release route) read the case's device
and market facts. Facts are the standard valuer's flat facts given when the case opens. Synthetic data. Legal: the wording of
these gates needs review by Kinective's Legal team before it is relied on.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key, tag_key
from di.services.canonical.store import Fact
from di.services.cases import store as cases
from tests import flowkit, starting
from tests.helpers import call, client, h

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "medical_capital.json"
BASE = {
    "cls": "infusion_pump", "age_years": 4, "resale_price": 4000, "refurb_cost": 1200, "parts_value": 500, "single_use": False,
    "origin_market": "US", "target_market": "US", "udi": "UDI-0001", "service_record_ref": "SR-1", "recalls_closed": True,
}  # fmt: skip
FULL_TEXT = "Would be remanufacturing or full refurbishment: needs manufacturer status in this market"
RATIONALE = "Replace the battery and the housing seals; no change to intended use or performance."


def tag(n: int) -> str:
    return f"SYN-MC-{n:04d}"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SYN-MC-%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYN-MC-%"})


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.4"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    yield
    _clean()
    flowkit.reset_flows()
    starting.reset()


def _get(cid: str) -> dict:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _open(n: int, **facts: Any) -> dict:
    key = tag_key(ORG, tag(n))
    row = {"asset_key": key, "type": "field_safety_status", "result": "pass", "ref": "R-1",
           "at": "2026-11-01T00:00:00+00:00", "value": {}}  # fmt: skip
    with SessionLocal() as s:  # no open field safety notice (G-MED-FSN)
        canonical.apply(
            s, "manual", [Fact("compliance", compliance_key(key, "field_safety_status"), f, v) for f, v in row.items()]
        )
        s.commit()
    body = {"org_unit_id": ORG, "template_key": "medical_capital", "asset_key": key, "reason": "trade_in",
            "facts": {"tag": tag(n)} | BASE | facts}  # fmt: skip
    return _get(_ok(call("case.open", body, "planner-a"))["case_id"])


def _record(c: dict, result: str, user: str = "engineer") -> dict:
    body = {"case_id": c["id"], "planned_work": "Battery and seal replacement", "result": result, "rationale": RATIONALE}
    return call("assessment.record", body, user)


def _gate(c: dict, gid: str) -> dict:
    return next(g for g in c["gates"] if g["id"] == gid)


def _route(c: dict, rid: str) -> dict:
    return next(r for r in c["routes"] if r["id"] == rid)


def test_ns_med_01_assessment_workflow():
    c = _open(1)
    g = _gate(c, "G-MED-1")
    assert not g["passed"] and g["missingTypes"] == ["servicing_assessment"] and g["routes"] == ["refurbish_resell"]
    assert _route(c, "refurbish_resell")["excluded"] and c["recommendation"]["id"] == "resell_as_is"
    out = _ok(_record(c, "servicing"))
    assert out["case_id"] == c["id"] and out["result"] == "servicing"
    after = _get(c["id"])
    assert _gate(after, "G-MED-1")["passed"] and not _route(after, "refurbish_resell")["excluded"]
    assert after["recommendation"]["id"] == "refurbish_resell"
    (rec,) = [e for e in after["evidenceRecords"] if e["type"] == "servicing_assessment"]
    assert rec["result"] == "pass" and rec["value"]["assessment"] == "servicing" and rec["value"]["rationale"] == RATIONALE
    assert rec["value"]["planned_work"] == "Battery and seal replacement" and rec["value"]["by"] == "engineer"
    assert rec["at"]  # the person and the time are kept
    full = _open(2)
    _ok(_record(full, "full_refurbishment"))
    blocked = _get(full["id"])
    assert not _gate(blocked, "G-MED-1")["passed"] and FULL_TEXT in _route(blocked, "refurbish_resell")["failReason"]
    assert blocked["recommendation"]["id"] == "resell_as_is"


def test_assessment_record_agent_cannot_record():
    assert "assessment.record".startswith(FORBIDDEN_ACTIONS)
    c = _open(3)
    body = {"case_id": c["id"], "planned_work": "Seal replacement", "result": "servicing", "rationale": RATIONALE}
    r = client.post(
        "/api/actions/assessment.record", json=body, headers=h("engineer") | {"X-Circularity-Preparer": "coordinator"}
    )
    assert r.status_code == 403, r.json()
    assert not [e for e in _get(c["id"])["evidenceRecords"] if e["type"] == "servicing_assessment"]


def test_assessment_record_needs_permission():
    c = _open(4)
    r = _record(c, "servicing", "planner-a")  # a Planner may open the case, not record the assessment
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope", r
    assert not [e for e in _get(c["id"])["evidenceRecords"] if e["type"] == "servicing_assessment"]


def test_assessment_record_tenant_boundary():
    c = _open(5)
    r = _record(c, "servicing", "planner-b")  # Customer B's person
    assert r["ok"] is False and r["error"]["code"] in ("tenant_boundary", "out_of_scope"), r
    assert not [e for e in _get(c["id"])["evidenceRecords"] if e["type"] == "servicing_assessment"]
    bad = call("assessment.record", {"case_id": c["id"], "planned_work": "x", "result": "rebuild", "rationale": "y"}, "engineer")
    assert bad["ok"] is False and bad["error"]["code"] == "validation_error", bad


def test_ns_med_02_patient_data_sanitised_before_release():
    c = _open(6, cls="patient_monitor")
    g = _gate(c, "G-DATA-3")
    assert not g["passed"] and g["missingTypes"] == ["sanitisation_record"]
    assert c["gateHold"]["gates"] == ["G-DATA-3"] and c["recommendation"] is None
    assert all(r["excluded"] and "Sanitisation record required" in r["failReason"] for r in c["routes"])
    ok = _open(7, cls="patient_monitor", sanitisation_ref="SAN-0001")  # the disposal partner's record is on file
    assert _gate(ok, "G-DATA-3")["passed"] and ok["recommendation"] is not None
    plain = _open(8)  # an infusion pump holds no patient data: the gate does not apply
    assert "G-DATA-3" not in {g["id"] for g in plain["gates"]}


def test_ns_med_03_cross_market_needs_udi_service_recalls():
    c = _open(9, target_market="EU", udi=None, recalls_closed=False)
    g = _gate(c, "G-MED-3")
    assert not g["passed"] and "UDI missing" in g["reason"] and "Recalls not closed" in g["reason"]
    assert "Service record missing" not in g["reason"]
    assert _route(c, "refurbish_resell")["excluded"]  # (it also lacks the assessment: a route keeps its first reason)
    assert _route(c, "resell_as_is")["excluded"] and "UDI missing" in _route(c, "resell_as_is")["failReason"]
    assert _gate(c, "G-MED-3")["routes"] == ["refurbish_resell", "resell_as_is"]
    assert not _route(c, "recycle")["excluded"]
    same = _open(10, udi=None)  # sold in the market it came from: no cross-market duties
    assert "G-MED-3" not in {g["id"] for g in same["gates"]}
    done = _open(11, target_market="EU")
    assert _gate(done, "G-MED-3")["passed"]


def test_single_use_is_recycled():
    c = _open(12, single_use=True)
    assert not _gate(c, "G-MED-2")["passed"]
    assert _route(c, "refurbish_resell")["excluded"] and _route(c, "resell_as_is")["excluded"]
    assert c["recommendation"]["id"] == "recycle"
