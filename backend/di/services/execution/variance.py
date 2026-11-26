"""The variance check of a confirmed tool-fleet outcome (plan 9, P9-3.17, story TF-10; registry entry I-20).

    tolerance(predicted, params=None) -> float      10% of the predicted net or $50, whichever is larger (pack data)
    check(s, c, actual, predicted) -> int | None    a work item for Finance when the realised net is off by more than that

`outcome.confirm` (di.services.actions.execution) calls `check` for a tool-fleet case once Finance has confirmed the actuals:
the realised net (`line_actuals`, the cost lines Finance posted) against the chosen route's predicted net. Above the tolerance
(either way) one item `variance_check` is opened for Finance through I-20 (`process.open_item`, the pack's SLA for exceptions);
a second confirmation never opens a second item while one is open. The case is closed already (the outcome is confirmed after
the last step), so the check changes nothing about the case itself.

The tolerance is the pack's `valuer.params.follow_through.variance_tolerance` (`pct`, `usd`; the customer layer may change it).
No model step (R16): it is arithmetic and a fixed sentence. Never does: confirm, approve or change a figure.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

EXCEPTION = "variance_check"
DEFAULT_TOLERANCE = {"pct": 10.0, "usd": 50.0}


def _params(pack: Any = None) -> dict[str, float]:
    if pack is None:
        from di.services.modeler.pack import load_pack  # lazy: the pack loader imports the valuers

        pack = load_pack("tool_fleet")
    got = ((pack.valuer.params or {}).get("follow_through") or {}).get("variance_tolerance") or {}
    return DEFAULT_TOLERANCE | {k: float(v) for k, v in got.items()}


def tolerance(predicted: float, pack: Any = None) -> float:
    """What a realised net may differ from `predicted` before Finance looks at it: `pct` of its size or `usd`, the larger."""
    p = _params(pack)
    return max(abs(predicted) * p["pct"] / 100, p["usd"])


def check(s: Session, c: dict[str, Any], actual: float, predicted: float) -> int | None:
    """Open the Finance item when the variance is above the tolerance; returns its id, None when within it or one is open. In
    the caller's transaction."""
    from di.repositories.packs import active_pack
    from di.services.cases import process

    pack = active_pack(s, "tool_fleet", c.get("owner"))
    gap = actual - predicted
    if abs(gap) <= tolerance(predicted, pack):
        return None
    cid = str(c["id"])
    if s.execute(
        text("SELECT 1 FROM work_item WHERE case_id = :c AND type = :t AND status = 'open'"), {"c": cid, "t": EXCEPTION}
    ).first():
        return None
    kind = next((t for t in pack.runtime.exception_types if t.id == EXCEPTION), None)
    below = "below" if gap < 0 else "above"
    return process.open_item(
        s, kind="exception", case_id=cid, org_unit_id=c.get("owner"), type=EXCEPTION, title=f"Check the variance on {cid}",
        cause=f"The confirmed net ${actual:,.0f} is ${abs(gap):,.0f} {below} the predicted ${predicted:,.0f}; "
        f"the tolerance is ${tolerance(predicted, pack):,.0f}.",
        action=kind.action if kind else "Check the cost lines against the prediction",
        owner_role=kind.owner_role if kind else "Finance",
        due_hours=pack.runtime.sla_hours.get("exception"), by="system",
    )  # fmt: skip
