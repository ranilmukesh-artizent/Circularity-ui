"""The canonical vendor records a decision qualifies downstream vendors on (plan 9, P9-13.3, story X-14).

    records(s) -> list[dict]   each canonical `vendor` as its fields plus `id` (the record key), in key order

`decide_case` reads them with the session it is given and sets them on the case as `vendors`, for gate G-DS-1
(`vendor_qualification.qualify`); a decision read without a session, or with `vendors` already on the case, uses those.
Never does: write a record, read a clock or judge a certificate.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def records(s: Session) -> list[dict[str, Any]]:
    """Every canonical vendor record as a flat dict with `id` (the record key)."""
    rows = s.execute(text("SELECT key, data FROM canonical WHERE model = 'vendor' ORDER BY key")).all()
    return [{**(data or {}), "id": key} for key, data in rows]
