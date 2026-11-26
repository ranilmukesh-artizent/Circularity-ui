"""What the device valuer reads when a received device's case opens (plan 9, P9-6.4; registry entry I-3 for the evidence).

Owns: `DeviceInputs` and `gather`: the market feed's price for the device's SKU and grade as of a date (its week, and
whether it is stale), and the value of each of the pack's evidence types (`valuer.params.evidence_types`) as the canonical
store and the trade-in hold it today. The case keeps the result as its valuer snapshot (`valuer.inputs`), so every later
read of the case sees the numbers it was opened with. P9-6.10 adds the price band of each channel (`bands`: the active price
model's, else the feed's reference value at the pack's channel index with no interval) and the sales of the SKU in 90 days;
the price confidence reads both. P9-6.11 adds `bid_per_unit`: the best net a unit among the approved bids on a lot of the device's
model and grade that is collecting bids (the wholesale channel then values the device at that bid). P9-6.13 adds `listing`:
the channel, days listed and offers of the device's live listing, which a rule's scope reads (`listChannel`, `listDaysMin`,
`offersMax`); `refresh_listing` keeps it current on every valuation. P9-6.14 adds `model_age_months`, which a customer's
diversion reads (grade C of a model over 36 months goes to wholesale). P9-6.18 keeps a proposed price candidate's band on the
case (`priceShadow`, `record_price_shadow`; it decides nothing).
P9-6.15 adds `repair_quote` (the lab's newest repair quote on the device, read from its raw records: the lab adapter makes no fact
of it) and `feed_price_a` (the grade-A feed price of the SKU, which `parts` is valued on).
P9-6.19 adds `live_buynow` and `parts_status` (the GR-D5 and GR-D9 checks). Later tasks add replacement demand.
Never does: write, value a channel (the valuer does) or invent a number: a missing price or evidence is None.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.repositories import device_lots, device_market, device_tradeins, model_versions
from di.services.canonical import store as canonical
from di.services.device import lock, verify, wipe
from di.services.engine.predictor import Predictor
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
    # the best approved net a unit on a lot of this model and grade that is collecting bids (P9-6.11); None when there is none
    bid_per_unit: float | None = None
    # the device's live listing, {channel, days, offers, offers_under, listing_id}; empty when it is not listed (P9-6.13)
    listing: dict[str, Any] = field(default_factory=dict)
    # months from the model's first week in the market feed to `as_of` (P9-6.14); None when the feed has none of the model
    model_age_months: float | None = None
    # the lab's newest repair quote on the device, {quote_id, repair, cost, price_uplift, days} (P9-6.15); None when it has none
    repair_quote: dict[str, Any] | None = None
    # the market feed's grade-A price of the device's SKU as of the date (P9-6.15); None when the feed has none
    feed_price_a: float | None = None
    # the lowest live Buy Now price of listings of the device's SKU and grade (P9-6.19, GR-D5); None when there is none
    live_buynow: float | None = None
    # the lab's parts declaration: genuine, non_genuine, unknown or None (P9-6.19, GR-D9)
    parts_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def listing_view(s: Session, imei: str | None, as_of: date) -> dict[str, Any]:
    """The device's live listing as a rule's scope reads it: its channel as the pack's key (`buynow`, `offers`, `auction`), the
    whole days it has been listed to `as_of` and its offers. `offers_under` is the offers less one: the scope dim `offersMax`
    holds a value below its bound, so "at most 0 offers" is a value below 0. Empty without a live listing."""
    row = device_market.listing_of(s, imei) if imei else None
    if row is None or row.status != "live":
        return {}
    names = {str(v).lower(): k for k, v in load_pack("device").valuer.params["dcn"].items()}
    return {
        "listing_id": row.listing_id, "channel": names.get(row.channel.lower(), row.channel.lower()),
        "days": max(0, (as_of - row.listed_at.date()).days), "offers": row.offers, "offers_under": row.offers - 1,
    }  # fmt: skip


def live_buynow(s: Session, sku_key: str | None, grade: str | None, as_of: date) -> float | None:
    """The lowest live Buy Now price a unit among listings of devices of `sku_key` and `grade` listed by `as_of` (P9-6.19,
    GR-D5): the listing's device is the canonical asset (its SKU) and condition (its cosmetic grade) of its IMEI. None when
    there is none, or the case has no SKU."""
    if not sku_key or not grade:
        return None
    buynow = str(load_pack("device").valuer.params["dcn"]["buynow"]).lower()
    sql = (
        "SELECT min(l.price) FROM device_listing l "
        "JOIN canonical a ON a.model = 'asset' AND a.key = 'IMEI:' || l.imei "
        "JOIN canonical c ON c.model = 'condition' AND c.key = 'IMEI:' || l.imei "
        "WHERE l.status = 'live' AND lower(l.channel) = :ch AND l.listed_at < CAST(:d AS date) + 1 "
        "AND a.data ->> 'sku_key' = :sku AND c.data ->> 'cosmetic_grade' = :g"
    )
    price = s.execute(text(sql), {"ch": buynow, "d": as_of, "sku": sku_key, "g": grade}).scalar_one()
    return float(price) if price is not None else None


def refresh_listing(s: Session, case: dict[str, Any], as_of: date) -> None:
    """The listing facts of a stored device case's valuer snapshot, read again (a valuation sees the days it is listed today)."""
    lot = case.get("valuer")
    if isinstance(lot, dict) and lot.get("imei") and isinstance(lot.get("inputs"), dict):
        lot["inputs"]["listing"] = listing_view(s, str(lot["imei"]), as_of)
    record_price_shadow(s, case, as_of)  # a proposed price candidate's band, beside the active model's (P9-6.18)


def record_price_shadow(s: Session, case: dict[str, Any], as_of: date) -> None:
    """While a price candidate is proposed, the candidate's band of each channel is kept on the case (`priceShadow`) beside the
    active model's, as of today's valuation (P9-6.18). Nothing reads it but the shadow's statistics: the case's channels, prices
    and net are the active model's, as before. Without a proposed candidate the case is left as it is."""
    lot = case.get("valuer")
    if not isinstance(lot, dict) or not lot.get("imei") or lot.get("ref") is None:
        return
    cand = model_versions.proposed(s, "device", "price")
    if cand is None or not cand.factors:
        return
    from di.services.actions.models import price_predictor  # lazily: the actions package imports this module
    from di.services.engine.predictor import FormulaPredictor
    from di.services.models.price import ModelPredictor, PriceModel

    imei = str(lot["imei"])
    cond = (canonical.get(s, "condition", imei_key(imei)) or {}).get("data") or {}
    point = device_market.feed_price(s, str(lot["sku_key"]), str(lot["grade"]), as_of) if lot.get("sku_key") else None
    week = point.week if point else None
    base = FormulaPredictor()
    shadow = ModelPredictor(base, PriceModel.load(cand.factors[0]["artefact"]), cand.id)
    active = price_predictor(s, base)

    def bands(pred: Predictor) -> dict[str, dict[str, float]]:
        return {ch: {k: b[k] for k in ("p10", "p50", "p90")} for ch, b in price_bands(s, lot, cond, week, pred).items()}

    case["priceShadow"] = {
        "model_id": cand.id, "at": as_of.isoformat(), "imei": imei, "bands": bands(shadow),
        "active": {"model_id": getattr(active, "model_id", None), "bands": bands(active)},
    }  # fmt: skip


def model_age_months(s: Session, model: str | None, as_of: date) -> float | None:
    """How old the model is, in months to one decimal: from its first week in the market feed (any SKU of the model) to `as_of`
    (a month is 30.4375 days). None for a model the feed does not have, or one it has only after `as_of`. Counted, never a
    model's guess (R16)."""
    if not model:
        return None
    first = s.execute(
        text("SELECT min(week) FROM device_price_point WHERE split_part(sku_key, '|', 1) = :m"), {"m": model}
    ).scalar_one()
    if first is None or first > as_of:
        return None
    return round((as_of - first).days / 30.4375, 1)


def repair_quote(s: Session, imei: str | None) -> dict[str, Any] | None:
    """The newest repair quote the lab (`dvlab`) made on the device, from its raw records (a dry-run sample is quarantined and
    never read): `{quote_id, repair, cost, price_uplift, days}`. None without a quote, or one with a figure missing: nothing is
    guessed (R16)."""
    if not imei:
        return None
    row = s.execute(
        text(
            "SELECT payload FROM raw_record WHERE source_id = 'dvlab' AND resource = 'repairQuotes' "
            "AND payload ->> 'imei' = :i AND coalesce(request, '') NOT LIKE 'dry-run sample%' "
            "ORDER BY payload ->> 'quotedAt' DESC NULLS LAST, ext_id DESC LIMIT 1"
        ),
        {"i": imei},
    ).scalar()
    if not isinstance(row, dict):
        return None
    try:
        return {
            "quote_id": str(row.get("quoteId")), "repair": str(row["repair"]), "cost": float(row["cost"]),
            "price_uplift": float(row["priceUplift"]), "days": float(row["days"]),
        }  # fmt: skip
    except (KeyError, TypeError, ValueError):
        return None


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
    s: Session, case: Mapping[str, Any], cond: Mapping[str, Any], feed_week: date | None, predictor: Predictor | None = None
) -> dict[str, dict[str, Any]]:
    """The price band of each of the pack's Recover channels for the device `case` (a lot with an IMEI; a PO lot has none): the
    active price model's (`price_predictor`; `predictor` replaces it, for a shadow), else the feed's reference value at the
    channel's index with no interval. A channel the formulas cannot price (the wholesale lot without a model) has none: the
    valuer estimates it."""
    if not case.get("imei") or case.get("ref") is None:
        return {}
    # lazily: the actions package imports the case intake, which imports this module
    from di.services.actions.models import intake_predictor, price_predictor
    from di.services.engine.predictor import FormulaPredictor
    from di.services.modeler.valuers import device
    from di.services.models.price import battery_band

    base = FormulaPredictor()
    priced = predictor or price_predictor(s, base)
    # a candidate (`predictor`) is scored as it is; a case is valued with the pack's promoted calibration (P9-13.7)
    pred = predictor or intake_predictor(s, priced, "device", "device")
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
        # repair, parts and recycle have no price band (P9-6.15)
        if ch in device.EXTRA or (isinstance(priced, FormulaPredictor) and ch == "wholesale"):
            continue
        b = pred.channel_price(facts, ch)
        week = b.feed_week or feed_week
        out[ch] = {
            "p10": b.p10, "p50": b.p50, "p90": b.p90, "model_id": b.model_id, "feed_week": week.isoformat() if week else None
        }  # fmt: skip
    return out


def bid_per_unit(s: Session, case: Mapping[str, Any], as_of: date) -> float | None:
    """The best approved net a unit on a lot of the received device's model and grade that is collecting bids (P9-6.11)."""
    if not case.get("imei") or not case.get("model"):
        return None
    return device_lots.best_net_per_unit(s, str(case["model"]), str(case["grade"]), as_of)


def gather(s: Session, case: Mapping[str, Any], as_of: date) -> DeviceInputs:
    """The inputs of the device case (or lot dict) `case`, which names `imei`, `sku_key` and `grade`, as of `as_of`."""
    imei = case.get("imei")
    point = device_market.feed_price(s, str(case["sku_key"]), str(case["grade"]), as_of) if case.get("sku_key") else None
    feed_a = device_market.feed_price(s, str(case["sku_key"]), "A", as_of) if case.get("sku_key") else None
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
        bid_per_unit=bid_per_unit(s, case, as_of),
        listing=listing_view(s, imei, as_of),
        model_age_months=model_age_months(s, case.get("model"), as_of),
        repair_quote=repair_quote(s, imei),
        feed_price_a=feed_a.price if feed_a else None,
        live_buynow=live_buynow(s, case.get("sku_key"), case.get("grade"), as_of),
        parts_status=cond.get("parts_status") if imei else None,
    )
