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
  (di.services.modeler.valuers), so a simulation equals the prototype's fSim on the same flows. Every one of them is
  decided by `decide_case` (P9-1.5, R19), as it is when it opens: a live tool-fleet case in the plan of its org's open
  queue, with named demand (P9-1.4); a sample return in the prototype's live world (its open returns and the inbox),
  which is what keeps a simulation equal to the prototype's.
- A live contract refresh case (P9-5.8) is in the tool-fleet queue and is priced by `refresh_decision` (its best route and net,
  to the cent, as the case panel and the decision show them); no flow rule or lever changes it.
"""

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

from di.repositories.context import visible_cases
from di.repositories.flows import FlowRow, flow_for
from di.repositories.live_rules import live_pack
from di.repositories.packs import published_pack
from di.services import refresh_decision
from di.services.actions.pipeline import CallContext
from di.services.cases import gate_hold, intake
from di.services.cases.decide import WhatIfPlanner, decide_case
from di.services.cases.lifecycle import STAGES
from di.services.engine.evaluate import draft_of, evaluate
from di.services.engine.queue import planner_for
from di.services.engine.routes import POLICY, Route
from di.services.modeler.apply import FLOW_REMOVED
from di.services.modeler.compile import CompiledRule, FlowVersion, compile_flow
from di.services.modeler.flow import Flow
from di.services.modeler.pack import Pack
from di.services.modeler.per_node import per_node
from di.services.modeler.simulate import Decider, Decision, SimResult, decision_to_sim, simulate
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


def _live(c: Mapping[str, Any]) -> bool:
    """An open case of the workspace (it has a stage), not one of the template's sample queue."""
    return "stage" in c


def template_decider(ctx: CallContext, f: FlowRow, params: Mapping[str, float] | None = None) -> Decider:
    """The template's decider: every case, live or a sample, is decided by `decide_case` (R19) under the rules given. A live
    case is decided in the plan of its org's open queue with its named demand and with its owner's pack (the customer
    overlay included), a sample as the flow's org's pack; a sample return is planned in the prototype's live world.
    `params` are the tool-fleet what-if levers over BASEP (None: the published numbers)."""
    world = tool_fleet.sample_live_cases() if f.template_key == "tool_fleet" else None
    packs: dict[str, Pack] = {}

    def decide(c: Mapping[str, Any], rules: Sequence[CompiledRule]) -> Decision:
        live = _live(c)
        if live and intake.is_refresh(c):  # a contract refresh is priced by refresh_decision (P9-5.8, R19), not by a flow rule
            return Decision(*refresh_decision.best_of(ctx.session, dict(c)))
        owner = c["owner"] if live else f.org_unit_id
        if owner not in packs:
            probe = {"template": f.template_key, "owner": owner}
            packs[owner] = live_pack(
                ctx.session, probe, gate_hold.base_pack(probe, published_pack(ctx.session, f.template_key, owner))
            )
        pack = packs[owner]
        planner = WhatIfPlanner(planner_for(pack), params) if params else None
        fv = FlowVersion(f.id, f.ver, tuple(rules))
        return decision_to_sim(decide_case(c, pack, fv, session=ctx.session, queue=None if live else world, planner=planner))

    return decide


def _tool_fleet(ctx: CallContext, f: FlowRow, _t: Template) -> tuple[list[dict[str, Any]], Decider]:
    return tool_fleet.sample_queue() + open_queue(ctx, f), template_decider(ctx, f)


def _device(ctx: CallContext, f: FlowRow, _t: Template) -> tuple[list[dict[str, Any]], Decider]:
    return device.sample_lots() + open_queue(ctx, f), template_decider(ctx, f)


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
    nodes_of: Flow | None = None,
) -> SimResult:
    """The candidate rules against `base` (default: the flow's published rules) on its queue; `params` (tool fleet)
    value the candidate side at BASEP | params. With `nodes_of` (the candidate's graph) the result also says how many cases
    reach and leave each node (`per_node`, P9-8.15)."""
    t = load_template(f.template_key)
    base = compile_flow(t, cast(Flow, f.published)) if base is None else base
    queue, decide = SOURCES.get(f.template_key, _industrial)(ctx, f, t)
    r = simulate(t, base, cand, queue, decide, template_decider(ctx, f, params) if params else None)
    return replace(r, per_node=per_node(t, nodes_of, queue)) if nodes_of is not None else r


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


def simulate_graph(
    ctx: CallContext, f: FlowRow, graph: Flow, params: Mapping[str, float] | None = None, with_nodes: bool = False
) -> SimResult:
    return simulate_rules(ctx, f, compile_flow(load_template(f.template_key), graph), params=params,
                          nodes_of=graph if with_nodes else None)  # fmt: skip


def sim_json(r: SimResult, params: Mapping[str, float] | None = None) -> dict[str, Any]:
    flips = [{"case_id": x.case_id, "from": x.from_path, "to": x.to_path, "dv": x.dv} for x in r.flips]
    used = dict(params) if params else None
    out: dict[str, Any] = {"kind": r.kind, "n": r.n, "flips": flips, "dv": r.dv, "extra": dict(r.extra), "params": used}
    if r.per_node:
        out["per_node"] = r.per_node
    return out
