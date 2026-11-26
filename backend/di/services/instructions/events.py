"""Acknowledgements from the systems' events: which event completes which step, and how it finds its instruction.

| Step | Completing event (source) | Matched by (our value the event carries) | Reference acknowledged |
|---|---|---|---|
| order | `sterling.order.allocated` (oms) | Reference = the instruction key | OrderNo (SO-48102) |
| repair, teardown | `oracle.apps.csd.repair.complete` (repair) | REPAIR_NUMBER = our WO number | REPAIR_NUMBER (WO-47349) |
| transport | `otm.shipment.tenderAccepted` (tms) | orderReleaseXids contains OR-<key> | shipmentXid (LD-5nnnn) |
| move | `manhattan.order.shipped` (wms) | OrderId = our TR number / ExternalReference = key | OrderId (TR-47362) |
| pod | `sterling.order.fulfilled` (oms) | Reference = the instruction key | the proof of delivery (POD-5nnnn) |
| finance | `sap.s4.beh.journalentry.v1.JournalEntry.Created.v1` (erp) | DocumentReferenceID = approval ref | AccountingDocument |

A tool-fleet refresh (P9-5.5) has three more, all matched by `issuedKey` (the instruction key): `propsend` by
`fleet.proposal.created` (fleet), `propdraft` by `fleet.draft_line.created` (fleet; the first line's event completes it) and
`propreserve` by `parts.stock.updated` (parts). The reference acknowledged is the planned PR-, DL- or RU- number the writer sent.

Why these: each is the moment the step's work is done in the system that owns it — the unit is allocated to the line;
the repair is complete (tests passed, release to service); the carrier accepted the tender, so the load is booked
(the delivery itself is the delivery step's business); the warehouse shipped the unit; the order line is delivered
with its proof of delivery; the actual costs are posted. The carrier's delivery (`otm.shipment.delivered`) completes
no step: it records the proof of delivery on the transport instruction and releases the waiting delivery step.

Matching: our values are stored on the instruction when it is queued (`match_refs`), so an event that arrives before
the send job has recorded its reply still finds its step. The acknowledgement goes through the action pipeline as the
system actor (adapter.acknowledge with `step` and `ref`), so it is journaled and idempotent: a redelivered event finds
the step acknowledged and changes nothing.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from di.core import jobs
from di.core.db import SessionLocal
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.instructions import queue

log = logging.getLogger("di.services.instructions")


@dataclass(frozen=True)
class Completion:
    source: str
    kinds: tuple[str, ...]
    refs: Callable[[dict], list]  # the values that identify our instruction
    ref: Callable[[dict], str | None]  # the system's own reference for the acknowledgement


COMPLETES: dict[str, Completion] = {
    "sterling.order.allocated": Completion("oms", ("order",), lambda d: [d.get("Reference")], lambda d: d.get("OrderNo")),
    "oracle.apps.csd.repair.complete": Completion(
        "repair", ("repair", "teardown"), lambda d: [d.get("REPAIR_NUMBER")], lambda d: d.get("REPAIR_NUMBER")
    ),
    "otm.shipment.tenderAccepted": Completion(
        "tms", ("transport",), lambda d: list(d.get("orderReleaseXids") or []), lambda d: d.get("shipmentXid")
    ),
    "manhattan.order.shipped": Completion(
        "wms", ("move",), lambda d: [d.get("OrderId"), d.get("ExternalReference")], lambda d: d.get("OrderId")
    ),
    "sterling.order.fulfilled": Completion(
        "oms", ("pod",), lambda d: [d.get("Reference")], lambda d: (d.get("ProofOfDelivery") or {}).get("PODReference")
    ),
    "sap.s4.beh.journalentry.v1.JournalEntry.Created.v1": Completion(
        "erp", ("finance",), lambda d: [d.get("DocumentReferenceID")], lambda d: d.get("AccountingDocument")
    ),
    # P9-3.17: the tool fleet's re-issue (the contract line is issued) and harvest (a repair order got its part); matched by the
    # `issuedKey` the writers send, which is the instruction key
    "fleet.line.updated": Completion("fleet", ("lease",), lambda d: [d.get("issuedKey")], lambda d: d.get("lineId")),
    "parts.repair_order.updated": Completion("parts", ("partsxfer",), lambda d: [d.get("issuedKey")], lambda d: d.get("roId")),
    # P9-5.5: an approved refresh's proposal is created, its draft lines are created (one event each; the first completes it)
    # and its units are reserved in the parts system; each carries the instruction key as `issuedKey` and the planned reference
    "fleet.proposal.created": Completion("fleet", ("propsend",), lambda d: [d.get("issuedKey")], lambda d: d.get("proposalId")),
    "fleet.draft_line.created": Completion("fleet", ("propdraft",), lambda d: [d.get("issuedKey")], lambda d: d.get("draftRef")),
    "parts.stock.updated": Completion("parts", ("propreserve",), lambda d: [d.get("issuedKey")], lambda d: d.get("reserveRef")),
}
DELIVERED = "otm.shipment.delivered"


def _find(s, source: str, kinds: tuple[str, ...], refs: list) -> dict | None:
    refs = [str(r) for r in refs if r]
    if not refs:
        return None
    row = (
        s.execute(
            text(
                "SELECT * FROM instruction WHERE system = :src AND kind = ANY(:kinds) "
                "AND jsonb_exists_any(match_refs, CAST(:refs AS text[])) ORDER BY id DESC LIMIT 1"
            ),
            {"src": source, "kinds": list(kinds), "refs": refs},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def handle(ev: dict) -> dict | None:
    """Act on one source-sim CloudEvent. Returns what it did for an event that concerns an instruction, else None."""
    if not queue.enabled():
        return None
    t: Any = ev.get("type")
    data = ev.get("data") or {}
    source = str(ev.get("source", "")).rsplit("/", 1)[-1]
    if t == DELIVERED and source == "tms":
        return _delivered(data)
    rule = COMPLETES.get(t)
    if rule is None or rule.source != source:
        return None
    with SessionLocal() as s:
        ins = _find(s, source, rule.kinds, rule.refs(data))
        if ins is None:
            return None
        out = {"instruction": ins["id"], "step": ins["step"], "kind": ins["kind"]}
        if ins["status"] == "acknowledged":
            return out | {"acknowledged": False, "reason": "already acknowledged"}  # a redelivered event
        ref = rule.ref(data) or None
        r = invoke(
            "adapter.acknowledge",
            {"case_id": ins["case_id"], "step": ins["step"], **({"ref": ref} if ref else {})},
            CallContext(actor=SYSTEM, session=s),
        )
        if r["ok"]:
            s.commit()
            return out | {"acknowledged": True, "ref": r["output"]["ref"]}
        s.rollback()
        log.info("event %s for instruction %s not acknowledged: %s", t, ins["id"], r["error"])
        return out | {"acknowledged": False, "reason": r["error"]["message"]}


def _delivered(data: dict) -> dict | None:
    """The carrier delivered: keep the proof of delivery on the transport instruction, and send the delivery step that
    waits for it."""
    with SessionLocal() as s:
        ins = _find(s, "tms", ("transport",), list(data.get("orderReleaseXids") or []))
        if ins is None:
            return None
        proof = {
            "pod": data.get("externalEventReference"),
            "received_by": data.get("ssContactName"),
            "shipment": data.get("shipmentXid"),
            "at": data.get("eventdate"),
        }
        s.execute(
            text(
                "UPDATE instruction SET detail = detail || jsonb_build_object('delivery', CAST(:p AS jsonb)), updated_at = now() "
                "WHERE id = :i"
            ),
            {"p": json.dumps(proof), "i": ins["id"]},
        )
        waiting = s.execute(
            text(
                "SELECT id FROM instruction WHERE approval_ref = :r AND kind = 'pod' AND status = 'queued' "
                "AND waiting_for IS NOT NULL"
            ),
            {"r": ins["approval_ref"]},
        ).scalars()
        released = []
        for wid in waiting:
            s.execute(text("UPDATE instruction SET waiting_for = NULL, updated_at = now() WHERE id = :i"), {"i": wid})
            jobs.enqueue(s, "instruction.send", {"instruction_id": wid})
            released.append(wid)
        s.commit()
    return {"instruction": ins["id"], "kind": "transport", "delivery": proof, "released": released}
