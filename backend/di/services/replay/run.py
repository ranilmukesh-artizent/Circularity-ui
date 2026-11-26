"""As-of replay of a history batch under a flow (plan 9, P9-7.2; registry entry I-16; story X-06; A section 3.2 and 3.3).

    as_of_facts(item)              the facts known at the decision date, and the later ones dropped (the leakage list)
    assert_no_future(facts, t)     raises when a fact is dated after `t` (a replay uses only facts known at the time)
    case_input(...)                the valuer-shaped case a history item is decided as (from its as-of facts and the pack)
    replay(batch, items, flow, ...) -> ReplayReport   every ok item decided by `decide_case` as of its own date
    bootstrap_band(deltas, ...)    the 80 % and 95 % bands of the uplift, seeded, no numpy

Owns: running the one decider (R19, I-6) over a batch and measuring the result with `measures.py`. Both sides use that one
decision's valued routes (A section 3.3 point 2, "estimated vs estimated"): the flow side is the route the decision chose
and its net, the actual side is the net the same valuer gives the route that was taken as of the same date; an actual route
the flow's gates exclude is still valued and listed as "actual route excluded by <gate>".
Never does: store anything (the action and the worker job do), value a route itself (never a second decider), read the
clock, or write free text: every number is computed here, and a flip's reason is composed from the decision's own gate
result. Counterfactual values are modelled; sensitivity runs (+-10 % market, +-20 % labour) are not part of this task.

Assumptions the history cannot settle (the pack's replay part, `replay.example`, may override them with `defaults`): a fact
column is the valuer's field of that name (`condition` is the grade); a tool fleet item that names no site or function takes
the valuer's default; a device item with no age band, reference value or units is one unit of band 25-48m at a reference of
300. Straight-through is judged at the `limits` autonomy with the pack's approval limit and the Decide stage's confidence
threshold (the policy a standing policy is judged at), since a pack's stage autonomy is a setting of the live stage.
"""

import random
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from di.repositories.replay import Batch
from di.services.actions.registry import ActionError
from di.services.cases.decide import Decision, decide_case
from di.services.modeler.compile import FlowVersion
from di.services.modeler.gates import catalogue
from di.services.modeler.pack import Pack
from di.services.policy_standing import decide_threshold, pack_value_limit
from di.services.replay import measures

FLIPS_SHOWN = 200
DEVICE_DEFAULTS: dict[str, Any] = {"band": "25-48m", "ref": 300, "qty": 1}
ALIASES = {"condition": "grade"}  # a history column name the valuers know under another field name
Decider = Callable[..., Decision]


# ---------------------------------------------------------------- as of
def _readings(raw: Any) -> list[Mapping[str, Any]]:
    """A fact is one `{value, at}` or, when the history knows several readings of it, a list of them."""
    return [raw] if isinstance(raw, Mapping) else [x for x in raw or [] if isinstance(x, Mapping)]


def as_of_facts(item: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(the facts known at the item's `decided_at`, the leakage list). Of several readings of a fact the newest one known on
    the day is used; a reading dated after the decision, or with no date, is dropped and listed as
    `{item_id, fact, fact_at, decided_at}`."""
    decided: datetime = item["decided_at"]
    known: dict[str, Any] = {}
    leaked: list[dict[str, Any]] = []
    for name, raw in (item.get("facts") or {}).items():
        best: tuple[datetime, Any] | None = None
        for r in _readings(raw):
            at = _when(r.get("at"))
            if at is None or at > decided:
                leaked.append({"item_id": item["item_id"], "fact": name, "fact_at": at.isoformat() if at else None,
                               "decided_at": decided.isoformat()})  # fmt: skip
            elif best is None or at >= best[0]:
                best = (at, r.get("value"))
        if best is not None:
            known[name] = best[1]
    return known, leaked


def _when(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def assert_no_future(facts: Mapping[str, Any], as_of: datetime) -> None:
    """Facts as `{name: {value, at}}`: raises when one is dated after `as_of`."""
    for name, raw in facts.items():
        for r in _readings(raw):
            at = _when(r.get("at"))
            if at is not None and at > as_of:
                raise ActionError(
                    "validation_error",
                    f"Fact {name} is dated {at.isoformat()}, after the decision date {as_of.isoformat()}: "
                    "a replay uses only facts known at the time.",
                )


# ---------------------------------------------------------------- the case an item is decided as
def _coerce(v: Any) -> Any:
    if not isinstance(v, str):
        return v
    for kind in (int, float):
        try:
            return kind(v)
        except ValueError:
            continue
    return v


def case_input(item: Mapping[str, Any], facts: Mapping[str, Any], pack: Pack) -> dict[str, Any]:
    """The valuer-shaped case of a history item decided on `facts` (its as-of facts): the tool fleet's return, the device's
    lot, or the facts as they are for a pack with another valuer. Raises ActionError when the valuer refuses the facts."""
    from di.services.cases import intake  # intake imports the decider

    defaults = dict((pack.replay.example or {}).get("defaults") or {})
    raw: dict[str, Any] = {**defaults, **{ALIASES.get(k, k): _coerce(v) for k, v in facts.items()}}
    kind, iid = pack.valuer.kind, str(item["item_id"])
    if kind == "tool_fleet":
        case = intake.tool_fleet_case(iid, {"cls": item.get("cls"), **raw})
    elif kind == "device":
        case = intake.device_lot(iid, {**DEVICE_DEFAULTS, **raw})
    elif kind == "industrial":
        raise ActionError("validation_error", "A replay does not value the industrial pack: its numbers come from the engine.")
    else:
        case = {"id": iid, "cls": item.get("cls"), **raw}
    return case | ({"market": item["market"]} if item.get("market") else {})


# ---------------------------------------------------------------- what a decision asks of a person
@dataclass(frozen=True)
class Signals:
    """What one decision would ask of people at the flow's settings: it may run straight through, need an approval, raise an
    exception, or both; `guardrails` are the gates or limits behind them, each with its owner."""

    straight: bool
    approval: bool
    exception: bool
    guardrails: dict[str, tuple[str, bool, bool]] = field(default_factory=dict)  # id -> (owner, approval, exception)


def confidence_of(d: Decision) -> float | None:
    from di.services.agents.stages.valuation import confidence  # lazy: the stage modules import the pipeline

    return confidence({}, {"routes": d.routes})


def signals(d: Decision, pack: Pack) -> Signals:
    """A decision's load on people (A section 3.2): `evaluate_hold` (P9-2.4) at the `limits` autonomy gives the reasons;
    a failed gate adds the owner it goes to, an approval or exception by its type and effect."""
    import di.services.actions.decisions  # noqa: F401 - registers decision.approveByPolicy, the action a policy judges
    from di.services.actions import hold
    from di.services.actions.registry import ACTIONS

    cat = catalogue()
    failed = [g for g in getattr(d, "gates", ()) if not g.passed]
    held = getattr(d, "hold", None)
    tick = getattr(d, "ticket", None) or {}
    ticket_holds = [str(h["id"]) for h in tick.get("holds") or [] if isinstance(h, Mapping)]
    value = Decimal(str(d.net)) if d.recommendation or d.route else None
    reasons = hold.evaluate_hold(
        action=ACTIONS["decision.approveByPolicy"], autonomy="limits", confidence=confidence_of(d), value=value, bulk=1,
        open_exception=False, conflict=False, guardrail_holds=[g.gate_id for g in failed] + ticket_holds, taint=False,
        policy=hold.HoldPolicy(pack_value_limit(pack), None, decide_threshold(pack)),
    )  # fmt: skip
    rails: dict[str, tuple[str, bool, bool]] = {}
    approval = any(r.reason in ("value", "confidence") for r in reasons) or bool(ticket_holds)
    exception = bool(held)
    for g in failed:
        gd = cat.get(g.gate_id)
        appr = bool(gd and gd.type in ("Approval", "Threshold")) or g.effect.kind == "require_approval"
        exc = bool(gd and gd.type == "Data quality") or bool(g.evidence_missing) or g.effect.hold
        rails[g.gate_id] = (gd.owner if gd else "", appr, exc)
        approval, exception = approval or appr, exception or exc
    for r in reasons:
        if r.reason == "value":
            limit = next(
                (x for x in pack.guardrails if x.type == "Approval" and x.param and x.param.field == "value_limit"), None
            )
            if limit is not None:
                rails[limit.id] = (limit.owner, True, False)
    steps = bool(getattr(d, "required_steps", None))
    return Signals(not reasons and not exception and not steps, approval, exception, rails)


# ---------------------------------------------------------------- bands
def bootstrap_band(
    deltas: Sequence[float | tuple[float, float]], n: int = 1000, seed: int = 2611
) -> dict[str, tuple[float, float]]:
    """The 80 % (10th and 90th percentile) and 95 % (2.5th and 97.5th) bands of the uplift, from `n` resamples of the items
    with replacement (`random.Random(seed)`). An item is its delta, or (delta, base) when the uplift is a share of a base:
    each resample's uplift is its sum of deltas over its sum of bases (the mean delta with no bases), in percent."""
    pairs = [(x, 1.0) if isinstance(x, float | int) else (x[0], x[1]) for x in deltas]
    if not pairs:
        return {"band80": (0.0, 0.0), "band95": (0.0, 0.0)}
    rng = random.Random(seed)  # noqa: S311 - a reproducible resample, not a secret
    bases = not any(isinstance(x, float | int) for x in deltas)
    stats: list[float] = []
    for _ in range(n):
        pick = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        num = sum(p[0] for p in pick)
        den = sum(abs(p[1]) for p in pick) if bases else len(pick)
        stats.append(100 * measures.ratio(num, den) if bases else num / den)
    stats.sort()

    def at(p: float) -> float:
        k = p * (len(stats) - 1)
        lo = int(k)
        hi = min(lo + 1, len(stats) - 1)
        return round(stats[lo] + (stats[hi] - stats[lo]) * (k - lo), 2)

    return {"band80": (at(0.10), at(0.90)), "band95": (at(0.025), at(0.975))}


# ---------------------------------------------------------------- the report
class Uplift(BaseModel):
    primary: float
    band80: tuple[float, float]
    band95: tuple[float, float]
    secondary: float
    bias: float
    conservative: float
    basis: str = "modelled"  # a counterfactual value is an estimate (E section 5.1)


class Flip(BaseModel):
    item_id: str
    actual: str | None
    flow: str | None
    delta: float
    reason: str


class ReplayReport(BaseModel):
    run_id: int
    batch_id: int
    flow_ver: str  # "draft" or the version number
    n_items: int
    n_held_rows: int
    n_decided: int
    days: int
    route_mix: list[dict[str, Any]]
    straight_through_pct: float
    approvals_per_day: float
    exceptions_per_day: float
    by_guardrail: list[dict[str, Any]]
    uplift: Uplift
    agreement_pct: float
    flips: list[Flip]
    leakage: list[dict[str, Any]]
    data_quality: list[dict[str, Any]]
    method: str = (
        "Every item is decided by the one decider as of its own decision date, on the facts known then. Both sides are "
        "valued by the same valuer (estimated vs estimated); the uplift is modelled. Sensitivity runs are not part of it."
    )


def _route(d: Decision, route: str | None) -> Mapping[str, Any] | None:
    return next((r for r in d.routes if r["id"] == route), None) if route else None


def _reason(actual: str | None, flow: str | None, ar: Mapping[str, Any] | None, delta: float) -> str:
    if ar is not None and ar.get("excluded"):
        return f"actual route excluded by {ar.get('failReason') or 'a gate'}"
    if flow is None:
        return "the flow recommends no route"
    return f"the flow's route is worth ${abs(delta):,.2f} {'more' if delta >= 0 else 'less'} than {actual}"


def replay(
    batch: Batch,
    items: Sequence[Mapping[str, Any]],
    flow_ver: FlowVersion,
    *,
    pack: Pack,
    decide: Decider = decide_case,
    run_id: int = 0,
    label: str | None = None,
) -> ReplayReport:
    """Decide each ok item as of its date under `flow_ver` (the draft or a published version, resolved by the caller:
    `label` names it in the report, default its version) and measure the result. An item the valuer refuses is counted
    under `data_quality`, not decided."""
    rows: list[dict[str, Any]] = []
    flips: list[Flip] = []
    leakage: list[dict[str, Any]] = []
    dq: Counter[str] = Counter(batch.held_reasons)
    sig: list[Signals] = []
    days: list[Any] = []
    actual_routes: list[str | None] = []
    flow_routes: list[str | None] = []
    rails: dict[str, list[Any]] = defaultdict(lambda: ["", 0, 0])
    for it in items:
        facts, leaked = as_of_facts(it)
        leakage += leaked
        try:
            d = decide(case_input(it, facts, pack), pack, flow_ver, as_of=it["decided_at"])
        except ActionError as e:
            dq[f"Not decided: {e.message}"] += 1
            continue
        actual = it["actual_route"]
        ar = _route(d, actual)
        if ar is None:
            dq["Actual route not valued by the flow's pack."] += 1
            continue
        s = signals(d, pack)
        sig.append(s)
        days.append(it["decided_at"].date())
        actual_routes.append(actual)
        flow_routes.append(d.route)
        real = float(it["realised_value"] or 0)
        rows.append({"actual_net": float(ar["net"]), "flow_net": float(d.net), "realised": real, "agree": d.route == actual})
        if d.route != actual:
            delta = float(d.net) - float(ar["net"])
            flips.append(Flip(item_id=str(it["item_id"]), actual=actual, flow=d.route, delta=round(delta, 2),
                              reason=_reason(actual, d.route, ar, delta)))  # fmt: skip
        for gid, (owner, appr, exc) in s.guardrails.items():
            rails[gid][0] = owner
            rails[gid][1] += appr
            rails[gid][2] += exc
    n = len(rows)
    ndays = measures.business_days(min(days), max(days)) if days else 1
    up = measures.uplift(rows)
    band = bootstrap_band([(r["flow_net"] - r["actual_net"], r["actual_net"]) for r in rows])
    flips.sort(key=lambda f: -abs(f.delta))
    return ReplayReport(
        run_id=run_id, batch_id=batch.id, flow_ver=label or str(flow_ver.ver), n_items=len(items), n_held_rows=batch.held,
        n_decided=n, days=ndays,
        route_mix=measures.route_mix(actual_routes, flow_routes, [r.id for r in pack.routes]),
        straight_through_pct=measures.pct(sum(s.straight for s in sig), n),
        approvals_per_day=measures.per_day(sum(s.approval for s in sig), ndays),
        exceptions_per_day=measures.per_day(sum(s.exception for s in sig), ndays),
        by_guardrail=[{"guardrail": g, "owner": o, "approvals": a, "exceptions": e} for g, (o, a, e) in sorted(rails.items())],
        uplift=Uplift(**up, **band), agreement_pct=measures.pct(sum(r["agree"] for r in rows), n),
        flips=flips[:FLIPS_SHOWN], leakage=leakage, data_quality=[{"reason": r, "count": c} for r, c in dq.most_common()],
    )  # fmt: skip
