"""Tasks: the background jobs of the queue (di/core/jobs.py) as a resource (plan 2, task 4; di.routes.tasks).

Reads (`page`, `one`) are plain queries. Every write is an action, so the pipeline checks the permission, journals it
and emits its event (di.services.actions.pipeline):

    task.enqueue       {kind, payload?, priority?, run_after?, dedupe_key?}  kind: a registered worker handler
    task.retry         {id}            a dead, failed or cancelled task, queued again with its attempts reset
    task.cancel        {id}            a queued task only (a running one: conflict)
    task.reprioritise  {id, priority}  a queued task only

Admin and Developer only (manageIntegrations). Agents never reach these: they are not read actions.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import jobs
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, implement

PERM = "manageIntegrations"
COLUMNS = (
    "id", "kind", "payload", "status", "priority", "attempts", "max_attempts", "run_after", "last_error", "history",
    "created_at", "updated_at",
)  # fmt: skip
_SELECT = "SELECT " + ", ".join(COLUMNS) + " FROM job"  # noqa: S608 - fixed column names, no input
_ID = {"id": {"req": True, "t": "number"}}


def _declare(action_id: str, title: str, verb: str, desc: str, inp: dict[str, dict[str, Any]]) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk="act", perm=PERM, scope="none", input=inp, verb=verb),
    )


_declare(
    "task.enqueue", "Queue a task", "queue tasks", "Queue a background job for the worker.",
    {"kind": {"req": True, "t": "string"}, "payload": {"req": False, "t": "object"},
     "priority": {"req": False, "t": "number"}, "run_after": {"req": False, "t": "string"},
     "dedupe_key": {"req": False, "t": "string"}},
)  # fmt: skip
_declare("task.retry", "Retry a task", "retry tasks", "Queue a dead, failed or cancelled task again.", _ID)
_declare("task.cancel", "Cancel a task", "cancel tasks", "Cancel a task that has not started.", _ID)
_declare(
    "task.reprioritise", "Reprioritise a task", "reprioritise tasks", "Change a queued task's priority (lower runs first).",
    _ID | {"priority": {"req": True, "t": "number"}},
)  # fmt: skip


# ---------------------------------------------------------------- reads
def one(session: Session, task_id: int) -> dict[str, Any] | None:
    row = session.execute(text(_SELECT + " WHERE id = :id"), {"id": task_id}).mappings().first()
    return dict(row) if row else None


def page(session: Session, status: str | None, kind: str | None, limit: int, cursor: int | None) -> dict[str, Any]:
    """Newest first; `cursor` is the last id of the previous page."""
    rows = session.execute(
        text(
            _SELECT + " WHERE (CAST(:st AS text) IS NULL OR status = :st) AND (CAST(:k AS text) IS NULL OR kind = :k)"
            " AND (CAST(:c AS bigint) IS NULL OR id < :c) ORDER BY id DESC LIMIT :n"
        ),
        {"st": status, "k": kind, "c": cursor, "n": limit + 1},
    ).mappings()
    items = [dict(r) for r in rows]
    more = len(items) > limit
    items = items[:limit]
    return {"items": items, "next_cursor": str(items[-1]["id"]) if more else None}


# ---------------------------------------------------------------- writes (actions)
def _known(kind: str) -> bool:
    from di.worker import HANDLERS  # the kinds a worker can run

    return kind in HANDLERS


def _task(ctx: CallContext, task_id: int) -> dict[str, Any]:
    t = one(ctx.session, task_id)
    if t is None:
        raise ActionError("not_found", f"No task {task_id}.")
    return t


def _out(t: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in t.items()}


@implement("task.enqueue")
def enqueue(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    if not _known(i["kind"]):
        raise ActionError("validation_error", f'No worker runs tasks of kind "{i["kind"]}".')
    try:
        run_after = datetime.fromisoformat(i["run_after"]) if i.get("run_after") else None
    except ValueError as e:
        raise ActionError("validation_error", '"run_after" must be an ISO date and time.') from e
    job = jobs.enqueue(
        ctx.session, i["kind"], i.get("payload") or {}, priority=int(i.get("priority") or 100), run_after=run_after,
        dedupe_key=i.get("dedupe_key") or None,
    )  # fmt: skip
    return _out(_task(ctx, job.id))


def _change(ctx: CallContext, task_id: int, done: bool, refusal: str) -> dict[str, Any]:
    t = _task(ctx, task_id)  # 404 before 409
    if not done:
        raise ActionError("conflict", refusal.format(id=task_id, status=t["status"]))
    return _out(_task(ctx, task_id))


@implement("task.retry")
def retry(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    tid = int(i["id"])
    return _change(
        ctx, tid, jobs.retry(ctx.session, tid), "Task {id} is {status}: only a dead, failed or cancelled task is retried."
    )


@implement("task.cancel")
def cancel(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    tid = int(i["id"])
    return _change(ctx, tid, jobs.cancel(ctx.session, tid), "Task {id} is {status}: only a queued task can be cancelled.")


@implement("task.reprioritise")
def reprioritise(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    tid = int(i["id"])
    done = jobs.reprioritise(ctx.session, tid, int(i["priority"]))
    return _change(ctx, tid, done, "Task {id} is {status}: only a queued task can be reprioritised.")
