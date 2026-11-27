"""Closes the approval item of a decision over an approval limit when a person decides it (plan 9, P9-9.11; registry entry I-20).

A used car whose recon estimate is over AP-UC-RECON waits for the used-car manager in My work (`di.services.cases.approval_hold`
opens the item). `decision.approve`, `decision.override` and `decision.decline` are a person's (`forbidden.py`); after one of
them the item is done, with who did it. A contract refresh submitted with a priced proposal closes its `refresh_late` item.
Never does: approve, override or decline anything.
"""

from typing import Any

from di.services.actions.pipeline import CallContext, after
from di.services.cases import approval_hold, intake, refresh_intake, store


@after("decision.approve")
def _approved(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001 - hooks take (input, output, ctx)
    approval_hold.close_for(ctx.session, str(i["case_id"]), f"Approved by {ctx.actor.id}", ctx.actor.id)


@after("decision.override")
def _overridden(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001
    approval_hold.close_for(ctx.session, str(i["case_id"]), f"Overridden by {ctx.actor.id}", ctx.actor.id)


@after("decision.decline")
def _declined(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001
    approval_hold.close_for(ctx.session, str(i["case_id"]), f"Declined by {ctx.actor.id}", ctx.actor.id)


@after("decision.submit")
def _submitted(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001
    """A contract refresh submitted with a priced proposal is in time: its `refresh_late` item is done (review M3)."""
    c = store.get(ctx.session, str(i["case_id"]))
    if c is not None and intake.is_refresh(c) and c.get("submitted") and not c.get("refreshBlock"):
        refresh_intake.close_proposal_item(ctx.session, c["id"], ctx.actor.id)
