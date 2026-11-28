"""The tool fleet's writes to its own systems (plan 9, P9-3.17 TF-10, P9-3.18 TF-14 and P9-5.5 CR-05; registry entries
I-6, I-11).

    nonreturnfee  a non-return fee posted by a person (`nonReturnFee.post`): one journal entry to SAP S/4HANA, the fee to the
                  fee income account against the clearing item, through the same SOAP call as a decision's actuals
                  (`writers.post_journal`); the key is the line, so a resend is a duplicate and posts nothing twice
    fleet_issue  the `lease` step of a re-issue (`release`): PATCH the contract line of the named renewal with the issued serial
                  fleet contract system  PATCH /contract-lines/{lineId}  {status: "issued", issuedSerial, issuedKey, issuedFor}
    parts_issue   the `partsxfer` step of a harvest: post each certified part to its open repair order
                  parts and service system  PATCH /repair-orders/open/{roId}
                  {status: "part_issued", issuedPart, issuedFrom, issuedKey}

Both are writers of the existing instruction queue (`writers.WRITERS`, chosen by `writers.write_kind` for a tool-fleet case):
the same contract as every writer (`Sent`; a business refusal is `Refused`, a case with nothing to write `NotApplicable`),
idempotent on the instruction key, which the writes carry as `issuedKey` and the mocks' update event returns, so
`instructions.events` acknowledges the step from it. Nothing is built beside the queue.

- **fleet_issue.** The renewal is the route's destination (`dest.id`, a fleet renewal such as FC-30117-R); its contract's
  lines are read and the line the tool comes off is the one written: the returned line of the renewal's tool class that
  carries the tool's own serial, else the first returned line of that class (by line id). A line already `issued` to this
  serial is a repeat: nothing is written again.
- **parts_issue.** The repair orders are the harvest route's `dest.wos`; the part is the one each order is waiting for
  (its `partName`). An order already holding this tool's part is left as it is.

Plan 9, P9-5.5 (story CR-05; registry entries I-6, I-11) adds the three steps of an approved contract refresh
(`execution/steps.py`: `propsend`, `propdraft`, `propreserve`), each written from `exec.proposal`, the document of the chosen
route (`services/refresh_decision.py`). The planned document numbers (PR-, DL-, RU-) are the ids the mock keeps, so a repeat finds
its document and writes nothing again:

    proposal_send  POST /proposals {proposalId, contractId, customer, feeMonthCurrent, feeMonthProposed, creditTotal,
                   renewalLikelihood, validUntil, status: "sent", issuedKey}: the fleet system delivers it to the customer
                   (synthetic: nothing leaves the stack)
    lines_draft    POST /draft-lines, one per tool {draftLineId: <ref>-NN, draftRef, proposalId, serial, action, feeMonth, credit}
    units_reserve  `unit_reservations.hold` for each matched unit, then PATCH /refurbished-units/{unitId} {status: "reserved",
                   reservedFor, reserveRef, issuedKey} in the parts system for a unit from stock

A unit that was reserved meanwhile (a held row of another case, or a reserved stock unit) refuses the step with `conflict`: what
the step held is let go, the case goes back to re-evaluation and the decision to the Fleet desk with the reason
(`refresh_decision.send_back`). The proposal and the lines already sent stay: the customer was told only what was approved.

Never does: approve or send for a person (the plan was approved by a person or the standing policy, the queue sends it), or
write language (no model step, R16: the document is computed). Only `units_reserve` reads and writes the database, through
`unit_reservations`. A source read-only here is refused by the queue before a writer runs (P9-0.14); the connected-tool unlink
before a re-issue (GR-11) is a known gap, not a story.
"""

import hashlib
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.connectors.adapters.fleet_contracts import issuable
from di.connectors.http import SourceClient, SourceError
from di.repositories import unit_reservations
from di.services.actions.registry import ActionError
from di.services.cases import store
from di.services.execution import ex_doc_ref
from di.services.instructions import writers
from di.services.instructions.writers import NotApplicable, Refused, Sent

# Paths are relative to the adapter's base path: `writers.client` already ends in /fleet/api/v1 (fleet) or /parts/api
# (parts), so a prefix here doubled it and every lease step failed with a 404 (writer 93, smoke-p9-3 step 14).
FLEET = ""
PARTS = ""


def _refused(e: SourceError) -> Exception:
    """A 4xx other than auth is a business refusal; anything else is retried (as `writers._refused`)."""
    return Refused(str(e)) if e.kind == "client" else e


def _line_of(lines: list[dict], serial: str, cls: str) -> dict | None:
    """The line to issue (module docstring): the tool's own returned line, else the first returned line of its class."""
    returned = sorted((x for x in lines if issuable(x, cls)), key=lambda x: x["lineId"])
    return next((x for x in returned if x.get("serial") == serial), returned[0] if returned else None)


def fleet_issue(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """The contract line of the named renewal is issued with the tool's serial (module docstring)."""
    route = c.get("chosen") or c["recommendation"]
    dest = route.get("dest") or {}
    renewal, serial = str(dest.get("id") or "").strip(), c["assetId"]
    if dest.get("kind") != "lease" or not renewal:
        raise NotApplicable("no named fleet renewal to issue the tool to")
    cl = writers.client(s, "fleet")
    try:
        ren = cl.get_json(f"{FLEET}/renewals/{renewal}")
        lines = cl.get_json(f"{FLEET}/contract-lines", params={"contractId": ren["contractId"], "limit": 100})["items"]
        done = next((x for x in lines if x.get("status") == "issued" and x.get("issuedSerial") == serial), None)
        if done:  # sent before: the line is issued to this tool already
            return Sent([], done["lineId"], {"lineId": done["lineId"], "renewal": renewal, "serial": serial, "duplicate": True})
        line = _line_of(lines, serial, str(ren.get("toolClass")))
        if line is None:
            raise Refused(
                f"No returned {ren.get('toolClass')} line on contract {ren['contractId']} to issue {serial} to for {renewal}"
            )
        body = {"status": "issued", "issuedSerial": serial, "issuedKey": ins["idem_key"], "issuedFor": renewal}
        cl.request("PATCH", f"{FLEET}/contract-lines/{line['lineId']}", json=body)
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    return Sent(
        [{"call": "PATCH contract-lines/{lineId}", "body": body}], line["lineId"],
        {"lineId": line["lineId"], "renewal": renewal, "contract": ren["contractId"], "serial": serial},
    )  # fmt: skip


def fee_post(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """The fee of the instruction's contract line is posted to S/4 (module docstring). The line and the amount come from the
    instruction's detail, which `instructions.fees.post` wrote from the canonical line when a person posted it."""
    d = ins.get("detail") or {}
    line_id, fee = str(d.get("line_id") or ""), float(d.get("fee") or 0)
    if not line_id or fee <= 0:
        raise NotApplicable("no fee to post")
    ref = f"FEE-{line_id}"
    if len(ref) > 16:  # the journal reference holds 16 characters: a long id keeps a hash of the whole id, so two never collide
        ref = "FEE-" + hashlib.sha1(line_id.encode()).hexdigest()[:12]  # noqa: S324 - a short reference, not a secret
    items = [
        writers._item(1, writers.GL_FEE, -fee, f"Non-return fee {line_id}", line_id, None, None),
        writers._item(2, writers.GL_CLEARING, fee, f"Fee clearing {line_id}", writers.CLEARING, None, None),
    ]
    doc, detail = writers.post_journal(s, ins, ref, f"Fee {line_id}", items)
    call = {"call": "POST JournalEntryCreateRequestConfirmation_In", "body": {"DocumentReferenceID": ref, "fee": fee}}
    return Sent([call], doc, detail | {"line_id": line_id, "fee": fee})


def parts_issue(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Each certified part is posted to its open repair order (module docstring)."""
    route = c.get("chosen") or c["recommendation"]
    orders = [str(x) for x in (route.get("dest") or {}).get("wos") or []]
    serial = c["assetId"]
    if not orders:
        raise NotApplicable("no open repair order to post a part to")
    calls: list[dict] = []
    cl = writers.client(s, "parts")
    try:
        for ro in orders:
            doc = cl.get_json(f"{PARTS}/repair-orders/open/{ro}")
            if doc.get("status") == "part_issued" and doc.get("issuedFrom") == serial:
                continue  # sent before
            body = {
                "status": "part_issued",
                "issuedPart": doc.get("partName"),
                "issuedFrom": serial,
                "issuedKey": ins["idem_key"],
            }
            cl.request("PATCH", f"{PARTS}/repair-orders/open/{ro}", json=body)
            calls.append({"call": "PATCH repair-orders/open/{roId}", "body": body})
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    return Sent(calls, orders[-1], {"orders": orders, "serial": serial, "duplicate": not calls})


# ---------------------------------------------------------------- an approved contract refresh (P9-5.5)
def _proposal(c: store.Case) -> dict[str, Any] | None:
    """The document of the approved route, kept on the plan at approval (`refresh_decision.on_approve`)."""
    return (c.get("exec") or {}).get("proposal")


def _step_ref(c: store.Case, kind: str) -> str:
    """The planned document number of the plan's step of this kind (`PR-40201`): the id the mock keeps."""
    return ex_doc_ref(c, next(st for st in c["exec"]["steps"] if st["k"] == kind))


def _found(cl: SourceClient, path: str) -> dict | None:
    """The document at `path`, None when the system has none (a 404)."""
    try:
        return cl.get_json(path)
    except SourceError as e:
        if e.status == 404:
            return None
        raise


def proposal_send(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """The proposal goes to the customer through the fleet contract system (module docstring)."""
    doc = _proposal(c)
    if not doc:
        raise NotApplicable("no approved proposal to send")
    ref = _step_ref(c, "propsend")
    body = {
        "proposalId": ref, "caseId": c["id"], "contractId": doc["contract"], "customer": doc["customer"], "market": doc["market"],
        "route": doc["route"], "currency": doc["currency"], "termMonths": doc["term_months"],
        "feeMonthCurrent": doc["fee_month_current"], "feeMonthProposed": doc["fee_month_proposed"],
        "savingVsNew": doc["saving_vs_new"], "creditTotal": doc["credit_total"], "renewalLikelihood": doc["renewal_likelihood"],
        "validUntil": doc["valid_until"], "approvedBy": doc.get("approver"), "status": "sent", "issuedKey": ins["idem_key"],
    }  # fmt: skip
    cl = writers.client(s, "fleet")
    try:
        if _found(cl, f"{FLEET}/proposals/{ref}"):  # sent before: the proposal with our number exists
            return Sent([], ref, {"proposalId": ref, "duplicate": True})
        cl.request("POST", f"{FLEET}/proposals", json=body)
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    return Sent([{"call": "POST proposals", "body": body}], ref, {"proposalId": ref, "validUntil": doc["valid_until"]})


def lines_draft(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """One draft contract line per tool of the proposal, under the proposal's number (module docstring)."""
    doc = _proposal(c)
    if not doc or not doc.get("lines"):
        raise NotApplicable("no proposal lines to draft")
    ref, pid = _step_ref(c, "propdraft"), _step_ref(c, "propsend")
    calls: list[dict] = []
    cl = writers.client(s, "fleet")
    try:
        for n, ln in enumerate(doc["lines"], start=1):
            line_id = f"{ref}-{n:02d}"
            if _found(cl, f"{FLEET}/draft-lines/{line_id}"):
                continue  # sent before
            body = {
                "draftLineId": line_id, "draftRef": ref, "proposalId": pid, "contractId": doc["contract"], "serial": ln["serial"],
                "toolClass": ln["cls"], "action": ln["action"], "feeMonth": ln["fee_month"], "credit": ln["credit"],
                "successor": ln["successor"], "issuedKey": ins["idem_key"],
            }  # fmt: skip
            cl.request("POST", f"{FLEET}/draft-lines", json=body)
            calls.append({"call": "POST draft-lines", "body": body})
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    return Sent(calls, ref, {"draftRef": ref, "lines": len(doc["lines"]), "duplicate": not calls})


def _already_mine(s: Session, case_id: str, unit_id: str) -> bool:
    return (
        s.execute(
            text("SELECT 1 FROM unit_reservation WHERE unit_id = :u AND case_id = :c AND status = 'held'"),
            {"u": unit_id, "c": case_id},
        ).first()
        is not None
    )


def _hold_all(s: Session, cl: SourceClient, c: store.Case, doc: dict[str, Any]) -> None:
    """Hold each matched unit (all or none, in a savepoint); a stock unit the parts system reserved for another case refuses
    it too. Raises ActionError conflict."""
    by = str(doc.get("approver") or "system")
    with s.begin_nested():
        for u in doc["units"]:
            if _already_mine(s, c["id"], u["unit_id"]):
                continue
            if u.get("source") == "stock":
                unit = _found(cl, f"{PARTS}/refurbished-units/{u['unit_id']}") or {}
                if unit.get("status") == "reserved" and unit.get("reservedFor") not in (None, c["id"]):
                    raise ActionError("conflict", f"{u['unit_id']} is already reserved for {unit['reservedFor']}")
            unit_reservations.hold(s, u["unit_id"], c["id"], u["need_id"], by, c.get("owner"))


def units_reserve(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Hold each matched unit and mark the stock units reserved in the parts system (module docstring)."""
    from di.services import refresh_decision  # lazy: it reads the case store and the intake, which load the writers

    doc = _proposal(c)
    units = list((doc or {}).get("units") or [])
    if not units:
        raise NotApplicable("no matched unit to reserve")
    ref = _step_ref(c, "propreserve")
    calls: list[dict] = []
    cl = writers.client(s, "parts")
    try:
        try:
            _hold_all(s, cl, c, doc or {})
        except ActionError as e:  # a unit was taken meanwhile: nothing of this step stays held, the decision goes back
            refresh_decision.send_back(s, c["id"], f"{e.message} Re-evaluate to propose another unit.")
            raise Refused(e.message) from e
        for u in (x for x in units if x.get("source") == "stock"):
            body = {"status": "reserved", "reservedFor": c["id"], "reserveRef": ref, "issuedKey": ins["idem_key"]}
            cl.request("PATCH", f"{PARTS}/refurbished-units/{u['unit_id']}", json=body)
            calls.append({"call": "PATCH refurbished-units/{unitId}", "body": body | {"unitId": u["unit_id"]}})
    except SourceError as e:  # the parts system refused a PATCH: the units held a moment ago are freed (review M2)
        unit_reservations.release(s, c["id"])
        raise _refused(e) from e
    finally:
        cl.close()
    return Sent(calls, ref, {"reserveRef": ref, "units": [u["unit_id"] for u in units]})
