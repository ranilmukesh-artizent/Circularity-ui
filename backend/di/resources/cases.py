"""Cases and My tasks as resources (plan 3 task 3).

`cases`: list and get go through the read actions `cases.list` and `case.get`, so the tenant boundary, the warehouse
lock and the page permission are the ones the UI gets (a Customer B planner lists Customer B cases only; `GET` of
another tenant's case is 403 `tenant_boundary`). No create (a case is opened from data, `case.open`/intake) and no
delete (a case is closed by its decision, never removed). `PATCH /cases/{id} {action, ...}` runs one of the decision
and evidence actions on the case.

`my-tasks`: the signed-in person's "Actions on me" (the My work screen's items), read only.
"""

from typing import Any

from di.resources import Resource, register
from di.resources.support import BIG, as_bool, as_int, principal, read
from di.services.actions.pipeline import CallContext
from di.services.screens import mywork

CASE_FILTERS = (
    "stage", "owner", "location", "cls", "product", "q", "route", "assessment", "evidence", "sort", "missing",
    "submitted", "received_within_days",
)  # fmt: skip


def list_cases(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:
    body: dict[str, Any] = {k: v for k, v in q.items() if k not in ("missing", "submitted", "received_within_days")}
    for k in ("missing", "submitted"):
        if (b := as_bool(q.get(k))) is not None:
            body[k] = b
    if (n := as_int(q.get("received_within_days"), "received_within_days")) is not None:
        body["received_within_days"] = n
    return read(ctx, "cases.list", body | {"limit": BIG})["rows"]


def get_case(ctx: CallContext, case_id: str) -> dict[str, Any] | None:
    return read(ctx, "case.get", {"case_id": case_id}, missing_ok=True)


def list_tasks(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:  # noqa: ARG001 - no filters
    return mywork.page(principal(ctx), ctx.session)["items"]


def get_task(ctx: CallContext, task_id: str) -> dict[str, Any] | None:
    return next((t for t in list_tasks(ctx, {}) if t["id"] == task_id), None)


register(
    Resource(
        name="cases", list=list_cases, get=get_case, create=None, update=None, delete=None, id_field="case_id",
        filters=CASE_FILTERS,
        update_actions={
            "submit": "decision.submit",
            "approve": "decision.approve",
            "override": "decision.override",
            "decline": "decision.decline",
            "request_evidence": "evidence.request",
            "record_evidence": "evidence.recordResult",
        },
        why_not={
            "create": "Cases are opened from data (a return, an import or a source), not created here.",
            "update": "Say what to do: PATCH with an action (submit, approve, override, decline, request_evidence, ...).",
            "delete": "A case is never deleted; it closes when its decision is executed. The journal keeps its history.",
        },
    )
)  # fmt: skip

register(
    Resource(
        name="my-tasks", list=list_tasks, get=get_task, create=None, update=None, delete=None,
        why_not={
            "create": "Tasks arise from cases, conflicts and proposals; they are not created here.",
            "update": "Act on the thing a task points at (its `go` route) or use /api/v1/tasks for background jobs.",
            "delete": "A task closes when its work is done.",
        },
    )
)  # fmt: skip
