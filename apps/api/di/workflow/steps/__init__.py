"""Workflow step implementations (plan 6, task C4): one function per transform block, keyed by the block's ref.

    STEPS[ref](records, cfg, ctx) -> StepResult(out, rejected, side)

`cfg` is the node's settings with the defaults filled in (`di.workflow.blocks.node_cfg`); each module keeps the keys
it reads in one `KEYS` mapping at its top. The shapes and the expression language are in `core`. Steps never change
the records they are given, and with `ctx.dry` they write nothing.

    ingest     x_gw, x_evt, x_file
    quality    x_val, x_late, x_ident
    transform  x_fx, x_utc, x_units, x_lookup, x_filter, x_expr, x_agg, x_join, x_enrich
    branch     x_branch
    flow       x_wait, x_loop, x_call, x_err, x_audit, x_pub
"""

from di.workflow.steps import branch, flow, ingest, quality, transform
from di.workflow.steps.core import (
    Expr,
    ExprError,
    Rec,
    Reject,
    Step,
    StepCtx,
    StepError,
    StepResult,
    compile_expr,
    condition,
    rule_ok,
)

STEPS: dict[str, Step] = {**ingest.STEPS, **quality.STEPS, **transform.STEPS, **branch.STEPS, **flow.STEPS}

__all__ = [
    "STEPS", "Expr", "ExprError", "Rec", "Reject", "Step", "StepCtx", "StepError", "StepResult", "compile_expr",
    "condition", "rule_ok",
]  # fmt: skip
