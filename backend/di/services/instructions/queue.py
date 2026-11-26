"""The instruction rows (table `instruction`): queue a step, record a send, acknowledge, and the simulated acknowledgements.

Steps go out strictly in the plan's order: `queue_first` (on approval) and `on_acknowledged` (on each acknowledgement)
insert one row and one `instruction.send` job, both inside the caller's transaction, so a step is queued exactly when
the action that makes it due commits.

A row's `match_refs` are written when it is queued, from values di chooses itself (the idempotency key, the planned
document number, the order-release id ...): an event can be matched even if it arrives before the send job has
recorded its own result.

Plan 6 C6: queuing a step also queues a run of the target system's approval-triggered (outbound) workflows
(di/workflow/triggers.py), in a savepoint, so a trigger that fails never fails the instruction.
"""

import logging
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock, jobs
from di.core.config import get_settings
from di.services.cases import store
from di.services.execution.steps import EX_STEP, ex_doc_ref
from di.services.instructions import follow_through

# The step kinds that are real writes to a mock, and the system (source id) each goes to. Every other kind is
# acknowledged by the simulated adapter (see di.services.instructions.writers).
SYSTEM_OF = {
    "order": "oms",
    "pod": "oms",
    "repair": "repair",
    "teardown": "repair",
    "transport": "tms",
    "move": "wms",
    "finance": "erp",
    "payout": "dvlab",  # P9-6.8: the payout of a received device, outside an approval's plan (di.services.device.payout.send)
    "recon_order": "uc_dms",  # P9-9.17: the used-car channels (the pack's route instructions)
    "lot_transfer": "uc_dms",
    "listing": "uc_dms",
    "dealer_trade": "uc_dms",
    "consignment": "uc_auction",
    "salvage_sale": "uc_auction",
    "residual": "erp",  # P9-9.20: the close of a used-car lease return, outside an approval's plan
    "lessee_charge": "uc_lease",
    "retire": "erp",  # P9-13.1: the fixed-asset retirement and transfer of a pack that owns the asset
    "transfer": "erp",
    "credit": "erp",  # P9-13.4: the customer credit memo (a service ticket's upgrade plan ends on it too: no credit, no write)
    "dispatch": "mr_rental",  # P9-11.17: the follow-through of a medical rental route (the pack's route instructions)
    "service_order": "mr_biomed",
    "biomed_refurb": "mr_biomed",
    "data_sanitisation": "mr_disposal",
    "disposal_collection": "mr_disposal",
    "enhanced_decon": "mr_decon",  # P9-11.12: an enhanced cycle for a device from an isolation ward
    "list": "dvmkt",  # P9-6.12: a received device is listed on the device market (di.services.device.settle)
}
# The kinds sent on their own, outside an approval's plan: no plan step to acknowledge, and the case's `exec` is not theirs
OFF_PLAN = frozenset({"payout", "residual", "lessee_charge"})


# P9-3.17: the steps a template writes to a source of its own (the tool fleet's re-issue goes to the fleet contract system, its
# harvest to the parts system); every other step, and every industrial step, goes where SYSTEM_OF says
TEMPLATE_SYSTEM_OF = {
    "tool_fleet": {"lease": "fleet", "partsxfer": "parts", "propsend": "fleet", "propdraft": "fleet", "propreserve": "parts"},
    "telecom_network": {  # P9-10.16: the telecom pack's steps go to its inventory, bench, broker and recycler sources
        "site_transfer": "tn_inv",
        "spares_transfer": "tn_inv",
        "refurb_order": "tn_bench",
        "teardown": "tn_bench",
        "firmware_upgrade": "tn_bench",
        "broker_listing": "tn_broker",
        "recycler_pickup": "tn_recycler",
    },
}  # P9-5.5: an approved refresh's proposal and draft lines go to the fleet contract system, its units to the parts system


def template_system(template: str | None, kind: str) -> str | None:
    """The source a template's step of this kind is written to, or None when the template has none of its own."""
    return TEMPLATE_SYSTEM_OF.get(template or "", {}).get(kind)


def enabled() -> bool:
    return get_settings().instructions


def instruction_key(approval_ref: str, step: int, kind: str) -> str:
    """The idempotency key, sent with every write of this step: APR-2026-10-3161.2.transport. Letters, digits, '-' and
    '.', so every system accepts it as an id or a reference."""
    return f"{approval_ref}.{step}.{kind}"


def journal_ref(approval_ref: str) -> str:
    """S/4's DocumentReferenceID (BKPF-XBLNR) holds 16 characters: the approval reference (APR-2026-10-3161), or for a
    later cycle's approval (APR-2026-10-3161-2) the same without its "APR-" prefix."""
    return approval_ref if len(approval_ref) <= 16 else approval_ref.removeprefix("APR-")[:16]


def _match_refs(c: store.Case, step: dict, key: str, approval_ref: str) -> list[str]:
    """What this step's events will carry that identifies it."""
    k = step["k"]
    refs = [key]
    if k in ("repair", "teardown", "move"):
        refs.append(ex_doc_ref(c, step))  # P_REPAIR_NUMBER / Manhattan OrderId: our planned document number
    if k == "transport":
        refs.append(f"OR-{key}")  # the order release id
    if k == "finance":
        refs.append(journal_ref(approval_ref))
    return refs


def queue(s: Session, c: store.Case, step: int) -> int | None:
    """Queue step `step` of the case's approved plan: an instruction row and its send job. Returns the row id."""
    x = c.get("exec")
    if not x or step >= len(x["steps"]):
        return None
    st = x["steps"][step]
    ref, kind = x["ref"], st.get("k") or "step"
    key = instruction_key(ref, step, kind)
    # a reset reopens cases with their old approval references; their earlier rows no longer mean anything
    s.execute(text("DELETE FROM instruction WHERE approval_ref = :r AND step = :n"), {"r": ref, "n": step})
    system = template_system(c.get("template"), kind) or SYSTEM_OF.get(kind) or (EX_STEP.get(kind) or {}).get("sys") or st["sys"]
    iid = s.execute(
        text(
            "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, match_refs, queued_at) "
            "VALUES (:c, :r, :n, :k, :sys, :key, CAST(:refs AS jsonb), :at) RETURNING id"
        ),
        {
            "c": c["id"],
            "r": ref,
            "n": step,
            "k": kind,
            "sys": system,
            "key": key,
            "refs": _json(_match_refs(c, st, key, ref)),
            "at": clock.now(),
        },
    ).scalar_one()
    if x.get("terms"):  # a service ticket's instruction carries the market terms (P9-4.9)
        s.execute(
            text("UPDATE instruction SET detail = detail || jsonb_build_object('terms', CAST(:t AS jsonb)) WHERE id = :i"),
            {"t": _json(x["terms"]), "i": iid},
        )
    jobs.enqueue(s, "instruction.send", {"instruction_id": iid})
    from di.services.actions.org_pilot import is_pilot  # plan 8 MVP-10.3; lazy: the actions import this package

    if not is_pilot(s, c["owner"]):  # pilot mode never sends, not even through an outbound workflow
        _trigger_outbound(s, system)
    return iid


def _trigger_outbound(s: Session, system: str) -> None:
    """Plan 6 C6: an instruction queued for a system runs its approval-triggered (outbound) workflows. In a savepoint
    (triggers.safely): a trigger that fails is logged and never fails the instruction."""
    try:
        from di.workflow import triggers

        triggers.safely(triggers.on_approval, s, system)
    except Exception:  # never let a trigger break the instruction
        logging.getLogger("di.services.instructions").exception("workflow triggers for %s failed", system)


def queue_first(s: Session, c: store.Case) -> int | None:
    """On approval: the first step goes out (only when sending instructions is switched on). A used car's route owner also gets
    the timer that reminds them when the route's confirmation is late (P9-9.17), whether or not instructions are sent."""
    follow_through.open_timer(s, c)
    return queue(s, c, 0) if enabled() else None


def on_acknowledged(s: Session, c: store.Case, step: int, ref: str) -> None:
    """In adapter.acknowledge's transaction: the step's row is acknowledged with the system's reference, and the next
    step is queued. A service ticket's `takeback` first opens the Returns cases of the old tools (P9-4.9)."""
    if c.get("serviceDesk") and c["exec"]["steps"][step]["k"] == "takeback":
        from di.services.service_desk import follow_through as sd_follow_through  # lazy: it reads the case store and the intake

        sd_follow_through.on_takeback(s, c, step)
    follow_through.on_confirmed(s, c, step, ref)  # a used car's last confirmation closes the route owner's timer
    if not enabled():
        return
    s.execute(
        text(
            "UPDATE instruction SET status = 'acknowledged', doc_ref = :ref, acknowledged_at = :at, waiting_for = NULL, "
            "last_error = NULL, updated_at = now() WHERE approval_ref = :r AND step = :n"
        ),
        {"ref": ref, "at": clock.now(), "r": c["exec"]["ref"], "n": step},
    )
    if step + 1 < len(c["exec"]["steps"]):
        queue(s, c, step + 1)


def resend(s: Session, c: store.Case) -> int | None:
    """instruction.resend: send the latest step again under the same key (the system deduplicates it)."""
    if not enabled() or not c.get("exec"):
        return None
    iid = s.execute(
        text("SELECT id FROM instruction WHERE approval_ref = :r ORDER BY step DESC LIMIT 1"), {"r": c["exec"]["ref"]}
    ).scalar()
    if iid is not None:
        jobs.enqueue(s, "instruction.send", {"instruction_id": iid, "resend": True})
    return iid


def get(s: Session, iid: int, for_update: bool = False) -> dict | None:
    q = "SELECT * FROM instruction WHERE id = :i" + (" FOR UPDATE" if for_update else "")  # noqa: S608 - only the fixed FOR UPDATE suffix is appended; values are bound
    row = s.execute(text(q), {"i": iid}).mappings().first()
    return dict(row) if row else None


def for_case(s: Session, case_id: str) -> list[dict]:
    rows = s.execute(text("SELECT * FROM instruction WHERE case_id = :c ORDER BY approval_ref, step"), {"c": case_id})
    return [dict(r) for r in rows.mappings()]


def simulated_due(s: Session) -> list[dict]:
    """Simulated steps whose acknowledgement time has come on the simulated clock."""
    rows = s.execute(
        text("SELECT * FROM instruction WHERE simulated AND status = 'sent' AND due_at <= :now ORDER BY id"), {"now": clock.now()}
    )
    return [dict(r) for r in rows.mappings()]


def simulated_due_at() -> object:
    return clock.now() + timedelta(hours=get_settings().simulated_ack_hours)


def _json(v) -> str:
    import json

    return json.dumps(v, default=str)
