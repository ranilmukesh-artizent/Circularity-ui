"""The close of a medical rental case: turnaround, utilisation and the 48-hour measure, the training rows, and the write-off of a
retired device (plan 9, P9-11.17; stories MR-22 and MR-19; reads registry entries I-7 (the outcome stage) and I-10 (the hold
policy); X-13 reuses its amounts).

    close_case(s, case_id, ctx=None) -> CloseResult   what the approved route's outcome says, and what the close prepares
    rental.close      {case_id}                       the action an agent (the close stage) or a person calls: `close_case`
    rental.writeOff   {case_id, amount, label}        the write-off of a retired device, posted once Finance accepts it

For a re-rent route (`rerent`, `service_rerent`) the dispatch is the end of the cycle. `close_case` reads the check-in time of the
device (canonical `asset.checked_in_at`, the rental system) and the time its `dispatch` instruction was sent (`instruction.sent_at`,
else `acknowledged_at`), and keeps on the case as `close`, all by code:
    turnaround_hours      check-in to dispatch, in hours (2 decimals)
    rerented_within_48h   the turnaround is at most 48 hours
    utilisation           rental days of the approved request / (rental days + turnaround days): the share of the cycle the device
                          earns (4 decimals)
    training              {demand: [row], repair_cost: [row]}: one row per case for each set, replaced, never duplicated by a
                          second close. The demand row is the request served and the hours it waited for a device; the repair-cost
                          row is the device's class, model and age with the repair estimate and the service orders of the case.
                          (The demand and repair-cost models of registry entry I-14 read these rows; the demand model is built
                          in a later phase, so the rows stay on the case until it is.)
A case with no dispatch yet is `waiting_for_dispatch`. A retired device's close keeps the disposal certificate
(`certificate_ref`, canonical `condition.disposal_certificate_ref`) and prepares the write-off: the device's book value as an agent's
`rental.writeOff`, which is in HELD_FOR_PERSON, so the hold policy holds it as a proposal for Finance at every level
(`proposal.accept` is a person's, never an agent's). Accepting it records the post on the case (`close.posted.write_off`) and, with
instructions on, queues a journal posting on its own, outside the approval's plan (`instructions.queue.OFF_PLAN`, writer `residual`
with the amount as a loss; key `CLOSE.<case>.write_off.<cents>`). A second close prepares nothing new for an amount that already has
a proposal, whatever its state.

Never does: close the case (its stage is the last acknowledgement's), approve anything, or post. A case that is not a rental case, or
was not approved, is left alone (`CloseResult.status`). No model step (R16): this reads facts and computes. Accounting references are
for orientation only: Finance and Kinective's Legal team confirm them.
"""

# ruff: noqa: E501 - long sentence and SQL lines

import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.core.config import get_settings
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.canonical import store as canonical
from di.services.cases import store as case_store

TEMPLATE = "medical_rental"
AGENT = "coordinator"  # the agent that prepares the write-off when the caller is not one (a person's call, a test)
RERENT = ("rerent", "service_rerent")
WITHIN_HOURS = 48
CENT = Decimal("0.01")

Status = Literal["closed", "not_applicable", "not_approved", "waiting_for_dispatch"]


@dataclass(frozen=True)
class CloseResult:
    """What `close_case` found and prepared. `posts` is one entry per write-off: {kind, amount, label, state, proposal}, state
    `held` (a proposal for Finance), `exists` (one was prepared before) or `refused` (`why`)."""

    status: Status
    reason: str = ""
    turnaround_hours: float | None = None
    rerented_within_48h: bool | None = None
    utilisation: float | None = None
    certificate_ref: str | None = None
    training: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    posts: list[dict[str, Any]] = field(default_factory=list)


def _d(v: Any) -> Decimal:
    return Decimal(str(v))


def _money(v: Decimal) -> float:
    return float(v.quantize(CENT, ROUND_HALF_UP))


def _time(v: Any) -> datetime | None:
    try:
        return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
    except ValueError:
        return None


def dispatched_at(s: Session, case_id: str) -> datetime | None:
    """When the case's dispatch instruction was sent (else acknowledged)."""
    row = s.execute(
        text(
            "SELECT COALESCE(sent_at, acknowledged_at) FROM instruction WHERE case_id = :c AND kind = 'dispatch' "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"c": case_id},
    ).scalar()
    return _time(row)


def _request(c: case_store.Case, route_id: str) -> dict[str, Any] | None:
    req_id = route_id.partition(":")[2]
    return next((q for q in c.get("rentalRequests") or [] if q.get("req_id") == req_id), None) if req_id else None


def measures(checked_in: datetime, sent: datetime, rental_days: Any) -> tuple[float, bool, float | None]:
    """(turnaround hours, re-rented within 48 hours, utilisation) of one cycle; pure."""
    hours = _d((sent - checked_in).total_seconds()) / 3600
    util: float | None = None
    if rental_days is not None and _d(rental_days) > 0:
        days = _d(rental_days)
        util = float((days / (days + hours / 24)).quantize(Decimal("0.0001"), ROUND_HALF_UP))
    return float(hours.quantize(CENT, ROUND_HALF_UP)), hours <= WITHIN_HOURS, util


def _training(
    c: case_store.Case, req: dict[str, Any] | None, hours: float | None, route_id: str
) -> dict[str, list[dict[str, Any]]]:
    """The rows this case adds to the demand set and the repair-cost set (module docstring)."""
    v = c.get("valuer") or {}
    out: dict[str, list[dict[str, Any]]] = {"demand": [], "repair_cost": []}
    if req is not None and hours is not None:
        out["demand"].append({
            "case_id": c["id"], "req_id": req.get("req_id"), "hospital_id": req.get("hospital_id"), "device_class": v.get("cls"),
            "requested_at": req.get("requested_at"), "start_date": req.get("start_date"), "days": req.get("days"),
            "hours_to_dispatch": hours,
        })  # fmt: skip
    out["repair_cost"].append({
        "case_id": c["id"], "device_class": v.get("cls"), "model": v.get("model"), "age_years": v.get("age_years"),
        "repair_estimate": v.get("repair_estimate"), "route": route_id.split(":", 1)[0],
        "service_orders": [o.get("kind") for o in c.get("serviceOrders") or []],
    })  # fmt: skip
    return out


def _prepared(s: Session, case_id: str, amount: Decimal) -> int | None:
    """The id of a write-off proposal already prepared for this amount (any state: a rejected one is not asked again)."""
    row = s.execute(
        text(
            "SELECT id FROM agent_proposal WHERE action = 'rental.writeOff' AND case_id = :c "
            "AND (input ->> 'amount')::numeric = :a ORDER BY id DESC LIMIT 1"
        ),
        {"c": case_id, "a": amount},
    ).scalar()
    return int(row) if row is not None else None


def _agent_ctx(s: Session, ctx: CallContext | None) -> CallContext:
    if ctx is None:
        return CallContext(actor=SYSTEM, session=s, preparer=AGENT)
    return replace(ctx, session=s, preparer=ctx.preparer or AGENT, confirmed=False)


def _write_off(s: Session, c: case_store.Case, ctx: CallContext | None) -> list[dict[str, Any]]:
    book = (c.get("valuer") or {}).get("book_value")
    amount = _d(book).quantize(CENT, ROUND_HALF_UP) if book is not None else Decimal(0)
    if amount <= 0:
        return []
    post = {"kind": "write_off", "amount": _money(amount), "label": "Write-off of the retired device"}
    if (pid := _prepared(s, c["id"], amount)) is not None:
        return [post | {"state": "exists", "proposal": pid}]
    r = invoke("rental.writeOff", {"case_id": c["id"], "amount": post["amount"], "label": post["label"]}, _agent_ctx(s, ctx))
    if r["ok"] and isinstance(r["output"], dict) and "held" in r["output"]:
        return [post | {"state": "held", "proposal": r["output"]["held"]}]
    return [post | {"state": "refused", "why": r["error"]["message"] if not r["ok"] else "Not held for a person."}]


def close_case(s: Session, case_id: str, ctx: CallContext | None = None) -> CloseResult:
    """The outcome of the approved route, kept on the case, and the write-off of a retired device prepared for Finance (module
    docstring). `ctx` is the caller's (an agent run's, with its stage); the write-off is always prepared by an agent, so it is
    always held."""
    c = case_store.get(s, case_id, for_update=True)
    if c is None or c.get("template") != TEMPLATE:
        return CloseResult("not_applicable", "Not a medical rental case.")
    route = c.get("chosen")
    if not c.get("exec") or not route:
        return CloseResult("not_approved", "No decision has been approved for the device yet.")
    route_id = str(route.get("id") or "")
    base = route_id.split(":", 1)[0]
    key = str(c.get("assetId") or "")
    close: dict[str, Any] = dict(c.get("close") or {})
    hours: float | None = None
    within: bool | None = None
    util: float | None = None
    req = _request(c, route_id)
    if base in RERENT:
        sent = dispatched_at(s, case_id)
        checked_in = _time(((canonical.get(s, "asset", key) or {}).get("data") or {}).get("checked_in_at"))
        if sent is None or checked_in is None:
            return CloseResult("waiting_for_dispatch", "The device has not been dispatched yet.")
        hours, within, util = measures(checked_in, sent, (req or {}).get("days"))
    certificate: str | None = None
    if base == "retire":
        certificate = ((canonical.get(s, "condition", key) or {}).get("data") or {}).get("disposal_certificate_ref")
    training = _training(c, req, hours, route_id)
    close |= {"route": base, "at": (ctx.now if ctx else clock.now()).isoformat(), "training": training}
    for name, value in (("turnaround_hours", hours), ("rerented_within_48h", within), ("utilisation", util),
                        ("certificate_ref", certificate)):  # fmt: skip
        if value is not None:
            close[name] = value
    c["close"] = close
    case_store.save(s, c)
    posts = _write_off(s, c, ctx) if base == "retire" else []
    return CloseResult("closed", "The outcome is recorded.", hours, within, util, certificate, training, posts)


# ---------------------------------------------------------------- the actions
ACTIONS.setdefault(
    "rental.close",
    ActionDef(
        id="rental.close", title="Close a rental device's case", verb="close a rental device's case",
        desc="Record the turnaround, utilisation and 48-hour re-rental of a dispatched rental device, add its training rows, and "
        "prepare the write-off of a retired device for Finance. The write-off is held for a person to accept.",
        risk="act", perm="confirm", scope="case", input={"case_id": {"req": True, "t": "string"}},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "rental.writeOff",
    ActionDef(
        id="rental.writeOff", title="Write off a retired rental device", verb="write off a retired rental device",
        desc="Post the write-off of a retired rental device to Finance once Finance accepts it. An agent's call is held for a person.",
        risk="act", perm="confirm", scope="case",
        input={
            "case_id": {"req": True, "t": "string"},
            "amount": {"req": True, "t": "number"},
            "label": {"req": True, "t": "string"},
        },
    ),
)  # fmt: skip


def _rental(ctx: CallContext, case_id: str) -> case_store.Case | None:
    c = case_store.get(ctx.session, case_id)
    return c if c is not None and c.get("template") == TEMPLATE else None


@guard("rental.close")
def close_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return None if _rental(ctx, i["case_id"]) else ("not_found", f"No live rental case {i['case_id']}.")


@implement("rental.close")
def close_action(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    r = close_case(ctx.session, i["case_id"], ctx)
    return {
        "case_id": i["case_id"], "status": r.status, "reason": r.reason, "turnaround_hours": r.turnaround_hours,
        "rerented_within_48h": r.rerented_within_48h, "utilisation": r.utilisation, "certificate_ref": r.certificate_ref,
        "posts": r.posts,
    }  # fmt: skip


@guard("rental.writeOff")
def write_off_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    c = _rental(ctx, i["case_id"])
    if c is None:
        return "not_found", f"No live rental case {i['case_id']}."
    if not i["amount"] or i["amount"] < 0:
        return "validation_error", "The amount is zero or negative."
    if ((c.get("close") or {}).get("posted") or {}).get("write_off"):
        return "duplicate", f"The write-off of {i['case_id']} is already posted."
    return None


@implement("rental.writeOff", idem=lambda i, ctx: f"{i['case_id']}:write_off")  # noqa: ARG005 - the key is the input
def write_off(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    c = case_store.get(ctx.session, i["case_id"], for_update=True)
    if c is None:  # not reached: the guard found it
        raise ActionError("not_found", f"No live rental case {i['case_id']}.")
    amount = _d(i["amount"]).quantize(CENT, ROUND_HALF_UP)
    iid = _queue(ctx.session, c, amount, str(i["label"]))
    close = dict(c.get("close") or {})
    close["posted"] = {
        **(close.get("posted") or {}),
        "write_off": {
            "amount": _money(amount),
            "label": i["label"],
            "by": ctx.actor.id,
            "at": ctx.now.isoformat(),
            "instruction": iid,
        },
    }
    c["close"] = close
    case_store.save(ctx.session, c)
    return {"case_id": c["id"], "kind": "write_off", "amount": _money(amount), "instruction": iid}


def _queue(s: Session, c: case_store.Case, amount: Decimal, label: str) -> int | None:
    """The journal posting of the write-off, sent on its own (only when sending instructions is switched on): one row and one
    `instruction.send` job, idempotent on the case and the amount in cents. The `residual` writer posts a loss as a debit."""
    from di.core import jobs  # lazy: the job queue is only needed by the write

    if not get_settings().instructions:
        return None
    cents = int((amount * 100).to_integral_value())
    ref, key = f"CLOSE-{c['id']}", f"CLOSE.{c['id']}.write_off.{cents}"
    detail = json.dumps({"close": {"kind": "write_off", "amount": -float(amount), "label": label}})
    s.execute(text("DELETE FROM instruction WHERE approval_ref = :r AND step = 0"), {"r": ref})
    iid = s.execute(
        text(
            "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, match_refs, detail, queued_at) "
            "VALUES (:c, :r, 0, 'residual', 'erp', :key, CAST(:refs AS jsonb), CAST(:d AS jsonb), :at) "
            "ON CONFLICT (idem_key) DO NOTHING RETURNING id"
        ),
        {"c": c["id"], "r": ref, "key": key, "refs": json.dumps([key]), "d": detail, "at": clock.now()},
    ).scalar()
    if iid is not None:
        jobs.enqueue(s, "instruction.send", {"instruction_id": iid})
    return int(iid) if iid is not None else None
