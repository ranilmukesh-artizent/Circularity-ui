"""Plan 9, P9-11.12 (stories MR-12, MR-13 and MR-14): the medical rental company's diversions, and the one it cannot have.

A customer overlay (published through `overlay.save`, `submit` and `approve`) adds, on top of the pack:
  - DV-MR-ISO, a step `enhanced_decon` at the decontamination stage for a device from an isolation ward: the gate G-MED-DECON
    then needs a record of an ENHANCED cycle (`decon_enhanced`); a standard record does not pass;
  - DV-MR-SAME, a shortcut to `rerent` at the decide stage when the hospital the device came back from asks again within 24
    hours: it takes the best `rerent:<request>`, but only after G-MED-DECON and G-MED-SVC pass (R20: gates, then diversions);
  - DV-MR-SKIP, a shortcut that skips the decontamination record: refused, with the pack's own wording and the suggestion to
    dispatch an already decontaminated unit from the nearest depot, and audited. A person asks for a change to the guardrail.
The writer `enhanced_decon` schedules the enhanced cycle in the decontamination log (`POST /cycles {enhanced: true}`, stubbed
here: no source-sim). An agent never waives or skips a locked guardrail. Facts are written by the real adapters' mapping on
literal records. Legal note: the decontamination wording is summarised guidance; Kinective's Legal team reviews it before it is
relied on.
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
from di.repositories.live_rules import live_pack
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key, tag_key
from di.services.canonical.store import Fact
from di.services.cases import store as cases
from di.services.cases.decide import decide_case
from di.services.instructions import queue, writers
from di.services.modeler.compile import FlowVersion
from di.services.modeler.overlay import apply_overlay, parse_ops
from tests import flowkit, starting
from tests.helpers import call

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "medical_rental.json"
IN = "2026-11-17T06:00:00+00:00"
AFTER = "2026-11-17T09:30:00+00:00"
ISO = {"id": "op-1", "op": "add_step", "stage": "match", "step": "enhanced_decon", "owner_role": "decontamination_lead",
       "when": [{"fact": "asset.ward_type", "op": "eq", "value": "isolation"}]}  # fmt: skip
SAME = {"id": "op-2", "op": "shortcut", "stage": "decide", "to": "rerent",
        "when": [{"fact": "demand.same_hospital_within_24h", "op": "eq", "value": True}]}  # fmt: skip
SKIP = {"id": "op-3", "op": "shortcut", "stage": "receive", "to": "condition",
        "when": [{"fact": "request.priority", "op": "eq", "value": "emergency"}]}  # fmt: skip
REFUSAL = (
    "Blocked: this would bypass the compliance guardrail 'Decontamination record required'; ask for a change to the guardrail "
    "instead. Suggestion: dispatch an already decontaminated unit from the nearest depot."
)


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
        conn.execute(text("DELETE FROM domain_event WHERE type = 'overlay.blocked'"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SYN-MR-%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYN-MR-%"})


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
    with SessionLocal() as s:
        for sid in ("mr_rental", "mr_decon", "mr_biomed", "mr_assets"):
            extra.register(s, sid, ORG)
        s.commit()
    yield
    _clean()
    flowkit.reset_flows()
    starting.reset()


def _write(source: str, resource: str, payload: dict[str, Any]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, ADAPTERS[source].map(Record(resource, "x", payload)))
        s.commit()


def _publish(*ops: dict[str, Any]) -> None:
    body = {"pack_key": "medical_rental", "org_unit_id": ORG}
    _ok(call("overlay.save", body | {"ops": list(ops)}, "planner-a"))
    _ok(call("overlay.submit", body, "planner-a"))
    _ok(call("overlay.approve", body, "approver"))


def _open(n: int, *, ward: str = "general", hospital: str = "HOSP-D", decon: str | None = AFTER, enhanced: bool = False) -> dict:
    """The return of device n from `hospital`'s `ward` ward, with its records on file (`decon`: when its cycle ended, None: no
    record; `enhanced`: it was an enhanced cycle), four open requests of HOSP-B, and its case opened from data."""
    _write("mr_assets", "devices", {"tag": tag(n), "deviceClass": "infusion_pump", "model": "IP-200", "serial": 2000 + n,
                                    "org_unit_id": ORG})  # fmt: skip
    _write("mr_biomed", "service", {
        "tag": tag(n), "model": "IP-200", "serialNo": 2000 + n, "pmDue": "2027-02-15", "pmCode": "PM-12M",
        "lastPm": "2026-02-15", "certificationExpiry": "2027-03-31", "functionalTest": {"result": "pass", "at": "2026-11-10"},
        "electricalSafety": {"standard": "IEC 62353", "result": "pass", "at": "2026-11-10"}, "notes": [], "repairEstimate": 0,
        "faults": [], "notice": None, "org_unit_id": ORG,
    })  # fmt: skip
    _write("mr_rental", "returns", {
        "returnId": f"RET-{n:04d}", "tag": tag(n), "hospitalId": hospital, "ward": "Ward 3", "wardType": ward, "depot": "EAST",
        "checkedInAt": IN, "previousRentalEnd": "2026-11-16", "org_unit_id": ORG,
    })  # fmt: skip
    reqs = [{"reqId": f"REQ-{k}", "hospitalId": "HOSP-B", "deviceClass": "infusion_pump", "startDate": "2026-11-27", "days": 30,
             "region": "EAST", "requestedAt": "2026-11-26T08:00:00+00:00", "latitude": 40.0, "longitude": -74.9}
            for k in (1, 2, 3, 4)]  # fmt: skip
    _write("mr_rental", "demand", {"tag": tag(n), "depot": {"latitude": 40.0, "longitude": -75.0}, "requests": reqs,
                                   "forecast": [], "org_unit_id": ORG})  # fmt: skip
    if decon is not None:
        _write("mr_decon", "cycles", {
            "cycleId": f"DC-{n:04d}", "tag": tag(n), "method": "enhanced" if enhanced else "standard", "enhanced": enhanced,
            "cycleStartedAt": "2026-11-17T04:00:00+00:00", "cycleEndedAt": decon, "operatorRef": "OP-01", "result": "pass",
            "org_unit_id": ORG,
        })  # fmt: skip
    key = tag_key(ORG, tag(n))
    for kind in ("refurb_assessment",):
        row = {"asset_key": key, "type": kind, "result": "pass", "ref": "R-1", "at": "2026-11-01T00:00:00+00:00", "value": {}}
        with SessionLocal() as s:
            canonical.apply(s, "manual", [Fact("compliance", compliance_key(key, kind), f, v) for f, v in row.items()])
            s.commit()
    body = {
        "org_unit_id": ORG,
        "template_key": "medical_rental",
        "asset_key": key,
        "reason": "rental_return",
        "facts": {"tag": tag(n), "cls": "infusion_pump", "age_years": 3, "book_value": 1150, "residual_sale_value": 1100},
    }
    with SessionLocal() as s:
        cid = _ok(call("case.open", body, "planner-a"))["case_id"]
        c = cases.get(s, cid)
    assert c is not None
    return c


def _decon(c: dict) -> dict:
    return next(g for g in c["gates"] if g["id"] == "G-MED-DECON")


# ---------------------------------------------------------------- MR-12
def test_mr_12_isolation_ward_enhanced_decon():
    _publish(ISO)
    standard = _open(10, ward="isolation", enhanced=False)  # SYN-MR-IP-0010: a standard record does not pass
    g = _decon(standard)
    assert not g["passed"] and "Enhanced decontamination record required" in g["reason"], g
    assert standard["recommendation"] is None and standard["gateHold"]["gates"] == ["G-MED-DECON"]
    assert [(x["step"], x["owner"], x["stage"]) for x in standard["requiredSteps"]] == [
        ("enhanced_decon", "decontamination_lead", "match")
    ]
    assert standard["asset"]["ward_type"] == "isolation"
    enhanced = _open(20, ward="isolation", enhanced=True)  # an enhanced record passes
    assert _decon(enhanced)["passed"] and enhanced["recommendation"] is not None and enhanced.get("gateHold") is None


def test_mr_12_general_ward_and_no_diversion_are_unchanged():
    _publish(ISO)
    general = _open(11, ward="general", enhanced=False)  # the diversion does not apply: a standard record passes
    assert _decon(general)["passed"] and general["recommendation"] is not None and not general.get("requiredSteps")
    _clean_overlay()
    plain = _open(21, ward="isolation", enhanced=False)  # no overlay: the pack's own gate, a standard record passes
    assert _decon(plain)["passed"] and not plain.get("requiredSteps")


def test_mr_12_the_writer_schedules_an_enhanced_cycle(monkeypatch):
    seen: list[tuple[str, str, Any]] = []

    class Reply:
        def json(self) -> dict:
            return {"cycleId": "DC-1001", "status": "scheduled"}

    class Fake:
        def request(self, method: str, path: str, **kw: Any) -> Reply:
            seen.append((method, path, kw["json"]))
            return Reply()

        def close(self) -> None:
            pass

    monkeypatch.setattr(writers, "client", lambda s, source_id: seen.append(("client", source_id, None)) or Fake())
    out = writers.WRITERS["enhanced_decon"](None, {"kind": "enhanced_decon"}, {"assetId": tag_key(ORG, tag(10))}, {})
    assert seen == [("client", "mr_decon", None), ("POST", "/cycles", {"tag": tag(10), "enhanced": True})]
    assert out.doc_ref == "DC-1001" and out.detail == {"cycleId": "DC-1001", "enhanced": True}
    assert queue.SYSTEM_OF["enhanced_decon"] == "mr_decon" and writers.operations("mr_decon") == ["enhanced_decon"]
    with pytest.raises(writers.NotApplicable):
        writers.WRITERS["enhanced_decon"](None, {"kind": "enhanced_decon"}, {}, {})


# ---------------------------------------------------------------- MR-13
def test_mr_13_same_hospital_shortcut_keeps_gates():
    _publish(SAME)
    c = _open(12, hospital="HOSP-B")  # SYN-MR-IP-0012 came back from HOSP-B, which asks again within 24 hours
    assert c["demand"]["same_hospital_within_24h"] is True
    assert c["recommendation"]["id"].startswith("rerent:") and c["recommendation"]["dest"]["name"] == "Re-rent · HOSP-B"
    assert c["preferred"] == c["recommendation"]["id"]
    held = _open(22, hospital="HOSP-B", decon=None)  # no decontamination record: the shortcut revives nothing
    assert _decon(held)["passed"] is False and held["gateHold"]["gates"] == ["G-MED-DECON"] and held["recommendation"] is None
    with SessionLocal() as s:
        d = decide_case(held["id"], live_pack(s, held), FlowVersion(None, 3, ()), session=s)
    assert d.diversions == ["op-2"] and d.route is None and all(r["excluded"] for r in d.routes)


def test_mr_13_another_hospital_takes_no_shortcut():
    _publish(SAME)
    c = _open(13, hospital="HOSP-D")
    assert c["demand"]["same_hospital_within_24h"] is False and c.get("preferred") is None


# ---------------------------------------------------------------- MR-14
@pytest.mark.parametrize("when", [SKIP["when"], ISO["when"], []], ids=["emergency", "isolation_ward", "always"])
def test_mr_14_decon_skip_blocked_with_suggestion(when):
    op = SKIP | {"when": when}
    r = call("overlay.save", {"pack_key": "medical_rental", "org_unit_id": ORG, "ops": [op]}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert r["error"]["overlay_code"] == "skips_compliance" and r["error"]["message"] == REFUSAL, r
    assert "dispatch an already decontaminated unit from the nearest depot" in r["error"]["message"]
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT payload FROM domain_event WHERE type = 'overlay.blocked'")).all()
    assert len(rows) == 1, rows  # audited
    p = rows[0].payload
    assert (p["guardrail"], p["by"], p["pack_key"], p["org_unit_id"]) == ("G-MED-DECON", "planner-a", "medical_rental", ORG)
    assert p["op"]["id"] == "op-3"
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM customer_overlay")).scalar_one() == 0  # nothing was saved


def test_mr_14_the_overlay_itself_refuses_it():
    from di.services.modeler.overlay import OverlayError as Refused
    from di.services.modeler.pack import load_pack

    with pytest.raises(Refused) as e:
        apply_overlay(load_pack("medical_rental"), parse_ops([SKIP]))
    assert e.value.code == "skips_compliance" and e.value.guardrail == "G-MED-DECON" and str(e.value) == REFUSAL


def _clean_overlay() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM customer_overlay"))
