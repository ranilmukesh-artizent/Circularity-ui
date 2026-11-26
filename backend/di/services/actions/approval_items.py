"""Closes the approval item of a decision over an approval limit when a person decides it (plan 9, P9-9.11; registry entry I-20).

A used car whose recon estimate is over AP-UC-RECON waits for the used-car manager in My work (`di.services.cases.approval_hold`
opens the item). `decision.approve`, `decision.override` and `decision.decline` are a person's (`forbidden.py`); after one of
them the item is done, with who did it. Never does: approve, override or decline anything.
"""

from typing import Any

from di.services.actions.pipeline import CallContext, after
from di.services.cases import approval_hold


@after("decision.approve")
def _approved(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001 - hooks take (input, output, ctx)
    approval_hold.close_for(ctx.session, str(i["case_id"]), f"Approved by {ctx.actor.id}", ctx.actor.id)


@after("decision.override")
def _overridden(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001
    approval_hold.close_for(ctx.session, str(i["case_id"]), f"Overridden by {ctx.actor.id}", ctx.actor.id)


@after("decision.decline")
def _declined(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001
    approval_hold.close_for(ctx.session, str(i["case_id"]), f"Declined by {ctx.actor.id}", ctx.actor.id)
