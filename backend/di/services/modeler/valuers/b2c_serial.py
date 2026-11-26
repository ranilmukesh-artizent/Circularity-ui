"""The valuer plug-in of the serialised retail returns pack (plan 9, P9-12.10, stories NS-B2C-01, NS-B2C-02; registry entry I-21:
`VALUERS["b2c_serial"]`, named by the pack's `valuer.params.params.plugin`). Pure: no Session, no I/O.

The pack is a standard pack with the device pack's channels in front: this plug-in
- values the channels named in `valuer.params.params.device_channels` (Buy Now, Offers, Auction, Marketplace, Wholesale lot) with
  the device valuer (`valuers.device.decide`, unchanged) on the item's facts, for a phone or tablet (`itemClass`) that has a
  grade (A-D), an age band, a reference value `ref` and units `qty`: the same scores as the device pack for the same facts, each
  as the value and the days-past-service-level penalty the device channel is made of;
- leaves every other route (`donate`, `recycle`, `exit`) to the standard valuer: the pack's own value lines.
A channel the device valuer does not price (apparel, footwear, an item with no grade or reference value, or a channel a single
device is not listed on) is not eligible, and says why.

Never does: read the canonical store (the wipe certificate and registry check are the gates' evidence, `services.device`), decide
a gate, or rank. The device valuer's tables are the PO prototype's synthetic ones; this plug-in adds no number of its own.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from di.services.modeler.pack import Pack
from di.services.modeler.valuers import device, standard
from di.services.modeler.valuers.tool_fleet import PathValue

DEVICE_CLASSES = ("phone", "tablet")
# the fields a received device keeps beside the lot's own (di.services.device.intake.EXTRA; not imported: a layer up)
EXTRA = (
    "imei", "sku_key", "storage_gb", "graded", "declared_grade", "ref_source", "quote", "partner", "batch_id", "received",
    "lines",
)  # fmt: skip
NOT_PRICED = "A device channel does not take {what}"
INCOMPLETE = "A device item needs a grade (A-D), an age band and a reference value to be priced on a channel"
SINGLE = "A single device is not priced on {channel}"


def device_lot(facts: Mapping[str, Any]) -> dict[str, Any] | None:
    """The device valuer's lot for a phone or tablet with a grade, an age band, a reference value and units; None otherwise."""
    grade, band, ref, qty = facts.get("grade"), facts.get("band"), facts.get("ref"), facts.get("qty") or 1
    if facts.get("itemClass") not in DEVICE_CLASSES or grade not in device.DST or band not in device.DST[grade]:
        return None
    if not isinstance(ref, int | float) or isinstance(ref, bool) or not isinstance(qty, int) or qty < 1:
        return None
    lot: dict[str, Any] = {
        "id": str(facts.get("id") or ""), "brand": facts.get("brand") or "", "model": facts.get("model") or "", "band": band,
        "grade": grade, "ref": ref, "qty": qty, "doh": facts.get("doh") or 1,
    }  # fmt: skip
    lot |= {k: facts[k] for k in EXTRA if k in facts}
    if isinstance(facts.get("inputs"), Mapping):
        lot["inputs"] = dict(facts["inputs"])  # the price bands the device valuer reads
    return lot


def _as_value(x: device.ChannelValue) -> PathValue:
    """A device channel's score as value lines: the expected cash a unit, and the penalty (or gain) of the days to sell."""
    held = round(x["score"] - x["cash"], 10)
    lines: list[Any] = [{"type": "v", "label": "Expected cash a unit", "basis": "", "amt": x["cash"], "kind": "sale"}]
    if held:
        lines.append({"type": "v" if held > 0 else "c", "label": "Days past the service level", "basis": "", "amt": abs(held),
                      "kind": "risk"})  # fmt: skip
    gross = sum(ln["amt"] for ln in lines if ln["type"] == "v")
    cost = sum(ln["amt"] for ln in lines if ln["type"] == "c")
    return {
        "k": x["k"], "ok": x["ok"], "gross": gross, "cost": cost, "hold": 0.0, "net": x["score"], "why": x["why"], "lines": lines,
        "dest": None, "misses": [], "co2": x["co2"], "co2Prov": x["co2Prov"],
    }  # fmt: skip


def value_routes(case: Mapping[str, Any], pack: Pack, as_of: datetime | None = None) -> list[PathValue]:
    """Every route of the pack valued for the item (module docstring), in the pack's order."""
    channels = {str(c) for c in (pack.valuer.params.get("params") or {}).get("device_channels") or ()}
    lot = device_lot(case)
    priced = {x["k"]: x for x in device.decide(lot, [])["all"]} if lot is not None else {}
    out: list[PathValue] = []
    for v in standard.value_routes(case, pack, as_of):
        if v["k"] in channels:
            if v["k"] in priced:
                v = _as_value(priced[v["k"]])
            else:
                if lot is not None:
                    why = SINGLE.format(channel=v["k"])
                elif case.get("itemClass") in DEVICE_CLASSES:
                    why = INCOMPLETE
                else:
                    why = NOT_PRICED.format(what=case.get("itemClass") or "this item")
                v = v | {"ok": False, "why": why}
        out.append(v)
    return out
