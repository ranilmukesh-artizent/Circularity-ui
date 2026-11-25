"""What the device valuer reads when a received device's case opens (plan 9, P9-6.4; registry entry I-3 for the evidence).

Owns: `DeviceInputs` and `gather`: the market feed's price for the device's SKU and grade as of a date (its week, and
whether it is stale), and the value of each of the pack's evidence types (`valuer.params.evidence_types`) as the canonical
store and the trade-in hold it today. The case keeps the result as its valuer snapshot (`valuer.inputs`), so every later
read of the case sees the numbers it was opened with. Later tasks add the price band, bids, listing and replacement demand.
Never does: write, value a channel (the valuer does) or invent a number: a missing price or evidence is None.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from di.repositories import device_market, device_tradeins
from di.services.canonical import store as canonical
from di.services.modeler.pack import load_pack


@dataclass(frozen=True)
class DeviceInputs:
    as_of: str
    feed_price: float | None
    feed_week: str | None
    feed_stale: bool
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def imei_key(imei: str) -> str:
    """The canonical key of a device (the lab and registry adapters key their facts the same way)."""
    return f"IMEI:{imei}"


def gather(s: Session, case: Mapping[str, Any], as_of: date) -> DeviceInputs:
    """The inputs of the device case (or lot dict) `case`, which names `imei`, `sku_key` and `grade`, as of `as_of`."""
    imei = case.get("imei")
    point = device_market.feed_price(s, str(case["sku_key"]), str(case["grade"]), as_of) if case.get("sku_key") else None
    cond = ((canonical.get(s, "condition", imei_key(imei)) or {}).get("data") or {}) if imei else {}
    row = device_tradeins.by_imei(s, imei) if imei else None
    evidence: dict[str, Any] = {}
    for e in load_pack("device").valuer.params["evidence_types"]:
        model, _, name = str(e["field"]).partition(".")
        evidence[e["id"]] = (row.quote if row else None) if model == "device_tradein" else cond.get(name)
    return DeviceInputs(
        as_of=as_of.isoformat(),
        feed_price=point.price if point else None,
        feed_week=point.week.isoformat() if point else None,
        feed_stale=point.stale if point else False,
        evidence=evidence,
    )
