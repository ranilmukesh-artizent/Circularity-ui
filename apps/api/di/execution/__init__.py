"""Execution detail and cost trace (B13), ported from the demo (index.html, "Execution detail and cost trace";
docs/PLAN_EXECUTION_DETAIL_AND_COST_TRACE.md): where the unit goes and how, who acts in which system, which document
each step creates, the time limit on each step, and the cost lines behind every term.

Pure functions of the case: no random draws, so seeded data never moves. Times are epoch milliseconds.

- steps: EX_STEP, STEP_TPL, ex_kinds, steps_for, ex_doc_ref, ack_ref, ref_label, ho_kind, ex_ev
- lanes: LOCS, RATE_CARD, lane_cost, ex_stage, ex_move_raw, ex_move_legs_for, ex_kg
- prep: ex_prep_parts, ex_svc, asset_health, as_sc
- move: ex_move
- trace: ex_trace, line_actuals, ex_actual
- plan: ex_plan, ex_what_if, ex_delivered, value_order, ack_note
"""

from di.execution.lanes import LOCS, RATE_CARD, ex_kg, ex_move_legs_for, ex_move_raw, ex_stage, lane_cost, loc_name
from di.execution.move import ex_move
from di.execution.plan import ack_note, ex_delivered, ex_plan, ex_what_if, value_order
from di.execution.prep import as_sc, asset_health, ex_inr, ex_prep_parts, ex_svc
from di.execution.steps import (
    EX_STEP,
    STEP_TPL,
    ack_ref,
    approval_ref,
    ex_doc_num,
    ex_doc_ref,
    ex_ev,
    ex_kinds,
    ho_kind,
    ref_label,
    steps_for,
)
from di.execution.trace import ex_actual, ex_trace, line_actuals

__all__ = [
    "EX_STEP", "LOCS", "RATE_CARD", "STEP_TPL", "ack_note", "ack_ref", "approval_ref", "as_sc", "asset_health",
    "ex_actual", "ex_delivered", "ex_doc_num", "ex_doc_ref", "ex_ev", "ex_inr", "ex_kg", "ex_kinds", "ex_move",
    "ex_move_legs_for", "ex_move_raw", "ex_plan", "ex_prep_parts", "ex_stage", "ex_svc", "ex_trace", "ex_what_if",
    "ho_kind", "lane_cost", "line_actuals", "loc_name", "ref_label", "steps_for", "value_order",
]  # fmt: skip
