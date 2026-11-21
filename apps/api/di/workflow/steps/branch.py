# ruff: noqa: ARG001 - every step has the STEPS signature (records, cfg, ctx); not every step needs ctx
"""Branch step (plan 6, task C4): sends records down one of two paths by a condition."""

from di.workflow.steps.core import Rec, StepCtx, StepResult, clone, condition, opt

# the settings each step reads (keys of di/workflow/blocks.py)
KEYS = {"x_branch": {"condition": "condition"}}


def x_branch(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Records that meet the condition go on (`out`, also side.then); the rest take the else path (side.else).
    An empty condition sends everything down the then path."""
    test = condition(opt(cfg, KEYS["x_branch"]["condition"], []))
    then: list[Rec] = []
    other: list[Rec] = []
    for r in recs:
        (then if test(r) else other).append(clone(r))
    return StepResult(then, [], {"then": then, "else": other})


STEPS = {"x_branch": x_branch}
