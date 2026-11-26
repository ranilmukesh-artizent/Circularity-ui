"""The odometer and recall evidence of a used car (plan 9, P9-9.9, stories UC-07 and UC-08).

    evidence(s, asset_key) -> (records, odometer, recall)   the evidence records of the car's odometer and recall check, and the
                                                           case facts `odometer` and `recall` the two gates read

The canonical `asset` record of the car (key `schema.vin_key`) holds what the lease system (`uc_lease`) wrote: `model_year`,
`return_kind`, `mileage_lease_record` (the lease system's own reading) and `seller_fleet_size`. Its `condition` record holds
`odometer_statement_ref` and `odometer_not_actual` (lease system), `odometer_photo_reading` (inspection app, `uc_insp`) and the
recall database's `recall_open`, `recall_campaigns`, `recall_checked_at` and `recall_remedy_ref` (`uc_recall`, also written by
`evidence.refresh`). They become:

    odometer_statement  {ref, statement_ref}, on file once the lessee's statement reference is (the evidence the gate lists)
    vin_recall          {checked_at, open, campaigns, remedy_ref}, dated at the check: the recall check and its date
    odometer (case)     {model_year, return_kind, statement_ref, photo_reading, lease_record, not_actual}
    recall (case)       {checked_at, open, campaigns, remedy_ref, fleet_size}

A fact that is not on file is left out of the dict; no recall check yet leaves `recall` empty and the gate asks for the check.
`gate_hold.attach_evidence` adds the records and the two dicts to a `used_cars` case; a later write of the odometer facts queues
`case.gateRecheck` (`canonical.store.apply`) for a car held for a second inspection.

Never does: decide a gate (`gate_checks.vehicle`), read the clock, call a source (that is `actions.evidence_refresh`) or write
the store. The odometer and recall rules are federal and state law; the wording needs review by Kinective's Legal team before
it is relied on.
"""

from typing import Any

from sqlalchemy.orm import Session

from di.services.canonical import store as canonical
from di.services.cases.title_evidence import _newest
from di.services.modeler.evidence import parse_time

ODOMETER_FIELDS = ("odometer_statement_ref", "odometer_not_actual", "odometer_photo_reading")  # the facts a hold waits for
RECALL_FIELDS = ("recall_open", "recall_campaigns", "recall_checked_at", "recall_remedy_ref")
SOURCE = "uc_lease"
RECALL_SOURCE = "uc_recall"


def _put(into: dict[str, Any], name: str, value: Any) -> None:
    if value is not None:
        into[name] = value


def evidence(s: Session, asset_key: Any) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """The records, `odometer` and `recall` facts of the car (module docstring); ([], {}, {}) when nothing is on file."""
    if not asset_key:
        return [], {}, {}
    cond = canonical.get(s, "condition", str(asset_key))
    asset = canonical.get(s, "asset", str(asset_key))
    c, a = (cond or {}).get("data") or {}, (asset or {}).get("data") or {}
    odometer: dict[str, Any] = {}
    for name, value in (
        ("model_year", a.get("model_year")), ("return_kind", a.get("return_kind")),
        ("statement_ref", c.get("odometer_statement_ref")), ("photo_reading", c.get("odometer_photo_reading")),
        ("lease_record", a.get("mileage_lease_record")),
        ("not_actual", c.get("odometer_not_actual")),
    ):  # fmt: skip
        _put(odometer, name, value)
    recall: dict[str, Any] = {}
    if c.get("recall_checked_at") is not None:
        for name, value in (
            ("checked_at", c.get("recall_checked_at")), ("open", bool(c.get("recall_open"))),
            ("campaigns", c.get("recall_campaigns") or []), ("remedy_ref", c.get("recall_remedy_ref")),
            ("fleet_size", a.get("seller_fleet_size")),
        ):  # fmt: skip
            _put(recall, name, value)
    elif a.get("seller_fleet_size") is not None:
        recall["fleet_size"] = a["seller_fleet_size"]
    records: list[dict[str, Any]] = []
    if odometer.get("statement_ref"):
        source, written = _newest(cond, "odometer_statement_ref")
        at = written.isoformat() if written else "1970-01-01T00:00:00+00:00"
        ref = odometer["statement_ref"]
        records.append({
            "type": "odometer_statement", "source": source or SOURCE, "at": at, "result": "pass",
            "value": {"ref": ref, "statement_ref": ref},
        })  # fmt: skip
    if recall.get("checked_at") and (checked := parse_time(recall["checked_at"])) is not None:
        source, _ = _newest(cond, "recall_checked_at")
        records.append({
            "type": "vin_recall", "source": source or RECALL_SOURCE, "at": checked.isoformat(), "result": "pass",
            "value": {k: recall.get(k) for k in ("checked_at", "open", "campaigns", "remedy_ref")},
        })  # fmt: skip
    return records, odometer, recall
