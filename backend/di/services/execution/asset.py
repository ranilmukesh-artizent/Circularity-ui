"""The ERP's answer to a fixed-asset step, kept on the case (plan 9, P9-13.1, story X-13).

    record(session, case, step)   on the acknowledgement of a `retire` or `transfer` step: `case["finance"]["asset"]` =
                                  {kind, doc, proceeds, book_value, gain_loss, currency, at} as the writer stored it on the
                                  instruction (`detail.asset`, `di.services.instructions.writers_asset`)

Never does: compute the gain or loss (it is the ERP's answer, stored as given), or write anything but `finance.asset`.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

KINDS = ("retire", "transfer")


def record(s: Session, c: dict[str, Any], step: int) -> None:
    """Copy the instruction's `detail.asset` to the case; a step the system acknowledged with no answer (a simulated one) leaves
    the case as it was."""
    row = s.execute(
        text("SELECT detail FROM instruction WHERE case_id = :c AND step = :n AND approval_ref = :r"),
        {"c": c["id"], "n": step, "r": c["exec"]["ref"]},
    ).first()
    asset = ((row[0] if row else None) or {}).get("asset")
    if isinstance(asset, dict) and asset.get("doc"):
        c["finance"] = {**(c.get("finance") or {}), "asset": asset}
