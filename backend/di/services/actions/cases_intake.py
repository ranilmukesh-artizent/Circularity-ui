"""Opening a case from data through the pipeline (plan 8, MVP-8.1); the work is di.services.cases.intake.

    case.open  act  {org_unit_id, template_key, asset_key, reason, facts?}  -> {case_id, owner, template, stage,
                                                                               recommendation}

The demo opens no case (its 128 come from the book), so the action is declared here, beside the catalog's (as
di.services.actions.orgs declares the org actions). It needs `openCases` (Admin, Developer, Planner); a tenant-scoped
person opens cases only for the org units they may see (`tenant_boundary`). The idempotency key is the asset and the
reason (Review Focus 5): the second call answers `duplicate`, and intake refuses the pair again outside the pipeline.
"""

from typing import Any

from di.core import policy
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, guard, implement
from di.services.cases import intake

_STR = {"req": True, "t": "string"}
ACTIONS.setdefault(
    "case.open",
    ActionDef(
        id="case.open", title="Open a case", verb="open cases",
        desc="Open a case for a returned asset from data (an RMA, lease end, trade-in, contract end or IoT alarm), "
        "valued by the template and the org's published flow.",
        risk="act", perm="openCases", scope="none",
        input={"org_unit_id": _STR, "template_key": _STR, "asset_key": _STR, "reason": _STR,
               "facts": {"req": False, "t": "object"}},
        dup_text="A case for this asset and reason is already open",
    ),
)  # fmt: skip


def _idem(i: dict[str, Any], ctx: CallContext) -> str:  # noqa: ARG001 - the IdemKey signature
    return intake.intake_key(i["asset_key"], i["reason"])


@guard("case.open")
def open_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := intake.problem(ctx.session, i):
        return bad
    acct = ctx.actor.account
    scoped = acct is not None and policy.policy(acct).get("tenantScoped")
    if scoped and acct is not None and not policy.tenant_ok(acct, i["org_unit_id"], ctx.actor.ctx):
        return "tenant_boundary", f"{i['org_unit_id']} is a tenant you cannot see. Request tenant access first."
    return None


@implement("case.open", idem=_idem)
def open_case(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    by = ctx.actor.account.label if ctx.actor.account else "system"
    c = intake.open_case(ctx.session, i, by)
    rec = c.get("recommendation")
    return {"case_id": c["id"], "owner": c["owner"], "template": c["template"], "stage": c["stage"],
            "recommendation": rec["id"] if rec else None}  # fmt: skip
