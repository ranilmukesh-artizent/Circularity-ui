"""Sending an instruction (the worker's `instruction.send` job) and acknowledging simulated steps.

A send locks its row, calls the step's writer and records the outcome:
    sent           the write went through (or had gone through before: same key, no second document); the step now
                   waits for the system's completion event
    simulated      no writer for the kind, or nothing for the system to act on (writers.NotApplicable): the row is
                   marked simulated and due `simulated_ack_hours` later on the simulated clock; `tick()` then
                   acknowledges it through adapter.acknowledge (demo reference, `simulated: true`)
    waiting        the step cannot go yet (delivery waits for the carrier's proof of delivery); the event that brings
                   what it waits for queues the send again (di/services/instructions/events.py)
    failed         the source's connection is in the test environment (P9-8.1), the source is read-only here
                   (lifecycle.access_of, P9-0.14), the system refused it for a business
                   reason (writers.Refused), or the job ran out of attempts
    held           plan 8 MVP-10.3: the case's org unit, or one above it, is in pilot mode (di.services.actions.
                   org_pilot): nothing is sent; the row is marked held with the note "Pilot mode: not sent to <target>"
                   (detail.held, detail.note) and acknowledged by the simulated adapter like a simulated step
A system that is down or refuses the credentials raises; the error is kept on the row and the job queue retries with
exponential backoff (di/core/jobs.py), up to `job_max_attempts`.

When the target has an outbound workflow published here (di/services/instructions/outbound.py), its delivery method's changed
Timeout is the HTTP timeout of the write, its Retries how many times a transient failure is tried again before the row
fails (at most `job_max_attempts` tries in all), and its write connector's Target operation picks the repair order
type for Oracle Depot Repair. Without one (the demo), or with the defaults, a send is exactly as described above.

`resend` (instruction.resend, or a test) sends an instruction again even when it was acknowledged: the writers are
idempotent, so the system answers with the document it already has.
"""

import json
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.connectors import connection, lifecycle
from di.core import clock
from di.core.config import get_settings
from di.core.db import SessionLocal
from di.services.actions.org_pilot import is_pilot
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.cases import store
from di.services.instructions import outbound, queue, writers

log = logging.getLogger("di.services.instructions")


def send(iid: int, resend: bool = False) -> str:
    """Send one instruction. Returns what happened (sent, simulated, waiting, failed, skipped); raises to retry."""
    with SessionLocal() as s:
        ins = queue.get(s, iid, for_update=True)
        if ins is None:
            return "skipped"
        if not resend and ins["status"] in ("acknowledged", "failed", "sent"):
            return "skipped"  # a duplicate job, or an event got there first
        c = store.get(s, ins["case_id"])
        own_ref = ins["kind"] == "payout"  # a payout is sent on its own, outside an approval's plan (P9-6.8)
        if c is None or (not own_ref and (not c.get("exec") or c["exec"]["ref"] != ins["approval_ref"])):
            _update(s, iid, status="failed", last_error="The approval this instruction belongs to is no longer current")
            s.commit()
            return "failed"
        if is_pilot(s, c["owner"]):
            return _hold(s, ins, resend)
        prev = _earlier(s, ins)
        cfg = outbound.settings(s, ins["system"])  # the target's outbound workflow published here; {}: none (the demo)
        kind = writers.operation_for(ins["kind"], cfg.get("operation"))
        writer = writers.WRITERS.get(kind)
        if refusal := _refusal(s, ins["system"], writer is not None):
            _update(s, iid, status="failed", last_error=refusal)
            s.commit()
            return "failed"
        s.execute(text("UPDATE instruction SET attempts = attempts + 1, updated_at = now() WHERE id = :i"), {"i": iid})
        try:
            if writer is None:
                raise writers.NotApplicable(f"no write for {ins['kind']} steps in the mocked systems")
            with writers.timeout(cfg.get("timeout_s")):
                out = writer(s, ins if kind == ins["kind"] else {**ins, "kind": kind}, c, prev)
        except writers.NotApplicable as e:
            if resend:
                s.commit()
                return "skipped"
            _update(
                s, iid, status="sent", simulated=True, due_at=queue.simulated_due_at(), sent_at=clock.now(),
                request=[{"call": "simulated", "body": {"reason": str(e)}}], waiting_for=None, last_error=None,
            )  # fmt: skip
            s.commit()
            return "simulated"
        except writers.Waiting as e:
            _update(s, iid, waiting_for=str(e))
            s.commit()
            return "waiting"
        except writers.Refused as e:
            _update(s, iid, status="failed", last_error=str(e)[:1000])
            s.commit()
            log.warning("instruction %s refused: %s", iid, e)
            return "failed"
        except Exception as e:
            # retried by the job queue; the row keeps the error, and fails with the job's last attempt
            attempts = ins["attempts"] + 1
            most = get_settings().job_max_attempts
            if "retries" in cfg:  # the delivery method's Retries: tries after the first, within the job queue's own
                most = min(most, int(cfg["retries"]) + 1)
            final = attempts >= most
            _update(s, iid, last_error=f"{type(e).__name__}: {e}"[:1000], **({"status": "failed"} if final else {}))
            s.commit()
            raise
        s.execute(
            text(
                "UPDATE instruction SET status = CASE WHEN status = 'acknowledged' THEN status ELSE 'sent' END, "
                "doc_ref = COALESCE(doc_ref, :doc), detail = detail || CAST(:detail AS jsonb), "
                "request = CASE WHEN request IS NULL THEN CAST(:req AS jsonb) ELSE request END, "
                "sent_at = COALESCE(sent_at, :at), waiting_for = NULL, last_error = NULL, updated_at = now() WHERE id = :i"
            ),
            {"i": iid, "doc": out.doc_ref, "detail": json.dumps(out.detail), "req": json.dumps(out.request), "at": clock.now()},
        )
        s.commit()
    if out.detail.get("confirmed") and not resend:
        _confirm(ins, out.doc_ref)
    return "sent"


def _confirm(ins: dict, ref: str | None) -> None:
    """A write whose reply is the system's confirmation (the dealer system and the auction platform send no completion event,
    P9-9.17): the step is acknowledged with the document's reference, as an event would, through the pipeline as the system."""
    with SessionLocal() as s:
        r = invoke(
            "adapter.acknowledge",
            {"case_id": ins["case_id"], "step": ins["step"], "ref": ref},
            CallContext(actor=SYSTEM, session=s),
        )
        if r["ok"]:
            s.commit()
        else:
            s.rollback()  # the step is acknowledged already, or the case moved on


def _refusal(s: Session, system: str, has_writer: bool) -> str | None:
    """Why nothing is sent to this system, or None. A connection in the test environment (plan 9 P9-8.1) gets no
    instruction at all; a read-only source (P9-0.14) refuses the ones a writer would send."""
    if not has_writer and not connection.in_test(s, system):
        return None
    vendor = s.execute(text("SELECT vendor FROM source_system WHERE id = :i"), {"i": system}).scalar() or system
    if connection.in_test(s, system):
        return (
            f"{vendor} is in the test environment here: instructions are not sent. "
            "Ask its system owner to approve production access, then promote it."
        )
    if lifecycle.access_of(s, system) == "read":
        return (
            f"{vendor} is connected read-only here: instructions are not sent. " "Change its access to Read / write to send them."
        )
    return None


def _hold(s: Session, ins: dict, resend: bool) -> str:
    """Plan 8 MVP-10.3: the case's org unit (or one above it) is in pilot mode. Nothing is sent; the row is held with
    a note and acknowledged later by the simulated adapter, so the run goes on as with a simulated step."""
    if not resend:
        target = s.execute(text("SELECT vendor FROM source_system WHERE id = :i"), {"i": ins["system"]}).scalar()
        note = f"Pilot mode: not sent to {target or ins['system']}"
        s.execute(
            text("UPDATE instruction SET detail = detail || CAST(:d AS jsonb) WHERE id = :i"),
            {"d": json.dumps({"held": True, "note": note}), "i": ins["id"]},
        )
        _update(
            s, ins["id"], status="sent", simulated=True, due_at=queue.simulated_due_at(), sent_at=clock.now(),
            request=[{"call": "held", "body": {"note": note}}], waiting_for=None, last_error=None,
        )  # fmt: skip
    s.commit()
    return "held"


def tick() -> int:
    """Acknowledge the simulated steps that are due on the simulated clock. Returns how many were acknowledged."""
    done = 0
    with SessionLocal() as s:
        due = queue.simulated_due(s)
    for ins in due:
        if ins["kind"] == "payout":  # no plan step to acknowledge: the simulated payout is done when due (P9-6.8)
            with SessionLocal() as s:
                _update(s, ins["id"], status="acknowledged")
                s.commit()
            done += 1
            continue
        with SessionLocal() as s:
            r = invoke(
                "adapter.acknowledge",
                {"case_id": ins["case_id"], "step": ins["step"], "simulated": True},
                CallContext(actor=SYSTEM, session=s),
            )
            if r["ok"]:
                s.commit()
                done += 1
            else:
                s.rollback()
                # the case no longer takes this acknowledgement (re-evaluated, or acknowledged some other way)
                status = "acknowledged" if r["error"]["code"] == "duplicate" else "failed"
                _update(s, ins["id"], status=status, last_error=r["error"]["message"])
                s.commit()
    return done


def _earlier(s: Session, ins: dict) -> dict[str, dict]:
    """The earlier steps of the same approval, by kind (a writer may need what they returned)."""
    rows = s.execute(
        text("SELECT * FROM instruction WHERE approval_ref = :r AND step < :n ORDER BY step"),
        {"r": ins["approval_ref"], "n": ins["step"]},
    ).mappings()
    return {r["kind"]: dict(r) for r in rows}


_UPDATABLE = frozenset({"status", "last_error", "simulated", "due_at", "sent_at", "request", "waiting_for"})


def _update(s: Session, iid: int, **values) -> None:
    # the names go into the SQL text: only the columns this module writes are allowed
    if unknown := set(values) - _UPDATABLE:
        raise ValueError(f"not an updatable instruction column: {', '.join(sorted(unknown))}")
    sets = ", ".join(f"{k} = CAST(:{k} AS jsonb)" if k == "request" else f"{k} = :{k}" for k in values)
    params = {k: json.dumps(v) if k == "request" else v for k, v in values.items()}
    s.execute(text(f"UPDATE instruction SET {sets}, updated_at = now() WHERE id = :i"), params | {"i": iid})  # noqa: S608 - column names checked against _UPDATABLE above; values are bound
