"""Repeat-return counts for the fraud triage (plan 9, P9-2.11; registry entry I-1, signal `repeat_returns`).

Owns: how many cases a returned asset key has had in each window of days (`repeat_counts`), the one read the triage's history
argument comes from (di.services.modeler.fraud).
Never does: write, or judge a count (the pack's rule says how many is too many).

The window runs back from the database clock, as the cases' `created_at` does (a case is stamped by the database), and a case
counts when its `data->>'assetId'` is the key. The case being triaged counts too: three cases of one key are three returns.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def repeat_counts(s: Session, case: Mapping[str, Any], windows: Iterable[int]) -> dict[str, int]:
    """`{"<days>": cases of the case's asset key created in the last <days> days}` for each window. No asset key: no counts."""
    key = case.get("assetId")
    if not key:
        return {}
    sql = text(
        "SELECT count(*) FROM case_record WHERE data ->> 'assetId' = :k AND created_at >= now() - make_interval(days => :d)"
    )
    return {str(days): int(s.execute(sql, {"k": str(key), "d": int(days)}).scalar_one()) for days in windows}
