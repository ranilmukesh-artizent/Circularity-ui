"""The export classification and the buyer's screening of a unit as evidence (plan 9, P9-10.8, stories TN-03, TN-07, TN-08).

    read(s, asset_key, model) -> dict | None   what is on file for resale (below); None: the inventory has not written the unit
    evidence(read) -> list                     the `export_classification` record of that read ([] for None)
    bid_view(bid) -> dict                      one broker bid as the case shows it

The canonical `asset` record of the unit (key `schema.serial_key`) holds the export class the network inventory (`tn_inv`)
confirmed (`export_class`) apart from the class it inferred from the part number (`export_class_inferred`); the market record
of the unit's model (key = the model number) holds the broker's bids (`tn_broker`). The record is

    export_classification   {export_class, class_source, inferred, model, bid {id, unit_price, qty, country, domestic,
                             screening, ref} | None, bids}, source `tn_inv`, at the newest of the inventory's write and the bids'

`export_class` is the class a source confirmed or a person entered, with the source that wrote it (`class_source`); the inferred
class is carried apart and is never promoted to it. `bid` is the best bid whose end-user screening is `clear`, else the best bid
of all (so the case can say its screening is not on file), else None. Whether the unit needs trade compliance and whether the
screening clears resale is the gate's (`gate_checks.network.check_export_control`).

Never does: derive, guess or accept a class (the classification is a person's; Kinective's Legal team reviews the rules
before they are relied on), decide a gate, screen a buyer, or write the store.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from di.services.canonical import store as canonical
from di.services.modeler.gate_checks.network import EXPORT_EVIDENCE

SOURCE = "tn_inv"
BROKER = "tn_broker"
CLEAR = "clear"


def bid_view(bid: dict[str, Any]) -> dict[str, Any]:
    """One bid as the case shows it: the broker's id, price, quantity, buyer country and the end-user screening."""
    screening = bid.get("endUserScreening") or {}
    return {
        "id": bid.get("bidId"), "unit_price": bid.get("unitPrice"), "qty": bid.get("qty"), "country": bid.get("buyerCountry"),
        "domestic": bid.get("domestic"), "screening": screening.get("result"), "ref": screening.get("ref"),
    }  # fmt: skip


def _price(bid: dict[str, Any]) -> float:
    p = bid.get("unitPrice")
    return float(p) if isinstance(p, int | float) and not isinstance(p, bool) else 0.0


def best_bid(bids: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The best-priced bid screened clear, else the best-priced bid, else None."""
    clear = [b for b in bids if (b.get("endUserScreening") or {}).get("result") == CLEAR]
    pool = clear or bids
    return max(pool, key=_price) if pool else None


def _written(rec: dict[str, Any], field: str, source: str | None = None) -> tuple[Any, str | None, datetime | None]:
    """The merged value of the field, the source that wrote it and when (the newest row that holds the merged value)."""
    value = rec["data"].get(field)
    if value in (None, ""):
        return None, None, None
    rows = [r for r in rec["provenance"].get(field) or [] if r["value"] == value and (source is None or r["source_id"] == source)]
    if not rows:
        return value, None, None
    row = max(rows, key=lambda r: r["fetched_at"])
    return value, row["source_id"], row["fetched_at"]


def read(s: Session, asset_key: Any, model: Any) -> dict[str, Any] | None:
    """What is on file for resale of the unit (module docstring); None when the inventory has not written the unit."""
    if not asset_key:
        return None
    rec = canonical.get(s, "asset", str(asset_key))
    if rec is None:
        return None
    at = max((r["fetched_at"] for r in rec["provenance"].get("inventory_status") or [] if r["source_id"] == SOURCE), default=None)
    if at is None:
        return None
    cls, cls_source, cls_at = _written(rec, "export_class")
    inferred, _, inf_at = _written(rec, "export_class_inferred")
    stamps = [t for t in (at, cls_at, inf_at) if t is not None]
    bids: list[dict[str, Any]] = []
    if model:
        market = canonical.get(s, "market", str(model))
        if market is not None:
            bids = [b for b in market["data"].get("broker_bids") or [] if isinstance(b, dict)]
            stamps += [r["fetched_at"] for r in market["provenance"].get("broker_bids") or [] if r["source_id"] == BROKER]
    best = best_bid(bids)
    return {
        "export_class": cls, "class_source": cls_source, "inferred": inferred, "model": str(model) if model else None,
        "bid": bid_view(best) if best else None, "bids": len(bids), "at": max(stamps).isoformat(),
    }  # fmt: skip


def evidence(got: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The `export_classification` record of the read (module docstring); [] when the inventory has not written the unit."""
    if not got:
        return []
    value = {k: v for k, v in got.items() if k != "at"}
    return [{"type": EXPORT_EVIDENCE, "source": SOURCE, "at": got["at"], "result": "pass", "value": value}]
