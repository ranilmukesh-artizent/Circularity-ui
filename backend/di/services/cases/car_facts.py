"""The money facts of a used car, read from the canonical store for the used-car valuer (plan 9, P9-9.11; registry entry I-21).

    records(s, asset_key) -> {"asset", "condition", "market", "vendor"}   the car's canonical records as nested dicts, the
                                                                shape `valuers/used_cars.py` reads (`asset.book_value`,
                                                                `condition.recon_estimate`, `market.lot_avg_price` ...)

`vendor` (P9-9.17) is the buyer of the best salvage bid: {buyer_id, title_db_reporting}, the auction platform's record of that
buyer (`title_db_reporting` is left out when the platform has not said); `G-VEH-SALV` reads it. A car with no bid has none.

The adapters of the lease system, the inspection app, the dealer system, the pricing guide and the auction platform write
these records (P9-9.3 to P9-9.6); until now the case only kept the facts it was opened with, so a stored car had no market to
value. `decide_case` reads them with the session it is given, on every decision, so a re-evaluation prices the car on the
market as it is now. A record the store does not hold is left out; a fact the valuer needs and cannot find makes its channel
"not valued" with the missing name (it is never made up).
Never does: write a record, read a clock, or decide anything.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from di.services.canonical import store as canonical

MODELS = ("asset", "condition", "market")


def records(s: Session, asset_key: str) -> dict[str, dict[str, Any]]:
    """The canonical `asset`, `condition` and `market` data of the car by model name (a model with no record is absent)."""
    out: dict[str, dict[str, Any]] = {}
    for model in MODELS:
        rec = canonical.get(s, model, asset_key)
        if rec and rec.get("data"):
            out[model] = dict(rec["data"])
    if buyer := out.get("market", {}).get("salvage_buyer"):
        reports = ((canonical.get(s, "vendor", str(buyer)) or {}).get("data") or {}).get("title_db_reporting")
        out["vendor"] = {"buyer_id": buyer} | ({} if reports is None else {"title_db_reporting": reports})
    return out


def _flag(v: Any) -> bool | None:
    """A history fact is text: `true`/`false` (any case) as a bool; None when it says neither."""
    if isinstance(v, bool):
        return v
    return {"true": True, "false": False}.get(str(v).strip().lower()) if v is not None else None


def replay_case(case_id: str, cls: str | None, facts: Mapping[str, Any]) -> dict[str, Any]:
    """The valuer-shaped used-car case of a history row (P9-9.15, the replay's `case_input`): the dotted facts as they are (the
    valuer and the diversions read `asset.*`, `condition.*`, `market.*`), and what the gates read built from them the way
    `gate_hold.attach_evidence` builds it from the store: the evidence records `title_status` (dated `condition.title_checked_at`)
    and `odometer_statement` (when `condition.odometer_statement_ref` is there), the case facts `title`, `odometer` and
    `recall` (dated `condition.recall_checked_at`). A fact the row does not carry is left out, so its gate asks for it, as it does
    for a stored car. Facts that already carry the evidence (`evidenceRecords`, a stored car's own) are taken as they are.
    Pure: no
    session, no clock."""
    g = facts.get
    c: dict[str, Any] = {"id": case_id, "cls": cls, **facts}
    if "evidenceRecords" in facts:
        return c
    records: list[dict[str, Any]] = []
    status = g("condition.title_status")
    if status is not None:
        lien = bool(_flag(g("condition.lien_open")))
        at = g("condition.title_checked_at")
        value = {"title_status": status, "lien_open": lien, "lien_release_ref": None,
                 "payoff_confirmed": _flag(g("condition.payoff_confirmed")), "return_kind": g("asset.return_kind"),
                 "checked_at": at}  # fmt: skip
        records.append({"type": "title_status", "source": "uc_title", "at": at, "result": "pass", "value": value})
        c["title"] = {"status": status, "lien_open": lien, "lien_release_ref": None}
    ref = g("condition.odometer_statement_ref")
    if ref:
        records.append({"type": "odometer_statement", "source": "uc_lease", "at": g("condition.title_checked_at"),
                        "result": "pass", "value": {"ref": ref, "statement_ref": ref}})  # fmt: skip
    seen = {"model_year": g("asset.model_year"), "return_kind": g("asset.return_kind"), "statement_ref": ref,
            "photo_reading": g("condition.odometer_photo_reading"), "lease_record": g("asset.mileage_lease_record")}  # fmt: skip
    c["odometer"] = {k: v for k, v in seen.items() if v is not None}
    if (checked := g("condition.recall_checked_at")) is not None:
        opened = bool(_flag(g("condition.recall_open")))
        c["recall"] = {"checked_at": checked, "open": opened, "campaigns": [], "remedied": []}
        records.append({"type": "vin_recall", "source": "uc_recall", "at": checked, "result": "pass",
                        "value": {"checked_at": checked, "open": opened, "campaigns": []}})  # fmt: skip
    if (reports := _flag(g("market.salvage_buyer_reports"))) is not None:  # the auction platform's word on the best salvage buyer
        c["vendor"] = {"title_db_reporting": reports}
        records.append({"type": "reporting_status", "source": "uc_auction", "at": g("condition.title_checked_at"),
                        "result": "pass" if reports else "fail", "value": {"title_db_reporting": reports}})  # fmt: skip
    c["evidenceRecords"] = records
    return c
