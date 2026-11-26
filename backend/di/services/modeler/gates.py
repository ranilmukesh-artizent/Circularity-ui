"""The gate catalogue and its evaluation (plan 9, P9-1.2; research B section 5). Implements registry entry I-2:
`GateDef`, `GateEffect`, `GateResult`, `evaluate_gates`, the catalogue `packs/gates.catalogue.json` (42 gates).

A gate is data: a type (Compliance, Data quality, ...), a stage, a trigger (which route classes, which case facts), the
evidence it needs and its effect (block routes, require a step, require approval, block the close). A pack lists the
gates it uses in its `gates` part (`GateRef`, with `params`); the catalogue is shared.

Owns: `GateDef` and its parts, `catalogue()`, `pack_gates`, `GateEffect`, `GateResult`, `evaluate_gates` (pure, in
catalogue order), `apply_gate_results` (fails the blocked routes at the policy gate, before the business rules) and
the `CHECKS` table for a gate that needs logic of its own.
Never does: read a session, the clock or the canonical store (the case carries its evidence records; `gate_hold.py` in
`di.services.cases` attaches them and holds a case), or write a case. `require_approval` is enforced by the hold policy
(P9-2.4) and `close_block` by the close stage (Phase 13); here they are evaluated and shown only. `disclose` (P9-9.8) blocks
nothing: its texts go on every route's `disclosures` (`apply_disclosures`).

Facts of a trigger resolve as dotted paths on the case (`vehicle.odometer_exempt` reads `case["vehicle"]["odometer_exempt"]`);
`class.<attr>` reads the attribute of the pack class of `case["cls"]`. A fact the case lacks fails every operator
except `ne` and `exists` with the value false.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from di.services.engine.routes import POLICY, Route, fail
from di.services.modeler.evidence import evidence_of, label_of
from di.services.modeler.pack import PACKS_DIR, Pack, RouteClass
from di.services.modeler.stages import GuardType, StageKey

GateKind = Literal["block", "require_step", "require_approval", "close_block", "disclose"]
Op = Literal["eq", "ne", "in", "gte", "lte", "exists"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Cond(_M):
    fact: str
    op: Op
    value: Any = None


class GateTrigger(_M):
    routes: list[RouteClass] | Literal["any"]
    when: list[Cond] = Field(default_factory=list)


class OnFail(_M):
    step: str


class GateEffectDef(_M):
    """What a gate does when its evidence is missing or failed (the catalogue's `effect`)."""

    kind: GateKind
    hold_until_evidence: bool = False
    step: str | None = None
    on_fail: OnFail | None = None


class GateDef(_M):
    id: str
    name: str
    type: GuardType
    stage: StageKey
    packs: list[str]
    trigger: GateTrigger
    evidence: list[str]
    effect: GateEffectDef
    owner: str
    citation: str
    legal_review: Literal["pending", "reviewed"]
    params: dict[str, Any] = Field(default_factory=dict)

    @property
    def locked(self) -> bool:
        """A compliance gate is locked by the pack, as is a gate whose pack ref says `locked` (GR-13): a customer may tighten it,
        never weaken it (B section 5.1)."""
        return self.type == "Compliance" or bool(self.params.get("locked"))


@dataclass(frozen=True)
class GateEffect:
    """What a gate does to a case now: its kind, the route ids it affects, whether it holds the case until evidence
    arrives, and the step it requires."""

    kind: GateKind
    routes: tuple[str, ...]
    hold: bool
    step: str | None


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    passed: bool
    effect: GateEffect
    evidence_missing: tuple[str, ...]
    reason: str
    disclosures: tuple[str, ...] = ()  # texts every route of the decision carries (effect `disclose`, `apply_disclosures`)
    route_reasons: tuple[tuple[str, str], ...] = ()  # (route id, reason) where a route fails with its own text (P9-10.7)
    route_notes: tuple[tuple[str, str], ...] = ()  # (route id, note) where a route is not affected and says why (P9-10.8)


Check = Callable[[Mapping[str, Any], Pack, GateDef], GateResult | None]
# A gate that needs logic the data cannot say registers a check here (modules in gate_checks/<domain>.py); a check
# returns the gate's result, or None to leave it to the data.
CHECKS: dict[str, Check] = {}


@cache
def catalogue() -> dict[str, GateDef]:
    """The 42 gates of `packs/gates.catalogue.json`, by id, in file order. Cached: treat as read-only."""
    rows = json.loads((PACKS_DIR / "gates.catalogue.json").read_text(encoding="utf-8"))
    return {g.id: g for g in (GateDef.model_validate(r) for r in rows)}


def pack_gates(pack: Pack) -> list[GateDef]:
    """The pack's active gates in catalogue order, each with the ref's `params` merged over its own."""
    refs = {r.id: r for r in pack.gates if r.active}
    unknown = sorted(set(refs) - set(catalogue()))
    if unknown:
        raise ValueError(f"Pack {pack.key} v{pack.version}: gates not in the catalogue: {', '.join(unknown)}")
    return [g.model_copy(update={"params": {**g.params, **refs[g.id].params}}) for g in catalogue().values() if g.id in refs]


# ---------------------------------------------------------------- triggers
def gate_routes(gate: GateDef, pack: Pack) -> tuple[str, ...]:
    """The pack's route ids the gate affects: the routes of the trigger's classes, or every route for "any"."""
    want = gate.trigger.routes
    return tuple(r.id for r in pack.routes if want == "any" or set(r.classes) & set(want))


def _fact(case: Mapping[str, Any], pack: Pack, path: str) -> Any:
    head, _, rest = path.partition(".")
    if head == "class" and rest:
        cls = next((c for c in pack.classes if c.id == case.get("cls")), None)
        return getattr(cls.attrs, rest, None) if cls else None
    cur: Any = case
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _holds(c: Cond, v: Any) -> bool:
    if c.op == "exists":
        return (v is not None) is (c.value is not False)
    if c.op == "ne":
        return v != c.value
    if v is None:
        return False
    try:
        if c.op == "eq":
            return bool(v == c.value)
        if c.op == "in":
            return v in c.value
        return bool(v >= c.value) if c.op == "gte" else bool(v <= c.value)
    except TypeError:
        return False


def conds_hold(conds: Sequence[Mapping[str, Any]], case: Mapping[str, Any], pack: Pack) -> bool:
    """Every condition (`{fact, op, value}`, as a diversion keeps them) holds for the case: the same reading a gate's trigger
    does, for a check that needs to know which customer diversions apply to the case (P9-11.12)."""
    return all(_holds(c, _fact(case, pack, c.fact)) for c in (Cond.model_validate(x) for x in conds))


def triggered(gate: GateDef, case: Mapping[str, Any], pack: Pack) -> bool:
    """The gate applies to the case: the pack has a route of the trigger's classes and every condition holds. A pack may narrow
    a gate with the conditions of its ref's `params.when` (P9-6.7: the wipe gate of the device pack applies to a received
    device only); they are `Cond`s like the trigger's."""
    narrow = [Cond.model_validate(c) for c in gate.params.get("when") or []]
    return bool(gate_routes(gate, pack)) and all(_holds(c, _fact(case, pack, c.fact)) for c in [*gate.trigger.when, *narrow])


# ---------------------------------------------------------------- evaluation
def _join(types: Sequence[str]) -> str:
    return ", ".join(label_of(t) for t in types)


def _evaluate(gate: GateDef, case: Mapping[str, Any], pack: Pack, as_of: datetime | None) -> GateResult:
    if (check := CHECKS.get(gate.id)) is not None and (own := check(case, pack, gate)) is not None:
        return own
    have = {t: evidence_of(case, t, as_of) for t in gate.evidence}
    missing = tuple(t for t, e in have.items() if e is None)
    failed = [t for t, e in have.items() if e is not None and e.result == "fail"]
    eff = gate.effect

    def effect(step: str | None) -> GateEffect:
        return GateEffect(eff.kind, gate_routes(gate, pack), eff.hold_until_evidence, step)

    if failed:
        step = eff.on_fail.step if eff.on_fail else eff.step
        return GateResult(gate.id, False, effect(step), missing, f"{_join(failed)} failed verification")
    if missing:
        return GateResult(gate.id, False, effect(eff.step), missing, f"{_join(missing)} missing")
    return GateResult(gate.id, True, effect(None), (), f"{_join(gate.evidence)} on file" if gate.evidence else "Nothing required")


def evaluate_gates(case: Mapping[str, Any], pack: Pack, as_of: datetime | None = None) -> list[GateResult]:
    """The result of every gate of the pack that applies to the case, in catalogue order. A gate whose trigger does not
    match is not listed. Evidence is read as at `as_of` (`evidence.evidence_of`). Pure."""
    return [_evaluate(g, case, pack, as_of) for g in pack_gates(pack) if triggered(g, case, pack)]


def apply_gate_results(routes: list[Route], results: Sequence[GateResult]) -> None:
    """Each failed `block` result fails its routes at the policy gate with "<gate name>: <reason>" (a route that
    already failed keeps its first reason; `route_reasons` give a route its own reason). Run it before the business rules and
    before ranking (R20)."""
    for res in results:
        if res.passed or res.effect.kind != "block":
            continue
        for r in routes:
            base = r["id"].split(":", 1)[0]  # `retail:<lot>` is the retail channel (P9-9.10)
            if base in res.effect.routes and not r["excluded"]:
                reasons = dict(res.route_reasons)
                fail(r, POLICY, f"{catalogue()[res.gate_id].name}: {reasons.get(r['id'], reasons.get(base, res.reason))}")


def apply_disclosures(routes: list[Route], results: Sequence[GateResult]) -> None:
    """Every text a result of effect `disclose` (or a result that blocks and also discloses) carries is added to the
    `disclosures` list of every route, in gate order, once each (P9-9.8: a title brand is disclosed on every route). A
    decision with no disclosure leaves the routes as they are. A disclosure never excludes or ranks a route."""
    texts = list(dict.fromkeys(t for res in results for t in res.disclosures))
    if texts:
        for r in routes:
            r["disclosures"] = list(texts)


# a gate whose logic lives in a valuer module registers its check on import (`CHECKS`); that module imports this one
from di.services.modeler.gate_checks import medical as _medical  # noqa: E402,F401
from di.services.modeler.gate_checks import network as _network  # noqa: E402,F401
from di.services.modeler.gate_checks import vehicle as _vehicle  # noqa: E402,F401
from di.services.modeler.valuers import fleet_evidence as _fleet_evidence  # noqa: E402,F401
