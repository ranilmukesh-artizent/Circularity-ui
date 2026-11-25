"""The hold policy (plan 9, P9-2.4; registry entry I-10): when an agent's write waits for a person, and why.

    evaluate_hold(...) -> [Hold]     pure: the typed reasons a call must be held for a person (none: it may run). The
                                     replay (P9-7.2) and the standing policy (P9-2.5) reuse it, so a call is judged the
                                     same way live, in a simulation and in a back-test.
    policy_of(pack, stage) -> HoldPolicy   the value limit, bulk limit and confidence threshold of a stage
    hold_check(a, i, ctx) -> [Hold]  the pipeline's step 9b: builds the arguments from the call context (the stage, the
                                     taint of the run, the case's open exceptions and conflicts, the agent's registry row)

Reasons (`HoldReason`): `risk` (a guardrail needs an owner, more items than the bulk limit, an open exception or a conflict
on the case), `value` (above the stage's limit), `confidence` (below the stage's threshold), `taint` (the run read
untrusted content), `destructive` (a delete, discard or revert), `autonomy` (the stage is set to Recommend only, or the
agent may only propose), `model_concern` (a stage's model raised a concern with `hold`, P9-2.18: it holds every later write
of the run at every level; the model adds caution and never clears a hold, and a person's accept of the proposal is the
only release).

Which reasons apply depends on the effective autonomy, the lower of the stage's level and the Access ceiling (Admin's
autonomy table, `di.services.agents.limits`):
    every level   destructive, taint, model concerns, each guardrail hold (reason `risk`)
    recommend     also autonomy: nothing runs, the agent only recommends
    limits        also value above the limit, risk (bulk, open exception, conflict), confidence below the threshold
    alone         also confidence below the threshold
Destructive and taint hold at every level because the research (F section 8b) puts them in the "always, at every level"
column beside the forbidden list (`di.services.agents.forbidden`), which is refused, never held. HELD_FOR_PERSON (P9-0.4) is
folded into `destructive`.

Order (R20): gates and guardrails are decided before valuation by `decide_case`; this policy runs last, on the write. A
confidence the case has no value for (None) never holds: a case with no confidence is not held for it (an industrial case has
no `grade` record, which the condition stage reads as 0.0; the runtime passes None for it, see `runtime.stage_confidence`).
Never does: run the action, approve anything (rule 10: agents only read or hold for a person) or touch the journal.
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import text

from di.core import state
from di.services.actions.registry import ActionDef
from di.services.agents import limits, registry
from di.services.agents.forbidden import held_for_person
from di.services.agents.stage_context import Autonomy

if TYPE_CHECKING:
    from di.services.actions.pipeline import CallContext
    from di.services.agents.chain import StageDef
    from di.services.modeler.pack import Pack

__all__ = ["Hold", "HoldPolicy", "HoldReason", "effective_autonomy", "evaluate_hold", "hold_check", "policy_of", "reasons_json"]

HoldReason = Literal["risk", "value", "confidence", "taint", "destructive", "autonomy", "model_concern"]
RANK: dict[Autonomy, int] = {"recommend": 0, "limits": 1, "alone": 2}
# the Access level of Admin's autonomy table, as the autonomy it allows (`off` is refused earlier, in limits.check)
CEILING: dict[str, Autonomy] = {"off": "recommend", "suggest": "recommend", "prepare": "limits", "act": "alone"}


@dataclass(frozen=True)
class Hold:
    reason: HoldReason
    detail: str


@dataclass(frozen=True)
class HoldPolicy:
    value_limit: Decimal | None
    bulk_limit: int | None
    threshold: float


def policy_of(pack: "Pack", stage: "StageDef") -> HoldPolicy:  # noqa: ARG001 - a pack has no hold parameters of its own yet
    """The stage's limits and threshold (the stage took its threshold from the pack, `chain.stage_defs`; the limits are
    None, no limit, until a pack or overlay sets them)."""
    return HoldPolicy(value_limit=stage.value_limit, bulk_limit=stage.bulk_limit, threshold=stage.threshold)


def effective_autonomy(stage: Autonomy, ceiling: Autonomy | None) -> Autonomy:
    """The lower of the stage's level and the Access ceiling (None: the action has no Access type, no ceiling)."""
    return stage if ceiling is None or RANK[stage] <= RANK[ceiling] else ceiling


def _money(v: Decimal) -> str:
    return f"${v:,.0f}" if v == v.to_integral_value() else f"${v:,.2f}"


def _guardrail(g: str) -> str:
    """A guardrail hold is its name, or "<name> needs <owner>" when it names the owner."""
    return f"Guardrail {g}" if " needs " in g else f"Guardrail {g} needs a person"


def evaluate_hold(
    *,
    action: ActionDef,
    autonomy: Autonomy,
    confidence: float | None,
    value: Decimal | None,
    bulk: int,
    open_exception: bool,
    conflict: bool,
    guardrail_holds: list[str],
    taint: bool,
    policy: HoldPolicy,
    stage_name: str = "The stage",
    model_concerns: list[str] | None = None,
) -> list[Hold]:
    """The reasons to hold `action` for a person at this autonomy, in the order they are decided (empty: it may run)."""
    out: list[Hold] = []
    if action.destructive:
        out.append(Hold("destructive", f"{action.title} cannot be undone: a person does it."))
    if taint:
        out.append(Hold("taint", "The run read untrusted content, so a person confirms every write."))
    out += [Hold("model_concern", c) for c in model_concerns or []]  # a stage's model raised it: it only ever adds caution
    out += [Hold("risk", _guardrail(g)) for g in guardrail_holds]
    if autonomy == "recommend":
        out.append(Hold("autonomy", f"{stage_name} is set to Recommend only"))
        return out
    if autonomy == "limits":
        if value is not None and policy.value_limit is not None and value > policy.value_limit:
            out.append(Hold("value", f"Value {_money(value)} is above the {_money(policy.value_limit)} limit"))
        if policy.bulk_limit is not None and bulk > policy.bulk_limit:
            out.append(Hold("risk", f"{bulk} items is above the limit of {policy.bulk_limit}"))
        if open_exception:
            out.append(Hold("risk", "The case has an open exception"))
        if conflict:
            out.append(Hold("risk", "The sources disagree on the case"))
    if confidence is not None and confidence < policy.threshold:
        out.append(Hold("confidence", f"Confidence {confidence:.2f} is below {policy.threshold:.2f}"))
    return out


def _bulk(i: dict[str, Any]) -> int:
    return max((len(v) for v in i.values() if isinstance(v, list)), default=0)


def _ceiling(a: ActionDef, ctx: "CallContext") -> Autonomy | None:
    t = limits.TYPE_OF.get(a.id)
    if t is None:
        return None
    level = limits.auto_level(state.get(ctx.session, "access_settings", "autonomy") or {}, ctx.actor.role, t)
    return CEILING[level]


def _case_state(a: ActionDef, i: dict[str, Any], ctx: "CallContext") -> tuple[bool, bool]:
    """Whether the case the call is about has an open exception, and whether its asset has an open conflict."""
    if a.scope != "case" or not i.get("case_id"):
        return False, False
    from di.services.cases import store  # the case store imports the pipeline's callers

    case_id = str(i["case_id"])
    s = ctx.session
    exception = s.execute(
        text("SELECT 1 FROM work_item WHERE case_id = :c AND kind = 'exception' AND status = 'open' LIMIT 1"), {"c": case_id}
    ).first()
    case = store.get(s, case_id)
    asset = (case or {}).get("assetId")
    conflict = (
        asset
        and s.execute(
            text("SELECT 1 FROM conflict WHERE key = :k AND status IN ('open', 'escalated') LIMIT 1"), {"k": asset}
        ).first()
    )
    return exception is not None, bool(conflict)


def hold_check(a: ActionDef, i: dict[str, Any], ctx: "CallContext") -> list[Hold]:
    """Step 9b: the reasons to hold an agent-prepared write for a person. Only an agent's own, unconfirmed write is judged:
    a person's call, a read and a call a person confirmed (proposal.accept) are never held."""
    if not ctx.preparer or not a.changes_state or ctx.confirmed:
        return []
    st = ctx.stage
    if st is None:  # an agent outside the chain: no stage to read, only what holds at every level
        autonomy: Autonomy = "alone"
        exception = conflict = False
        policy = HoldPolicy(None, None, 0.0)
        guardrails: list[str] = []
        concerns: list[str] = []
        confidence = value = None
        name = "The stage"
    else:
        autonomy = effective_autonomy(st.autonomy, _ceiling(a, ctx))
        exception, conflict = _case_state(a, i, ctx) if autonomy == "limits" else (False, False)
        policy = HoldPolicy(st.value_limit, st.bulk_limit, st.threshold)
        guardrails, confidence, value, name = st.guardrail_holds, st.confidence, st.value, st.stage.replace("_", " ").capitalize()
        concerns = st.model_concerns
    holds = evaluate_hold(
        action=replace(a, destructive=True) if held_for_person(a.id) else a,  # P9-0.4's list is folded into `destructive`
        autonomy=autonomy,
        confidence=confidence,
        value=value,
        bulk=_bulk(i),
        open_exception=exception,
        conflict=conflict,
        guardrail_holds=guardrails,
        taint=ctx.taint,
        policy=policy,
        stage_name=name,
        model_concerns=concerns,
    )
    agent = registry.get(ctx.session, ctx.preparer)
    if agent is not None and agent.autonomy == "propose":
        holds.append(Hold("autonomy", f"{agent.name} may only propose"))
    return holds


def reasons_json(holds: list[Hold]) -> list[dict[str, str]]:
    """The holds as the answer and the stored column carry them: [{reason, detail}]."""
    return [{"reason": h.reason, "detail": h.detail} for h in holds]
