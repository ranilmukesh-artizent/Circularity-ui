"""Plan 9, P9-11.7 (stories MR-06, MR-07, MR-15): the service in date gate G-MED-SVC, the safety notice gate G-MED-FSN and the
service booking action `service.book`.

A unit whose certification or preventive maintenance ends before a request's rental ends fails the re-rent routes for that
request, with "Send a different unit" naming an in-date unit of the class and a `service.book` proposed for this one. The
biomedical system's test results show with source and age; a cosmetic note changes nothing unless a test failed. An open
field safety notice holds the re-rent until a correction record exists. `service.book` is held for a person when an agent
prepares it. Facts are written by the real adapters' mapping on literal records (no source-sim). Legal note: Kinective's Legal
team reviews the wording of both gates before it is relied on.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di import worker
from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, forbidden, held_for_person
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key, tag_key
from di.services.canonical.store import Fact
from di.services.cases import intake
from di.services.cases import store as cases
from di.services.engine.routes import mk_route
from di.services.modeler.gates import apply_gate_results, evaluate_gates
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import call, client, h

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "medical_rental.json"
IN = "2026-11-17T06:00:00+00:00"
AFTER = "2026-11-17T09:30:00+00:00"
CERT_TEXT = "Certification ends 2026-12-07, before the rental ends 2026-12-27"
PM_TEXT = "Preventive maintenance due 2026-12-10, before the rental ends 2026-12-27"
FSN_TEXT = "Open field safety notice FSN-031: re-rent held until corrected"
NOTICE = {
    "noticeId": "FSN-031",
    "model": "IP-300",
    "serialFrom": 3000,
    "serialTo": 3099,
    "status": "open",
    "correctionRef": "FSN-031-A",
}


def tag(n: int) -> str:
    return f"SYN-MR-IP-{n:04d}"


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
    doc["version"] = "1.9.2"
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


def _service(n: int, **over: Any) -> dict[str, Any]:
    return {
        "tag": tag(n), "model": "IP-200", "serialNo": 2000 + n, "pmDue": "2027-02-15", "pmCode": "PM-12M", "lastPm": "2026-02-15",
        "certificationExpiry": "2027-03-31", "functionalTest": {"result": "pass", "at": "2026-11-10"},
        "electricalSafety": {"standard": "IEC 62353", "result": "pass", "at": "2026-11-10"}, "notes": [], "repairEstimate": 0,
        "faults": [], "notice": None, "org_unit_id": ORG,
    } | over  # fmt: skip


def _requests() -> list[dict[str, Any]]:
    return [
        {"reqId": f"REQ-{k}", "hospitalId": "HOSP-B", "deviceClass": "infusion_pump", "startDate": "2026-11-27", "days": 30,
         "region": "EAST", "requestedAt": "2026-11-26T08:00:00+00:00", "latitude": 40.0, "longitude": -74.9}
        for k in (1, 2, 3, 4)
    ]  # fmt: skip


def _device(n: int, **service: Any) -> None:
    """The register's and the biomedical system's records of a pump."""
    pump = {"tag": tag(n), "deviceClass": "infusion_pump", "model": "IP-200", "serial": 2000 + n, "org_unit_id": ORG}
    _write("mr_assets", "devices", pump)
    _write("mr_biomed", "service", _service(n, **service))


def _case(n: int, **service: Any) -> dict:
    """A return of pump n with its decontamination on file, the other gates' evidence, the requests, and its case."""
    _device(n, **service)
    _write("mr_rental", "returns", {
        "returnId": f"RET-{n:04d}", "tag": tag(n), "hospitalId": "HOSP-D", "ward": "Ward 3", "wardType": "general",
        "depot": "EAST",
        "checkedInAt": IN, "previousRentalEnd": "2026-11-16", "org_unit_id": ORG,
    })  # fmt: skip
    _write("mr_rental", "demand", {
        "tag": tag(n), "depot": {"latitude": 40.0, "longitude": -75.0}, "requests": _requests(), "forecast": [],
        "org_unit_id": ORG,
    })  # fmt: skip
    _write("mr_decon", "cycles", {
        "cycleId": f"DC-{n:04d}", "tag": tag(n), "method": "standard", "enhanced": False,
        "cycleStartedAt": "2026-11-17T04:00:00+00:00",
        "cycleEndedAt": AFTER, "operatorRef": "OP-01", "result": "pass", "org_unit_id": ORG,
    })  # fmt: skip
    _manual(n, "refurb_assessment")
    body = {"org_unit_id": ORG, "template_key": "medical_rental", "asset_key": tag_key(ORG, tag(n)), "reason": "rental_return",
            "facts": {"tag": tag(n)}}  # fmt: skip
    return _get(_ok(call("case.open", body, "planner-a"))["case_id"])


def _manual(n: int, kind: str, result: str = "pass", at: str = "2026-11-01T00:00:00+00:00", **value: Any) -> None:
    key = tag_key(ORG, tag(n))
    row = {"asset_key": key, "type": kind, "result": result, "ref": "R-1", "at": at, "value": value}
    with SessionLocal() as s:
        canonical.apply(s, "manual", [Fact("compliance", compliance_key(key, kind), f, v) for f, v in row.items()])
        s.commit()


def _get(cid: str) -> dict:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _gate(c: dict, gate_id: str) -> dict:
    return next(g for g in c["gates"] if g["id"] == gate_id)


def _failed(c: dict) -> dict[str, str]:
    pack = load_pack("medical_rental")
    routes = [mk_route({"id": r.id, "plan": r.id, "terms": []}) for r in pack.routes]
    apply_gate_results(routes, evaluate_gates(c, pack))
    return {r["id"]: r["failReason"] for r in routes if r["excluded"]}


def _recheck() -> None:
    with SessionLocal() as s:
        jobs = s.execute(text("SELECT payload FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).scalars().all()
    for p in jobs:
        worker.HANDLERS["case.gateRecheck"](p)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()


def _items(cid: str, kind: str) -> list[dict]:
    with engine.connect() as conn:
        q = text("SELECT owner_role, action FROM work_item WHERE case_id = :c AND type = :t AND status = 'open'")
        return [dict(r) for r in conn.execute(q, {"c": cid, "t": kind}).mappings()]


def test_mr_06_certification_short_of_rental():
    _device(1)  # an in-date pump of the class (certified to 31 Mar 2027)
    c = _case(2, certificationExpiry="2026-12-07")  # MR-S2
    g = _gate(c, "G-MED-SVC")
    assert not g["passed"] and g["reason"] == CERT_TEXT and g["owner"] == "Biomedical engineer"
    assert sorted(g["routes"]) == ["rerent", "service_rerent"] and not g["hold"]
    assert _failed(c)["rerent"] == f"Service and certification in date for the whole rental: {CERT_TEXT}"
    chk = c["serviceCheck"]
    req4 = next(r for r in chk["requests"] if r["req_id"] == "REQ-4")
    assert req4["ok"] is False and req4["reason"] == CERT_TEXT and req4["ends"] == "2026-12-27"
    assert req4["recommendation"] == f"Send a different unit: {tag(1)}" and all(not r["ok"] for r in chk["requests"])
    p = chk["proposed"]
    assert p == {
        "action": "service.book",
        "input": {"case_id": c["id"], "asset_tag": tag(2), "kind": "certification", "due_by": "2026-12-07"},
    }
    items = _items(c["id"], "EX-MR-CERT")  # the exception goes to the biomedical engineer
    assert len(items) == 1 and items[0]["action"] == "Send a different unit; book certification for this one"
    assert c.get("gateHold") is None  # the other routes stay open


def test_mr_06_preventive_maintenance_short_of_rental():
    c = _case(2, pmDue="2026-12-10")
    g = _gate(c, "G-MED-SVC")
    assert not g["passed"] and g["reason"] == PM_TEXT
    assert c["serviceCheck"]["proposed"]["input"]["kind"] == "pm"


def test_mr_06_in_date_unit_passes():
    c = _case(1)
    assert _gate(c, "G-MED-SVC")["passed"] and c["serviceCheck"]["proposed"] is None
    assert "rerent" not in _failed(c)


def test_service_book_agent_held():
    c = _case(2, certificationExpiry="2026-12-07")
    assert held_for_person("service.book") and not forbidden("service.book") and not "service.book".startswith(FORBIDDEN_ACTIONS)
    body = c["serviceCheck"]["proposed"]["input"]
    hdr = h("engineer") | {"X-Circularity-Preparer": "coordinator"}
    r = client.post("/api/actions/service.book", json=body, headers=hdr).json()
    assert r["ok"] is True and "held" in r["output"], r
    assert _get(c["id"]).get("serviceOrders") in (None, [])  # nothing was written


def test_service_book_records_the_order_for_a_person():
    c = _case(2, certificationExpiry="2026-12-07")
    body = c["serviceCheck"]["proposed"]["input"]
    out = _ok(call("service.book", body, "engineer"))
    assert out["case_id"] == c["id"] and out["kind"] == "certification"
    orders = _get(c["id"])["serviceOrders"]
    assert [(o["asset_tag"], o["kind"], o["due_by"], o["source"]) for o in orders] == [
        (tag(2), "certification", "2026-12-07", "mr_biomed")
    ]
    again = call("service.book", body, "engineer")  # the same order again is a duplicate, not a second order
    assert again["ok"] is False and again["error"]["code"] in ("duplicate", "conflict")
    assert len(_get(c["id"])["serviceOrders"]) == 1


def test_service_book_needs_permission():
    c = _case(2, certificationExpiry="2026-12-07")
    r = call("service.book", c["serviceCheck"]["proposed"]["input"], "finance")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope", r
    assert _get(c["id"]).get("serviceOrders") in (None, [])


def test_service_book_tenant_boundary():
    c = _case(2, certificationExpiry="2026-12-07")
    r = call("service.book", c["serviceCheck"]["proposed"]["input"], "planner-b")  # Customer B's planner
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", r
    assert _get(c["id"]).get("serviceOrders") in (None, [])


def test_service_book_validates_kind_and_tag():
    c = _case(2, certificationExpiry="2026-12-07")
    body = c["serviceCheck"]["proposed"]["input"]
    assert call("service.book", body | {"kind": "paint"}, "engineer")["error"]["code"] == "validation_error"
    assert call("service.book", body | {"asset_tag": tag(9)}, "engineer")["error"]["code"] == "validation_error"


def test_mr_07_test_results_read_cosmetic_ignored():
    note = [{"text": "Housing scuff", "kind": "cosmetic"}]
    c = _case(1, notes=note)  # SYN-MR-IP-0001
    read = c["serviceRead"]
    assert read["source"] == "mr_biomed" and isinstance(read["ageDays"], float)
    assert read["functionalTest"]["result"] == "pass" and read["electricalSafety"]["standard"] == "IEC 62353"
    assert read["notes"] == [{"text": "Housing scuff", "kind": "cosmetic"}]
    assert read["certificationExpiry"] == "2027-03-31" and read["pmDue"] == "2027-02-15"
    assert _gate(c, "G-MED-SVC")["passed"] and "rerent" not in _failed(c)  # the scuff changes no eligibility
    # a failed functional test makes the unit ineligible for re-rent
    _write("mr_biomed", "service", _service(1, notes=note, functionalTest={"result": "fail", "at": "2026-11-12"}))
    with SessionLocal() as s:
        c2 = cases.get(s, c["id"], for_update=True)
        assert c2 is not None
        intake.revalue(s, c2)
        cases.save(s, c2)
        s.commit()
    c2 = _get(c["id"])
    g = _gate(c2, "G-MED-SVC")
    assert not g["passed"] and "Functional test failed" in g["reason"] and g["routes"] == ["rerent"]
    assert "Functional test failed" in _failed(c2)["rerent"]
    assert c2["serviceRead"]["notes"] == [{"text": "Housing scuff", "kind": "cosmetic"}]


def test_mr_15_open_notice_holds_rerent():
    c = _case(30, model="IP-300", serialNo=3030, notice=NOTICE)  # SYN-MR-IP-0030 under FSN-031
    g = _gate(c, "G-MED-FSN")
    assert not g["passed"] and g["hold"] and g["reason"] == FSN_TEXT
    assert sorted(g["routes"]) == ["rerent", "service_rerent"]
    assert c["gateHold"]["gates"] == ["G-MED-FSN"] and c["recommendation"] is None
    assert _failed(c)["rerent"] == f"No open recall or field safety notice: {FSN_TEXT}"
    # the correction record arrives: the unit is eligible again and the case is released
    _manual(30, "field_safety_status", at="2027-01-01T00:00:00+00:00", correction_ref="FSN-031-A")
    _recheck()
    c = _get(c["id"])
    assert _gate(c, "G-MED-FSN")["passed"] and c.get("gateHold") is None and "rerent" not in _failed(c)


def test_mr_15_a_unit_outside_the_serial_range_is_clear():
    c = _case(31, model="IP-300", serialNo=3131)  # just outside the notice's range
    assert _gate(c, "G-MED-FSN")["passed"] and c.get("gateHold") is None


def test_gate_wording_carries_the_legal_review_note():
    pack = load_pack("medical_rental")
    notes = {g.id: g.params.get("legal_review", "") for g in pack.gates if g.id in ("G-MED-SVC", "G-MED-FSN")}
    assert all("Kinective's Legal team" in n for n in notes.values()) and len(notes) == 2
    from di.services.modeler.gate_checks import medical

    assert "Kinective's Legal team" in (medical.__doc__ or "")
