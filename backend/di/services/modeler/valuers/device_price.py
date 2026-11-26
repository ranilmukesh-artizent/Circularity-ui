"""What holds a device's price for a person (plan 9, P9-6.10, story DV-06; the confidence is read by the hold policy, I-10). Pure.

    floor_pct(pack) -> float                   the recovery floor (GR-D2): the pack's share, or a customer's higher one
    confidence(p10, p50, p90) -> float         max(0, 1 - (p90 - p10) / (2 * p50)) of the best channel's price band
    signals(...) -> list[str]                  the price-confidence signals that fired (GR-D8)
    approval(...) -> dict | None               the case's holds, role and confidence for `decide_case` (`Decision.approval`)

- Floor GR-D2 (every device lot, a PO lot too): the best channel's cash a unit under `pct` times the reference value holds the
  case for the Approver role, owner label "Recommerce finance": "Below the recovery floor: $105 is 52.5% of the $200 reference
  value (floor 55%)". `pct` is the guardrail's value (a customer's `tighten` may raise it) or the overlay parameter
  `device.floor` (`set_param`, whose range starts at the pack's share, so it can only tighten), whichever is higher.
- Confidence GR-D8 (a received device only, the lot has an `imei`): the signals are an unseen SKU or fewer sales of it in 90 days
  than `min_sales_90d`, a stale or missing feed, a band wider than `max_interval_share` of its P50, and the top two channels'
  cash intervals overlapping by more than `max_overlap` of the best one's. The case's confidence goes to the hold policy
  (`decisionConfidence`); the case also holds, owner "Pricing analyst", when the confidence is under the flow's threshold or a
  signal other than the width fired (the width counts through the confidence only: a share of 0.5 is 0.75, at a threshold of
  0.75 not held).
Never does: read the database, approve or release anything (the hold waits for a person; agents only hold) or write language: the
texts are fixed wording over computed numbers, so no model call. The price and its interval come from the price model (or the
feed); code alone floors it.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from di.services.engine.predictor import PriceBand
from di.services.modeler.pack import Pack
from di.services.modeler.valuers import device

FLOOR_GUARD, CONFIDENCE_GUARD = "GR-D2", "GR-D8"
FLOOR_OWNER, CONFIDENCE_OWNER = "Recommerce finance", "Pricing analyst"
ROLE = "Approver"
FLOOR_PARAM = "device.floor"
PRICE_GUARDS = (FLOOR_GUARD, CONFIDENCE_GUARD)
DEFAULT_THRESHOLD = 0.75


def floor_pct(pack: Pack) -> float:
    """The floor's share of the reference value: the larger of GR-D2's value and the customer's `device.floor`."""
    g = next((x for x in pack.guardrails if x.id == FLOOR_GUARD), None)
    own = float(g.param.value) if g is not None and g.param is not None else float(device.DG["floor"])
    layer = pack.customer_layer.params.get(FLOOR_PARAM)
    return max(own, float(layer.value)) if layer is not None else own


def interval_share(p10: float, p50: float, p90: float) -> float:
    """(P90 - P10) / P50: how wide the band is, 0 for a price with no interval or none at all."""
    return (p90 - p10) / p50 if p50 > 0 else 0.0


def confidence(p10: float, p50: float, p90: float) -> float:
    """max(0, 1 - (P90 - P10) / (2 * P50)); 0 for a price of nothing."""
    return max(0.0, 1.0 - interval_share(p10, p50, p90) / 2) if p50 > 0 else 0.0


def band_figures(v: Mapping[str, Any], band: PriceBand | None) -> dict[str, float]:
    """What a channel's value adds to the decider's figures when it has a band: the cash interval and the band's own prices."""
    if band is None or "p10_cash" not in v:
        return {}
    return {"p10_cash": v["p10_cash"], "p90_cash": v["p90_cash"], "p10": band.p10, "p50": band.p50, "p90": band.p90}


def channels_view(lot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The case page's channels (facade `ChannelView`): per channel the expected net a unit, days to sell, the P10 to P90 cash
    (None without a band), the feed week, the model and the valuer's note, best first among the channels the valuer allows;
    `repair` on Repair then sell (P9-6.15)."""
    values = device.decide(dict(lot), [])["all"]
    order = {v["k"]: i for i, v in enumerate(sorted(values, key=lambda v: (not v["ok"], -v["score"])))}
    return [
        {
            "k": v["k"],
            "name": device.DCN[v["k"]],
            "cash": v["cash"],
            "days": v["days"],
            "p10": v.get("p10_cash"),
            "p90": v.get("p90_cash"),
            "feedWeek": v.get("feed_week"),
            "modelId": v.get("model_id"),
            "ok": v["ok"],
            "why": v["why"],
            **(
                {"repair": _repair_view(v["repair"])} if "repair" in v else {}
            ),  # the quote a Repair then sell route rests on (P9-6.15)
            **(
                {"replacement": _replacement_view(v["replacement"])} if "replacement" in v else {}
            ),  # the demand unit a Replacement stock route fills (P9-6.16)
        }  # fmt: skip
        for v in sorted(values, key=lambda v: order[v["k"]])
    ]


def _repair_view(q: Mapping[str, Any]) -> dict[str, Any]:
    return {"repair": q["repair"], "cost": q["cost"], "priceUplift": q["price_uplift"], "days": q["days"]}


def _replacement_view(r: Mapping[str, Any]) -> dict[str, Any]:
    return {"demandId": r["demand_id"], "unitCost": r["unit_cost"], "open": r["open"]}


def usd(v: float) -> str:
    """ "$105" for a whole amount, "$105.30" otherwise."""
    r = round(v, 2)
    return f"${r:,.0f}" if r == int(r) else f"${r:,.2f}"


def _pct(v: float) -> str:
    return f"{round(v * 100, 1):g}%"


def floor_reason(cash: float, ref: float, pct: float) -> str:
    return f"Below the recovery floor: {usd(cash)} is {_pct(cash / ref)} of the {usd(ref)} reference value (floor {_pct(pct)})"


def _overlap(top: Sequence[Mapping[str, float]]) -> float:
    """How much of the best channel's cash interval the second one covers (0 to 1; 0 with fewer than two bands)."""
    if len(top) < 2 or not all("p10_cash" in f for f in top):
        return 0.0
    a, b = top[0], top[1]
    width = a["p90_cash"] - a["p10_cash"]
    cover = max(0.0, min(a["p90_cash"], b["p90_cash"]) - max(a["p10_cash"], b["p10_cash"]))
    return (1.0 if cover > 0 else 0.0) if width <= 0 else cover / width


def signals(
    figures: Mapping[str, Mapping[str, float]],
    best: str,
    ranked: Sequence[str],
    inputs: Mapping[str, Any],
    params: Mapping[str, Any],
) -> list[str]:
    """The price-confidence signals that fired for the best channel `best` (module docstring); `ranked` the channels in order."""
    out: list[str] = []
    seen = inputs.get("sales_90d")
    if seen is None or seen == 0:
        out.append("unseen SKU")
    elif seen < params["min_sales_90d"]:
        out.append(f"only {seen} sales in 90 days")
    if inputs.get("feed_price") is None or inputs.get("feed_stale"):
        out.append("stale feed")
    f = figures[best]
    if "p50" in f and interval_share(f["p10"], f["p50"], f["p90"]) > params["max_interval_share"]:
        out.append("wide interval")
    if _overlap([figures[k] for k in ranked[:2] if k in figures]) > params["max_overlap"]:
        out.append("channels overlap")
    return out


def approval(
    best: str | None,
    ranked: Sequence[str],
    figures: Mapping[str, Mapping[str, float]],
    lot: Mapping[str, Any],
    pack: Pack,
) -> dict[str, Any] | None:
    """What `decide_case` keeps on a device case (`Decision.approval`): `{kind, role, reasons, holds, confidence}`, or None
    when there is nothing to say (a PO lot above the floor, or no channel chosen). `ranked`: the eligible channels, best first."""
    if best is None or best not in figures:
        return None
    holds: list[dict[str, Any]] = []
    cash, ref = figures[best]["cash"], float(lot["ref"])
    pct = floor_pct(pack)
    if ref > 0 and cash < pct * ref:
        holds.append({"id": FLOOR_GUARD, "reason": floor_reason(cash, ref, pct), "owner": FLOOR_OWNER})
    conf: float | None = None
    if lot.get("imei"):  # a received device: the price confidence
        f = figures[best]
        params = pack.valuer.params["confidence"]
        conf = confidence(f["p10"], f["p50"], f["p90"]) if "p50" in f else 1.0
        fired = signals(figures, best, ranked, lot.get("inputs") or {}, params)
        threshold = next((float(s.confidence) for s in pack.stages if s.key == "decide"), DEFAULT_THRESHOLD)
        if [s for s in fired if s != "wide interval"] or conf < threshold:
            why = fired or ["confidence under threshold"]
            holds.append(
                {
                    "id": CONFIDENCE_GUARD, "reason": "Low price confidence: " + ", ".join(why),
                    "owner": CONFIDENCE_OWNER, "signals": fired,
                }
            )  # fmt: skip
    if not holds and conf is None:
        return None
    return {
        "kind": "person" if holds else "policy", "role": ROLE if holds else None,
        "reasons": [h["reason"] for h in holds], "holds": holds, "confidence": conf,
    }  # fmt: skip
