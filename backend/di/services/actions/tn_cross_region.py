"""Cross-region transfer alert and rule suggestion for a telecom flow (plan 9, P9-10.15, story TN-18).

    telecom.crossRegion  read  {flow_id}  the `AL-TN-XREGION` alerts for the Planner (units idle in one region while another has
                                          an open requisition for the model, with a transfer suggestion per unit) and the
                                          rule `SR-TN-XREGION` placed into the flow's draft as a checked, simulated proposal

The facts are `di.services.cases.tn_cross_region` (canonical records only; no figure by a model). The rule goes through
`modeler_suggest._proposal` as every rule suggestion does. Nothing is saved: adopting it is the person's own `flow.saveDraft`
with the proposal's graph, then a different person's `flow.approve` and `flow.publish` (maker-checker, MVP-3.2). Who may read it:
a person who may edit or approve flows, within the flow's org scope. It is in `FORBIDDEN_ACTIONS` (R21: the choice of a rule is
a person's). Implements registry entry I-4 (rules that run).
"""

from typing import Any, cast

from di.core import policy
from di.core.orgs import subtree
from di.repositories import orgs
from di.services.actions import modeler_suggest as base
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, guard, implement
from di.services.cases import tn_cross_region as xr
from di.services.modeler.flow import Flow
from di.services.modeler.pack import load_pack
from di.services.modeler.suggest import Suggestion
from di.services.modeler.templates import load_template

PACK = "telecom_network"

ACTIONS.setdefault(
    "telecom.crossRegion",
    ActionDef(
        id="telecom.crossRegion",
        title="Cross-region transfer alert",
        desc="Idle units in one region while another buys new, with a transfer per unit and the rule suggestion. Changes nothing.",
        risk="read",
        perm=None,
        scope="none",
        input={"flow_id": {"req": True, "t": "number"}},
        verb="read cross-region transfers",
    ),
)


@guard("telecom.crossRegion")
def cross_region_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    bad = base.suggestions_guard(i, ctx)
    if bad:
        return bad
    if base._flow(ctx, i).template_key != PACK:
        return "validation_error", f"Flow {i['flow_id']} is not a telecom flow."
    return None


@implement("telecom.crossRegion")
def cross_region(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = base._flow(ctx, i)
    pack = load_pack(PACK)
    mine = sorted(subtree(orgs.units(ctx.session), f.org_unit_id))
    if ctx.actor.account is not None and policy.policy(ctx.actor.person).get("tenantScoped"):
        mine = [u for u in mine if policy.tenant_ok(ctx.actor.person, u, ctx.actor.ctx)]
    found = [a.as_dict() for a in xr.alerts_for(ctx.session, mine, pack)]
    sug = xr.rule_suggestion(pack) if found else None
    proposal = None
    if sug is not None:
        g = cast(Flow, f.draft if f.draft is not None else f.published)
        s = Suggestion("region", "", sug["rule"]["path"], 0, 0, 0.0, sug["text"], sug["rule"])
        proposal = base._proposal(ctx, f, load_template(PACK), g, s)
    return {"flow_id": f.id, "alerts": found, "suggestion": None if sug is None else sug | {"proposal": proposal}}
