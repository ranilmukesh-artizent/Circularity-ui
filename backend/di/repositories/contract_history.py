"""The fleet source's ended contracts, as they were read (plan 9, P9-5.4, story CR-04). A read only.

`rows(s)` is the `history` resource of the fleet source from its raw records: `{contractId, market, lines, endedAt, outcome,
hadProposal, feeBefore, feeAfter}` for each ended contract, oldest id first. The adapter keeps no fact for it (P9-3.1), so the
renewal odds (di.services.modeler.valuers.renewal_odds) read the raw payloads. Empty before the source has synced.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

SOURCE = "fleet"


def rows(s: Session) -> list[dict[str, Any]]:
    return list(
        s.execute(
            text("SELECT payload FROM raw_record WHERE source_id = :s AND resource = 'history' ORDER BY ext_id"), {"s": SOURCE}
        ).scalars()
    )
