"""Who must approve a returned tool's decision (plan 9, P9-3.15, story TF-09). Pure.

    thresholds(pack) -> Thresholds                              the pack's approval limits, as the customer's overlay left them
    confidence_of(life, pack) -> float | None                   the decision's confidence from the tool's life confidence class
    route_for_approval(best, case, confidence, gates, pack) -> ApprovalRoute

The route is `person` (with the role that signs) or `policy` (the standing policy of the flow, I-11, may approve within its
limits). The reasons, in this order:

    GR-14   the repair of a refurbish path costs over the limit ("Refurbish to certified condition" lines)  -> Fleet manager
    GR-15   a tool younger than the write-off months is recycled or harvested                                -> Service operations
    gate    any gate that failed on the case                                                                -> the gate's owner
    TF-CONF the decision's confidence is under the flow's threshold                                          -> Fleet desk
    TF-KEY  the customer is a key account (contract evidence, P9-3.16)                                        -> Account manager

The first reason names the role; every reason is a hold (`ApprovalRoute.holds`, `{id, reason, owner}`, the shape of
`service_desk.approval_holds`) that the decider keeps on the case as `approvalHolds`. The hold policy (I-10) and the standing
policy (I-11, `_guardrail_holds`) already read it: a case with any waits for a person, whoever or whatever submits it. Open
exceptions and conflicts need no reason here: I-10 and I-11 read them on the case themselves.

The limits are pack data: GR-14 and GR-15 carry their value in `param` (a customer may tighten them, never loosen), the flow's
confidence threshold is the Decide stage's, and the confidence of each life class is `valuer.params.approval`.

Never does: read the database, approve anything (a person or the standing policy does) or write text from a model: it is
arithmetic on the valuer's lines, so no `AgentLoop` and no model step belong here. Implements no registry entry.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from di.services.modeler import gates as gate_catalogue
from di.services.modeler.pack import Pack
from di.services.modeler.valuers import tool_inputs
from di.services.modeler.valuers.tool_fleet import PathValue

REPAIR_LABEL = "Refurbish to certified condition"
REPAIR_GUARD, WRITE_OFF_GUARD, CONFIDENCE_HOLD = "GR-14", "GR-15", "TF-CONF"
REPAIR_ROLE, WRITE_OFF_ROLE, DESK_ROLE = "Fleet manager", "Service operations", "Fleet desk"
WRITE_OFF_PATHS = ("exit", "harvest")
DEFAULT_THRESHOLD = 0.75


@dataclass(frozen=True)
class Thresholds:
    repair_usd: float | None  # GR-14: a repair costing more waits for the fleet manager (None: the pack sets none)
    write_off_months: float | None  # GR-15: a tool younger than this is not written off without service operations
    confidence: float  # the flow's: a decision below it goes to a person
    by_life: Mapping[str, float]  # the confidence of a decision on each life class (High, Medium, Low)


@dataclass(frozen=True)
class ApprovalRoute:
    kind: Literal["policy", "person"]
    role: str | None
    reasons: list[str]
    holds: tuple[Mapping[str, str], ...] = ()


def _param(pack: Pack, guard: str) -> float | None:
    g = next((x for x in pack.guardrails if x.id == guard), None)
    return float(g.param.value) if g and g.param else None


def thresholds(pack: Pack) -> Thresholds:
    flow = next((float(s.confidence) for s in pack.stages if s.key == "decide"), DEFAULT_THRESHOLD)
    by_life = pack.valuer.params.get("approval", {}).get("confidence_by_life", {})
    return Thresholds(_param(pack, REPAIR_GUARD), _param(pack, WRITE_OFF_GUARD), flow, {k: float(v) for k, v in by_life.items()})


def confidence_of(life: Mapping[str, Any] | None, pack: Pack) -> float | None:
    """The decision's confidence from the life class of the tool's wear reading; None with no reading (the case keeps the
    valuation's own confidence)."""
    label = (life or {}).get("confidence")
    return thresholds(pack).by_life.get(str(label)) if label else None


def repair_cost(best: PathValue) -> float:
    """What the refurbish path spends on the repair: the sum of its repair lines."""
    return sum(float(x["amt"]) for x in best["lines"] if x["type"] == "c" and x["label"] == REPAIR_LABEL)


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _owner(gate_id: str) -> str:
    g = gate_catalogue.catalogue().get(gate_id)
    return g.owner if g and g.owner else DESK_ROLE


def route_for_approval(
    best: PathValue | None,
    case: Mapping[str, Any],
    confidence: float | None,
    gates: Sequence[Any],
    pack: Pack,
) -> ApprovalRoute:
    """Who must approve the case's recommended path `best` (module docstring). `case["age"]` is the tool's age in months;
    `gates` are the gate results of the decision (`GateResult`); `confidence` None skips the confidence rule."""
    t = thresholds(pack)
    holds: list[dict[str, str]] = []

    def hold(i: str, why: str, owner: str) -> None:
        holds.append({"id": i, "reason": why, "owner": owner})

    if best is not None and best["k"] == "refurb" and t.repair_usd is not None:
        cost = repair_cost(best)
        if cost > t.repair_usd:
            hold(REPAIR_GUARD, f"Repair {_money(cost)} is over {_money(t.repair_usd)} ({REPAIR_GUARD})", REPAIR_ROLE)
    age = case.get("age")
    young = t.write_off_months is not None and isinstance(age, int | float) and age < t.write_off_months
    if best is not None and best["k"] in WRITE_OFF_PATHS and young:
        hold(
            WRITE_OFF_GUARD,
            f"Write-off at {age:g} months is under {t.write_off_months:g} months ({WRITE_OFF_GUARD})",
            WRITE_OFF_ROLE,
        )
    for g in gates:
        if not g.passed:
            hold(g.gate_id, g.reason or f"Gate {g.gate_id} failed", _owner(g.gate_id))
    if confidence is not None and confidence < t.confidence:
        hold(CONFIDENCE_HOLD, f"Confidence {confidence:.2f} is under the flow's {t.confidence:.2f}", DESK_ROLE)
    key = pack.valuer.params.get("approval", {}).get("key_account")
    if key:  # P9-3.16 (TF-12), after the gates: it adds the account manager, never changes the route ranking
        is_key, customer = tool_inputs.key_account(case)
        if is_key:
            hold(key["id"], f"Key account {customer or 'customer'}: the account manager reviews the return", key["role"])
    if not holds:
        return ApprovalRoute("policy", None, [])
    return ApprovalRoute("person", holds[0]["owner"], [h["reason"] for h in holds], tuple(holds))
