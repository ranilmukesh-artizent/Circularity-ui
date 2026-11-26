"""A case's stage, and the moves between stages (docs/backend-steps.md, B11).

The demo keeps one stored stage per case; the ten stages a person sees (Lease ends ... Reconcile and learn) are
derived from it and from the case's approval, execution steps and outcome (see di.services.cases.run).

| Stage | Means | Moves to |
|---|---|---|
| none | no decision yet: evidence missing, or every route failed a gate | awaiting_approval (evidence recorded, re-evaluated) |
| awaiting_approval | a recommendation waits for approval | approved, reeval (declined), or re-evaluated |
| approved | approved; instructions not yet acknowledged | executing, closed, reeval |
| executing | instructions acknowledged step by step | closed, reeval |
| reeval | declined, or changed after approval; must be re-evaluated | awaiting_approval, none |
| closed | every step acknowledged | (end) |

Every move writes the stage log, a domain event `case.stage_changed` and, through the action that caused it, the
action journal. A move to `reeval` is a case request: the case-triggered (decision) workflows run (plan 6 C6).
"""

import json
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.actions.registry import ActionError
from di.services.cases import store

MOVES: dict[str, set[str]] = {
    "none": {"awaiting_approval", "none"},
    "awaiting_approval": {"approved", "reeval", "awaiting_approval", "none"},
    "approved": {"executing", "closed", "reeval"},
    "executing": {"closed", "reeval"},
    "reeval": {"awaiting_approval", "none"},
    "closed": set(),
}
STAGES = list(MOVES)


def can_move(frm: str, to: str) -> bool:
    return to in MOVES.get(frm, set())


def move(s: Session, c: store.Case, to: str, reason: str, actor: str, seq: int | None = None) -> None:
    """Move a case (held FOR UPDATE by the caller) to a new stage, and record it. The caller commits."""
    frm = c["stage"]
    if not can_move(frm, to):
        raise ActionError("conflict", f"{c['id']} cannot go from {frm} to {to}.")
    c["stage"] = to
    store.save(s, c)
    p = {
        "c": c["id"], "f": frm, "t": to, "r": reason, "a": actor, "s": seq,
        "p": json.dumps({"case_id": c["id"], "from": frm, "to": to, "reason": reason, "by": actor}),
    }  # fmt: skip
    s.execute(
        text("INSERT INTO case_stage_log (case_id, from_stage, to_stage, reason, actor, seq) VALUES (:c, :f, :t, :r, :a, :s)"),
        p,
    )
    s.execute(
        text("INSERT INTO domain_event (type, seq, case_id, payload) VALUES ('case.stage_changed', :s, :c, CAST(:p AS jsonb))"),
        p,
    )
    if to == "reeval":
        # a reservation of the declined or changed decision frees its units (review M2; `unit_reservations.release`, written here
        # because the cases layer does not import the repositories)
        s.execute(text("UPDATE unit_reservation SET status = 'released' WHERE case_id = :c AND status = 'held'"), {"c": c["id"]})
        _case_request(s, c["id"])


def _case_request(s: Session, case_id: str) -> None:
    """The case needs a new decision: the published case-triggered (decision) workflows run (plan 6 C6,
    di/workflow/triggers.py on_case). In a savepoint of the caller's transaction: a trigger never fails the move."""
    try:
        from di.workflow import triggers

        triggers.safely(triggers.on_case, s, case_id)
    except Exception:  # never let a trigger break the stage move
        logging.getLogger("di.services.cases").exception("case request triggers for %s failed", case_id)


def history(s: Session, case_id: str) -> list[dict]:
    rows = s.execute(
        text("SELECT from_stage, to_stage, reason, actor, seq, at FROM case_stage_log WHERE case_id = :c ORDER BY id"),
        {"c": case_id},
    ).mappings()
    return [dict(r) | {"at": r["at"].isoformat()} for r in rows]
