"""Ageing suggestions for listed devices (plan 9, P9-6.13, story DV-08) and worked device questions (P9-6.17, DV-13).

    device.question           read  {question_id, org_unit_id?}  one worked question of the device pack answered from the data
                                                             (`di.services.device.analytics`): sentence, chart, examples
`device.question` is a read with no permission, open to every account and to agents (Ask calls it); it reads only the rows of the
actor's own org units (a tenant-scoped role: its tenants) and of `org_unit_id`'s subtree when named (a tenant it cannot see is
`tenant_boundary`). Every figure is computed; a model may word the sentence only through `analytics.word`.


    device.ageingSuggestions  read  {flow_id | org_unit_id, offers_days?}  the moves the live listings of the flow's org (or of
                                                             the named org, read with the flow that decides it) call for, each
                                                             placed into that flow's draft as a checked, simulated proposal

The suggestions (`di.services.device.ageing`) are counted from the live listings; each draft rule is placed into the draft (or
the published graph) as `flow.suggestions` places a rule, checked against the guardrails and the other rules and simulated on
the open queue. Nothing is saved. Accepting is the person's own `flow.saveDraft` with the proposal's graph; the flow is then
submitted and approved by a different person and published as any change (maker-checker, MVP-3.2). Who may read it: a person
who may edit or approve flows, within the flow's org scope, as `flow.suggestions`. No agent runs it (it is in
`FORBIDDEN_ACTIONS`: the choice of a rule is a person's, R21). No language model and no figure by a model: counts and sums only.
"""

from typing import Any, cast

from di.core import clock, policy
from di.core.orgs import subtree
from di.repositories import flows as repo
from di.repositories import orgs
from di.repositories.flows import FlowRow
from di.services.actions import modeler_suggest as base
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.cases import pack_questions  # noqa: F401  (registers every pack's worked questions)
from di.services.device import ageing, analytics
from di.services.modeler.flow import Flow
from di.services.modeler.suggest import Suggestion
from di.services.modeler.templates import load_template

ACTIONS.setdefault(
    "device.ageingSuggestions",
    ActionDef(
        id="device.ageingSuggestions",
        title="Suggest ageing rules",
        desc="Moves for listings that sit unsold or with no offer, each drafted as a checked, simulated rule. Changes nothing.",
        risk="read",
        perm=None,
        scope="none",
        input={
            "flow_id": {"req": False, "t": "number"},
            "org_unit_id": {"req": False, "t": "string"},
            "offers_days": {"req": False, "t": "number"},
        },
        verb="read ageing suggestions",
    ),
)


def _target(ctx: CallContext, i: dict[str, Any]) -> tuple[FlowRow, str]:
    """The flow that decides, and the org whose listings are read: the named `flow_id` and its org, or the `org_unit_id` and the
    flow nearest above it (its own, else the one it inherits)."""
    if i.get("flow_id") is not None:
        f = base._flow(ctx, i)
        return f, f.org_unit_id
    org = str(i.get("org_unit_id") or "")
    if org not in orgs.units(ctx.session):
        raise ActionError("not_found", f"No org unit {org}.")
    found = repo.flow_for(ctx.session, "device", org)
    if found is None:
        raise ActionError("not_found", f"No device decision flow above {org}.")
    return found, org


@guard("device.ageingSuggestions")
def ageing_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if i.get("offers_days") not in (None, *ageing.choices()):
        return "validation_error", f"offers_days is one of {', '.join(str(d) for d in ageing.choices())}."
    if (i.get("flow_id") is None) == (not i.get("org_unit_id")):
        return "validation_error", "Name the flow (flow_id) or the org unit (org_unit_id), not both."
    acct = ctx.actor.account
    if acct is None or not any(policy.can(acct, p, ctx.actor.ctx) for p in ("manageFlows", "approve.flows")):
        return "out_of_scope", f"The {ctx.actor.role} view cannot read ageing suggestions."
    try:
        f, org = _target(ctx, i)
    except ActionError as e:
        return e.code, e.message
    if f.template_key != "device":
        return "validation_error", f"Flow {f.id} is not a device flow."
    person = ctx.actor.person
    if policy.policy(person).get("tenantScoped") and not policy.tenant_ok(person, org, ctx.actor.ctx):
        return "tenant_boundary", f"{org} is a tenant you cannot see. Request tenant access first."
    return None


def _visible(ctx: CallContext) -> list[str] | None:
    """The org units whose listings the actor may see: every one, or for a tenant-scoped role those of its tenants."""
    if ctx.actor.account is None or not policy.policy(ctx.actor.person).get("tenantScoped"):
        return None
    return [u for u in orgs.units(ctx.session) if policy.tenant_ok(ctx.actor.person, u, ctx.actor.ctx)]


@implement("device.ageingSuggestions")
def ageing_suggestions(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f, org = _target(ctx, i)
    t = load_template("device")
    g = cast(Flow, f.draft if f.draft is not None else f.published)
    today = clock.now().date()
    cfg = ageing.settings(i.get("offers_days"))
    out = []
    for x in ageing.suggestions_for(ctx.session, org, today, i.get("offers_days"), _visible(ctx)):
        s = Suggestion("listChannel", x.frm, x.to, 0, 0, 0.0, x.text, x.rule)  # the shape a proposal is built from
        out.append(x.as_dict() | {"proposal": base._proposal(ctx, f, t, g, s)})
    return {
        "flow_id": f.id, "flow_org": f.org_unit_id, "org_unit_id": org, "as_of": today.isoformat(),
        "offers_days": cfg.offers_to_auction_days, "choices": list(ageing.choices()), "buynow_days": cfg.buynow_to_offers_days,
        "suggestions": out,
    }  # fmt: skip


ACTIONS.setdefault(
    "device.question",
    ActionDef(
        id="device.question",
        title="Answer a device question",
        desc="One worked question of the device pack (price after a launch, disputes by partner), computed. Changes nothing.",
        risk="read",
        perm=None,
        scope="none",
        input={"question_id": {"req": True, "t": "string"}, "org_unit_id": {"req": False, "t": "string"}},
        verb="read a device question",
    ),
)


@guard("device.question")
def question_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if i.get("question_id") not in analytics.REGISTRY:
        return "not_found", f"No question {i.get('question_id')}. Questions: {', '.join(analytics.REGISTRY)}."
    org = i.get("org_unit_id")
    if org:
        if org not in orgs.units(ctx.session):
            return "not_found", f"No org unit {org}."
        person = ctx.actor.person
        if policy.policy(person).get("tenantScoped") and not policy.tenant_ok(person, org, ctx.actor.ctx):
            return "tenant_boundary", f"{org} is a tenant you cannot see. Request tenant access first."
    return None


@implement("device.question")
def question(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    visible = _visible(ctx)
    allowed = None if visible is None else set(visible)
    if i.get("org_unit_id"):
        wanted = subtree(orgs.units(ctx.session), i["org_unit_id"])
        allowed = wanted if allowed is None else wanted & allowed
    as_of = clock.now().date()
    scope = analytics.Scope(frozenset(allowed)) if allowed is not None else None
    ans = analytics.answer(ctx.session, i["question_id"], scope, as_of)
    return ans.as_dict() | {"question": analytics.REGISTRY[i["question_id"]].question, "as_of": as_of.isoformat()}
