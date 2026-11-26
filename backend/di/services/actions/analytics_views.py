"""Saved analytics views (plan 9, P9-9.19, story UC-20): the actions over `di.services.analytics_views`.

    view.save      draft  {org_unit_id, pack, question_id, name, params?}  saveView: keep a worked question as a view of an org unit
    view.share     act    {view_id, roles}                                 saveView, owner only: the roles that may open the view
    view.setAlert  act    {view_id, measure, op, threshold} | {view_id, clear}   saveView, owner only: one alert on a measure
    view.list      read   {}                                               the views the account owns or that are shared with its role

Who: Admin, Planner, Approver, Executive, Finance and Engineer (`saveView`). A view of a tenant's org unit is saved only by a
person who may see that tenant (`tenant_boundary`), and a person sees a shared view only within their own tenants. Only the owner
shares a view or sets its alert (`out_of_scope`). `measure` is one the question registers (`days_in_stock` for the used-car
questions), `op` one of > >= < <=. A crossing raises My work items for the owner and the shared roles (the worker's
`views.alerts` tick, and at once when the alert is set).

Agents: `view.list` is a read, open to agents (they act as the signed-in person); `view.save` they may run; `view.share` is in
FORBIDDEN_ACTIONS (it changes who sees the data, R21) and `view.setAlert` in HELD_FOR_PERSON (it sends work to other people).
"""

# ruff: noqa: E501 - long action declarations and docstring table

from typing import Any

from di.core import policy
from di.repositories import orgs
from di.services import analytics_views as av
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.device import analytics

PERM = "saveView"
MAX_NAME = 80

ACTIONS.setdefault(
    "view.save",
    ActionDef(
        id="view.save", title="Save an analytics view", verb="save a view", risk="draft", perm=PERM, scope="none",
        desc="Save a worked analytics question as a view of an org unit: the question and its parameters, asked again each time "
        "it is opened over what the viewer may see.",
        input={
            "org_unit_id": {"req": True, "t": "string"}, "pack": {"req": True, "t": "string"},
            "question_id": {"req": True, "t": "string"}, "name": {"req": True, "t": "string"}, "params": {"req": False, "t": "object"},
        },
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "view.share",
    ActionDef(
        id="view.share", title="Share a view with roles", verb="share a view", risk="act", perm=PERM, scope="none",
        desc="Set the roles that may open one of your saved views. No agent shares a view: it changes who sees the data.",
        input={"view_id": {"req": True, "t": "number"}, "roles": {"req": True, "t": "array"}},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "view.setAlert",
    ActionDef(
        id="view.setAlert", title="Set an alert on a view", verb="set an alert", risk="act", perm=PERM, scope="none",
        desc="Alert the owner and the shared roles in My work when a measure of the view crosses a threshold (or clear the alert). "
        "An agent's call is held for a person.",
        input={
            "view_id": {"req": True, "t": "number"}, "measure": {"req": False, "t": "string"}, "op": {"req": False, "t": "string"},
            "threshold": {"req": False, "t": "number"}, "clear": {"req": False, "t": "boolean"},
        },
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "view.list",
    ActionDef(
        id="view.list", title="List saved views", verb="read the saved views", risk="read", perm=None, scope="none",
        desc="The saved views you own or that are shared with your role, within the tenants you may see. Changes nothing.",
        input={},
    ),
)  # fmt: skip


def _tenant_ok(ctx: CallContext, org: str) -> bool:
    person = ctx.actor.person
    return not policy.policy(person).get("tenantScoped") or policy.tenant_ok(person, org, ctx.actor.ctx)


def _own(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = av.get(ctx.session, int(i["view_id"]))
    if row is None or not _tenant_ok(ctx, row["org_unit_id"]):
        return "not_found", f"No view {i['view_id']}."
    if row["owner"] != ctx.actor.id:
        return "out_of_scope", f"View {i['view_id']} is {row['owner']}'s: only its owner changes it."
    return None


@guard("view.save")
def save_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    q = analytics.REGISTRY.get(i["question_id"])
    if q is None:
        return "not_found", f"No question {i['question_id']}. Questions: {', '.join(analytics.REGISTRY)}."
    if i["pack"] != q.pack:
        return "validation_error", f"{i['question_id']} is a question of {q.pack or 'no pack'}, not {i['pack']}."
    if i["org_unit_id"] not in orgs.units(ctx.session):
        return "not_found", f"No org unit {i['org_unit_id']}."
    if not _tenant_ok(ctx, i["org_unit_id"]):
        return "tenant_boundary", f"{i['org_unit_id']} is a tenant you cannot see. Request tenant access first."
    if len(i["name"].strip()) > MAX_NAME:
        return "validation_error", f"A view's name has at most {MAX_NAME} characters."
    return None


@implement("view.save")
def save(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = av.save(
        ctx.session, owner=ctx.actor.id, owner_role=ctx.actor.role, org=i["org_unit_id"], pack=i["pack"],
        question_id=i["question_id"], name=i["name"].strip(), params=i.get("params") or {},
    )  # fmt: skip
    return av.view_dict(row, ctx.actor.id) | {"log": f"Saved the view {row['name']}"}


@guard("view.share")
def share_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if (refusal := _own(i, ctx)) is not None:
        return refusal
    bad = [r for r in i["roles"] if r not in policy.roles()]
    if bad or not all(isinstance(r, str) for r in i["roles"]):
        return "validation_error", f"Unknown role {', '.join(map(str, bad))}. Roles: {', '.join(policy.roles())}."
    return None


@implement("view.share")
def share(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = av.get(ctx.session, int(i["view_id"]), lock=True)
    if row is None:
        raise ActionError("not_found", f"No view {i['view_id']}.")
    out = av.share(ctx.session, row, list(i["roles"]), ctx.actor.id)
    roles = ", ".join(out["shared_with_roles"]) or "no role"
    return av.view_dict(out, ctx.actor.id) | {"log": f"Shared the view {out['name']} with {roles}"}


@guard("view.setAlert")
def alert_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if (refusal := _own(i, ctx)) is not None:
        return refusal
    if i.get("clear"):
        return None
    row = av.get(ctx.session, int(i["view_id"]))
    if row is None:
        return "not_found", f"No view {i['view_id']}."
    have = analytics.measures_of(row["question_id"])
    if i.get("measure") not in have:
        return (
            "validation_error",
            f"{row['question_id']} has no measure {i.get('measure')}. Measures: {', '.join(have) or 'none'}.",
        )
    if i.get("op") not in av.OPS:
        return "validation_error", f"op must be one of {', '.join(av.OPS)}."
    if i.get("threshold") is None:
        return "validation_error", 'Missing "threshold".'
    return None


@implement("view.setAlert")
def set_alert(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = av.get(ctx.session, int(i["view_id"]), lock=True)
    if row is None:
        raise ActionError("not_found", f"No view {i['view_id']}.")
    if i.get("clear"):
        out = av.clear_alert(ctx.session, row, ctx.actor.id)
        return av.view_dict(out, ctx.actor.id) | {"log": f"Removed the alert of the view {out['name']}"}
    alert = {"measure": i["measure"], "op": i["op"], "threshold": i["threshold"]}
    out = av.set_alert(ctx.session, row, alert, ctx.actor.id)
    return av.view_dict(out, ctx.actor.id) | {
        "log": f"Set the alert {i['measure']} {i['op']} {i['threshold']:g} on {out['name']}"
    }


@implement("view.list")
def list_views(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:  # noqa: ARG001 - no input
    me = ctx.actor.person
    rows = [r for r in av.candidates(ctx.session, me.id, me.role) if r["owner"] == me.id or _tenant_ok(ctx, r["org_unit_id"])]
    return {"views": [av.view_dict(r, me.id) for r in rows]}
