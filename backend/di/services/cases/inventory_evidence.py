"""The network inventory's record of a unit as evidence (plan 9, P9-10.6, story TN-05).

    evidence(s, asset_key) -> list of evidence records   the `inventory_match` record, or [] when the unit is not in the inventory

The canonical `asset` record of the unit (key `schema.serial_key`) holds what the network inventory (`tn_inv`) wrote
(`inventory_status`, `site`, `model`, ...); the decommission tracker (`tn_decom`) writes the same record's `model`, so the
inventory's own model is read from the provenance of `tn_inv`, never from the merged value. The record exists once the
inventory has written the unit:

    inventory_match   {serial, model, site, status}, source `tn_inv`, at the time the inventory last wrote the unit

Whether it matches the removal (same model, same site) is the gate's (`gate_checks.network`); no record means "not in the
inventory". `gate_hold.attach_evidence` adds the record to a `telecom_network` case; a later write of the unit's inventory
facts queues `case.gateRecheck` (`canonical.store.apply`), which releases a case the match now clears.

Never does: decide a gate, write the store, or confirm a serial (the field team does, and a person closes the exception).
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from di.services.canonical import store as canonical

SOURCE = "tn_inv"


def _own(rec: dict[str, Any], field: str) -> tuple[Any, datetime | None]:
    """The value `tn_inv` wrote to the field and when, or (None, None)."""
    rows = [r for r in rec["provenance"].get(field) or [] if r["source_id"] == SOURCE]
    if not rows:
        return None, None
    row = max(rows, key=lambda r: r["fetched_at"])
    return row["value"], row["fetched_at"]


def evidence(s: Session, asset_key: Any) -> list[dict[str, Any]]:
    """The `inventory_match` record of the unit (module docstring); [] when the inventory has not written it."""
    if not asset_key:
        return []
    rec = canonical.get(s, "asset", str(asset_key))
    if rec is None:
        return []
    status, at = _own(rec, "inventory_status")
    if at is None:
        return []
    model, _ = _own(rec, "model")
    site, _ = _own(rec, "site")
    data = rec["data"]
    value = {"serial": data.get("serial"), "model": model, "site": site, "status": status}
    return [{"type": "inventory_match", "source": SOURCE, "at": at.isoformat(), "result": "pass", "value": value}]
