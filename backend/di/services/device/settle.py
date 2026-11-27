"""List, settle and learn from the sale of a received device (plan 9, P9-6.12, story DV-09).

    forecast_p50(lot, channel) -> float          the price a unit is expected to sell for on a channel (its band's P50)
    listing_id(case_id, channel), listing_key    the id and the idempotency key of a case's listing on a channel
    listing_body(case) -> dict | None            what the `list` step posts to the device market
    on_sale(s, sale)                             a sale the market reports -> the case's `settlement`
    lines(case, route) -> list[dict]             the cost lines of a settled case's outcome (`execution.trace.line_actuals`)
    view(case) -> dict | None                    the case page's `settlement`

An approved case on a listing channel (`buynow`, `offers`, `auction`; the route's `variant` is "listing") has a `list`
step: the listing is posted to the device market (`dvmkt`, `POST /listings`) at the channel's forecast P50, idempotent on
`<case id>:<channel>` (the listing id is made from it, so a repeat is the market's own 409 and the writer reads the first
listing). It is sent only after a person (or the standing policy, I-11) approved the case: no agent lists, approves or
settles for a person.

A sale the market reports for the case (`devicemarket.sale`, landed by the connector, `on_sale`) sets the case's
`settlement`: `{price, fees, logistics, buyer_returns, forecast_p50, realised_vs_forecast, settled_at, sale_id}` for one
unit (a lot's sale is split over its devices). `realised_vs_forecast` is the price over the forecast P50. The sale does not
close the case: its last step does, as today. Finance then confirms the outcome with `outcome.confirm` (forbidden to
agents) and, for a device case with a settlement, the outcome's lines are the settlement's (the realised net against the
predicted one), which `outcome_rows` gives to `model.fit` (calibration) and to the price model's retraining (P9-6.18).
Model first (R16): every figure is computed from the sale and the forecast; the texts are fixed wording over them. Nothing
here writes language, so there is no model call.
"""

from collections.abc import Mapping, MutableMapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.repositories import device_market
from di.services.cases import store
from di.services.device.payout import money
from di.services.modeler.valuers import device

LISTING = ("buynow", "offers", "auction")  # the channels a device is listed on (a wholesale lot is sold to a bid)
KIND = "list"  # the step kind


# ---------------------------------------------------------------- pure
def forecast_p50(lot: Mapping[str, Any], channel: str) -> float:
    """The price a unit is expected to sell for on `channel`: its price band's P50 (`inputs.bands`) when the case opened with
    one, else the reference value times the grade's price index; a wholesale lot's best open bid a unit, else the index
    estimate."""
    band = (((lot.get("inputs") or {}).get("bands")) or {}).get(channel)
    if band:
        return float(band["p50"])
    if channel == "wholesale":
        bid = (lot.get("inputs") or {}).get("bid_per_unit")
        return float(bid) if bid is not None else float(lot["ref"]) * float(device.WHOLESALE_INDEX[lot["grade"]])
    return float(lot["ref"]) * device.DST[lot["grade"]][lot["band"]][channel][3]


def listing_id(case_id: str, channel: str) -> str:
    return f"LST-{case_id}-{channel}"


def listing_key(case_id: str, channel: str) -> str:
    return f"{case_id}:{channel}"


def channel_of(case: Mapping[str, Any]) -> str | None:
    """The channel the case was approved on (the chosen route, else the recommendation)."""
    r = case.get("chosen") or case.get("recommendation")
    return str(r["id"]) if r else None


def listing_body(case: Mapping[str, Any]) -> dict[str, Any] | None:
    """The listing to post for a case on a listing channel: the unit, the channel's name, the forecast P50 as the asking price."""
    lot, channel = case.get("valuer"), channel_of(case)
    if not isinstance(lot, dict) or not lot.get("imei"):
        return None
    uplift = 0.0
    if channel == "repair_sell":  # a repaired device is listed on the channel it sells best on (`via`), at the repaired price
        via = device.score(lot, "repair_sell").get("via")
        channel = str(via) if via else None
        uplift = float(((lot.get("inputs") or {}).get("repair_quote") or {}).get("price_uplift") or 0)
    if channel not in LISTING:
        return None
    return {
        "listingId": listing_id(case["id"], channel), "caseKey": listing_key(case["id"], channel), "imei": lot["imei"],
        "skuKey": lot.get("sku_key"), "grade": lot["grade"], "channel": device.DCN[channel],
        "price": round(forecast_p50(lot, channel) + uplift, 2), "offers": 0, "status": "live",
    }  # fmt: skip


def _split(sale: device_market.SaleRow) -> float:
    return float(max(1, len(sale.imeis)))


def settlement_of(case: Mapping[str, Any], sale: device_market.SaleRow) -> dict[str, Any] | None:
    """The settlement of one unit of `sale`, or None for a case with no channel to compare against."""
    lot, channel = case.get("valuer"), channel_of(case)
    if not isinstance(lot, dict) or channel not in device.DCFG:
        return None
    n = _split(sale)
    forecast = round(forecast_p50(lot, channel), 2)
    price = round(sale.price / n, 2)
    return {
        "price": price, "fees": round(sale.fees / n, 2), "logistics": float(device.DCFG[channel]["log"]),
        "buyer_returns": round(sale.buyer_returns / n, 2), "forecast_p50": forecast,
        "realised_vs_forecast": round(price / forecast, 4) if forecast else 0.0, "settled_at": sale.settled_at.isoformat(),
        "sale_id": sale.sale_id,
    }  # fmt: skip


def net_of(st: Mapping[str, Any]) -> float:
    """What a unit realised: the price less fees, logistics and what the buyer returned."""
    return round(float(st["price"]) - float(st["fees"]) - float(st["logistics"]) - float(st["buyer_returns"]), 2)


def _pct(st: Mapping[str, Any]) -> str:
    """The share of the forecast with one decimal and no trailing zero: "98.6%", "90%"."""
    return f"{round(float(st['realised_vs_forecast']) * 100, 1):g}%"


def kpi(st: Mapping[str, Any]) -> str:
    return f"Price realised against forecast {_pct(st)}"


def line(st: Mapping[str, Any]) -> str:
    """ "Sold $318 · fees $9.54 · returns $0 · 98.6% of forecast"."""
    return (
        f"Sold {money(st['price'])} · fees {money(st['fees'])} · returns {money(st['buyer_returns'])} · "
        f"{_pct(st)} of forecast"
    )


# ---------------------------------------------------------------- on a case
def _journal(s: Session, case: Mapping[str, Any], reason: str) -> None:
    stage = str(case.get("stage") or "none")
    s.execute(
        text("INSERT INTO case_stage_log (case_id, from_stage, to_stage, reason, actor) VALUES (:c, :st, :st, :r, 'system')"),
        {"c": case["id"], "st": stage, "r": reason},
    )


def on_sale(s: Session, sale: device_market.SaleRow) -> None:
    """The market reported a sale: each case it names (that has no settlement yet) gets one. In the caller's transaction (the
    connector's sync), so a dry or rolled-back run leaves nothing."""
    for cid in sale.case_ids:
        case = store.get(s, cid)
        if case is None or case.get("settlement") or (st := settlement_of(case, sale)) is None:
            continue
        mutable: MutableMapping[str, Any] = case
        mutable["settlement"] = st
        store.save(s, case)
        _journal(s, case, line(st))


def lines(case: Mapping[str, Any], route: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The outcome's cost lines of a settled case: the route's sale line at what the unit realised, the others as predicted."""
    st = case["settlement"]
    src = f"Device market sale {st['sale_id']}"
    return [
        {
            "label": t["label"], "kind": t["kind"], "pred": t["amt"], "act": net_of(st) if t["kind"] == "sale" else t["amt"],
            "model": None, "ver": None, "src": src if t["kind"] == "sale" else "Fixed amount (retrieved)",
        }
        for t in route["terms"]
    ]  # fmt: skip


def view(case: Mapping[str, Any]) -> dict[str, Any] | None:
    """The case page's `settlement` (camel case), or None while the case has none."""
    st = case.get("settlement")
    if not isinstance(st, dict):
        return None
    return {
        "price": st["price"], "fees": st["fees"], "logistics": st["logistics"], "buyerReturns": st["buyer_returns"],
        "forecastP50": st["forecast_p50"], "realisedVsForecast": st["realised_vs_forecast"], "settledAt": st["settled_at"],
        "saleId": st["sale_id"], "net": net_of(st), "kpi": kpi(st), "line": line(st),
    }  # fmt: skip
