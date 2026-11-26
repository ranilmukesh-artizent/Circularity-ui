"""The route owner's timer for a used car's follow-through (plan 9, P9-9.17; story UC-18; registry entry I-20).

    open_timer(s, case)                  on approval: one step item (a task in My work) for the route owner, due in lead days
    on_confirmed(s, case, step, ref)     in an acknowledgement: the route's last confirmation closes the task

The approved route's steps are instructions to the dealer system and the auction platform (`writers`); each acknowledgement is
the system's confirmation and is kept on the step of the case's plan (`exec.steps[].ack`). The task is a work item of type
`UC-CONFIRM` (My work, I-20) for the pack route's `owner` (through the pack's `roles`), due `lead_days` days after the approval;
the case process layer's SLA timer (`process.on_sla`) escalates it when it is overdue, which is the reminder: the item stays with
its owner, more urgent, and a journal row and the event `work.escalated` say so. The last step's confirmation closes it with
"Confirmed: <reference>". A new approval of the same case closes the earlier task first, so there is one at a time.

Applies only to a case whose plan is a used-car channel's (a step kind of `KINDS`); every other case is left alone. Never does:
approve, send an instruction or change the case.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.cases import process
from di.services.cases import store as case_store

TYPE = "UC-CONFIRM"
KINDS = frozenset({"recon_order", "lot_transfer", "listing", "consignment", "dealer_trade", "salvage_sale"})
HOURS_PER_DAY = 24


def _is_used_car_plan(c: case_store.Case) -> bool:
    x = c.get("exec") or {}
    return any(st.get("k") in KINDS for st in x.get("steps") or [])


def open_timer(s: Session, c: case_store.Case) -> int | None:
    """The task for the chosen route's owner (module docstring); its id, or None for a case that is not a used car's or a route
    with no lead days."""
    if not _is_used_car_plan(c):
        return None
    pack = process.pack_of(s, c["id"])
    chosen: dict[str, Any] = c.get("chosen") or {}
    route = next((r for r in pack.routes if r.id == str(chosen.get("id", "")).split(":", 1)[0]), None)
    if route is None or not route.lead_days:
        return None
    close_open(s, c["id"], "Replaced by a new approval")
    last = c["exec"]["steps"][-1]
    return process.open_item(
        s, kind="step", case_id=c["id"], org_unit_id=c["owner"], type=TYPE,
        title=f"Confirm {route.name} for {c['id']} within {route.lead_days} days",
        cause=f"{last['label']} is not confirmed yet",
        action=f"Check that the {last['sys'].split(' · ')[0]} has accepted it",
        owner_role=pack.roles.get(route.owner) or process.role_of_owner(route.owner),
        due_hours=route.lead_days * HOURS_PER_DAY, by="system",
    )  # fmt: skip


def close_open(s: Session, case_id: str, outcome: str) -> None:
    """Close the case's open follow-through tasks."""
    ids = s.execute(
        text("SELECT id FROM work_item WHERE case_id = :c AND type = :t AND status = 'open'"), {"c": case_id, "t": TYPE}
    ).scalars()
    for i in list(ids):
        process.close_item(s, i, outcome, "system")


def on_confirmed(s: Session, c: case_store.Case, step: int, ref: str) -> None:
    """The step `step` is acknowledged with the system's reference `ref`: the last step's confirmation closes the task."""
    if _is_used_car_plan(c) and step == len(c["exec"]["steps"]) - 1:
        close_open(s, c["id"], f"Confirmed: {ref}")
