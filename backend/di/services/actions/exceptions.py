"""Exception actions (plan 9, P9-2.10): the exception assistant's draft for a work item of My work.

    exception.explain  read  {exception_id}   the draft: {cause, recommended_action, owner_role, by_model, sources}

The caller needs the My work page and the case of the exception in scope (the tenant boundary and the warehouse lock, as
the case actions apply them). Agents may call it (a read). It only proposes text: resolving or handing on the item stays
with a person (`work.resolve`, `work.assign`: `FORBIDDEN_ACTIONS`). The logic is `di.services.agents.exception_assistant`.
"""

from typing import Any

from di.core import policy
from di.repositories.packs import active_pack
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.agents import exception_assistant
from di.services.cases import process
from di.services.modeler.pack import Pack, load_pack

ACTIONS.setdefault(
    "exception.explain",
    ActionDef(
        id="exception.explain", title="Explain an exception", verb="see the exception assistant's draft",
        desc="Draft the cause, the recommended action and the owner of an exception item, with the facts it rests on.",
        risk="read", perm=None, scope="none",
        input={"exception_id": {"req": True, "t": "number"}},
    ),
)  # fmt: skip


@guard("exception.explain")
def explain_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    a = ctx.actor.account
    if a is None:
        return None  # the system actor
    if not policy.can_page(a, "mywork"):
        return "out_of_scope", f"The {a.role} view has no My work."
    found = process.exception_of(ctx.session, i["exception_id"])
    if found is None:
        return "not_found", "No such exception."
    exc, case = found
    if case:
        if not policy.tenant_ok(a, case["owner"], ctx.actor.ctx):
            return (
                "tenant_boundary",
                f"{case['id']} belongs to {case['owner']}, a tenant you cannot see. Request tenant access first.",
            )
        if not policy.location_ok(a, case["location"]):
            return "tenant_boundary", f"{case['id']} is at {case['location']}, outside your warehouse."
    elif exc["org_unit_id"] and not policy.tenant_ok(a, exc["org_unit_id"], ctx.actor.ctx):
        return "tenant_boundary", f"{exc['org_unit_id']} is a tenant you cannot see. Request tenant access first."
    return None


def _pack(ctx: CallContext, case: dict[str, Any]) -> Pack:
    template = case.get("template") or "industrial"
    try:
        return active_pack(ctx.session, template, None)
    except KeyError:  # no longer published: the file as shipped
        return load_pack(template)


@implement("exception.explain")
def explain(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    found = process.exception_of(ctx.session, i["exception_id"])
    if found is None:
        raise ActionError("not_found", "No such exception.")
    exc, case = found
    return exception_assistant.explain_exception(ctx, exc, case, _pack(ctx, case)).model_dump(mode="json")
