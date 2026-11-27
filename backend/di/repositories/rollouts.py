"""The rollouts of a decision flow (migration 0051; plan 9 P9-7.3, registry I-17): which version of the flow decides a case.

`version_for` is the one place that answers it. A case's stored assignment wins (sticky through approval, execution and
close, even after a pause or a rollback); else, while a canary runs, the case is assigned (`di.services.modeler.rollout.assign`)
and the assignment is stored; a paused rollout sends new cases to the base version; with no rollout the published version
decides, arm `none`. The write helpers are used by di.services.actions.rollout only.
"""

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.orm import Session

from di.repositories import flows as flow_repo
from di.repositories.flows import FlowRow
from di.services.modeler.canary_stats import DEFAULT_RULES
from di.services.modeler.rollout import Rollout, assign
from di.services.modeler.tables import market_spec

Arm = Literal["canary", "control", "out", "none"]
_COLS = "id, subject_kind, subject_id, candidate_ver, base_ver, stage, region_key, region, share, salt"
# the stages in which a stored assignment still decides its case (after `full` everything runs the published version)
STICKY = ("canary", "paused", "rolled_back")
DECIDED = ("approved", "executing", "closed")  # a case in one of these keeps the version it was approved on


def _row(r: Any) -> Rollout:
    return Rollout(*r)


def rollouts_of(s: Session, flow_id: int, stages: tuple[str, ...] | None = None, kind: str = "flow") -> list[Rollout]:
    """The flow's (or, `kind` "table", its service-desk tables') rollout rows, oldest first (one per region), optionally only
    those in these stages."""
    sql = f"SELECT {_COLS} FROM rollout WHERE subject_kind = :k AND subject_id = :i"  # noqa: S608 - fixed columns
    if stages:
        sql += " AND stage = ANY(:st)"
    rows = s.execute(text(sql + " ORDER BY id"), {"k": kind, "i": str(flow_id), "st": list(stages or ())}).all()
    return [_row(r) for r in rows]


def active_rollout(s: Session, flow_id: int, kind: str = "flow") -> list[Rollout]:
    """The rows of the flow's running or paused canary (empty: none). A flow has one canary at a time, one row a region."""
    return rollouts_of(s, flow_id, ("canary", "paused"), kind)


def latest_stage(s: Session, flow_id: int, kind: str = "flow") -> str | None:
    """The stage of the flow's newest rollout (None: it never had one)."""
    return s.execute(
        text("SELECT stage FROM rollout WHERE subject_kind = :k AND subject_id = :i ORDER BY id DESC LIMIT 1"),
        {"k": kind, "i": str(flow_id)},
    ).scalar()


def _stored(s: Session, case_id: str, flow_id: int, kind: str = "flow") -> tuple[str, str] | None:
    r = s.execute(
        text(
            "SELECT a.arm, a.ver FROM rollout_assignment a JOIN rollout r ON r.id = a.rollout_id "
            "WHERE a.case_id = :c AND r.subject_kind = :k AND r.subject_id = :f AND r.stage = ANY(:st) "
            "ORDER BY a.at DESC LIMIT 1"
        ),
        {"c": case_id, "k": kind, "f": str(flow_id), "st": list(STICKY)},
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


# ---------------------------------------------------------------- the market canary of the service-desk tables (P9-7.7)
TABLE_PACK = "tool_fleet"
TABLE_FLOW = "tool_fleet"  # the template whose flow a table rollout hangs on (the service desk is a flow of the tool-fleet pack)


def standard_market(market: str) -> str:
    """The market whose tables give the standard quote of a pilot market: the first other market of the pack in the same
    currency (FR in pilot: DE, both EUR), so the quote stays in the customer's currency; the market itself when there is none."""
    spec = market_spec(TABLE_PACK)
    markets = spec.markets if spec else {}
    same = sorted(m for m, cur in markets.items() if cur == markets.get(market) and m != market)
    return same[0] if same else market


def table_version_for(s: Session, case: Mapping[str, Any]) -> tuple[str, Arm]:
    """(the market whose tables price the ticket of this case, its arm). A stored assignment wins (sticky through approval,
    execution and close); while a table canary of the case's market runs, the ticket is assigned (the canary: the market's own
    tables; the control: the standard quote) and the assignment is stored; a paused or rolled-back canary sends new tickets to the
    standard quote; with no rollout, or once it is full, the market's own tables, arm `none`. A market outside a running table
    rollout is `out`: the canary of another market never touches it."""
    sd = case.get("serviceDesk")
    market = str(sd.get("market") or "") if isinstance(sd, dict) else ""
    owner = case.get("owner")
    flow = flow_repo.flow_for(s, TABLE_FLOW, str(owner)) if market and owner else None
    if flow is None:
        return market, "none"
    mine = [r for r in rollouts_of(s, flow.id, kind="table") if r.region_key == "market"]
    if not mine:
        return market, "none"
    case_id = str(case.get("id") or "")
    if market not in {r.region for r in mine}:
        return market, "out" if any(r.stage in ("canary", "paused") for r in mine) else "none"
    if case_id and (got := _stored(s, case_id, flow.id, "table")):
        return got[1], cast(Arm, got[0])
    ro = next(r for r in reversed(mine) if r.region == market)
    if ro.stage == "canary":
        arm = assign(case_id, str(flow.id), ro.salt, market, ro)
        read = market if arm == "canary" else standard_market(market)
        if case_id:
            store_assignment_text(s, ro.id, case_id, arm, read)
        return read, cast(Arm, arm)
    if ro.stage in ("paused", "rolled_back"):
        return standard_market(market), "none"
    return market, "none"


def store_assignment_text(s: Session, rollout_id: int, case_id: str, arm: str, ver: str) -> None:
    """Keep an assignment whose `ver` is text (a table rollout stores the market whose tables priced the case)."""
    s.execute(
        text(
            "INSERT INTO rollout_assignment (rollout_id, case_id, arm, ver) VALUES (:r, :c, :a, :v) "
            "ON CONFLICT (rollout_id, case_id) DO NOTHING"
        ),
        {"r": rollout_id, "c": case_id, "a": arm, "v": ver},
    )


def table_makers(s: Session, market: str) -> set[str]:
    """Who made the market's tables that are not yet in force or are the newest approved one: the creators and submitters of
    its drafts and submitted versions, and of its newest approved version made by a person (not the pack's own seed)."""
    rows = s.execute(
        text(
            "SELECT created_by, submitted_by FROM market_table WHERE pack = :p AND market = :m AND created_by NOT LIKE 'pack %' "
            "AND (status IN ('draft', 'submitted') OR id = (SELECT max(id) FROM market_table WHERE pack = :p AND market = :m "
            "AND status = 'approved' AND created_by NOT LIKE 'pack %'))"
        ),
        {"p": TABLE_PACK, "m": market},
    ).all()
    return {x for r in rows for x in r if x}


def done_replay_any(s: Session, flow_id: int) -> int | None:
    """The newest done replay run of the flow, whatever version it replayed (a table canary needs one), else None."""
    r = s.execute(
        text("SELECT id FROM replay_run WHERE flow_id = :f AND status = 'done' ORDER BY id DESC LIMIT 1"), {"f": flow_id}
    ).scalar()
    return int(r) if r is not None else None


# ---------------------------------------------------------------- writes (the rollout actions)
def insert(s: Session, flow_id: int, *, candidate: int | None, base: int | None, region_key: str, region: str, share: int,
           salt: str, by: str, run_id: int | None, rules: dict[str, Any] | None = None, kind: str = "flow") -> int:  # fmt: skip
    return int(
        s.execute(
            text(
                "INSERT INTO rollout (subject_kind, subject_id, candidate_ver, base_ver, stage, region_key, region, share, "
                "salt, replay_run_id, set_by, stop_rules) VALUES (:kind, :f, :c, :b, 'canary', :k, :r, :sh, :salt, :run, :by, "
                "CAST(:rules AS jsonb)) RETURNING id"
            ),
            {
                "kind": kind,
                "f": str(flow_id),
                "c": candidate,
                "b": base,
                "k": region_key,
                "r": region,
                "sh": share,
                "salt": salt,
                "run": run_id,
                "by": by,
                "rules": json.dumps(rules or DEFAULT_RULES),  # the stop rules the canary starts with (P9-7.4)
            },
        ).scalar_one()  # fmt: skip
    )


def set_share(s: Session, rollout_id: int, share: int, by: str, now: Any) -> None:
    s.execute(text("UPDATE rollout SET share = :sh, set_by = :by, set_at = :at WHERE id = :i"),
              {"sh": share, "by": by, "at": now, "i": rollout_id})  # fmt: skip


def set_stage(s: Session, flow_id: int, stage: str, frm: tuple[str, ...], by: str, now: Any,
              note: dict[str, Any] | None = None, kind: str = "flow") -> None:  # fmt: skip
    """Move the flow's rows in `frm` to `stage`; `note` is merged into `stop_rules` (the reason of a pause)."""
    s.execute(
        text(
            "UPDATE rollout SET stage = :st, set_by = :by, set_at = :at, "
            "stop_rules = stop_rules || CAST(:n AS jsonb) "
            "WHERE subject_kind = :kind AND subject_id = :f AND stage = ANY(:frm)"
        ),
        {"st": stage, "by": by, "at": now, "n": json.dumps(note or {}), "f": str(flow_id), "frm": list(frm), "kind": kind},
    )


def clear_undecided(s: Session, flow_id: int, kind: str = "flow") -> int:
    """Delete the assignments of cases not yet approved (a rollback), so their next evaluation uses the base version; approved,
    executing and closed cases keep theirs. Answers how many were deleted."""
    r = s.execute(
        text(
            "DELETE FROM rollout_assignment a USING rollout r WHERE a.rollout_id = r.id AND r.subject_kind = :kind "
            "AND r.subject_id = :f AND NOT EXISTS "
            "(SELECT 1 FROM case_record c WHERE c.id = a.case_id AND c.stage = ANY(:done))"
        ),
        {"f": str(flow_id), "done": list(DECIDED), "kind": kind},
    )
    return int(cast(CursorResult[Any], r).rowcount or 0)


def arm_counts(s: Session, flow_id: int, kind: str = "flow") -> dict[str, int]:
    """The assignments per arm over the flow's rollouts."""
    rows = s.execute(
        text(
            "SELECT a.arm, count(*) FROM rollout_assignment a JOIN rollout r ON r.id = a.rollout_id "
            "WHERE r.subject_kind = :kind AND r.subject_id = :f GROUP BY a.arm"
        ),
        {"f": str(flow_id), "kind": kind},
    ).all()
    return {"canary": 0, "control": 0} | {k: int(n) for k, n in rows}


def draft_hash(graph: Any) -> str | None:
    """The hash of a draft graph's content (canonical JSON), None for no draft. A replay stores it; a canary compares it."""
    if graph is None:
        return None
    return hashlib.sha256(json.dumps(graph, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def done_replay(s: Session, f: FlowRow) -> int | None:
    """The newest done replay run of the flow's draft as it is now (version `dver` and the same draft content), else None.
    The content matters: saveDraft gives an edited or re-made draft the same `dver` (review P9-7.9 F1)."""
    h = draft_hash(f.draft)
    if f.dver is None or h is None:
        return None
    r = s.execute(
        text(
            "SELECT id FROM replay_run WHERE flow_id = :f AND dver = :d AND draft_hash = :h AND status = 'done' "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"f": f.id, "d": f.dver, "h": h},
    ).scalar()
    return int(r) if r is not None else None


def stale_replay(s: Session, f: FlowRow) -> bool:
    """A done replay of the flow's draft version exists, but of other draft content than the draft now in the flow."""
    if f.dver is None:
        return False
    r = s.execute(
        text("SELECT 1 FROM replay_run WHERE flow_id = :f AND dver = :d AND status = 'done' LIMIT 1"), {"f": f.id, "d": f.dver}
    ).first()
    return r is not None and done_replay(s, f) is None


# ---------------------------------------------------------------- the canary report (P9-7.4)
def stop_rules_of(s: Session, flow_id: int, kind: str = "flow") -> dict[str, Any]:
    """The stored stop rules (and pause reason, if any) of the flow's newest running or paused canary row; {} when none."""
    r = s.execute(
        text(
            "SELECT stop_rules FROM rollout WHERE subject_kind = :kind AND subject_id = :f AND stage IN ('canary', 'paused') "
            "ORDER BY id LIMIT 1"
        ),
        {"f": str(flow_id), "kind": kind},
    ).scalar()
    return dict(r) if r else {}


def arm_rows(s: Session, flow_id: int, kind: str = "flow") -> dict[str, list[dict[str, Any]]]:
    """One row per case assigned over the flow's running or paused canary rows, by arm: {decided, override, exception, hold,
    net, realised}. `net` is the chosen route's net of a decided case (none before the decision), `realised` the confirmed
    outcome's. An exception is any exception work item of the case, a hold a gate hold or a fraud hold on it."""
    rows = s.execute(
        text(
            "SELECT a.arm, jsonb_typeof(c.data -> 'approval') = 'object' AS decided, "
            "jsonb_typeof(c.data -> 'override') = 'object' AS override, "
            "EXISTS (SELECT 1 FROM work_item w WHERE w.case_id = c.id AND w.kind = 'exception') AS exception, "
            "(jsonb_typeof(c.data -> 'gateHold') = 'object' "
            "OR COALESCE(c.data -> 'fraud' ->> 'status', '') IN ('held', 'rejected')) AS hold, "
            "CASE WHEN jsonb_typeof(c.data -> 'approval') = 'object' THEN (c.data -> 'chosen' ->> 'net')::float END AS net, "
            "(c.data -> 'outcome' ->> 'net')::float AS realised, c.data -> 'serviceDesk' AS sd "
            "FROM rollout_assignment a JOIN rollout r ON r.id = a.rollout_id JOIN case_record c ON c.id = a.case_id "
            "WHERE r.subject_kind = :kind AND r.subject_id = :f AND r.stage IN ('canary', 'paused') "
            "AND a.arm IN ('canary', 'control') ORDER BY a.case_id"
        ),
        {"f": str(flow_id), "kind": kind},
    ).mappings()
    out: dict[str, list[dict[str, Any]]] = {"canary": [], "control": []}
    for r in rows:
        out[r["arm"]].append({k: r[k] for k in ("decided", "override", "exception", "hold", "net", "realised", "sd")})
    return out


def canary_of_case(s: Session, case_id: str) -> int | None:
    """The id of the running canary rollout the case is assigned to, else None."""
    r = s.execute(
        text(
            "SELECT a.rollout_id FROM rollout_assignment a JOIN rollout r ON r.id = a.rollout_id "
            "WHERE a.case_id = :c AND r.subject_kind = 'flow' AND r.stage = 'canary' ORDER BY a.at DESC LIMIT 1"
        ),
        {"c": case_id},
    ).scalar()
    return int(r) if r is not None else None


def get(s: Session, rollout_id: int) -> Rollout | None:
    r = s.execute(text(f"SELECT {_COLS} FROM rollout WHERE id = :i"), {"i": rollout_id}).first()  # noqa: S608 - fixed columns
    return _row(r) if r else None
