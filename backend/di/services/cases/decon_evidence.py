"""The decontamination record of a rental device as evidence (plan 9, P9-11.6, stories MR-04 and MR-05).

    evidence(s, asset_key) -> records   the evidence records of the device's decontamination, [] when no cycle is on file

The canonical `condition` record of the device (key `schema.tag_key`) holds what the decontamination log (`mr_decon`) wrote:
`decon_ended_at`, `decon_started_at`, `decon_record_ref`, `decon_enhanced`, `decon_result`; the `asset` record holds the
check-in time (`checked_in_at`, the rental system). They become one record:

    decontamination   {decon_ended_at, decon_started_at, decon_record_ref, decon_enhanced, decon_result, checked_in_at}, at the
                      END of the cycle (MR-03: never the start), source the log that wrote it, result `fail` when the log
                      says the cycle failed, else `pass` (on file)

Whether the record is VALID, that is whether it ends after check-in, is the gate's (`gate_checks.medical`). `gate_hold.
attach_evidence` adds the record to a `medical_rental` case; a later write of the decontamination facts queues
`case.gateRecheck` (`canonical.store.apply`), which releases the case a valid record now clears.

Never does: decide a gate, write the store, or clear a hold. Decontamination rules are health and safety guidance; the
wording needs review by Kinective's Legal team before it is relied on.
"""

from typing import Any

from sqlalchemy.orm import Session

from di.services.canonical import store as canonical
from di.services.modeler.evidence import parse_time

SOURCE = "mr_decon"
FIELDS = ("decon_ended_at", "decon_started_at", "decon_record_ref", "decon_enhanced", "decon_result")


def evidence(s: Session, asset_key: Any) -> list[dict[str, Any]]:
    """The decontamination evidence record of the device (module docstring); [] when the log has no cycle for it."""
    if not asset_key:
        return []
    cond = canonical.get(s, "condition", str(asset_key))
    data = (cond or {}).get("data") or {}
    ended = parse_time(data.get("decon_ended_at"))
    if ended is None:
        return []
    rows = ((cond or {}).get("provenance") or {}).get("decon_ended_at") or []
    source = str(max(rows, key=lambda r: r["fetched_at"])["source_id"] or "") if rows else ""
    asset = (canonical.get(s, "asset", str(asset_key)) or {}).get("data") or {}
    value = {f: data.get(f) for f in FIELDS} | {"checked_in_at": asset.get("checked_in_at")}
    failed = str(data.get("decon_result") or "pass").lower() in ("fail", "failed")
    return [
        {"type": "decontamination", "source": source or SOURCE, "at": ended.isoformat(),
         "result": "fail" if failed else "pass", "value": value}
    ]  # fmt: skip
