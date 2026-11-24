"""A flow simulated on its open queue (plan 8, MVP-4.1; Domain spec D9): what `flow.simulate` and the assistant's
proposals (MVP-5.2) answer.

- The queue: the live cases the actor may see (tenant boundary and warehouse lock, as the case pages) of the flow's
  template, not closed, whose nearest flow (`flow_for` on the case's owner) is this flow.
- The base rule set is the flow's published graph compiled; the candidate is the graph given (or the draft).
- `industrial` cases are decided by the engine on their stored route terms: the drafts keep their hand-modelled and
  gate exclusions, drop the ones earlier business rules made, and are evaluated with the rule set (no predictor draws,
  so the answer is deterministic).
- What-if (P9-0.15): on the tool-fleet template `params` {market, labor, lease, slots} are laid over the valuer's
  base parameters (BASEP) on the candidate side only; the base side stays the published rules at BASEP. Read only.
- `tool_fleet` and `device` (MVP-6.3): the template's sample queue (the prototype's open tool returns, rng(26110); its
  device lots, rng(4242)) plus any live cases of the template, decided by the template's valuer
  (di.services.modeler.valuers), so a simulation equals the prototype's fSim on the same flows.
"""

import copy
import dataclasses
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from di.repositories.context import visible_cases
from di.repositories.flows import FlowRow, flow_for
from di.services.actions.pipeline import CallContext
from di.services.cases import intake
from di.services.cases.lifecycle import STAGES
from di.services.engine.evaluate import draft_of, evaluate
from di.services.engine.routes import POLICY, Route
from di.services.modeler.apply import FLOW_REMOVED
from di.services.modeler.compile import CompiledRule, compile_flow
from di.services.modeler.flow import Flow
from di.services.modeler.simulate import Decider, Decision, SimResult, simulate
from di.services.modeler.templates import Template, load_template
from di.services.modeler.valuers import device, tool_fleet

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


def _rule_dicts(rules: Sequence[CompiledRule]) -> list[dict[str, Any]]:
    return [dataclasses.asdict(r) for r in rules]


def _live(c: Mapping[str, Any]) -> bool:
    """An open case of the workspace (it has a stage), not one of the template's sample queue."""
    return "stage" in c


def tool_fleet_decider_at(params: Mapping[str, float] | None = None) -> Decider:
    """The tool-fleet valuer (the prototype's decide): a sample return within the sample queue's plan; an open case
    as it is valued when it opens or is re-evaluated (di.services.cases.intake.template_decide; audit F1). `params`
    are what-if levers over BASEP (None: the published numbers)."""
    p = None if params is None else tool_fleet.BASEP | dict(params)

    def decide(c: Mapping[str, Any], rules: Sequence[CompiledRule]) -> Decision:
        if _live(c):
            best = intake.template_decide("tool_fleet", intake.valuer_input(c, "tool_fleet"), rules, params)["best"]
        else:
            best = tool_fleet.decide(dict(c), p, _rule_dicts(rules))["best"]
        return Decision(best["k"], float(best["net"])) if best else Decision(None, 0.0)

    return decide


tool_fleet_decider = tool_fleet_decider_at()


def device_decider(c: Mapping[str, Any], rules: Sequence[CompiledRule]) -> Decision:
    """The device valuer (dDecide): the expected cash a unit and its days to sell."""
    lot = intake.valuer_input(c, "device") if _live(c) else dict(c)
    best = device.decide(lot, _rule_dicts(rules))["best"]
    return Decision(best["k"], float(best["cash"]), {"days": best["days"]}) if best else Decision(None, 0.0, {"days": 0.0})


def _tool_fleet(ctx: CallContext, f: FlowRow, _t: Template) -> tuple[list[dict[str, Any]], Decider]:
    return tool_fleet.sample_queue() + open_queue(ctx, f), tool_fleet_decider


def _device(ctx: CallContext, f: FlowRow, _t: Template) -> tuple[list[dict[str, Any]], Decider]:
    return device.sample_lots() + open_queue(ctx, f), device_decider


# industrial: the live cases; tool_fleet and device: the template's sample queue plus any live cases of the template
SOURCES: dict[str, QueueDecider] = {"industrial": _industrial, "tool_fleet": _tool_fleet, "device": _device}


LEVER_BOUNDS: dict[str, tuple[float, float]] = {"market": (0.5, 1.5), "labor": (0.5, 1.5), "lease": (0.5, 1.5), "slots": (0, 20)}


def lever_problem(f: FlowRow, params: Mapping[str, Any]) -> str | None:
    """Why the what-if levers are refused: not the tool-fleet template, an unknown lever, or a value out of range."""
    if f.template_key != "tool_fleet":
        return "What-if levers apply to the tool-fleet template."
    for k, v in params.items():
        if k not in LEVER_BOUNDS:
            return f"{k} is not a what-if lever."
        lo, hi = LEVER_BOUNDS[k]
        whole = k != "slots" or (isinstance(v, int | float) and float(v).is_integer())
        if isinstance(v, bool) or not isinstance(v, int | float) or not whole or not lo <= v <= hi:
            return f"{k} must be between {lo:g} and {hi:g}."
    return None


def simulate_rules(
    ctx: CallContext,
    f: FlowRow,
    cand: Sequence[CompiledRule],
    base: Sequence[CompiledRule] | None = None,
    params: Mapping[str, float] | None = None,
) -> SimResult:
    """The candidate rules against `base` (default: the flow's published rules) on its queue; `params` (tool fleet)
    value the candidate side at BASEP | params."""
    t = load_template(f.template_key)
    base = compile_flow(t, cast(Flow, f.published)) if base is None else base
    queue, decide = SOURCES.get(f.template_key, _industrial)(ctx, f, t)
    return simulate(t, base, cand, queue, decide, tool_fleet_decider_at(params) if params else None)


def queue_rows(ctx: CallContext, f: FlowRow) -> list[dict[str, Any]]:
    """The queue as the Modeler lists it: {id, label, best, net} under the flow's published rules."""
    t = load_template(f.template_key)
    base = compile_flow(t, cast(Flow, f.published))
    queue, decide = SOURCES.get(f.template_key, _industrial)(ctx, f, t)
    out = []
    for c in queue:
        d = decide(c, base)
        out.append({"id": c["id"], "label": _label(c), "best": d.best, "net": d.net})
    return out


def _label(c: Mapping[str, Any]) -> str:
    """A case's product and model (industrial), serial (tool fleet) or brand and model (device)."""
    parts = [c[k] for k in ("product", "brand", "model", "serial") if isinstance(c.get(k), str) and c[k]]
    return " · ".join(parts[:2]) or str(c["id"])


def simulate_graph(ctx: CallContext, f: FlowRow, graph: Flow, params: Mapping[str, float] | None = None) -> SimResult:
    return simulate_rules(ctx, f, compile_flow(load_template(f.template_key), graph), params=params)


def sim_json(r: SimResult, params: Mapping[str, float] | None = None) -> dict[str, Any]:
    flips = [{"case_id": x.case_id, "from": x.from_path, "to": x.to_path, "dv": x.dv} for x in r.flips]
    used = dict(params) if params else None
    return {"kind": r.kind, "n": r.n, "flips": flips, "dv": r.dv, "extra": dict(r.extra), "params": used}
