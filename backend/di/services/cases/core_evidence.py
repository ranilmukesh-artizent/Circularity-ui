"""The core returns system's record of a core as the case's `core` and fraud evidence (plan 9, P9-12.8, story NS-CORE-03).

    read(s, asset_key) -> core dict | None     the core `core_ret` wrote, in the shape the gate and the fraud rules read
    evidence(core) -> list of evidence records the X-15 triage reads (`gate_checks.core.fraud_evidence`)

The canonical `asset`, `condition` and `market` records of the core (key `schema.serial_key(org, core id)`) hold what the adapter
`core_ret` wrote (declared and observed part number, dealer, the inspection checks, the dealer's recent rejects, the deposit). The
core is `{coreId, dealerId, declaredPartNumber, observedPartNumber, deposit, checks, receivedAt, dealerRejects}`, as the mock
serves it; `receivedAt` is the time `core_ret` last wrote the checks (the adapter does not carry the mock's own date).
`gate_hold.attach_evidence` sets `case["core"]` and adds the evidence records to an `auto_core` case on opening and on every
re-check, so a mismatch or a repeat returner is held at intake by `fraud.hold`,
and CORE-ACCEPT reads the checks the system reported.

Never does: decide a credit or a hold, release a case (only a person does), or write the store.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from di.services.canonical import store as canonical
from di.services.modeler.gate_checks.core import SOURCE, fraud_evidence

TEMPLATE = "auto_core"


def _data(s: Session, model: str, key: str) -> dict[str, Any]:
    return (canonical.get(s, model, key) or {}).get("data") or {}


def _written(s: Session, key: str) -> datetime | None:
    """When `core_ret` last wrote the core's inspection checks."""
    rows = [r for r in ((canonical.get(s, "condition", key) or {}).get("provenance") or {}).get("core_checks") or []
            if r["source_id"] == SOURCE]  # fmt: skip
    return max((r["fetched_at"] for r in rows), default=None)


def read(s: Session, asset_key: Any) -> dict[str, Any] | None:
    """The core of the asset key (module docstring); None when `core_ret` has not written its inspection."""
    if not asset_key:
        return None
    key = str(asset_key)
    asset, cond, market = _data(s, "asset", key), _data(s, "condition", key), _data(s, "market", key)
    if cond.get("core_checks") is None or asset.get("declared_part_number") is None:
        return None
    at = _written(s, key)
    return {
        "coreId": key.rpartition(":")[2], "dealerId": asset.get("dealer_id"),
        "declaredPartNumber": asset.get("declared_part_number"), "observedPartNumber": asset.get("observed_part_number"),
        "deposit": market.get("core_deposit"), "checks": cond["core_checks"],
        "receivedAt": at.isoformat() if at else None, "dealerRejects": cond.get("dealer_rejects") or {},
    }  # fmt: skip


def evidence(core: dict[str, Any]) -> list[dict[str, Any]]:
    """The core's evidence records (none without a time: a record needs one)."""
    return fraud_evidence(core) if core.get("receivedAt") else []
