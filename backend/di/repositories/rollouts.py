"""The rollouts of a decision flow (migration 0051; plan 9 P9-7.3, registry I-17): which version of the flow decides a case.

`version_for` is the one place that answers it. A case's stored assignment wins (sticky through approval, execution and
close, even after a pause or a rollback); else, while a canary runs, the case is assigned (`di.services.modeler.rollout.assign`)
and the assignment is stored; a paused rollout sends new cases to the base version; with no rollout the published version
decides, arm `none`. The write helpers are used by di.services.actions.rollout only.
"""

import json
from collections.abc import Mapping
from typing import Any, Literal, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.orm import Session

from di.repositories.flows import FlowRow
from di.services.modeler.rollout import Rollout, assign

Arm = Literal["canary", "control", "out", "none"]
_COLS = "id, subject_kind, subject_id, candidate_ver, base_ver, stage, region_key, region, share, salt"
# the stages in which a stored assignment still decides its case (after `full` everything runs the published version)
STICKY = ("canary", "paused", "rolled_back")
DECIDED = ("approved", "executing", "closed")  # a case in one of these keeps the version it was approved on


def _row(r: Any) -> Rollout:
    return Rollout(*r)


def rollouts_of(s: Session, flow_id: int, stages: tuple[str, ...] | None = None) -> list[Rollout]:
    """The flow's rollout rows, oldest first (one per region), optionally only those in these stages."""
    sql = f"SELECT {_COLS} FROM rollout WHERE subject_kind = 'flow' AND subject_id = :i"  # noqa: S608 - fixed columns
    if stages:
        sql += " AND stage = ANY(:st)"
    rows = s.execute(text(sql + " ORDER BY id"), {"i": str(flow_id), "st": list(stages or ())}).all()
    return [_row(r) for r in rows]


def active_rollout(s: Session, flow_id: int) -> list[Rollout]:
    """The rows of the flow's running or paused canary (empty: none). A flow has one canary at a time, one row a region."""
    return rollouts_of(s, flow_id, ("canary", "paused"))


def latest_stage(s: Session, flow_id: int) -> str | None:
    """The stage of the flow's newest rollout (None: it never had one)."""
    return s.execute(
        text("SELECT stage FROM rollout WHERE subject_kind = 'flow' AND subject_id = :i ORDER BY id DESC LIMIT 1"),
        {"i": str(flow_id)},
    ).scalar()


def _stored(s: Session, case_id: str, flow_id: int) -> tuple[str, str] | None:
    r = s.execute(
        text(
            "SELECT a.arm, a.ver FROM rollout_assignment a JOIN rollout r ON r.id = a.rollout_id "
            "WHERE a.case_id = :c AND r.subject_kind = 'flow' AND r.subject_id = :f AND r.stage = ANY(:st) "
            "ORDER BY a.at DESC LIMIT 1"
        ),
        {"c": case_id, "f": str(flow_id), "st": list(STICKY)},
    ).first()
    return (r[0], r[1]) if r else None


def _resolve(ver: str, f: FlowRow) -> int | Literal["draft"]:
    """A stored version as the caller reads it: `draft` while it is the flow's draft, else its number."""
    n = int(ver)
    return "draft" if f.draft is not None and n == (f.dver or f.ver + 1) and n != f.ver else n


def store_assignment(s: Session, rollout_id: int, case_id: str, arm: str, ver: int) -> None:
    s.execute(
        text(
            "INSERT INTO rollout_assignment (rollout_id, case_id, arm, ver) VALUES (:r, :c, :a, :v) "
            "ON CONFLICT (rollout_id, case_id) DO NOTHING"
        ),
        {"r": rollout_id, "c": case_id, "a": arm, "v": str(ver)},
    )


def version_for(s: Session, case: Mapping[str, Any], flow: FlowRow) -> tuple[int | Literal["draft"], Arm]:
    """(the flow version that decides the case, its arm). `draft` is the flow's draft (the canary's candidate, not yet
    published); an int is a published version (the flow's own or one in its history)."""
    case_id = str(case.get("id") or "")
    if case_id and (got := _stored(s, case_id, flow.id)):
        return _resolve(got[1], flow), cast(Arm, got[0])
    running = rollouts_of(s, flow.id, ("canary",))
    if not running:
        return flow.ver, "none"
    candidate = running[0].candidate_ver
    for ro in running:
        arm = assign(case_id, str(flow.id), ro.salt, _region(case, ro), ro)
        if arm == "out":
            continue
        if case_id:
            store_assignment(s, ro.id, case_id, arm, (candidate if arm == "canary" else flow.ver) or flow.ver)
        return (_resolve(str(candidate), flow) if arm == "canary" and candidate else flow.ver), arm
    return flow.ver, "out"


def _region(case: Mapping[str, Any], ro: Rollout) -> str | None:
    v = case.get(ro.region_key)
    return None if v is None else str(v)


# ---------------------------------------------------------------- writes (the rollout actions)
def insert(s: Session, flow_id: int, *, candidate: int | None, base: int, region_key: str, region: str, share: int,
           salt: str, by: str, run_id: int | None) -> int:  # fmt: skip
    return int(
        s.execute(
            text(
                "INSERT INTO rollout (subject_kind, subject_id, candidate_ver, base_ver, stage, region_key, region, share, "
                "salt, replay_run_id, set_by) VALUES ('flow', :f, :c, :b, 'canary', :k, :r, :sh, :salt, :run, :by) RETURNING id"
            ),
            {
                "f": str(flow_id),
                "c": candidate,
                "b": base,
                "k": region_key,
                "r": region,
                "sh": share,
                "salt": salt,
                "run": run_id,
                "by": by,
            },
        ).scalar_one()  # fmt: skip
    )


def set_share(s: Session, rollout_id: int, share: int, by: str, now: Any) -> None:
    s.execute(text("UPDATE rollout SET share = :sh, set_by = :by, set_at = :at WHERE id = :i"),
              {"sh": share, "by": by, "at": now, "i": rollout_id})  # fmt: skip


def set_stage(s: Session, flow_id: int, stage: str, frm: tuple[str, ...], by: str, now: Any,
              note: dict[str, Any] | None = None) -> None:  # fmt: skip
    """Move the flow's rows in `frm` to `stage`; `note` is merged into `stop_rules` (the reason of a pause)."""
    s.execute(
        text(
            "UPDATE rollout SET stage = :st, set_by = :by, set_at = :at, "
            "stop_rules = stop_rules || CAST(:n AS jsonb) "
            "WHERE subject_kind = 'flow' AND subject_id = :f AND stage = ANY(:frm)"
        ),
        {"st": stage, "by": by, "at": now, "n": json.dumps(note or {}), "f": str(flow_id), "frm": list(frm)},
    )


def clear_undecided(s: Session, flow_id: int) -> int:
    """Delete the assignments of cases not yet approved (a rollback), so their next evaluation uses the base version; approved,
    executing and closed cases keep theirs. Answers how many were deleted."""
    r = s.execute(
        text(
            "DELETE FROM rollout_assignment a USING rollout r WHERE a.rollout_id = r.id AND r.subject_kind = 'flow' "
            "AND r.subject_id = :f AND NOT EXISTS "
            "(SELECT 1 FROM case_record c WHERE c.id = a.case_id AND c.stage = ANY(:done))"
        ),
        {"f": str(flow_id), "done": list(DECIDED)},
    )
    return int(cast(CursorResult[Any], r).rowcount or 0)


def arm_counts(s: Session, flow_id: int) -> dict[str, int]:
    """The assignments per arm over the flow's rollouts."""
    rows = s.execute(
        text(
            "SELECT a.arm, count(*) FROM rollout_assignment a JOIN rollout r ON r.id = a.rollout_id "
            "WHERE r.subject_kind = 'flow' AND r.subject_id = :f GROUP BY a.arm"
        ),
        {"f": str(flow_id)},
    ).all()
    return {"canary": 0, "control": 0} | {k: int(n) for k, n in rows}


def done_replay(s: Session, flow_id: int, dver: int | None) -> int | None:
    """The newest done replay run of the flow's draft version `dver` (its id), else None."""
    if dver is None:
        return None
    r = s.execute(
        text("SELECT id FROM replay_run WHERE flow_id = :f AND dver = :d AND status = 'done' ORDER BY id DESC LIMIT 1"),
        {"f": flow_id, "d": dver},
    ).scalar()
    return int(r) if r is not None else None
