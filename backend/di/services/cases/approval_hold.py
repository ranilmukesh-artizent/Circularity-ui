"""The approval item of a decision that is over a pack's approval limit (plan 9, P9-9.11, stories UC-11 and UC-12; registry
entry I-20 `process.open_item`).

    sync(s, case, pack)       one open `approval` item per approval limit the case's decision is over (`case["approvalHolds"]`
                              of kind `value`, set by `decide.write_back`), none once it is not: a used car whose recon
                              estimate is over AP-UC-RECON waits for the used-car manager (role Approver)
    close_for(...)            the person's `decision.approve`, `decision.override` or `decision.decline` closes the item with
                              who did it (the hooks are `di.services.actions.approval_items`)

The item's cause is the limit's reason ("Recon $2,800 over the $2,500 limit") with the figures behind it (the best retail price
after the recon, the auction price) and the action is the pack's own wording for the approval rule. The item is a `step` row of
type `AP-...`, which My work (I-20, `process.items_for`) shows as an `approval`; its SLA is the pack's
`runtime.sla_hours.approval` when it has one.
A case under the limit has no item: the standing policy (I-11) may approve it, as for any decision it covers.

Owns: the work items of type `AP-UC-RECON` (and any other limit of kind `value` a pack sets). Never does: approve, override or
decline (golden rule 10: `decision.approve` and `decision.override` are a person's and in `forbidden.py`), nor decide the channel:
the numbers are the valuer's, the words fixed wording over them (no language model reads or writes anything here, R16).
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.cases import process
from di.services.modeler.pack import Pack

# the work_item kinds are fixed by migration 0033 (exception, needs_info, step): My work shows an `AP-` step as an approval
ROW_KIND = "step"
PREFIX = "AP-"


def _money(v: Any) -> str:
    return f"${float(v):,.0f}" if v is not None else "not valued"


def _holds(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [h for h in case.get("approvalHolds") or [] if isinstance(h, Mapping) and h.get("kind") == "value"]


def _cause(case: Mapping[str, Any], hold: Mapping[str, Any]) -> str:
    rec = case.get("recommendation") or {}
    return (
        f"{hold['reason']}. Retail gross after recon {_money(hold.get('retail_after_recon'))}, auction gross "
        f"{_money(hold.get('auction_gross'))}. Recommended: {rec.get('plan') or 'no channel'}."
    )


def _open(s: Session, case_id: str) -> dict[str, int]:
    rows = s.execute(
        text("SELECT id, type FROM work_item WHERE case_id = :c AND type LIKE :p AND status = 'open' ORDER BY id"),
        {"c": case_id, "p": PREFIX + "%"},
    ).all()
    return {r.type: int(r.id) for r in rows}


def sync(s: Session, case: Mapping[str, Any], pack: Pack) -> None:
    """Open the item of each limit the decision is over, close the item of each it is no longer over (outcome "within the
    limit"). A case that already has the item keeps it. In the caller's transaction."""
    cid = str(case["id"])
    open_ = _open(s, cid)
    holds = {str(h["id"]): h for h in _holds(case)} if case.get("stage") != "closed" else {}
    for type_, item in open_.items():
        if type_ not in holds:
            process.close_item(s, item, "Within the limit", "system")
    for type_, h in holds.items():
        if type_ in open_:
            continue
        owner = str(h.get("owner") or "")
        process.open_item(
            s, kind=ROW_KIND, case_id=cid, org_unit_id=case.get("owner"), type=type_, title=f"{cid}: {h['reason']}",
            cause=_cause(case, h), action=str(h["action"]), owner_role=pack.roles.get(owner) or process.role_of_owner(owner),
            due_hours=pack.runtime.sla_hours.get("approval"), by="system",
        )  # fmt: skip


def close_for(s: Session, case_id: str, outcome: str, by: str) -> None:
    """Close every open approval item of the case (the person decided it)."""
    for item in _open(s, case_id).values():
        process.close_item(s, item, outcome, by)
