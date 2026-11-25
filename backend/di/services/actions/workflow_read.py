"""Read actions for Workflow Studio's workflows and runs (plan 9, P9-2.23, interface I-12's reads for Ask).

    workflow.list    read  {status?, src?, q?, limit?}   the workflows the caller may see: {workflows: [row], total}
    workflow.get     read  {id}                           one workflow: blocks, version, trigger, last run, recent runs
    workflow.runs    read  {id, limit?}                   the runs that happened, newest first
    workflow.runGet  read  {id: "RUN-xxxxx"}              one run: steps, error, retries, log lines, held records, fix

Owns: the four declarations, their access rule and their handlers; the views are `workflow_run_view`.
Access: the Workflow Studio section of the Connection Fabric (`integration/studio`, as the screen endpoints), and the
org unit of the workflow's source when it has one (the tenant boundary). A person who may not see a workflow or run gets
the same `not_found` as one that does not exist ("There is no workflow WF-999 you can see."), so nothing about it leaks.
Never does: write (no run, reprocess, fix, save or publish: they are `workflow.*` writes and never an Ask tool), or
answer from a second query: the lists and runs are the ones `di.repositories.workflows` gives the page. An agent may
call them (agent mode "yes").
"""

from typing import Any

from sqlalchemy import text

from di.core import policy
from di.repositories import workflows as studio
from di.services.actions import workflow_run_view as view
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement

DEFAULT_LIMIT, MAX_LIMIT = 20, 50
STATUSES = ("published", "draft", "paused", "failing")

_ID = {"id": {"req": True, "t": "string", "ex": "WF-116"}}
for _id, _title, _desc, _inp in (
    ("workflow.list", "List workflows", "The workflows you can see in Workflow Studio, by status, source or text.",
     {"status": {"req": False, "t": "string"}, "src": {"req": False, "t": "string"}, "q": {"req": False, "t": "string"},
      "limit": {"req": False, "t": "number"}}),
    ("workflow.get", "Read a workflow", "One workflow: its blocks, version, status, trigger, last run and recent runs.", _ID),
    ("workflow.runs", "List a workflow's runs", "The runs of a workflow that happened, newest first.",
     _ID | {"limit": {"req": False, "t": "number"}}),
    ("workflow.runGet", "Read a workflow run",
     "One run (RUN-xxxxx): its steps with status and record counts, log lines, held records, retries, the error and the fix.",
     {"id": {"req": True, "t": "string", "ex": "RUN-D1CFE"}}),
):  # fmt: skip
    ACTIONS.setdefault(
        _id,
        ActionDef(id=_id, title=_title, desc=_desc, risk="read", perm=None, scope="none", input=_inp, verb="read workflows"),
    )


def _source_org(s: Any, w: dict[str, Any]) -> str | None:
    """The org unit of the workflow's source (None: the source has none, or the workflow has no source)."""
    if not w.get("src"):
        return None
    return s.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": w["src"]}).scalar()


def _may_open_studio(ctx: CallContext) -> bool:
    a = ctx.actor.account
    return a is None or policy.can_page(a, "integration", "studio")


def visible(ctx: CallContext, w: dict[str, Any]) -> bool:
    """May the caller see this workflow: Workflow Studio is theirs, and the source's org unit is inside their tenants."""
    if not _may_open_studio(ctx):
        return False
    org = _source_org(ctx.session, w)
    a = ctx.actor.account
    return org is None or a is None or policy.tenant_ok(a, org, ctx.actor.ctx)


def _workflows(ctx: CallContext) -> list[dict[str, Any]]:
    return [w for w in studio.all_workflows(ctx.session) if visible(ctx, w)]


def _no_workflow(wid: Any) -> tuple[str, str]:
    return "not_found", f"There is no workflow {wid} you can see."


def _no_run(rid: Any) -> tuple[str, str]:
    return "not_found", f"There is no run {rid} you can see."


def _limit_problem(i: dict[str, Any]) -> tuple[str, str] | None:
    lim = i.get("limit")
    if lim is not None and not (isinstance(lim, int) and 1 <= lim <= MAX_LIMIT):
        return "validation_error", f"The limit is a whole number from 1 to {MAX_LIMIT}."
    return None


def _mine(ctx: CallContext, wid: str) -> dict[str, Any] | None:
    return next((w for w in _workflows(ctx) if w["id"] == wid), None)


@guard("workflow.list")
def list_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if not _may_open_studio(ctx):
        return "not_found", "There are no workflows you can see."
    if i.get("status") not in (None, *STATUSES):
        return "validation_error", f"The status is one of {', '.join(STATUSES)}."
    return _limit_problem(i)


@implement("workflow.list")
def list_workflows(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    q = str(i.get("q") or "").strip().lower()
    rows = [view.workflow_row(w) for w in _workflows(ctx)]
    rows = [
        r for r in rows
        if (not i.get("status") or r["status"] == i["status"]) and (not i.get("src") or r["source"] == i["src"])
        and (not q or q in f"{r['name']} {r['id']} {r['owner']}".lower())
    ]  # fmt: skip
    return {"workflows": rows[: i.get("limit") or DEFAULT_LIMIT], "total": len(rows)}


@guard("workflow.get")
def get_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return None if _mine(ctx, str(i["id"])) else _no_workflow(i["id"])


@implement("workflow.get")
def get_workflow(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    w = _mine(ctx, str(i["id"]))
    if w is None:
        raise ActionError(*_no_workflow(i["id"]))
    return view.workflow_view(ctx.session, w)


@guard("workflow.runs")
def runs_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return _limit_problem(i) or get_guard(i, ctx)


@implement("workflow.runs")
def workflow_runs(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    w = _mine(ctx, str(i["id"]))
    if w is None:
        raise ActionError(*_no_workflow(i["id"]))
    return {"workflow": w["id"], "runs": view.history(ctx.session, w, i.get("limit") or view.RECENT)}


@guard("workflow.runGet")
def run_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    found = view.find_run(ctx.session, str(i["id"]), _workflows(ctx))
    return None if found else _no_run(i["id"])


@implement("workflow.runGet")
def run_get(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    found = view.find_run(ctx.session, str(i["id"]), _workflows(ctx))
    if found is None:
        raise ActionError(*_no_run(i["id"]))
    w, rec = found
    return view.run_view(ctx.session, w, str(i["id"]), rec)
