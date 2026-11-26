"""The title and lien search of a used car as evidence (plan 9, P9-9.8, stories UC-06 and UC-24).

    evidence(s, asset_key) -> (records, title)   the evidence records of the car's title, and the case's `title` facts

The canonical `condition` record of the car (key `schema.vin_key`) holds what the title and lien service (`uc_title`) and the
dealer system (`uc_dms`, the trade-in's payoff) wrote: `title_status`, `lien_open`, `lien_release_ref`, `title_brand`,
`title_checked_at`, `payoff_confirmed`. The `asset` record says whether the car is a trade-in (`return_kind`). They become:

    title_status   {title_status, lien_open, lien_release_ref, payoff_confirmed, return_kind, checked_at}, on file once the
                   title service has answered (no title status: no record, the gate says "not on file")
    lien_release   {lien_open: false, lien_release_ref}, only when a lien was released and none is open (the release
                   `work.resolve` waits for on `EX-UC-LIEN`)
    title_brand    {brand}, only when the title carries a brand

`title` is {status, brand, lien_open, lien_release_ref}: the case's own fact `title.brand` triggers `G-VEH-BRAND`. A record's
`result` says it is on file; whether it clears the car is the gate's (`gate_checks.vehicle`). `gate_hold.attach_evidence`
adds the records to a `used_cars` case; a later write of the title facts queues `case.gateRecheck` (`canonical.store.apply`),
which releases a case the release now clears.

Never does: decide a gate, release a lien (a lien is released by its holder; a person closes the exception), or write the
store. Title rules are state law and differ; the wording needs review by Kinective's Legal team before it is relied on.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from di.services.canonical import store as canonical
from di.services.modeler.evidence import parse_time

SOURCE = "uc_title"


def _newest(rec: dict[str, Any] | None, field: str) -> tuple[str, datetime | None]:
    """The source that last wrote the field of a canonical record and when."""
    rows = ((rec or {}).get("provenance") or {}).get(field) or []
    if not rows:
        return "", None
    row = max(rows, key=lambda r: r["fetched_at"])
    return str(row["source_id"] or ""), row["fetched_at"]


def evidence(s: Session, asset_key: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The title evidence records of the car and its `title` facts (module docstring); ([], {}) when the title service has
    not answered."""
    if not asset_key:
        return [], {}
    cond = canonical.get(s, "condition", str(asset_key))
    data = (cond or {}).get("data") or {}
    if data.get("title_status") is None:
        return [], {}
    asset = (canonical.get(s, "asset", str(asset_key)) or {}).get("data") or {}
    source, written = _newest(cond, "title_status")
    at = parse_time(data.get("title_checked_at")) or written
    when = at or written
    stamp = when.isoformat() if when else "1970-01-01T00:00:00+00:00"
    lien_open, ref = bool(data.get("lien_open")), data.get("lien_release_ref")
    status = {
        "title_status": data["title_status"], "lien_open": lien_open, "lien_release_ref": ref,
        "payoff_confirmed": data.get("payoff_confirmed"), "return_kind": asset.get("return_kind"), "checked_at": stamp,
    }  # fmt: skip
    records = [{"type": "title_status", "source": source or SOURCE, "at": stamp, "result": "pass", "value": status}]
    if ref and not lien_open:
        records.append({
            "type": "lien_release", "source": source or SOURCE, "at": stamp, "result": "pass",
            "value": {"lien_open": False, "lien_release_ref": ref},
        })  # fmt: skip
    brand = data.get("title_brand")
    if brand:
        records.append(
            {"type": "title_brand", "source": source or SOURCE, "at": stamp, "result": "pass", "value": {"brand": brand}}
        )
    title = {"status": data["title_status"], "lien_open": lien_open, "lien_release_ref": ref}
    if brand:
        title["brand"] = brand
    return records, title
