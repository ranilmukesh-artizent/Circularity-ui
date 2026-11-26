"""Calibration of the route value estimates on confirmed outcomes (plan 8, MVP-12.1; story M).

- `fit(rows)`: per (template, route, asset class), the median of actual/predicted net over the confirmed outcomes
  (rows with a zero prediction say nothing and are left out), when there are at least `min_n` of them, clipped to
  [0.5, 1.5].
- `CalibratedPredictor(base, factors, cls)`: the base predictor with each route's value estimate scaled by the factor
  for (template, route, cls); a route without a factor keeps the base estimate. It draws the same random numbers as
  the base, in the same order, so a factor of 1 changes nothing.

Pure: no Session, no I/O. The rows come from `di.repositories.outcomes`.
"""

import dataclasses
import statistics
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

from di.services.engine.jsmath import js_round
from di.services.engine.predictor import Asset, Predictor, PriceBand

MIN_FACTOR, MAX_FACTOR = 0.5, 1.5
Key = tuple[str, str, str]  # (template, route, asset class)


class OutcomeRow(TypedDict):
    case_id: str
    template: str
    cls: str
    route: str
    predicted_net: float
    actual_net: float
    confirmed_at: str


def fit(rows: Sequence[OutcomeRow], min_n: int = 5) -> dict[Key, float]:
    ratios: dict[Key, list[float]] = {}
    for r in rows:
        if r["predicted_net"]:
            ratios.setdefault((r["template"], r["route"], r["cls"]), []).append(r["actual_net"] / r["predicted_net"])
    return {k: min(MAX_FACTOR, max(MIN_FACTOR, statistics.median(xs))) for k, xs in ratios.items() if len(xs) >= min_n}


class CalibratedPredictor:
    """Scales the value estimate of each standard route (`evaluate.build_routes`): resale's sale proceeds, redeploy's
    avoided purchase, re-lease's lease income, the parts value of intparts and extparts, and material's material
    value. Costs and the market value are the base's."""

    def __init__(self, base: Predictor, factors: Mapping[Key, float], cls: str, template: str = "industrial"):
        self.base, self.factors, self.cls, self.template = base, factors, cls, template

    def _f(self, route: str) -> float:
        return self.factors.get((self.template, route, self.cls), 1.0)

    def _scale(self, route: str, v: int) -> int:
        f = self._f(route)
        return v if f == 1.0 else js_round(v * f)

    def channel_price(self, facts: Mapping[str, Any], channel: str) -> PriceBand:
        """The base's band with its prices scaled by the factor of the route named like the channel (a device pack's channels
        are its routes, P9-13.7); a channel without a factor keeps the base's band."""
        b = self.base.channel_price(facts, channel)
        f = self._f(channel)
        return b if f == 1.0 else dataclasses.replace(b, p10=b.p10 * f, p50=b.p50 * f, p90=b.p90 * f)

    def market_value(self, a: Asset) -> float:
        return self.base.market_value(a)

    def sale(self, a: Asset, mv: float) -> tuple[int, int]:
        sale, fees = self.base.sale(a, mv)
        return self._scale("resale", sale), fees

    def refurbishment(self, a: Asset, sale: int) -> tuple[int, int]:
        return self.base.refurbishment(a, sale)

    def avoided_purchase(self, a: Asset) -> int:
        return self._scale("redeploy", self.base.avoided_purchase(a))

    def prep_cost(self, a: Asset) -> int:
        return self.base.prep_cost(a)

    def service_cost(self, a: Asset) -> int:
        return self.base.service_cost(a)

    def residual(self, a: Asset) -> int:
        return self.base.residual(a)

    def lease_income(self, a: Asset) -> int:
        return self._scale("relase", self.base.lease_income(a))

    def parts_value(self, a: Asset, internal: bool) -> int:
        return self._scale("intparts" if internal else "extparts", self.base.parts_value(a, internal))

    def material(self, a: Asset) -> tuple[int, int]:
        mat, proc = self.base.material(a)
        return self._scale("material", mat), proc
