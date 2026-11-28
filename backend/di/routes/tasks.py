"""Tasks: CRUD over the background job queue (plan 2, task 4). Admin and Developer only (manageIntegrations).

    GET    /api/v1/tasks?status=&kind=&limit=50&cursor=   {items: [Task], next_cursor}, newest first
    GET    /api/v1/tasks/{id}                              one Task
    POST   /api/v1/tasks  {kind, payload?, priority?, run_after?, dedupe_key?}   201 Task (a dedupe hit: the queued one)
    PATCH  /api/v1/tasks/{id}  {action: retry | cancel | reprioritise, priority?}  Task
    DELETE /api/v1/tasks/{id}                              cancel; Task

Every write runs as an action through the pipeline (task.enqueue, task.retry, task.cancel, task.reprioritise in
di.services.tasks), so it is permission-checked and journalled like any other. Refusals: 403 out_of_scope, 404
not_found, 409 conflict (cancel a running task, retry a queued one), 422 validation_error (an unknown kind).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from di.core.auth import Principal
from di.core.deps import CurrentPrincipal, DbSession, PersonPrincipal
from di.core.errors import ApiError
from di.schemas.tasks import Task, TaskIn, TaskPage, TaskPatch
from di.services import tasks as service
from di.services.actions.pipeline import ERROR_STATUS, Actor, CallContext, invoke

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])


def _run(action: str, body: dict[str, Any], p: Principal, session: DbSession, status: int = 200) -> JSONResponse:
    result = invoke(action, body, CallContext(actor=Actor(account=p.account, ctx=p.ctx), session=session))
    if result["ok"]:
        session.commit()
        return JSONResponse(result["output"], status)
    session.rollback()
    code = result["error"]["code"]
    return JSONResponse(result, 422 if code == "validation_error" else ERROR_STATUS.get(code, 400))


@router.get("", response_model=TaskPage)
def list_tasks(
    p: CurrentPrincipal,
    session: DbSession,
    status: str | None = None,
    kind: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[int | None, Query(ge=1)] = None,
):
    p.require(service.PERM)
    return service.page(session, status, kind, limit, cursor)


@router.get("/{task_id}", response_model=Task)
def get_task(task_id: int, p: CurrentPrincipal, session: DbSession):
    p.require(service.PERM)
    t = service.one(session, task_id)
    if t is None:
        raise ApiError("not_found", f"No task {task_id}.", 404)
    return t


@router.post("", status_code=201, response_model=Task)
def create_task(body: TaskIn, p: PersonPrincipal, session: DbSession):
    p.require(service.PERM)
    i = body.model_dump(mode="json", exclude_none=True)
    return _run("task.enqueue", i, p, session, 201)


@router.patch("/{task_id}", response_model=Task)
def change_task(task_id: int, body: TaskPatch, p: PersonPrincipal, session: DbSession):
    p.require(service.PERM)
    if body.action == "reprioritise":
        if body.priority is None:
            raise ApiError("validation_error", "priority: needed to reprioritise", 422)
        return _run("task.reprioritise", {"id": task_id, "priority": body.priority}, p, session)
    return _run(f"task.{body.action}", {"id": task_id}, p, session)


@router.delete("/{task_id}", response_model=Task)
def cancel_task(task_id: int, p: PersonPrincipal, session: DbSession):
    p.require(service.PERM)
    return _run("task.cancel", {"id": task_id}, p, session)
