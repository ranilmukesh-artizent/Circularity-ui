"""Standing policy rules (plan 9, P9-2.5; registry entry I-11; story X-05): what a person-owned approval policy may cover.

A standing policy approves a submitted decision that is below every threshold (value, confidence, route, class, market) with no
hold reason, open exception, conflict or fraud hold. A person owns it and a different person approved it (maker-checker); the
policy approves, never an agent (AGENTS.md rule 10). The actions are `di.services.actions.standing_policy`.

Owns: `StandingRules`, `parse_rules`, `rules_json`, `rules_problem` (a policy cannot be wider than the pack, the owner or
the flow allow), `covers` (does it approve this decision), `pack_value_limit` and `decide_threshold` (what the pack says).
Never does: read a case or a session, approve anything or write. Pure.

The pack's hold value limit is the `param` of an Approval guardrail whose `field` is `value_limit` (GR-05 and GR-D6 are Approval
guardrails "by threshold" in a Recover flow, decision-log row of P9-0.1); a pack without one has no limit, as the demo's
packs have none. Needs review by Kinective's Legal team before a customer relies on it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from di.services.actions.hold import Hold
    from di.services.modeler.pack import Pack

__all__ = [
    "DEFAULT_THRESHOLD",
    "StandingRules",
    "covers",
    "decide_threshold",
    "pack_value_limit",
    "parse_rules",
    "rules_json",
    "rules_problem",
]

DEFAULT_THRESHOLD = 0.75  # the chain's default (di.services.agents.chain), for a pack without a decide stage
LIMIT_FIELD = "value_limit"


@dataclass(frozen=True)
class StandingRules:
    max_value: Decimal
    min_confidence: float
    routes: tuple[str, ...] | None = None  # None: any route
    classes: tuple[str, ...] | None = None  # None: any asset class
    markets: tuple[str, ...] | None = None  # None: any market


def _money(v: Decimal | float) -> str:
    d = Decimal(str(v))
    return f"${d:,.0f}" if d == d.to_integral_value() else f"${d:,.2f}"


def _names(raw: Any, key: str) -> tuple[str, ...] | None | str:
    if raw is None:
        return None
    if not isinstance(raw, list) or not all(isinstance(x, str) and x.strip() for x in raw):
        return f'"{key}" is a list of names, or left out for any.'
    return tuple(dict.fromkeys(x.strip() for x in raw)) or None


def parse_rules(raw: Any) -> StandingRules | str:
    """The rules as saved ({max_value, min_confidence, routes?, classes?, markets?}), or the sentence that says what is wrong."""
    if not isinstance(raw, Mapping):
        return "The rules are an object: max_value, min_confidence and, optionally, routes, classes and markets."
    extra = set(raw) - {"max_value", "min_confidence", "routes", "classes", "markets"}
    if extra:
        return f'The rules have no "{sorted(extra)[0]}".'
    mv, mc = raw.get("max_value"), raw.get("min_confidence")
    if isinstance(mv, bool) or not isinstance(mv, int | float | str):
        return '"max_value" is a number of dollars.'
    try:
        value = Decimal(str(mv))
    except InvalidOperation:
        return '"max_value" is a number of dollars.'
    if not value.is_finite() or value <= 0:
        return '"max_value" is more than $0.'
    if isinstance(mc, bool) or not isinstance(mc, int | float) or not 0 <= mc <= 1:
        return '"min_confidence" is a number from 0 to 1.'
    lists = [_names(raw.get(k), k) for k in ("routes", "classes", "markets")]
    for x in lists:
        if isinstance(x, str):
            return x
    routes, classes, markets = (x if isinstance(x, tuple) or x is None else None for x in lists)
    return StandingRules(value, float(mc), routes, classes, markets)


def rules_json(r: StandingRules) -> dict[str, Any]:
    """The rules as stored (JSON-safe: the amount is a number)."""
    v = float(r.max_value)
    return {
        "max_value": int(v) if v == int(v) else v,
        "min_confidence": r.min_confidence,
        "routes": list(r.routes) if r.routes else None,
        "classes": list(r.classes) if r.classes else None,
        "markets": list(r.markets) if r.markets else None,
    }


def pack_value_limit(pack: "Pack") -> Decimal | None:
    """The most a decision under this pack may be worth before a person must approve it: the smallest `value_limit` an Approval
    guardrail carries (None: the pack sets none)."""
    limits = [
        Decimal(str(g.param.value)) for g in pack.guardrails if g.type == "Approval" and g.param and g.param.field == LIMIT_FIELD
    ]
    return min(limits) if limits else None


def decide_threshold(pack: "Pack") -> float:
    """The flow's confidence threshold at the Decide stage."""
    return next((float(s.confidence) for s in pack.stages if s.key == "decide"), DEFAULT_THRESHOLD)


def rules_problem(rules: StandingRules, pack: "Pack", owner_limit: Decimal) -> str | None:
    """Why these rules are wider than allowed, or None. The pack's limit is checked first, then the owner's, then the flow's."""
    limit = pack_value_limit(pack)
    if limit is not None and rules.max_value > limit:
        return f"The policy cannot approve above the pack's {_money(limit)} threshold."
    if owner_limit.is_finite() and rules.max_value > owner_limit:
        return f"The owner may approve up to {_money(owner_limit)}."
    t = decide_threshold(pack)
    if rules.min_confidence < t:
        return f"The policy needs at least the flow's {t:.2f} confidence."
    return None


def covers(
    rules: StandingRules,
    *,
    value: Decimal,
    confidence: float | None,
    route: str | None,
    cls: str | None,
    market: str | None,
    holds: "list[Hold]",
    open_exception: bool,
    conflict: bool,
    fraud_hold: bool,
) -> bool:
    """Does the policy approve this decision? Every rule holds, and there is no hold reason, exception, conflict or fraud hold.
    A fact the case lacks (no confidence, no route, no class or market where the rules name some) never passes."""
    if holds or open_exception or conflict or fraud_hold:
        return False
    if abs(value) > rules.max_value:
        return False
    if confidence is None or confidence < rules.min_confidence:
        return False
    for allowed, fact in ((rules.routes, route), (rules.classes, cls), (rules.markets, market)):
        if allowed is not None and fact not in allowed:
            return False
    return True
