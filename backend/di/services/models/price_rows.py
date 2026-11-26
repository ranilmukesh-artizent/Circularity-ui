"""The rows a price model learns from (plan 9, P9-6.9, I-14; stories DV-06 and DV-14): reads the device market tables and the
canonical lab facts and returns `price.PriceModel.fit`'s rows. Reads only.

    training_rows(s, as_of) -> list[TrainRow]

- A settled sale (`device_sale`, settled on or before `as_of`) gives one row per sold IMEI at the sale's price per unit, with
  the lab's facts of that device (canonical `asset.sku_key`, `condition.cosmetic_grade`, `battery_health_pct`,
  `functional_fails`). A device the lab has not read, or whose grade or SKU is unknown, gives no row. The channel is the
  listing's (Buy Now, Offers, Auction, Marketplace), `wholesale` for a lot sale, else `other`.
- A feed price (`device_price_point`, week on or before `as_of`) gives one row with channel `feed` and no battery or fault facts.
- `age_months` is the midpoint of the model's age band in the device valuer's table (0-24m 12, 25-48m 36, 49m+ 60); a model
  that is not in it has none.

Never writes, and never returns a row dated after `as_of` (the leakage rule of `di.repositories.device_market`).
"""

from datetime import date
from typing import Any, TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.repositories import device_market
from di.services.modeler.valuers.device import DMOD
from di.services.models.price import battery_band

FROM = date(2000, 1, 1)
_BAND_MONTHS = {"0-24m": 12.0, "25-48m": 36.0, "49m+": 60.0}
_AGE = {str(m[1]): _BAND_MONTHS[str(m[3])] for m in DMOD}
_CHANNEL = {"buy now": "buynow", "offers": "offers", "auction": "auction", "marketplace": "market"}


class TrainRow(TypedDict):
    model: str
    storage_gb: int
    grade: str
    battery_band: str | None
    functional_fails: int | None
    age_months: float | None
    channel: str
    price: float
    on: date


def _split(sku_key: str) -> tuple[str, int] | None:
    name, _, gb = sku_key.rpartition("|")
    return (name, int(gb)) if name and gb.isdigit() else None


def _facts(s: Session, imeis: set[str]) -> dict[tuple[str, str], dict[str, Any]]:
    keys = [f"IMEI:{i}" for i in imeis]
    rows = s.execute(
        text("SELECT model, key, data FROM canonical WHERE model IN ('asset', 'condition') AND key = ANY(:k)"), {"k": keys}
    )
    return {(r.model, r.key): r.data for r in rows}


def _listing_channels(s: Session, ids: set[str]) -> dict[str, str]:
    rows = s.execute(text("SELECT listing_id, channel FROM device_listing WHERE listing_id = ANY(:i)"), {"i": list(ids)})
    return {r.listing_id: _CHANNEL.get(str(r.channel).strip().lower(), "other") for r in rows}


def training_rows(s: Session, as_of: date) -> list[TrainRow]:
    sales = device_market.sales(s, FROM, as_of)
    imeis = {i for x in sales for i in x.imeis}
    facts = _facts(s, imeis)
    channels = _listing_channels(s, {x.listing_id for x in sales if x.listing_id})
    out: list[TrainRow] = []
    for sale in sales:
        channel = channels.get(sale.listing_id or "") or ("wholesale" if sale.lot_ref else "other")
        for imei in sale.imeis:
            key = f"IMEI:{imei}"
            sku = _split(str((facts.get(("asset", key)) or {}).get("sku_key") or ""))
            cond = facts.get(("condition", key)) or {}
            if sku is None or cond.get("cosmetic_grade") is None:
                continue
            fails = cond.get("functional_fails")
            pct = cond.get("battery_health_pct")
            out.append(
                {
                    "model": sku[0], "storage_gb": sku[1], "grade": str(cond["cosmetic_grade"]),
                    "battery_band": battery_band(float(pct)) if pct is not None else None,
                    "functional_fails": len(fails) if isinstance(fails, list) else None,
                    "age_months": _AGE.get(sku[0]), "channel": channel, "price": sale.price,
                    "on": sale.settled_at.date(),
                }
            )  # fmt: skip
    for p in device_market.price_history(s, None, FROM, as_of):
        sku = _split(p.sku_key)
        if sku is not None:
            out.append(
                {
                    "model": sku[0], "storage_gb": sku[1], "grade": p.grade, "battery_band": None, "functional_fails": None,
                    "age_months": _AGE.get(sku[0]), "channel": "feed", "price": p.price, "on": p.week,
                }
            )  # fmt: skip
    return out
