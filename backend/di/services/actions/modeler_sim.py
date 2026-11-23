"""A flow simulated on its open queue (plan 8, MVP-4.1; Domain spec D9): what `flow.simulate` and the assistant's
proposals (MVP-5.2) answer.

- The queue: the live cases the actor may see (tenant boundary and warehouse lock, as the case pages) of the flow's
  template, not closed, whose nearest flow (`flow_for` on the case's owner) is this flow.
- The base rule set is the flow's published graph compiled; the candidate is the graph given (or the draft).
- `industrial` cases are decided by the engine on their stored route terms: the drafts keep their hand-modelled and
  gate exclusions, drop the ones earlier business rules made, and are evaluated with the rule set (no predictor draws,
  so the answer is deterministic).
"""

import copy
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from di.repositories.context import visible_cases
from di.repositories.flows import FlowRow, flow_for
from di.services.actions.pipeline import CallContext
from di.services.cases.lifecycle import STAGES
from di.services.engine.evaluate import draft_of, evaluate
from di.services.engine.routes import POLICY, Route
from di.services.modeler.apply import FLOW_REMOVED
from di.services.modeler.compile import CompiledRule, compile_flow
from di.services.modeler.flow import Flow
from di.services.modeler.simulate import Decider, Decision, SimResult, simulate
from di.services.modeler.templates import Template, load_template

OPEN_STAGES = tuple(s for s in STAGES if s != "closed")
BUSINESS_REASONS = ("Excluded by business rule ", "Business rule ", FLOW_REMOVED)


def open_queue(ctx: CallContext, f: FlowRow) -> list[dict[str, Any]]:
    """The open live cases the actor may see that this flow decides."""
    nearest: dict[str, int | None] = {}
    out = []
    for c in visible_cases(ctx):
        if c["stage"] not in OPEN_STAGES or (c.get("template") or "industrial") != f.template_key:
            continue
        owner = c["owner"]
        if owner not in nearest:
            nf = flow_for(ctx.session, f.template_key, owner)
            nearest[owner] = nf.id if nf else None
        if nearest[owner] == f.id:
            out.append(c)
    return out


def _draft(r: Route) -> Route:
    """The route's draft with its hand-modelled and gate exclusions; an exclusion an earlier business rule made is
    dropped, so each rule set is judged on its own."""
    d = draft_of(r, keep_exclusion=True)
    pre = d.get("preset_fail")
    if pre and pre[0] == POLICY and str(pre[1]).startswith(BUSINESS_REASONS):
        del d["preset_fail"]
    return d


def industrial_decider(t: Template) -> Decider:
    def decide(c: Mapping[str, Any], rules: Sequence[CompiledRule]) -> Decision:
        case = copy.deepcopy(dict(c))
        _, rec = evaluate(case, [_draft(r) for r in c["routes"]], rules=False, business=list(rules), template=t)
        return Decision(rec["id"], float(rec["net"])) if rec else Decision(None, 0.0)

    return decide


QueueDecider = Callable[[CallContext, FlowRow, Template], tuple[list[dict[str, Any]], Decider]]


def _industrial(ctx: CallContext, f: FlowRow, t: Template) -> tuple[list[dict[str, Any]], Decider]:
    return open_queue(ctx, f), industrial_decider(t)


SOURCES: dict[str, QueueDecider] = {"industrial": _industrial}


def simulate_rules(ctx: CallContext, f: FlowRow, cand: Sequence[CompiledRule]) -> SimResult:
    """The candidate rules against the flow's published ones on its queue."""
    t = load_template(f.template_key)
    base = compile_flow(t, cast(Flow, f.published))
    queue, decide = SOURCES.get(f.template_key, _industrial)(ctx, f, t)
    return simulate(t, base, cand, queue, decide)


def simulate_graph(ctx: CallContext, f: FlowRow, graph: Flow) -> SimResult:
    return simulate_rules(ctx, f, compile_flow(load_template(f.template_key), graph))


def sim_json(r: SimResult) -> dict[str, Any]:
    flips = [{"case_id": x.case_id, "from": x.from_path, "to": x.to_path, "dv": x.dv} for x in r.flips]
    return {"kind": r.kind, "n": r.n, "flips": flips, "dv": r.dv, "extra": dict(r.extra)}
