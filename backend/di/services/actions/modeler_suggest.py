"""Rule suggestions from overrides (plan 8, MVP-12.3).

    flow.suggestions  read  {flow_id}  the overrides of this flow's decisions, grouped, and the prefer rules they
                                       suggest, each drafted into the flow's draft as a checked and simulated proposal

The decisions are the journaled approvals and overrides (di.repositories.overrides) of the cases the actor may see whose
nearest flow for their template is this one. Each suggestion (di.services.modeler.suggest) is placed into the draft (or
the published graph) as the assistant places a rule, checked against the guardrails and the other rules, and simulated
on the open queue (di.services.actions.modeler_sim). Nothing is saved: a person who agrees applies the proposal's graph
with their own `flow.saveDraft`, and the flow is then approved by someone else and published as any other change.
Who may read it: a person who may edit or approve flows, within the flow's org scope (as flow.simulate).
"""

import dataclasses
from typing import Any, cast

from di.core import policy
from di.repositories import flows as repo
from di.repositories.context import visible_cases
from di.repositories.flows import FlowRow
from di.repositories.overrides import JournaledDecision, journaled_decisions
from di.services.actions.modeler_sim import sim_json, simulate_graph
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.modeler.flow import Flow
from di.services.modeler.guard import rule_breaks
from di.services.modeler.scope import case_value
from di.services.modeler.suggest import DecisionRow, Suggestion, override_groups, place_rule, suggest
from di.services.modeler.templates import Template, load_template
from di.services.modeler.validate import validate_flow

ACTIONS.setdefault(
    "flow.suggestions",
    ActionDef(
        id="flow.suggestions",
        title="Suggest rules from overrides",
        desc="Rules suggested by repeated Approver overrides, each checked and simulated as a proposal. Changes nothing.",
        risk="read",
        perm=None,
        scope="none",
        input={"flow_id": {"req": True, "t": "number"}},
        verb="read rule suggestions",
    ),
)


def _flow(ctx: CallContext, i: dict[str, Any]) -> FlowRow:
    f = repo.get_flow(ctx.session, int(i["flow_id"]))
    if f is None:
        raise ActionError("not_found", f"No decision flow {i['flow_id']}.")
    return f


@guard("flow.suggestions")
def suggestions_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    acct = ctx.actor.account
    if acct is None or not any(policy.can(acct, p, ctx.actor.ctx) for p in ("manageFlows", "approve.flows")):
        return "out_of_scope", f"The {ctx.actor.role} view cannot read rule suggestions."
    try:
        f = _flow(ctx, i)
    except ActionError as e:
        return e.code, e.message
    person = ctx.actor.person
    if policy.policy(person).get("tenantScoped") and not policy.tenant_ok(person, f.org_unit_id, ctx.actor.ctx):
        return "tenant_boundary", f"{f.org_unit_id} is a tenant you cannot see. Request tenant access first."
    return None


def _decided_cases(ctx: CallContext, f: FlowRow) -> dict[str, dict[str, Any]]:
    """The cases the actor may see that this flow decides (any stage)."""
    nearest: dict[str, int | None] = {}
    out: dict[str, dict[str, Any]] = {}
    for c in visible_cases(ctx):
        if (c.get("template") or "industrial") != f.template_key:
            continue
        owner = c["owner"]
        if owner not in nearest:
            nf = repo.flow_for(ctx.session, f.template_key, owner)
            nearest[owner] = nf.id if nf else None
        if nearest[owner] == f.id:
            out[c["id"]] = c
    return out


def _route_id(c: dict[str, Any], plan: str | None) -> str | None:
    return next((r["id"] for r in c["routes"] if plan is not None and r["plan"] == plan), None)


def _row(t: Template, c: dict[str, Any], j: JournaledDecision) -> DecisionRow | None:
    rec = (c.get("recommendation") or {}).get("id")
    to = _route_id(c, j["route"]) or (rec if j["action"] == "decision.approve" else None)
    if to is None:
        return None
    ov = c.get("override") if j["action"] == "decision.override" else None
    frm = (_route_id(c, ov.get("rec")) if isinstance(ov, dict) else None) or rec
    return DecisionRow(c["id"], t.key, frm, to, {d.key: case_value(c, d) for d in t.dims})


def _proposal(ctx: CallContext, f: FlowRow, t: Template, g: Flow, s: Suggestion) -> dict[str, Any]:
    graph, node_id, rid = place_rule(t, g, s.rule, ctx.actor.role, s.text)
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    broken = rule_breaks(t, node)
    checks = [
        {"level": c.level, "msg": c.msg, "node_id": c.node_id}
        for c in validate_flow(t, graph)
        if c.node_id == node_id or c.msg.startswith("Conflict")
    ]
    msg = ""
    if broken:
        gd = next(x for x in t.guardrails if x.id == broken)
        msg = f"I drafted {rid} ({s.text}), but it breaks {broken}: {gd.text}. I won't apply it."
    return {
        "kind": "blocked" if broken else "rule", "text": s.text, "graph": graph, "node_id": node_id, "rid": rid,
        "label": f"{rid}: {s.text}", "guard": broken, "checks": checks,
        "sim": None if broken else sim_json(simulate_graph(ctx, f, graph)), "msg": msg,
    }  # fmt: skip


@implement("flow.suggestions")
def suggestions(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow(ctx, i)
    t = load_template(f.template_key)
    cases = _decided_cases(ctx, f)
    rows = [r for j in journaled_decisions(ctx.session) if j["case_id"] in cases if (r := _row(t, cases[j["case_id"]], j))]
    g = cast(Flow, f.draft if f.draft is not None else f.published)
    groups = [{"template": x.template, "from": x.from_path, "to": x.to_path, "n": x.n} for x in override_groups(rows)]
    return {
        "flow_id": f.id,
        "decisions": len(rows),
        "groups": groups,
        "suggestions": [{**dataclasses.asdict(s), "proposal": _proposal(ctx, f, t, g, s)} for s in suggest(t, rows)],
    }
