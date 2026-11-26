"""The one decider (plan 9, P9-1.5; registry entry I-6; rule R19). Opening a case, re-evaluating it, a shadow probe and a
simulation all call `decide_case`; replay (P9-7.2) and the chain (P9-2.1) join them. Never write a second decider.

    decide_case(case_id_or_facts, pack, flow_ver, as_of=None, *, session, queue, planner) -> Decision
    write_back(case, decision)             the decision's fields set on a case document (the caller moves the stage)
    WhatIfPlanner(planner, levers)         a planner whose parameters carry the what-if levers (P9-0.15)

The order for every case is R20 (`Decision.trace`, asserted by `test_order_invariant_<pack>`):

1. **gates**: the pack's gates (I-2) are evaluated first and may hold the case for evidence (di.services.cases.gate_hold);
   the routes they block are known before any value is computed;
2. **valuation** over the routes the gates left eligible, and, for the tool fleet, 3. the **queue plan**: a blocked route
   is left out of the plan (the case's `gateBlocked`), so it never wins a named order and leaves it unfilled; the gates'
   results then fail those routes with the gate's reason;
   (the compiled rules that break a locked guardrail are dropped before this, as compile drops them too: that is the
   run-time check, and it is also what the valuer is given);
4. **rules**: the pack's diversions that match the case (`add_step` lists a required step with its owner role, `shortcut`
   to a route prefers it when it is eligible), then the flow's business rules (`apply_business`);
5. **rank**: `rank_routes`: the shortcut's route, else the valuer's choice while it is eligible, else a rule's preference.

A route's money does not depend on a gate (only the tool fleet's plan of named orders does), and no later step brings back
a route an earlier step excluded: the waiver of the rules restores only what the gates left eligible (audit F5). The pack's
valuer kind chooses the values: `industrial` is the engine's formulas on the case's seeded predictor, `tool_fleet` the queue
planner's plan over the org's open returns with their named demand (a `queue` given decides the case within that queue,
without named demand), `device` the channel scores, `standard` the pack's own value lines (P9-1.9; the `VALUERS` table of
I-21, where a code plug-in registers too). The valuers read the case as it was before a hold set its stage.

A case is a stored case (a `str` id, loaded with the session) or a Mapping: a case document, or a valuer-shaped sample
(the Modeler's sample queue). The case given is never changed; callers set the result on their own copy with `write_back`.
Never does: write a database row, approve anything, or move a stage.
"""

import copy
import dataclasses
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from importlib import import_module
from typing import Any, cast

from sqlalchemy.orm import Session

from di.core import clock
from di.services.actions.registry import ActionError
from di.services.cases import gate_hold, store
from di.services.device import lock as _device_lock  # noqa: F401 - registers the check of the gate G-DEV-LOCK (P9-6.6)
from di.services.device import verify as _device_verify  # noqa: F401 - registers the check of the gate G-DEV-QUOTE (P9-6.5)
from di.services.device import wipe as _device_wipe  # noqa: F401 - registers the check of the gate G-DEV-WIPE (P9-6.7)
from di.services.engine.evaluate import apply_business, build_routes
from di.services.engine.jsmath import js_round
from di.services.engine.queue import Capacity, Dem, QueuePlanner, planner_for
from di.services.engine.routes import Route, rank_routes
from di.services.modeler.apply import FLOW_REMOVED
from di.services.modeler.compile import FLOW, CompiledRule, FlowVersion
from di.services.modeler.gates import (
    Cond,
    GateDef,
    GateEffectDef,
    GateResult,
    GateTrigger,
    apply_disclosures,
    apply_gate_results,
    triggered,
)
from di.services.modeler.guard import rule_breaks
from di.services.modeler.pack import Diversion, Pack
from di.services.modeler.templates import Template, template_of_pack
from di.services.modeler.valuers import VALUERS, device, fleet_evidence, service_desk, tool_fleet
from di.services.modeler.valuers.device import ChannelValue
from di.services.modeler.valuers.routes_adapter import to_routes
from di.services.modeler.valuers.tool_fleet import PathValue

TRACE = ("gates", "valuation", "queue_plan", "rules", "rank")
GATE_KEYS = ("gates", "gateHold", "requiredSteps")  # the case keys the gates and the diversions set
RULE_KEYS = ("rulesApplied", "rulesWaived", "preferred")
RULE_REASONS = ("Excluded by business rule ", "Business rule ", FLOW_REMOVED)  # why a path a business rule excluded says


@dataclass(frozen=True)
class Decision:
    """What `decide_case` decided. `net` is the recommendation's net (0 with none). `extra` holds the valuer's figures of
    the chosen route that a caller may need (device: `cash` a unit and `days` to sell). `case_fields` are the gate keys the
    case document is left with (`GATE_KEYS`); `write_back` sets them."""

    case_id: str
    pack_key: str
    pack_version: str
    flow_ver: int
    route: str | None
    net: float
    routes: list[Route]
    recommendation: Route | None
    gates: list[GateResult]
    diversions: list[str]
    rules_applied: list[str]
    waived: bool
    preferred: str | None
    plan: dict[str, Any] | None
    required_steps: list[dict[str, Any]]
    hold: dict[str, Any] | None
    trace: tuple[str, ...]
    as_of: datetime | None
    extra: Mapping[str, float] = field(default_factory=dict)
    case_fields: Mapping[str, Any] = field(default_factory=dict)
    ticket: Mapping[str, Any] | None = None  # a service ticket's options, holds and inputs (P9-4.6)


class WhatIfPlanner:
    """A planner that lays the what-if levers (market, labor, lease, slots; P9-0.15) over the parameters it is given."""

    def __init__(self, base: QueuePlanner, levers: Mapping[str, float]) -> None:
        self.base, self.levers = base, dict(levers)

    def plan(
        self,
        cases: Sequence[tool_fleet.Case],
        demand: Mapping[str, Dem],
        capacity: Capacity,
        *,
        rules: Sequence[tool_fleet.Rule] = (),
        params: tool_fleet.Params | None = None,
    ) -> tool_fleet.Plan:
        p = (params or tool_fleet.BASEP) | self.levers
        return self.base.plan(cases, demand, Capacity(slots=js_round(p["slots"]), depots=capacity.depots), rules=rules, params=p)


@dataclass(frozen=True)
class _Valued:
    """What a valuer gives the decider: the routes, the path it chose, the queue plan slice (tool fleet) and the figures a
    route is valued with by id (device: cash a unit and days to sell)."""

    routes: list[Route]
    best: str | None
    plan: dict[str, Any] | None = None
    figures: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    ticket: dict[str, Any] | None = None


# ---------------------------------------------------------------- the steps
def _intake() -> Any:
    from di.services.cases import intake  # intake imports this module

    return intake


def _load(case_or_facts: str | Mapping[str, Any], session: Session | None) -> dict[str, Any]:
    if isinstance(case_or_facts, str):
        if session is None:
            raise TypeError(f"decide_case needs a session to load {case_or_facts}")
        c = store.get(session, case_or_facts)
        if c is None:
            raise ActionError("not_found", f"No case {case_or_facts}.")
        return c
    return copy.deepcopy(dict(case_or_facts))


def _compliant(t: Template, rules: Sequence[CompiledRule]) -> list[CompiledRule]:
    """The rules that break no locked guardrail (the flow's own `FLOW` pseudo-rule is the process, not a business rule)."""
    locked = dataclasses.replace(t, guardrails=tuple(g for g in t.guardrails if g.locked))
    return [r for r in rules if r.id == FLOW or not rule_breaks(locked, {"scope": r.scope, "action": r.action, "path": r.path})]


def _matches(d: Diversion, case: Mapping[str, Any], pack: Pack) -> bool:
    """The diversion's conditions hold for the case: a gate's trigger is the one place that reads `when` conditions."""
    probe = GateDef(
        id=d.op_id, name=d.op_id, type="Approval", stage=d.stage, packs=[pack.key],
        trigger=GateTrigger(routes="any", when=[Cond.model_validate(c) for c in d.when]), evidence=[],
        effect=GateEffectDef(kind="require_step"), owner="", citation="", legal_review="pending",
    )  # fmt: skip
    return triggered(probe, case, pack)


def _decorate(t: Template, routes: list[Route]) -> None:
    """What the case pages read of a template route: who takes it, through which application."""
    for r in routes:
        p = t.path(r["id"])
        r |= {"demandLabel": f"{p.owner} · {p.app}" if p else r["plan"], "demandStatus": "forecast", "unc": ""}


def _valuer_case(c: Mapping[str, Any], template_key: str) -> dict[str, Any]:
    """What the valuer decides the case on: the snapshot or the fields of a stored case, a sample as it is."""
    if "valuer" in c or "stage" in c:
        return dict(_intake().valuer_input(c, template_key))
    return copy.deepcopy(dict(c))


def _queue_of(
    c: Mapping[str, Any], v: dict[str, Any], session: Session | None, queue: Sequence[Mapping[str, Any]] | None
) -> tuple[list[dict[str, Any]], dict[str, Dem]]:
    """The returns the case is planned with and their named demand: the queue given (as it is), else the org's open
    tool-fleet cases when the session and the owner are known, else the case alone."""
    if queue is not None:
        cases = [dict(x) for x in queue]
        if all(x["id"] != v["id"] for x in cases):
            cases.append(v | {"status": "new"})
        return cases, {}
    if session is not None and c.get("owner"):
        q = _intake().tool_queue(session, c["owner"], v)
        return q.cases, q.demand
    return [v | {"status": "new"}], {}


def _rule_dicts(rules: Sequence[CompiledRule]) -> list[dict[str, Any]]:
    return [dataclasses.asdict(r) for r in rules]


def _tool_fleet(
    c: Mapping[str, Any], pack: Pack, t: Template, rules: Sequence[CompiledRule], session: Session | None,
    queue: Sequence[Mapping[str, Any]] | None, planner: QueuePlanner | None, blocked: frozenset[str] = frozenset(),
) -> _Valued:  # fmt: skip
    """The queue plan under the flow's rules gives the values, the valuer's choice and what the valuer itself leaves out (a
    depot slot, an order another return holds): the rules change who gets a slot, so these are read from that plan. A path a
    rule excluded is let through again here, with its description from the plan without rules, so `apply_business` excludes
    it with its own reason and records the rule. `blocked` are the paths the gates blocked for this case (R20: the gates ran
    first): the plan leaves them out (`gateBlocked`, so none wins a named order) and they are let through again here the
    same way, for `apply_gate_results` to fail them with the gate's reason."""
    v = _valuer_case(c, "tool_fleet")
    if parts := fleet_evidence.blocked_parts(c):  # the parts harvest never certifies (GR-12, P9-3.7)
        v["recallParts"] = sorted(parts)
    cases, demand = _queue_of(c, v, session, queue)
    if v.get("recallParts"):  # the queue holds this case as it was read: the plan sees the same parts blocked
        cases = [x | {"recallParts": v["recallParts"]} if x["id"] == v["id"] else x for x in cases]
    p = planner or planner_for(pack)
    cap = Capacity(slots=js_round(tool_fleet.BASEP["slots"]))

    me = v["id"]
    stamped = [x | {"gateBlocked": sorted(blocked)} if x["id"] == me else x for x in cases] if blocked else cases

    def planned(rs: list[dict[str, Any]], gated: bool = False) -> tool_fleet.Plan:
        return p.plan(stamped if gated else cases, demand, cap, rules=rs, params=tool_fleet.BASEP)

    plan = planned(_rule_dicts(rules), True)
    dec: dict[str, Any] = {**plan["res"][me], "indep": plan["indep"][me], "blk": sorted(plan["blk"][me])}
    by_rule = [x["k"] for x in dec["all"] if not x["ok"] and str(x["why"]).startswith(RULE_REASONS)]
    by_gate = [x["k"] for x in dec["all"] if not x["ok"] and x["why"] == tool_fleet.GATE_BLOCKED]
    plain = {x["k"]: x for x in planned([])["res"][me]["all"]} if by_rule or by_gate else {}
    values = [x | {"ok": True, "why": plain[x["k"]]["why"]} if x["k"] in by_rule + by_gate else x for x in dec["all"]]
    routes = to_routes(t, values)
    _decorate(t, routes)
    queue_plan = {
        "holds": next((o for o, who in sorted(plan["own"].items()) if who == me), None),
        "contested": sorted(o for o, w in plan["why"].items() if me == w["to"] or me in w["others"]),
        "lost": [{"order": o, "to": w["to"], "gain": w["gain"]} for o, w in sorted(plan["why"].items()) if me in w["others"]],
    }
    best = dec.get("best")
    return _Valued(routes, best["k"] if best else None, queue_plan)


def _service_desk(c: Mapping[str, Any], t: Template, session: Session | None, as_of: datetime | None) -> _Valued | None:
    """A ticket case (flow `service_desk`) is valued as its three options: fix, covered swap, upgrade (P9-4.6). None when the
    case is not one, or its market has no tables: it is then valued as a tool-fleet return, as before."""
    sd = c.get("serviceDesk")
    if c.get("flow") != "service_desk" or not isinstance(sd, dict) or "lines" not in sd:
        return None
    if session is not None:
        on = (
            as_of.date()
            if as_of
            else max(
                (date.fromisoformat(ln["estimate"]["as_of"]) for ln in sd["lines"] if ln.get("estimate")),
                default=clock.now().date(),
            )
        )
        inputs = import_module("di.services.service_desk.inputs").gather(
            session, c, on
        )  # not imported: the case store may not import repositories
    else:
        inputs = sd.get("inputs")  # a replay or a simulation without a session: the snapshot the case holds
    if inputs is None:
        return None
    ticket = service_desk.decide_ticket(inputs)
    if (
        ticket["best"] is None
    ):  # nothing priced yet (a draft, no estimate): the return is valued as before, a technician checks first
        return None
    values = [
        {"k": o["k"], "ok": o["eligible"], "gross": 0.0, "cost": 0.0, "hold": 0.0, "net": o["expected_margin"] or 0.0,
         "why": o["why"], "lines": [{"type": "v" if (o["expected_margin"] or 0) >= 0 else "c", "label": "Expected margin",
                                    "basis": o["why"], "amt": abs(o["expected_margin"] or 0.0)}],
         "dest": None, "misses": [], "co2": None, "co2Prov": None}
        for o in ticket["options"]
    ]  # fmt: skip
    routes = to_routes(t, cast(list[PathValue | ChannelValue], values))
    _decorate(t, routes)
    return _Valued(routes, ticket["best"], ticket=ticket | {"inputs": inputs})


def _device(c: Mapping[str, Any], t: Template, rules: Sequence[CompiledRule]) -> _Valued:
    lot = _valuer_case(c, "device")
    dec = device.decide(dict(lot), _rule_dicts(rules))
    own = {x["k"]: x for x in device.decide(dict(lot), [])["all"]}
    routes = to_routes(t, [x | {"ok": own[x["k"]]["ok"], "why": own[x["k"]]["why"]} for x in dec["all"]])
    _decorate(t, routes)
    best = dec["best"]
    return _Valued(
        routes, best["k"] if best else None, None, {x["k"]: {"cash": x["cash"], "days": x["days"]} for x in dec["all"]}
    )


def _plugin(kind: str, c: Mapping[str, Any], pack: Pack, t: Template, as_of: datetime | None) -> _Valued:
    """A pack valued by the `VALUERS` plug-in of its kind (I-21; the standard valuer reads the pack's own value lines) on
    the case's facts: the snapshot of a stored case over its fields, a facts mapping as it is. The values are given with
    only what the valuer itself leaves out (a requirement); the flow's rules act afterwards in `apply_business`."""
    facts = {**{k: v for k, v in c.items() if k != "valuer"}, **(c.get("valuer") or {})}
    values = VALUERS[kind](facts, pack, as_of)
    routes = to_routes(t, values)
    _decorate(t, routes)
    best = max((v for v in values if v["ok"]), key=lambda v: v["net"], default=None)
    return _Valued(routes, best["k"] if best else None)


def _industrial(c: dict[str, Any], session: Session | None) -> list[Route]:
    if session is None:
        raise TypeError(f"decide_case needs a session to value {c.get('id')} (the active model and PLM)")
    return build_routes(c, _intake().industrial_predictor(session, c))  # valued, the engine's gate rules applied


def _shortcut(diversions: Sequence[Diversion], routes: list[Route]) -> str | None:
    """The route of the first shortcut whose route is still eligible."""
    open_ids = {r["id"] for r in routes if not r["excluded"]}
    return next((d.to for d in diversions if d.kind == "shortcut" and d.to in open_ids), None)


LOW_LIFE_HELD = frozenset({"release", "redeploy"})  # re-issue and pool: a Low life confidence leaves them to a person (P9-3.9)


def _not_held_for_person(
    rec: Route | None,
    routes: Sequence[Route],
    results: Sequence[GateResult],
    life: Mapping[str, Any] | None = None,
    disagreement: Mapping[str, Any] | None = None,
) -> Route | None:
    """GR-13 (P9-3.8): the routes a failed stale-telematics gate leaves to a person (re-issue, pool) are valued and shown but
    are never the recommendation: the best of the other eligible routes is. Choosing one goes to a person (the hold policy).
    A Low life confidence (P9-3.9: no telematics, or a reading a week old) holds the same two routes, whatever the gate says.
    So does a telematics and inspection disagreement (P9-3.11): Quality settles it first,
    so neither of those two paths is the recommendation."""
    person = {i for r in results if r.gate_id == fleet_evidence.TEL_GATE and not r.passed for i in r.effect.routes}
    if (life or {}).get("confidence") == "Low":
        person |= LOW_LIFE_HELD
    if disagreement:
        person |= LOW_LIFE_HELD
    if rec is None or rec["id"] not in person:
        return rec
    ranked = sorted((r for r in routes if not r["excluded"] and r["id"] not in person), key=lambda r: r["rank"])
    return ranked[0] if ranked else None


def _extra(rec: Route | None, figures: Mapping[str, Mapping[str, float]]) -> Mapping[str, float]:
    """The device's cash a unit and days to sell of the route chosen (zero with none); other packs have none."""
    if not figures:
        return {}
    v = figures.get(rec["id"]) if rec else None
    return {"cash": float(v["cash"]), "days": float(v["days"])} if v else {"cash": 0.0, "days": 0.0}


def _valuer_kind(pack: Pack) -> str:
    """The `VALUERS` key a pack is valued by: a standard pack that names a code plug-in (`valuer.params.params.plugin`, P9-9.10)
    is valued by it, else the pack's valuer kind."""
    plugin = (pack.valuer.params.get("params") or {}).get("plugin") if pack.valuer.kind == "standard" else None
    return str(plugin) if plugin in VALUERS else pack.valuer.kind


# ---------------------------------------------------------------- the decider
def decide_case(
    case_or_facts: str | Mapping[str, Any],
    pack: Pack,
    flow_ver: FlowVersion,
    as_of: datetime | None = None,
    *,
    session: Session | None = None,
    queue: Sequence[Mapping[str, Any]] | None = None,
    planner: QueuePlanner | None = None,
) -> Decision:
    """Decide the case with the pack and the flow version (module docstring). `as_of` is the time evidence is read at
    (default: now, or the newest record's time when later). `queue` and `planner` are the tool fleet's: the returns the
    case is planned with and the planner (default: the pack's)."""
    c = _load(case_or_facts, session)
    t = template_of_pack(pack)
    rules = _compliant(t, flow_ver.rules)
    if pack.valuer.kind == "tool_fleet" and "stage" not in c:  # a sample-world return (P9-3.6)
        have = {r.get("type") for r in c.get("evidenceRecords") or []}
        c["evidenceRecords"] = [
            *(c.get("evidenceRecords") or []),
            *(
                {"type": e.type, "source": e.source, "at": e.at.isoformat(), "result": e.result, "value": dict(e.value)}
                for e in fleet_evidence.sample_evidence(c).values()
                if e.type not in have
            ),
        ]  # its evidence is complete: an active contract line, so the gates pass and the sample's numbers stay
    before = dict(c)  # what the valuers read: the case as it was before a hold set its stage and recommendation
    results = gate_hold.apply(c, [], pack, as_of)  # 1. gates (and the hold), before any valuation or queue plan
    blocked = frozenset(i for r in results if not r.passed and r.effect.kind == "block" for i in r.effect.routes)
    kind = _valuer_kind(pack)
    if kind == "industrial":
        valued = _Valued(_industrial(before, session), None)
    elif kind == "tool_fleet":  # 2. valuation, then the queue plan, over the routes the gates left eligible
        valued = _service_desk(before, t, session, as_of) or _tool_fleet(before, pack, t, rules, session, queue, planner, blocked)
    elif kind == "device":
        valued = _device(before, t, rules)
    elif kind in VALUERS:  # a data-only pack (`standard`) or a code plug-in (I-21)
        valued = _plugin(kind, before, pack, t, as_of)
    else:
        raise ValueError(f"No valuer for the {kind} pack {pack.key}")
    routes = valued.routes
    apply_gate_results(routes, results)  # the gates' results fail the routes they block
    apply_disclosures(routes, results)  # a title brand is disclosed on every route (P9-9.8)
    # (compliance: `rules` above are the compiled rules that break no locked guardrail)
    diversions = [d for d in pack.diversions if _matches(d, c, pack)]  # 4. diversions, then the business rules
    steps = [
        {"gate": d.op_id, "step": d.step, "owner": d.owner_role, "stage": d.stage, "kind": "diversion"}
        for d in diversions
        if d.kind == "step"
    ]
    kept = [x for x in c.get("requiredSteps") or [] if x.get("kind") != "diversion"]  # an earlier decision's steps are stale
    if kept or steps:
        c["requiredSteps"] = [*kept, *steps]
    else:
        c.pop("requiredSteps", None)
    apply_business(c, routes, rules, t)
    go = _shortcut(diversions, routes)
    if go:
        c["preferred"] = go
    eligible = {r["id"] for r in routes if not r["excluded"]}  # 5. rank
    chosen = go or (valued.best if valued.best in eligible else c.get("preferred"))
    rec = rank_routes(routes, c.get("blocked") or c.get("gateHold"), chosen)
    rec = _not_held_for_person(rec, routes, results, c.get("life"), c.get("disagreement"))
    return Decision(
        case_id=str(c.get("id")), pack_key=pack.key, pack_version=pack.version, flow_ver=flow_ver.ver,
        route=rec["id"] if rec else None, net=float(rec["net"]) if rec else 0.0, routes=routes, recommendation=rec,
        gates=results, diversions=[d.op_id for d in diversions], rules_applied=list(c["rulesApplied"]),
        waived=bool(c["rulesWaived"]), preferred=c.get("preferred"), plan=valued.plan,
        required_steps=list(c.get("requiredSteps") or []),
        hold=c.get("gateHold"), trace=TRACE, as_of=as_of, extra=_extra(rec, valued.figures),
        case_fields={k: c[k] for k in GATE_KEYS if k in c}, ticket=_ticket_of(valued.ticket, rec),
    )  # fmt: skip


def _ticket_of(ticket: dict[str, Any] | None, rec: Route | None) -> dict[str, Any] | None:
    """The ticket's decision with the holds of the route finally recommended (R20: the holds come last)."""
    if ticket is None:
        return None
    return ticket | {"holds": service_desk.approval_holds(ticket, rec["id"] if rec else None)}


def write_back(case: MutableMapping[str, Any], d: Decision) -> None:
    """Set the decision on a case document: the routes and recommendation, the flow version, the gate keys and what the
    rules did (kept only when they did something). The stage is the caller's to move."""
    case["routes"], case["recommendation"], case["flowVer"] = d.routes, d.recommendation, d.flow_ver
    for k in GATE_KEYS:
        if k in d.case_fields:
            case[k] = d.case_fields[k]
        else:
            case.pop(k, None)
    for k in RULE_KEYS:
        case.pop(k, None)
    if d.rules_applied or d.waived or d.preferred:
        case.update(rulesApplied=d.rules_applied, rulesWaived=d.waived, preferred=d.preferred)
    case.pop("approvalHolds", None)
    if d.ticket is not None and isinstance(
        case.get("serviceDesk"), dict
    ):  # a ticket: each line's options, the holds I-10 and I-11 read
        sd = case["serviceDesk"]
        sd["inputs"] = d.ticket["inputs"]
        sd["options"] = d.ticket["options"]
        by_n = {ln["n"]: ln for ln in d.ticket["lines"]}
        for line in sd["lines"]:
            line["options"], line["best"] = by_n[line["n"]]["options"], by_n[line["n"]]["best"]
        if d.ticket["holds"]:
            case["approvalHolds"] = d.ticket["holds"]
