"""Non-return fee action (plan 9, P9-3.18, story TF-14; registry entries I-11 and I-20).

The logic is `di.services.instructions.fees`.

    nonReturnFee.post   commit  {line_id}   a person posts the fee of a contract line that closed without the tool: one
                                            instruction to the billing system (SAP S/4HANA) through the instruction queue, the
                                            Fleet desk's `non_return` item closes; a second post is a `duplicate`

Permission `postFees` (Admin, Planner, Finance). A tenant-scoped person reaches only the lines whose item belongs to their
units (`tenant_boundary`). An agent may prepare the post but never run it: the call is held for a person (HELD_FOR_PERSON,
I-10), so it is not in FORBIDDEN_ACTIONS. The fee is the contract line's own figure, read from the canonical store when it is
posted; no model step (R16).
"""

from typing import Any

from di.core import policy
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.instructions import fees, queue

ACTIONS.setdefault(
    "nonReturnFee.post",
    ActionDef(
        id="nonReturnFee.post", title="Post the non-return fee", verb="post non-return fees",
        desc="Post the contract fee of a tool that was not returned to the billing system, from the contract line that closed "
             "without it. Closes the Fleet desk's item. A second post does nothing.",
        risk="commit", perm="postFees", scope="none", input={"line_id": {"req": True, "t": "string"}},
        dup_text="This fee was posted already",
    ),
)  # fmt: skip


@guard("nonReturnFee.post")
def post_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    line = fees.line_row(ctx.session, i["line_id"])
    if line is None:
        return "not_found", f"No contract line {i['line_id']}."
    if line["status"] != fees.STATUS or line["fee"] <= 0:
        return "validation_error", f"Line {i['line_id']} has no non-return fee to post."
    item = fees.item_of(ctx.session, i["line_id"])
    org = (item or {}).get("org_unit_id") or fees.org_of(ctx.session, line["serial"], line["contract_id"])
    a = ctx.actor.account
    if a is not None and policy.policy(a).get("tenantScoped"):
        if not org:  # no contract owner and no case: the tenant is unknown, so a tenant-scoped person may not post (R21)
            return "tenant_boundary", f"The org unit that owns {i['line_id']} is not on file. Ask an administrator to post it."
        if not policy.tenant_ok(a, org, ctx.actor.ctx):
            return "tenant_boundary", f"{org} is a tenant you cannot see. Request tenant access first."
    if not queue.enabled():  # nothing would be sent: the item stays open and the key unspent
        return "validation_error", "Sending instructions is switched off: the fee is not posted."
    return None


@implement("nonReturnFee.post", idem=lambda i, ctx: i["line_id"])  # noqa: ARG005 - the key is the line
def post(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    try:
        return fees.post(ctx.session, i["line_id"], ctx.actor.id)
    except LookupError as e:
        raise ActionError("not_found", str(e)) from e
