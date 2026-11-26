"""What the device valuer reads when a received device's case opens (plan 9, P9-6.4; registry entry I-3 for the evidence).

Owns: `DeviceInputs` and `gather`: the market feed's price for the device's SKU and grade as of a date (its week, and
whether it is stale), and the value of each of the pack's evidence types (`valuer.params.evidence_types`) as the canonical
store and the trade-in hold it today. The case keeps the result as its valuer snapshot (`valuer.inputs`), so every later
read of the case sees the numbers it was opened with. P9-6.10 adds the price band of each channel (`bands`: the active price
model's, else the feed's reference value at the pack's channel index with no interval) and the sales of the SKU in 90 days;
the price confidence reads both. Later tasks add bids, listing and replacement demand.
Never does: write, value a channel (the valuer does) or invent a number: a missing price or evidence is None.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.repositories import device_market, device_tradeins
from di.services.canonical import store as canonical
from di.services.device import lock, verify, wipe
from di.services.modeler.pack import load_pack

AGE_MONTHS = {"0-24m": 12.0, "25-48m": 36.0, "49m+": 60.0}  # the midpoint of each age band, as the price model's rows have it


@dataclass(frozen=True)
class DeviceInputs:
    as_of: str
    feed_price: float | None
    feed_week: str | None
    feed_stale: bool
    evidence: dict[str, Any] = field(default_factory=dict)
    # the quote against the lab's read of the device (P9-6.5, `verify.comparison`)
    comparison: dict[str, Any] = field(default_factory=lambda: {"state": "waiting", "mismatches": []})
    # the registry's check of the device (blacklist, lock, finance), its date and age (P9-6.6, `lock.registry_view`)
    registry: dict[str, Any] = field(default_factory=dict)
    # the lab's data-wipe certificate and whether it is complete (P9-6.7, `wipe.certificate_view`)
    wipe: dict[str, Any] = field(default_factory=dict)
    # the price band of each channel, {p10, p50, p90, model_id, feed_week} (P9-6.10); empty for a lot with no IMEI
    bands: dict[str, dict[str, Any]] = field(default_factory=dict)
    # devices of the SKU sold in the 90 days to `as_of`; None for a lot with no SKU
    sales_90d: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def imei_key(imei: str) -> str:
    """The canonical key of a device (the lab and registry adapters key their facts the same way)."""
    return f"IMEI:{imei}"


def sales_of_sku(s: Session, sku_key: str, as_of: date, days: int = 90) -> int:
    """Devices of the SKU (canonical `asset.sku_key`) sold in the `days` to `as_of` (a settled sale counts each device)."""
    imeis = [imei_key(i) for x in device_market.sales(s, as_of - timedelta(days=days), as_of) for i in x.imeis]
    if not imeis:
        return 0
    sql = "SELECT count(*) FROM canonical WHERE model = 'asset' AND key = ANY(:k) AND data ->> 'sku_key' = :sku"
    return int(s.execute(text(sql), {"k": imeis, "sku": sku_key}).scalar_one())


def price_bands(
    s: Session, case: Mapping[str, Any], cond: Mapping[str, Any], feed_week: date | None
) -> dict[str, dict[str, Any]]:
    """The price band of each of the pack's Recover channels for the device `case` (a lot with an IMEI; a PO lot has none): the
    active price model's (`price_predictor`), else the feed's reference value at the channel's index with no interval. A channel
    the formulas cannot price (the wholesale lot without a model) has none: the valuer estimates it."""
    if not case.get("imei") or case.get("ref") is None:
        return {}
    # lazily: the actions package imports the case intake, which imports this module
    from di.services.actions.models import price_predictor
    from di.services.engine.predictor import FormulaPredictor
    from di.services.modeler.valuers import device
    from di.services.models.price import battery_band

    base = FormulaPredictor()
    pred = price_predictor(s, base)
    pct, fails = cond.get("battery_health_pct"), cond.get("functional_fails")
    age = next((str(m[3]) for m in device.DMOD if m[1] == case.get("model")), None)
    facts = {
        "model": case.get("model"), "storage_gb": case.get("storage_gb"), "grade": case["grade"], "band": age, "ref": case["ref"],
        "battery_band": battery_band(float(pct)) if pct is not None else None,
        "functional_fails": len(fails) if isinstance(fails, list) else None,
        "age_months": AGE_MONTHS.get(str(age)), "feed_week": feed_week,
    }  # fmt: skip
    out: dict[str, dict[str, Any]] = {}
    for ch in device.RECOVER:
        if pred is base and ch == "wholesale":
            continue
        b = pred.channel_price(facts, ch)
        week = b.feed_week or feed_week
        out[ch] = {
            "p10": b.p10, "p50": b.p50, "p90": b.p90, "model_id": b.model_id, "feed_week": week.isoformat() if week else None
        }  # fmt: skip
    return out


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
        comparison=verify.comparison(verify.quote_of(case), verify.diagnostics_of(cond)),
        registry=lock.registry_view(cond, clock.now(), float(lock.params(load_pack("device"))["recheck_days"])),
        wipe=wipe.certificate_view(cond),
        bands=price_bands(s, case, cond, point.week if point else None),
        sales_90d=sales_of_sku(s, str(case["sku_key"]), as_of) if case.get("sku_key") else None,
    )
