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
