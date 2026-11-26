"""Workflows and workflow runs as resources (plan 3 task 3).

`workflows`: the workflows the account may see in Workflow Studio (the same rule as the read actions `workflow.list`
and `workflow.get`: the Studio page and the org unit of the workflow's source). Full CRUD through the workflow
actions: create = `workflow.create`, update = `workflow.save`, delete = `workflow.delete`; `PATCH {action: publish|status|
duplicate}`.
`workflow-runs`: the runs that happened (filter `workflow`), read only; create = `workflow.run` (start one run of the
workflow named by `id`). A run is never edited or deleted: it is the record of what happened.
"""

from typing import Any

from di.repositories import workflows as studio
from di.resources import Resource, register
from di.resources.support import require_page
from di.services.actions import workflow_read
from di.services.actions import workflow_run_view as view
from di.services.actions.pipeline import CallContext

STATUS_FIELDS = ("status", "src", "q")


def _visible(ctx: CallContext) -> list[dict[str, Any]]:
    require_page(ctx, "integration", "studio")
    return [w for w in studio.all_workflows(ctx.session) if workflow_read.visible(ctx, w)]


def list_workflows(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:
    text = str(q.get("q") or "").strip().lower()
    rows = [view.workflow_row(w) for w in _visible(ctx)]
    return [
        r for r in rows
        if (not q.get("status") or r["status"] == q["status"]) and (not q.get("src") or r["source"] == q["src"])
        and (not text or text in f"{r['name']} {r['id']} {r['owner']}".lower())
    ]  # fmt: skip


def get_workflow(ctx: CallContext, wid: str) -> dict[str, Any] | None:
    w = next((w for w in _visible(ctx) if w["id"] == wid), None)
    return None if w is None else {"id": wid, **view.workflow_view(ctx.session, w)}


def list_runs(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for w in _visible(ctx):
        if not q.get("workflow") or q["workflow"] == w["id"]:
            out += [r | {"workflow": w["id"]} for r in view.history(ctx.session, w, 1000)]
    return out


def get_run(ctx: CallContext, run_id: str) -> dict[str, Any] | None:
    found = view.find_run(ctx.session, run_id, _visible(ctx))
    if found is None:
        return None
    w, rec = found
    return {"id": run_id, **view.run_view(ctx.session, w, run_id, rec)}


register(
    Resource(
        name="workflows", list=list_workflows, get=get_workflow, create="workflow.create", update="workflow.save",
        delete="workflow.delete", fields=("ch", "desc", "graph", "name", "note", "owner", "src", "trig", "type"),
        filters=STATUS_FIELDS,
        update_actions={"publish": "workflow.publish", "status": "workflow.setStatus", "duplicate": "workflow.duplicate"},
    )
)  # fmt: skip

register(
    Resource(
        name="workflow-runs", list=list_runs, get=get_run, create="workflow.run", update=None, delete=None,
        fields=("id",), filters=("workflow",),
        why_not={
            "update": "A run is the record of what happened; start a new one, or reprocess its failed records.",
            "delete": "Runs are kept for the monitor and the audit trail.",
        },
    )
)  # fmt: skip
