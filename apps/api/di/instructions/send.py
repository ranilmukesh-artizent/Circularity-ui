"""Sending an instruction (the worker's `instruction.send` job) and acknowledging simulated steps.

A send locks its row, calls the step's writer and records the outcome:
    sent           the write went through (or had gone through before: same key, no second document); the step now
                   waits for the system's completion event
    simulated      no writer for the kind, or nothing for the system to act on (writers.NotApplicable): the row is
                   marked simulated and due `simulated_ack_hours` later on the simulated clock; `tick()` then
                   acknowledges it through adapter.acknowledge (demo reference, `simulated: true`)
    waiting        the step cannot go yet (delivery waits for the carrier's proof of delivery); the event that brings
                   what it waits for queues the send again (di/instructions/events.py)
    failed         the system refused it for a business reason (writers.Refused), or the job ran out of attempts
A system that is down or refuses the credentials raises; the error is kept on the row and the job queue retries with
exponential backoff (di/jobs.py), up to `job_max_attempts`.

`resend` (instruction.resend, or a test) sends an instruction again even when it was acknowledged: the writers are
idempotent, so the system answers with the document it already has.
"""

import json
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from di import clock
from di.actions.pipeline import SYSTEM, CallContext, invoke
from di.cases import store
from di.config import get_settings
from di.db import SessionLocal
from di.instructions import queue, writers

log = logging.getLogger("di.instructions")


def send(iid: int, resend: bool = False) -> str:
    """Send one instruction. Returns what happened (sent, simulated, waiting, failed, skipped); raises to retry."""
    with SessionLocal() as s:
        ins = queue.get(s, iid, for_update=True)
        if ins is None:
            return "skipped"
        if not resend and ins["status"] in ("acknowledged", "failed", "sent"):
            return "skipped"  # a duplicate job, or an event got there first
        c = store.get(s, ins["case_id"])
        if c is None or not c.get("exec") or c["exec"]["ref"] != ins["approval_ref"]:
            _update(s, iid, status="failed", last_error="The approval this instruction belongs to is no longer current")
            s.commit()
            return "failed"
        prev = _earlier(s, ins)
        writer = writers.WRITERS.get(ins["kind"])
        s.execute(text("UPDATE instruction SET attempts = attempts + 1, updated_at = now() WHERE id = :i"), {"i": iid})
        try:
            if writer is None:
                raise writers.NotApplicable(f"no write for {ins['kind']} steps in the mocked systems")
            out = writer(s, ins, c, prev)
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
            final = attempts >= get_settings().job_max_attempts
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
        return "sent"


def tick() -> int:
    """Acknowledge the simulated steps that are due on the simulated clock. Returns how many were acknowledged."""
    done = 0
    with SessionLocal() as s:
        due = queue.simulated_due(s)
    for ins in due:
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


def _update(s: Session, iid: int, **values) -> None:
    sets = ", ".join(f"{k} = CAST(:{k} AS jsonb)" if k == "request" else f"{k} = :{k}" for k in values)
    params = {k: json.dumps(v) if k == "request" else v for k, v in values.items()}
    s.execute(text(f"UPDATE instruction SET {sets}, updated_at = now() WHERE id = :i"), params | {"i": iid})
