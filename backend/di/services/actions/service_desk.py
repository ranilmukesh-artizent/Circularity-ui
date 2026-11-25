"""Service desk actions (plan 9, P9-4.5, story SD-08; registry entry I-14 measured, not changed).

    serviceDesk.computeAccuracy   act  {}   replay the estimate on the held-out repairs of every org unit and store today's
                                            figures per tool class (`di.services.service_desk.accuracy`)

It only measures: no model, table or bar changes, so it needs no maker-checker and an agent may run it (not in
FORBIDDEN_ACTIONS). Permission `manageMarketTables`. The worker runs the same job once a simulated day (`serviceDesk.accuracy`).
Changing the bar is a guardrail change (the GR-S1 parameters, I-4), not an action here.
"""

from typing import Any

from di.core import clock
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, implement
from di.services.service_desk import accuracy

ACTIONS.setdefault(
    "serviceDesk.computeAccuracy",
    ActionDef(
        id="serviceDesk.computeAccuracy", title="Compute repair estimate accuracy", verb="compute the repair estimate accuracy",
        desc="Replay the repair estimate on the repairs closed in the last weeks and store its accuracy per tool class. "
             "Changes no model or price.",
        risk="act", perm="manageMarketTables", scope="none", input={},
    ),
)  # fmt: skip


@implement("serviceDesk.computeAccuracy")
def compute_accuracy(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:  # noqa: ARG001 - takes no input
    rows = accuracy.compute(ctx.session, clock.now().date())
    below = sum(1 for r in rows if not r.instant)
    return {
        "families": len(rows), "below": below, "as_of": clock.now().date().isoformat(),
        "log": f"Repair estimate accuracy computed: {len(rows)} families, {below} below the bar",
    }  # fmt: skip
