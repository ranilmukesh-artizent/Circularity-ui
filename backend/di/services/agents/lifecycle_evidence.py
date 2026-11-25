"""The lifecycle evidence of a case, put where the three lifecycle stages read it (plan 9, P9-2.20; registry entries I-3, I-7).

    refresh(s, case, st)        the asset's lease, intent, return-authorisation, shipment and goods-receipt records from the
                                canonical `compliance` model are added to `case["evidenceRecords"]` (in memory, newest first
                                wins in `evidence_of`), and the workspace clock goes to `st["now"]`; a case whose asset has
                                none of them is left exactly as it was
    wake_transit(s, asset_key)  a record landed for the asset: the runs of its open cases that wait `transit` run on; the transit
                                stage reads the case again and waits on if no goods receipt is there yet

The stages are pure (`di.services.agents.stages.lifecycle`); this is the one place that reads the store for them and the one
that wakes them, as `runtime.resume_waiting` does for an approval.
Never does: write a record, save a case, open a hold (`gate_hold.attach_evidence`, which binds the gates, is not used) or run a
step; the worker's job `case.gateRecheck` calls `wake_transit` after the gates are rechecked.
"""

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.services.agents.stages.lifecycle import LEASE_TYPES

log = logging.getLogger(__name__)
SELECT = text(
    "SELECT c.data, (SELECT p.source_id FROM provenance p WHERE p.model = 'compliance' AND p.key = c.key "
    "AND p.field = 'result' ORDER BY p.fetched_at DESC LIMIT 1) AS source "
    "FROM canonical c WHERE c.model = 'compliance' AND c.data ->> 'asset_key' = :a AND c.data ->> 'type' = ANY(:t) "
    "ORDER BY c.key"
)
OPEN_CASES = text("SELECT id FROM case_record WHERE data ->> 'assetId' = :a AND stage <> 'closed' ORDER BY id")


def refresh(s: Session, case: dict[str, Any], st: dict[str, Any]) -> None:
    """Add the case's lifecycle records to `case["evidenceRecords"]` and the clock to `st["now"]`; nothing when it has none."""
    rows = s.execute(SELECT, {"a": case.get("assetId"), "t": list(LEASE_TYPES)}).all()
    if not rows:
        return
    recs = [
        {k: d.get(k) for k in ("type", "result", "at", "valid_until")}
        | {"source": src or "", "value": d.get("value") if isinstance(d.get("value"), dict) else {}}
        for d, src in rows
    ]
    case["evidenceRecords"] = [*(case.get("evidenceRecords") or []), *recs]
    st["now"] = clock.now().isoformat()


def wake_transit(s: Session, asset_key: str) -> int:
    """Run on every run waiting `transit` on an open case of the asset; returns how many were woken. In the caller's
    transaction."""
    from di.services.agents import runtime  # the runtime imports the stages

    woken = 0
    for case_id in s.execute(OPEN_CASES, {"a": asset_key}).scalars().all():
        woken += runtime.resume_waiting(s, str(case_id), "transit")
    if woken:
        log.info("transit: %s run(s) woken for %s", woken, asset_key)
    return woken
