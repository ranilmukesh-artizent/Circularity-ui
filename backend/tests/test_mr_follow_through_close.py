"""Plan 9, P9-11.17 (stories MR-19, MR-22, MR-23): the follow-through of an approved medical rental decision and its close.

`MR-S1` (pump, re-rent to `REQ-1`) is dispatched with the service record reference, the certification date and the
decontamination record reference. `MR-S8` (4-year patient monitor, repair over residual) is retired: sanitisation first, the
collection only after the sanitisation record, and a write-off held for Finance (`proposal.accept` is a person's). The close
records utilisation, turnaround and re-rented within 48 hours, and one training row each for demand and repair cost. The
writers run against a stub client (no source-sim). Legal note: G-DATA-3 (HIPAA 45 CFR 164.310(d); GDPR Art. 32) needs review by
Kinective's Legal team before it is relied on.
"""

# ruff: noqa: E501 - long sentence and SQL lines

from datetime import datetime, timedelta
from typing import Any, ClassVar

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.canonical.schema import tag_key
from di.services.cases import close_medical_rental as close
from di.services.cases import store
from di.services.instructions import queue, writers
from di.services.modeler.gate_checks.data import check_patient_data_sanitised as check
from di.services.modeler.gates import catalogue
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers.medical_steps import follow_steps
from tests.helpers import call
from tests.test_medical_rental_paths import (  # noqa: F401 - `fresh` is the autouse fixture
    ORG,
    SCENARIOS,
    _get,
    _open,
    _write,
    fresh,
    tag,
)

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")


class _Reply:
    def __init__(self, doc: dict[str, Any]):
        self._doc = doc

    def json(self) -> dict[str, Any]:
        return self._doc


class Stub:
    """A source client that records its writes and answers like the mocks do."""

    calls: ClassVar[list[tuple[str, str, Any]]] = []

    def __init__(self, source: str):
        self.source = source

    def request(self, method: str, path: str, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
        Stub.calls.append((self.source, path, json))
        doc = {
            "/dispatches": {"dispatchId": "DSP-0001", "status": "dispatched"},
            "/service-orders": {"orderId": "SO-0001"},
            "/sanitisations": {"sanitisationId": "SAN-0001", "status": "pending"},
            "/collections": {"collectionId": "COL-0001", "status": "collected"},
        }[path]
        return _Reply(doc)

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    Stub.calls = []
    monkeypatch.setattr(writers, "client", lambda s, source_id: Stub(source_id))


def _approve(c: dict, plan: str | None = None) -> dict:
    body = {"case_id": c["id"], "reviewed": True, "rationale": "Follow the numbers."}
    r = call(
        "decision.approve" if plan is None else "decision.override", body | ({} if plan is None else {"route": plan}), "approver"
    )
    assert r["ok"], r
    return _get(c["id"])


def _kinds(c: dict) -> list[str]:
    return [s["k"] for s in c["exec"]["steps"]]


def _send(c: dict, kind: str) -> Any:
    """Run the writer of the step `kind` of the approved case the way the sender does."""
    with SessionLocal() as s:
        case = store.get(s, c["id"])
        assert case is not None
        step = next(i for i, x in enumerate(case["exec"]["steps"]) if x["k"] == kind)
        ins = {
            "case_id": c["id"],
            "step": step,
            "kind": kind,
            "idem_key": f"K.{step}.{kind}",
            "approval_ref": case["exec"]["ref"],
        }
        return writers.WRITERS[kind](s, ins, case, {})


def _retired() -> dict:
    c = _open(8, **SCENARIOS["MR-S8"])
    assert c["approvalHolds"][0]["alternative"]["route"] == "retire"  # the repair is over the limit: retire is the alternative
    return _approve(c, "Retire")


def _held(cid: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT id, agent, action, status, input FROM agent_proposal WHERE case_id = :c ORDER BY id"), {"c": cid}
        )
        return [dict(r._mapping) for r in rows]


def _close(cid: str) -> close.CloseResult:
    with SessionLocal() as s:
        r = close.close_case(s, cid)
        s.commit()
    return r


def test_mr_19_retire_steps_and_write_off_held():
    c = _retired()
    assert _kinds(c) == ["data_sanitisation", "disposal_collection"]  # a patient monitor: sanitised, then collected
    assert [queue.SYSTEM_OF[k] for k in _kinds(c)] == ["mr_disposal", "mr_disposal"]
    out = _send(c, "data_sanitisation")
    assert out.doc_ref == "SAN-0001" and Stub.calls == [("mr_disposal", "/sanitisations", {"tag": tag(8)})]
    _write("mr_disposal", "sanitisations", {"sanitisationId": "SAN-0001", "tag": tag(8), "org_unit_id": ORG})
    out = _send(c, "disposal_collection")  # the record is on file: the collection goes, with its reference
    assert Stub.calls[-1] == ("mr_disposal", "/collections", {"tags": [tag(8)], "sanitisationRef": "SAN-0001"})
    assert out.doc_ref == "COL-0001"
    _write("mr_disposal", "certificates", {"certificateId": "DC-0001-1", "tag": tag(8), "org_unit_id": ORG})
    r = _close(c["id"])
    with SessionLocal() as s:
        cond = s.execute(
            text("SELECT data FROM canonical WHERE model = 'condition' AND key = :k"), {"k": tag_key(ORG, tag(8))}
        ).scalar()
    assert r.status == "closed" and cond["disposal_certificate_ref"] == "DC-0001-1"  # the certificate is stored
    assert _get(c["id"])["close"]["certificate_ref"] == "DC-0001-1"
    (p,) = _held(c["id"])
    assert p["action"] == "rental.writeOff" and p["status"] == "pending" and p["agent"] == close.AGENT
    assert p["input"]["amount"] == 700.0 and p["input"]["case_id"] == c["id"]
    again = _close(c["id"])
    assert len(_held(c["id"])) == 1 and [x["state"] for x in again.posts] == ["exists"]


def test_mr_19_patient_data_blocks_collection():
    c = _retired()
    with pytest.raises(writers.Waiting, match="sanitisation record"):
        _send(c, "disposal_collection")
    assert Stub.calls == []  # nothing was sent
    gate, pack = catalogue()["G-DATA-3"], load_pack("medical_rental")
    assert check({"cls": "patient_monitor"}, pack, gate).passed is False  # type: ignore[union-attr]
    assert check({"cls": "patient_monitor", "sanitisationRef": "SAN-1"}, pack, gate).passed is True  # type: ignore[union-attr]
    assert check({"cls": "infusion_pump"}, pack, gate) is None  # no patient data: nothing to sanitise
    assert check({"cls": "patient_monitor"}, load_pack("device"), gate) is None  # other packs keep the data's gate


def test_mr_23_dispatch_carries_evidence():
    c = _approve(_open(1, **SCENARIOS["MR-S1"]))
    assert _kinds(c) == ["dispatch"] and queue.SYSTEM_OF["dispatch"] == "mr_rental"
    out = _send(c, "dispatch")
    ((system, path, body),) = Stub.calls
    assert (system, path) == ("mr_rental", "/dispatches") and body["tag"] == tag(1) and body["reqId"] == "REQ-1"
    ev = body["evidence"]
    assert ev["certExpiry"] == "2027-03-31" and ev["serviceRef"] and ev["deconRef"] == "DC-0001"
    assert out.doc_ref == "DSP-0001"


def test_mr_19_the_steps_of_each_route():
    pack = load_pack("medical_rental")
    pump, monitor = {"cls": "infusion_pump"}, {"cls": "patient_monitor"}
    assert follow_steps("service_rerent", pack, pump) == ["service_order", "dispatch"]
    assert follow_steps("rerent:REQ-2", pack, pump) == ["dispatch"]
    assert follow_steps("refurbish", pack, pump) == ["refurb_order"]
    assert follow_steps("retire", pack, pump) == ["disposal_collection"]
    assert follow_steps("retire", pack, monitor) == ["data_sanitisation", "disposal_collection"]
    assert queue.SYSTEM_OF["service_order"] == queue.SYSTEM_OF["refurb_order"] == "mr_biomed"


def _dispatched(c: dict, hours: int) -> None:
    """The dispatch instruction is recorded as sent `hours` after the device's check-in (06:00 on 17 Nov)."""
    at = datetime.fromisoformat("2026-11-17T06:00:00+00:00") + timedelta(hours=hours)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM instruction WHERE case_id = :c AND kind = 'dispatch'"), {"c": c["id"]})
        s.execute(
            text(
                "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, match_refs, sent_at, status) "
                "VALUES (:c, :r, 0, 'dispatch', 'mr_rental', :k, '[]'::jsonb, :at, 'acknowledged')"
            ),
            {"c": c["id"], "r": c["exec"]["ref"], "k": f"T.{c['id']}", "at": at},
        )
        s.commit()


def test_mr_22_close_records_turnaround_and_48h():
    c = _approve(_open(1, **SCENARIOS["MR-S1"]))
    _dispatched(c, hours=30)
    r = _close(c["id"])
    assert r.status == "closed" and r.turnaround_hours == 30.0 and r.rerented_within_48h is True
    assert r.utilisation is not None and 0 < r.utilisation < 1
    got = _get(c["id"])["close"]
    assert got["turnaround_hours"] == 30.0 and got["rerented_within_48h"] is True
    assert len(got["training"]["demand"]) == 1 and len(got["training"]["repair_cost"]) == 1
    _close(c["id"])  # a second close adds no second row
    assert len(_get(c["id"])["close"]["training"]["demand"]) == 1
    late = _approve(_open(2, **SCENARIOS["MR-S1"]))
    _dispatched(late, hours=50)
    assert _close(late["id"]).rerented_within_48h is False


def test_mr_22_close_needs_an_approved_rental_case():
    c = _open(1, **SCENARIOS["MR-S1"])
    assert _close(c["id"]).status == "not_approved"
    assert _close("RT-1048").status == "not_applicable"
