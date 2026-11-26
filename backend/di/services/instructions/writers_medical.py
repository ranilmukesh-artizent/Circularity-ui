"""The medical rental pack's writes to its own systems (plan 9, P9-11.17; stories MR-19 and MR-23; registry entry I-4).

    dispatch             rental system (`mr_rental`)  POST /dispatches {tag, reqId, evidence: {serviceRef, certExpiry, deconRef}}
    service_order        biomedical service (`mr_biomed`)  POST /service-orders {tag, kind, dueBy}
    refurb_order         biomedical service            POST /service-orders {tag, kind: refurbish, dueBy}
    data_sanitisation    disposal partner (`mr_disposal`)  POST /sanitisations {tag}
    disposal_collection  disposal partner              POST /collections {tags, sanitisationRef}

The steps of a route are the pack's route instructions (`valuers.medical_steps`); each writer is a writer of the existing
instruction queue (`writers.WRITERS`): the same contract as every writer (`Sent`; a business refusal is `Refused`, a case with
nothing to write `NotApplicable`, a step that cannot go yet `Waiting`). Each system answers with its own document, which is the
confirmation: `detail.confirmed` lets the send acknowledge the step (the mocks send no completion event). All five are
idempotent in the systems (the dispatch on the request, the service order on tag, kind and date, the sanitisation on the tag).

- **dispatch (MR-23).** The request is the route's (`rerent:REQ-2`). The hospital's evidence is read from the device's `condition`
  record: the service record reference (the preventive maintenance code and its due date), the certification date and the
  decontamination record reference. A device with one missing is refused: the hospital must never get a device without them.
- **service_order / refurb_order.** The kind is the one the service gate proposed (`serviceCheck.proposed`), else `repair`
  (`refurbish` for a refurbishment); it is due by the rental's start date, or the route's lead days from now.
- **data_sanitisation / disposal_collection (MR-19).** The collection of a device with patient data waits for the sanitisation
  record (`condition.sanitisation_record_ref`): G-DATA-3's check (`gate_checks.data`) decides, and the write is `Waiting` until the
  record is on file. Its reference goes with the collection.

Never does: approve, or write language (no model step, R16). HIPAA 45 CFR 164.310(d) and GDPR Art. 32 are the reason for the
sanitisation gate; the wording needs review by Kinective's Legal team before it is relied on.
"""

# ruff: noqa: E501 - long sentence and SQL lines

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from di.connectors.http import SourceError
from di.core import clock
from di.services.cases import process, store
from di.services.instructions import writers
from di.services.instructions.writers import NotApplicable, Refused, Sent
from di.services.modeler.gate_checks.data import GATE, check_patient_data_sanitised
from di.services.modeler.gates import catalogue


def _device(c: store.Case) -> tuple[str, str]:
    key = str(c.get("assetId") or "")
    if ":" not in key:
        raise NotApplicable("no device tag")
    return key, key.split(":", 1)[1]


def _condition(s: Session, key: str) -> dict[str, Any]:
    from di.services.canonical import store as canonical  # lazy: only these writers read the store

    return dict((canonical.get(s, "condition", key) or {}).get("data") or {})


def _request(c: store.Case) -> dict[str, Any] | None:
    """The rental request of the chosen route (`rerent:REQ-2`), as the case holds it."""
    route = c.get("chosen") or c.get("recommendation") or {}
    req_id = str(route.get("id") or "").partition(":")[2]
    return next((q for q in c.get("rentalRequests") or [] if q.get("req_id") == req_id), None) if req_id else None


def _post(s: Session, source: str, path: str, body: dict[str, Any], id_field: str, extra: dict[str, Any] | None = None) -> Sent:
    cl = writers.client(s, source)
    try:
        doc = cl.request("POST", path, json=body).json()
    except SourceError as e:
        raise writers._refused(e) from e
    finally:
        cl.close()
    ref = str(doc.get(id_field) or "")
    detail = {"confirmed": bool(ref), id_field: ref, "step": True} | (extra or {})
    return Sent([{"call": f"POST {path.lstrip('/')}", "body": body}], ref or None, detail)


def dispatch(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Rental system: POST /dispatches with the evidence the hospital asks for (module docstring)."""
    key, tag = _device(c)
    req = _request(c)
    if req is None:
        raise NotApplicable("no rental request to dispatch the device against")
    cond = _condition(s, key)
    service = f"{cond['pm_code']}:{str(cond.get('pm_due') or '')[:10]}" if cond.get("pm_code") else ""
    evidence = {
        "serviceRef": service, "certExpiry": str(cond.get("certification_expiry") or "")[:10],
        "deconRef": str(cond.get("decon_record_ref") or ""),
    }  # fmt: skip
    if missing := [k for k, v in evidence.items() if not v]:
        raise Refused(f"The device has no {', '.join(missing)} on file: the hospital's evidence is incomplete")
    body = {"tag": tag, "reqId": str(req["req_id"]), "evidence": evidence}
    return _post(s, "mr_rental", "/dispatches", body, "dispatchId", {"evidence": evidence})


def _order(s: Session, c: store.Case, kind: str, lead_days: int) -> Sent:
    _, tag = _device(c)
    req = _request(c)
    if req is not None and req.get("start_date"):
        due = str(req["start_date"])[:10]
    else:
        due = (clock.now().date() + timedelta(days=lead_days)).isoformat()
    body = {"tag": tag, "kind": kind, "dueBy": due}
    return _post(s, "mr_biomed", "/service-orders", body, "orderId", {"kind": kind, "dueBy": due})


def service_order(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Biomedical service system: the service a device needs before it is rented again."""
    proposed = ((c.get("serviceCheck") or {}).get("proposed") or {}).get("input") or {}
    return _order(s, c, str(proposed.get("kind") or "repair"), 2)


def refurb_order(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Biomedical service system: the refurbishment of the device."""
    return _order(s, c, "refurbish", 10)


def data_sanitisation(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Disposal partner: the sanitisation of a device with patient data. Its record arrives later as `condition.sanitisation_record_ref`."""
    _, tag = _device(c)
    pack = process.pack_of(s, c["id"])
    if check_patient_data_sanitised({"cls": c.get("cls")}, pack, catalogue()[GATE]) is None:
        raise NotApplicable("the device has no patient data to sanitise")
    return _post(s, "mr_disposal", "/sanitisations", {"tag": tag}, "sanitisationId")


def disposal_collection(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Disposal partner: the collection. A device with patient data waits for its sanitisation record (G-DATA-3)."""
    key, tag = _device(c)
    ref = _condition(s, key).get("sanitisation_record_ref")
    gate = check_patient_data_sanitised(
        {"cls": c.get("cls"), "sanitisationRef": ref}, process.pack_of(s, c["id"]), catalogue()[GATE]
    )
    if gate is not None and not gate.passed:
        raise writers.Waiting("the sanitisation record (condition.sanitisation_record_ref)")
    body: dict[str, Any] = {"tags": [tag]} | ({"sanitisationRef": str(ref)} if gate is not None else {})
    return _post(s, "mr_disposal", "/collections", body, "collectionId")
