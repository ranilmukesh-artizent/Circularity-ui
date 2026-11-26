"""The generic /api/v1 router (plan 3 task 2): one set of endpoints for every registered resource (di.resources).

    GET    /api/v1/{name}?limit=50&cursor=&<filters>   {items: [row], next_cursor}
    GET    /api/v1/{name}/{id}                         one row, or 404 not_found
    POST   /api/v1/{name}  {fields}                    201, the action's output
    PATCH  /api/v1/{name}/{id}  {fields}               the action's output (the id is added to the input)
    DELETE /api/v1/{name}/{id}                         the action's output

Reads call the resource's own `list` and `get`, which enforce tenant and permission scope. Every write calls
`pipeline.invoke` with the action id the resource names, as the signed-in account (an agent's token makes the agent
the preparer, as in `routes/actions.py`), then commits; a refusal rolls back and keeps the pipeline's status. A verb
the resource has no action for answers 405 `not_supported` with the resource's reason. An unknown body field is a 422
naming it, before any action runs. Registered after the specific routers (tasks), so `/api/v1/tasks` keeps its own.
"""

import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from di.core import golden
from di.core.deps import CurrentPrincipal, DbSession
from di.core.errors import ApiError
from di.resources import REGISTRY, Resource
from di.services import agent_credentials
from di.services.actions.pipeline import ERROR_STATUS, Actor, CallContext, invoke
from di.services.actions.registry import ACTIONS

router = APIRouter(prefix="/api/v1", tags=["Resources"])

DEFAULT_WHY = {
    "create": "This resource has no create.",
    "update": "This resource has no update.",
    "delete": "This resource has no delete.",
}
VERB_OF = {"create": "POST", "update": "PATCH", "delete": "DELETE"}


def _resource(name: str) -> Resource:
    r = REGISTRY.get(name)
    if r is None:
        raise ApiError("not_found", f"No resource {name}.", 404)
    return r


def _allow(r: Resource) -> str:
    return ", ".join(["GET"] + [VERB_OF[v] for v in ("create", "update", "delete") if getattr(r, v)])


def _action(r: Resource, verb: str) -> str | JSONResponse:
    action = getattr(r, verb)
    if action:
        return action
    msg = r.why_not.get(verb) or DEFAULT_WHY[verb]
    body = {"ok": False, "error": {"code": "not_supported", "message": msg}}
    return JSONResponse(body, 405, headers={"Allow": _allow(r)})


def _ctx(p: Any, session: Any) -> CallContext:
    return CallContext(actor=Actor(account=p.account, ctx=p.ctx), session=session)


def _check_fields(r: Resource, body: dict[str, Any], action: str) -> None:
    """Unknown body keys are a 422 naming them: against `fields`, else (none declared) against the action's own inputs."""
    if r.fields and (bad := sorted(set(body) - set(r.fields))):
        raise ApiError("validation_error", f"Unknown field {', '.join(bad)}. Accepted: {', '.join(r.fields)}.", 422)
    if not r.fields:
        _check_action_fields(action, body, r.id_keys.get(action, r.id_field))


def _run(action: str, body: dict[str, Any], p: Any, session: Any, status: int) -> JSONResponse:
    ctx = _ctx(p, session)
    if p.agent_id:  # an agent's own token: the agent prepares, a person confirms, never the agent (P9-13.9)
        ctx.preparer, ctx.confirmed = p.agent_id, False
        if refusal := agent_credentials.tools_refusal(session, p.agent_id, action):
            return JSONResponse({"ok": False, "error": refusal}, 403)
    result = invoke(action, body, ctx)
    if result["ok"]:
        session.commit()
        return JSONResponse(result["output"], status)
    session.rollback()
    code = result["error"]["code"]
    return JSONResponse(result, 422 if code == "validation_error" else ERROR_STATUS.get(code, 400))


_INPUTS: dict[str, set[str] | None] = {}


def _input_keys(action_id: str) -> set[str] | None:
    """The input keys an action declares (a `$[n].input` reference in the catalogue is followed); None: not known,
    so the action's own validation decides."""
    if action_id not in _INPUTS:
        a = ACTIONS.get(action_id)
        keys: set[str] = set(a.input) - {"$ref"} if a else set()
        catalogue = golden.load("actions_catalog")
        entry = next((x for x in catalogue if x["id"] == action_id), None)
        ref = ((entry or {}).get("input") or {}).get("$ref")
        if isinstance(ref, str) and (m := re.fullmatch(r"\$\[(\d+)\]\.input", ref)):
            keys |= set(catalogue[int(m[1])]["input"]) - {"$ref"}
        _INPUTS[action_id] = keys or None
    return _INPUTS[action_id]


def _check_action_fields(action_id: str, body: dict[str, Any], id_key: str) -> None:
    allowed = _input_keys(action_id)
    if allowed is not None and (bad := sorted(set(body) - allowed - {id_key})):
        raise ApiError("validation_error", f"Unknown field {', '.join(bad)}. Accepted: {', '.join(sorted(allowed))}.", 422)


def _input(r: Resource, action: str, rid: str, body: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """The action's input: the body, the row's extra fields, then the row id under the key the action reads."""
    out = {**body, **{k: row.get(src) for k, src in r.from_row.items()}}
    if key := r.id_keys.get(action, r.id_field):
        out[key] = rid
    return out


def _object(body: Any) -> dict[str, Any]:
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ApiError("validation_error", "The body must be a JSON object.", 422)
    return body


@router.get("/{name}")
def list_rows(name: str, request: Request, p: CurrentPrincipal, session: DbSession, limit: int = 50, cursor: str | None = None):
    r = _resource(name)
    if not 1 <= limit <= 500:
        raise ApiError("validation_error", "limit must be between 1 and 500.", 422)
    try:
        start = int(cursor) if cursor else 0
    except ValueError:
        raise ApiError("validation_error", "cursor is not one this resource gave.", 422) from None
    query = {k: v for k, v in request.query_params.items() if k in r.filters}
    rows = r.list(_ctx(p, session), query)
    page = rows[start : start + limit]
    more = start + limit < len(rows)
    return {"items": page, "next_cursor": str(start + limit) if more else None}


@router.get("/{name}/{rid}")
def get_row(name: str, rid: str, p: CurrentPrincipal, session: DbSession):
    r = _resource(name)
    row = r.get(_ctx(p, session), rid)
    if row is None:
        raise ApiError("not_found", f"No {name} {rid}.", 404)
    return row


@router.post("/{name}")
def create_row(name: str, p: CurrentPrincipal, session: DbSession, body: Annotated[Any, Body()] = None):
    r = _resource(name)
    action = _action(r, "create")
    if isinstance(action, JSONResponse):
        return action
    b = _object(body)
    _check_fields(r, b, action)
    return _run(action, b, p, session, 201)


@router.patch("/{name}/{rid}")
def update_row(name: str, rid: str, p: CurrentPrincipal, session: DbSession, body: Annotated[Any, Body()] = None):
    r = _resource(name)
    b = _object(body)
    if r.update_actions and "action" in b:
        chosen = b["action"]
        if chosen not in r.update_actions:
            raise ApiError("validation_error", f"Unknown action {chosen}. Accepted: {', '.join(sorted(r.update_actions))}.", 422)
        action = r.update_actions[chosen]
        b = {k: v for k, v in b.items() if k != "action"}
        _check_action_fields(action, b, r.id_keys.get(action, r.id_field))
    elif r.update:
        action = r.update
        _check_fields(r, b, action)
    elif r.update_actions:
        raise ApiError("validation_error", f"Say which action: one of {', '.join(sorted(r.update_actions))}.", 422)
    else:
        return _action(r, "update")  # 405 with the reason
    row = r.get(_ctx(p, session), rid)
    if row is None:
        raise ApiError("not_found", f"No {name} {rid}.", 404)
    return _run(action, _input(r, action, rid, b, row), p, session, 200)


@router.delete("/{name}/{rid}")
def delete_row(name: str, rid: str, p: CurrentPrincipal, session: DbSession):
    r = _resource(name)
    action = _action(r, "delete")
    if isinstance(action, JSONResponse):
        return action
    row = r.get(_ctx(p, session), rid)
    if row is None:
        raise ApiError("not_found", f"No {name} {rid}.", 404)
    return _run(action, _input(r, action, rid, {}, row), p, session, 200)
