"""The case process layer (plan 9, P9-1.7; registry entry I-20; research E section 8.2): work items with an owner role,
SLA timers on the job queue, escalation and "needs info" questions, and the one list of everything that waits for a
person (`items_for`, My work).

    open_item(s, kind=, case_id=, ..., due_hours=, by=)   a `work_item` row; with `due_hours` it gets a due time and a
                                                          `work.sla` job (dedupe key `work.sla:<id>`) that runs then
                                                          (`run_after` is on the database clock; an early run queues
                                                          itself again)
    close_item(s, item_id, outcome, by)                   the item is done
    on_sla(s, item_id)                                    the timer: an item still open and overdue is escalated
                                                          ("escalated", "not_due", "closed")
    items_for(s, ctx)                                     `WorkView`s for the signed-in account, merged from the work
                                                          items, the approvals and tasks of Home (`aome_items`), the
                                                          agents' proposals for the person and the conflicts that hold
                                                          a decision, sorted by priority, then due time
    role_of_owner(owner)                                  a pack owner's name as one of today's roles
    exception_of(s, item_id), facts_of(exc, case)         an exception item with its case, and the facts behind it
                                                          (the exception assistant, P9-2.10)

Time is the workspace clock (`di.core.clock`): a due time is `clock.now()` plus the hours, and `on_sla` compares with the
same clock, so the pinned test clock and the simulated clock both work. Owns: the `work_item` table (migration 0033).
Never does: approve, decline, resolve or override anything (golden rule 10). An escalation changes who is asked (the
pack's `runtime.escalate_to`, or the delegate in force while the Approver is out of office) and how urgent it is; the
case, its stage and its approval are not touched.

Item ids in `WorkView.id` say where a row comes from: `w:<id>` a work item, `a:<title>` an approval or task of Home, `p:<id>` a
proposal, `c:<id>` a conflict.
"""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock, jobs, policy
from di.services.modeler.pack import Pack, load_pack

if TYPE_CHECKING:
    from di.services.actions.pipeline import CallContext

SLA_JOB = "work.sla"
ESCALATION_PRIORITY = 50  # taken off an item's priority when it is escalated (lower sorts first)
HELD_STAGES = ("none", "awaiting_approval")  # a decision is still to be made or approved (as the menu's conflict badge)
KINDS = ("exception", "approval", "needs_info", "proposal", "conflict", "task")

# A pack's owner names that are not a role today (Global Constraints, "Owner roles"): compliance owners resolve to
# Approver and the sustainability lead to Engineer. The pack's `owners` table is the place to change this later.
_OWNER_ROLES = {
    "compliance": "Approver", "trade compliance": "Approver", "regulatory": "Approver", "quality": "Engineer",
    "quality / regulatory": "Approver", "sustainability lead": "Engineer", "fleet manager": "Approver",
    "service operations": "Approver", "fleet desk": "Planner", "sales": "Approver", "account manager": "Approver",
}  # fmt: skip

Outcome = Literal["escalated", "not_due", "closed"]


@dataclass(frozen=True)
class WorkView:
    """One row of My work. `owner` is the account or role it waits for; `due` is an ISO time; `go` is a route (no
    leading `#/`) to the thing it is about."""

    id: str
    kind: str
    case_id: str | None
    title: str
    cause: str | None
    action: str | None
    owner: str
    due: str | None
    overdue: bool
    priority: int
    go: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def role_of_owner(owner: str) -> str:
    """A pack owner's name as a role: a role's own name, a mapped owner, else Approver (the one who decides)."""
    if owner in policy.roles():
        return owner
    return _OWNER_ROLES.get(owner.strip().lower(), "Approver")


def pack_of(s: Session, case_id: str | None) -> Pack:
    """The pack of the case's template (industrial when there is no case)."""
    template = "industrial"
    if case_id:
        t = s.execute(text("SELECT data ->> 'template' FROM case_record WHERE id = :c"), {"c": case_id}).scalar()
        template = t or template
    return load_pack(template)


def sla_hours(s: Session, case_id: str | None, kind: str) -> float | None:
    """The hours the case's pack gives an item of this kind (`runtime.sla_hours`), or None."""
    return pack_of(s, case_id).runtime.sla_hours.get(kind)


# ---------------------------------------------------------------- open, close
def open_item(
    s: Session,
    *,
    kind: str,
    case_id: str | None,
    org_unit_id: str | None,
    type: str,
    title: str,
    cause: str | None,
    action: str | None,
    owner_role: str,
    owner_account: str | None = None,
    due_hours: float | None,
    by: str,
) -> int:
    """Insert a work item and return its id. With `due_hours` it is due that long from now and a `work.sla` job is
    queued to run then. In the caller's transaction."""
    now = clock.now()
    due = now + timedelta(hours=due_hours) if due_hours is not None else None
    item_id = s.execute(
        text(
            "INSERT INTO work_item (kind, case_id, org_unit_id, type, title, cause, action, owner_role, owner_account, due_at, "
            "created_by, created_at) VALUES (:k, :c, :o, :t, :ti, :ca, :ac, :r, :a, :d, :by, :now) RETURNING id"
        ),
        {"k": kind, "c": case_id, "o": org_unit_id, "t": type, "ti": title, "ca": cause, "ac": action, "r": owner_role,
         "a": owner_account, "d": due, "by": by, "now": now},
    ).scalar_one()  # fmt: skip
    if due is not None:
        wait = due - now  # the job queue claims on the database clock, so the wait is added to that, not to `due`
        jobs.enqueue(s, SLA_JOB, {"item_id": item_id}, run_after=_db_now(s) + wait, dedupe_key=f"{SLA_JOB}:{item_id}")
    return int(item_id)


def _db_now(s: Session) -> datetime:
    """The database clock, which `jobs.claim` compares `run_after` with (the workspace clock may be pinned or simulated)."""
    return s.execute(text("SELECT now()")).scalar_one()


def close_item(s: Session, item_id: int, outcome: str, by: str) -> None:
    """The item is done with this outcome. An item that is not open is left as it is."""
    s.execute(
        text(
            "UPDATE work_item SET status = 'done', outcome = :o, closed_by = :by, closed_at = :now "
            "WHERE id = :i AND status = 'open'"
        ),
        {"o": outcome, "by": by, "now": clock.now(), "i": item_id},
    )


# ---------------------------------------------------------------- the timer
def _system_ctx(s: Session) -> "CallContext":
    from di.core.auth import load_context
    from di.services.actions.pipeline import Actor, CallContext

    return CallContext(actor=Actor(account=None, ctx=load_context(s), system=True), session=s)


def _cover(s: Session, role: str) -> str | None:
    """The delegate's account when the Approver is out of office and decisions are delegated (common.ooo_cover)."""
    if role != "Approver":
        return None
    from di.repositories.common import ooo_cover

    cover = ooo_cover(_system_ctx(s))
    return str(cover["acct"]) if cover else None


def on_sla(s: Session, item_id: int) -> Outcome:
    """The item's timer ran. Still open and due: its priority drops by 50, it is stamped escalated and goes to the
    pack's `runtime.escalate_to` (to the delegate in force while the Approver is out of office); a journal row by
    `system` says so and the event `work.escalated` is written. Returns "escalated"; "closed" when the item is not open;
    "not_due" when it has no due time, is not yet due or was escalated already. Never approves, declines or resolves."""
    row = s.execute(
        text(
            "SELECT id, case_id, title, due_at, owner_role, owner_account, status, escalated_at, priority "
            "FROM work_item WHERE id = :i FOR UPDATE"
        ),
        {"i": item_id},
    ).mappings().first()  # fmt: skip
    if row is None or row["status"] != "open":
        return "closed"
    now = clock.now()
    if row["due_at"] is None or row["escalated_at"] is not None:
        return "not_due"
    if row["due_at"] > now:  # early: wait the rest of the time on the database clock (fresh key: this job still runs)
        at = _db_now(s)
        jobs.enqueue(
            s,
            SLA_JOB,
            {"item_id": item_id},
            run_after=at + (row["due_at"] - now),
            dedupe_key=f"{SLA_JOB}:{item_id}:{at.isoformat()}",
        )
        return "not_due"
    role = pack_of(s, row["case_id"]).runtime.escalate_to or row["owner_role"]
    account = _cover(s, role)
    s.execute(
        text(
            "UPDATE work_item SET priority = priority - :p, escalated_at = :now, owner_role = :r, owner_account = :a "
            "WHERE id = :i"
        ),
        {"p": ESCALATION_PRIORITY, "now": now, "r": role, "a": account, "i": item_id},
    )
    log = f"Escalated: {row['title']}, due {row['due_at'].strftime('%Y-%m-%d %H:%M UTC')}"
    payload = {"item_id": item_id, "title": row["title"], "from": row["owner_role"], "to": role, "log": log}
    s.execute(
        text(
            "INSERT INTO action_journal (action, input, actor, role, case_id, at) "
            "VALUES ('work.escalate', CAST(:p AS jsonb), 'system', 'System', :c, :now)"
        ),
        {"p": _json(payload), "c": row["case_id"], "now": now},
    )
    s.execute(
        text("INSERT INTO domain_event (type, case_id, payload, at) VALUES ('work.escalated', :c, CAST(:p AS jsonb), :now)"),
        {"c": row["case_id"], "p": _json(payload), "now": now},
    )
    return "escalated"


def _json(v: Any) -> str:
    return json.dumps(v, default=str)


# ---------------------------------------------------------------- the list for a person
def _may_see(a: policy.Account, pctx: policy.Context | None, org_unit_id: str | None, case: dict[str, Any] | None) -> bool:
    """The tenant boundary (and, for a case, the warehouse lock) as the case screens apply them."""
    if case is not None:
        return policy.tenant_ok(a, case["owner"], pctx) and policy.location_ok(a, case["location"])
    return org_unit_id is None or policy.tenant_ok(a, org_unit_id, pctx)


APPROVAL_PREFIX = "AP-"  # a work item whose type starts so is an approval of a pack (P9-10.8: AP-TN-EXP), stored as an exception


def _view_kind(row: Any) -> str:
    """The kind My work shows for a work item: an approval of a pack (type `AP-…`) is an approval, a step a task."""
    if str(row["type"]).startswith(APPROVAL_PREFIX):
        return "approval"
    return "task" if row["kind"] == "step" else str(row["kind"])


def _work_rows(s: Session, a: policy.Account, pctx: policy.Context | None, now: datetime) -> list[WorkView]:
    rows = s.execute(
        text(
            "SELECT w.*, c.owner AS c_owner, c.location AS c_location FROM work_item w "
            "LEFT JOIN case_record c ON c.id = w.case_id "
            "WHERE w.status = 'open' AND (w.owner_role = :r OR w.owner_account = :a) ORDER BY w.id"
        ),
        {"r": a.role, "a": a.id},
    ).mappings()
    out = []
    for r in rows:
        case = {"owner": r["c_owner"], "location": r["c_location"]} if r["c_owner"] is not None else None
        if not _may_see(a, pctx, r["org_unit_id"], case):
            continue
        due = r["due_at"]
        out.append(
            WorkView(
                id=f"w:{r['id']}", kind=_view_kind(r), case_id=r["case_id"], title=r["title"],
                cause=r["cause"], action=r["action"], owner=r["owner_account"] or r["owner_role"],
                due=due.isoformat() if due else None, overdue=bool(due and due < now), priority=r["priority"],
                go=f"product/{r['case_id']}" if r["case_id"] else None,
            )
        )  # fmt: skip
    return out


def _home_rows(ctx: "CallContext", a: policy.Account) -> list[WorkView]:
    """Home's list (`aome_items`): approvals are the ones that ask for a decision or the approvals inbox, the rest tasks."""
    from di.repositories.workspace import aome_items

    out = []
    for n, i in enumerate(aome_items(ctx)):
        approval = i.get("btn") in ("Decide", "Open inbox")
        go = i.get("go")
        out.append(
            WorkView(
                id=f"a:{i['t']}", kind="approval" if approval else "task", case_id=None, title=i["t"], cause=i.get("d"),
                action=i.get("btn"), owner=a.role, due=None, overdue=False, priority=100 + n,
                go=go if isinstance(go, str) else None,
            )
        )  # fmt: skip
    return out


def _proposal_rows(s: Session, a: policy.Account, pctx: policy.Context | None) -> list[WorkView]:
    from di.services.agents import proposals

    return [
        WorkView(
            id=f"p:{p['id']}", kind="proposal", case_id=p["case_id"], cause=p["why"],
            title=f"{p['agentName']} proposes: {p['title']}",
            action="Accept or reject", owner=a.role, due=None, overdue=False, priority=100,
            go=f"product/{p['case_id']}" if p["case_id"] else None,
        )
        for p in proposals.pending_for(s, a, pctx or policy.Context())
    ]  # fmt: skip


def _conflict_rows(s: Session, a: policy.Account, pctx: policy.Context | None) -> list[WorkView]:
    """The open or escalated conflicts on the asset of a case the account may see whose decision is still to be made
    (what the menu's `conf` badge counts)."""
    from di.services.cases import store

    cases: dict[str, str] = {}
    for c in store.all_cases(s):
        if c["stage"] in HELD_STAGES and c.get("assetId") and _may_see(a, pctx, None, c):
            cases.setdefault(c["assetId"], c["id"])
    if not cases:
        return []
    rows = s.execute(
        text(
            "SELECT id, key, field, values, authority FROM conflict WHERE status IN ('open', 'escalated') "
            "AND key = ANY(:k) ORDER BY id"
        ),
        {"k": list(cases)},
    ).mappings()
    return [
        WorkView(
            id=f"c:{r['id']}", kind="conflict", case_id=cases[r["key"]], title=f"Sources disagree on {r['field']} of {r['key']}",
            cause="Values: " + ", ".join(f"{k} {v}" for k, v in (r["values"] or {}).items()),
            action="Pick the source whose value counts", owner=a.role, due=None, overdue=False, priority=100,
            go="integration/conflicts",
        )
        for r in rows
    ]  # fmt: skip


def items_for(s: Session, ctx: "CallContext") -> list[WorkView]:
    """Everything that waits for the signed-in account, in one list: open work items for its role or assigned to it, within
    its tenants; its approvals and tasks; the agents' proposals it may decide; the conflicts that hold a decision. Sorted by
    priority, then due time (none last). The system actor has no list."""
    a = ctx.actor.account
    if a is None:
        return []
    pctx = ctx.actor.ctx
    rows = [*_work_rows(s, a, pctx, clock.now()), *_home_rows(ctx, a), *_proposal_rows(s, a, pctx), *_conflict_rows(s, a, pctx)]
    return sorted(rows, key=lambda w: (w.priority, w.due is None, w.due or "", w.id))


# ---------------------------------------------------------------- an exception, for the exception assistant (P9-2.10)
def exception_of(s: Session, item_id: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """An exception work item (any status) and its case (`{}` when it has none), or None when `item_id` is not an
    exception. The assistant reads the item's type, case and facts here and nowhere else."""
    row = s.execute(text("SELECT * FROM work_item WHERE id = :i AND kind = 'exception'"), {"i": int(item_id)}).mappings().first()
    if row is None:
        return None
    from di.services.cases import store

    case = store.get(s, row["case_id"]) if row["case_id"] else None
    return dict(row), dict(case or {})


def facts_of(exc: Mapping[str, Any], case: Mapping[str, Any]) -> list[dict[str, str]]:
    """The facts behind an exception, each `{fact, source, at}`: the asset of the case, what the item itself says, the
    reasons of the gates that failed and the evidence that is not ready. `at` is the item's creation time (ISO)."""
    at = exc["created_at"].isoformat() if exc.get("created_at") else clock.now().isoformat()
    out: list[dict[str, str]] = []
    if case.get("assetId"):
        out.append({"fact": f"Asset {case['assetId']}", "source": "case record", "at": at})
    if exc.get("cause"):
        out.append({"fact": str(exc["cause"]).strip(), "source": f"work item {exc['id']}", "at": at})
    for g in case.get("gates") or []:
        if not g.get("passed") and g.get("reason"):
            out.append({"fact": str(g["reason"]).strip(), "source": f"gate {g.get('name') or g.get('id')}", "at": at})
    for e in case.get("evidence") or []:
        if e.get("state") not in (None, "ready"):
            note = f" ({e['note']})" if e.get("note") else ""
            out.append({"fact": f"{e['label']}: {e['state']}{note}", "source": str(e.get("source") or "case evidence"), "at": at})
    return out
