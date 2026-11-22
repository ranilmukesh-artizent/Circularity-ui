"""What each route's terms are worth: the demo's valuation formulas behind a `Predictor` interface.

The demo's predictions are computed, not trained (the formulas in its buildRoutes). Each quantity is one method, so a
trained model (XGBoost or LightGBM, as the demo names) can replace one formula at a time: subclass
`FormulaPredictor` and override that method.

The formulas draw random factors (the demo's market noise and price spreads). `FormulaPredictor` takes the random
source, so tests can pin it; the draws happen in the demo's order.
"""

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from di.services.engine.jsmath import js_round

# per asset class: price of a new unit and the age (years) over which value decays by 1/e (the demo's CLASSES)
CLASSES: dict[str, dict[str, float]] = {
    "motor": {"pnew": 11800, "tau": 11},
    "pump": {"pnew": 6400, "tau": 9},
    "control": {"pnew": 4300, "tau": 7},
    "drill": {"pnew": 340, "tau": 4.5},
    "batch": {"pnew": 150, "tau": 4},
    "it": {"pnew": 820, "tau": 3.2},
}
GRADE_F = {"A": 1, "B": 0.86, "C": 0.64, "D": 0.38}
HEAVY = ("motor", "pump")  # crated freight, not parcel


@dataclass(frozen=True)
class Asset:
    cls: str
    grade: str  # A-D; an ungraded asset is valued as C
    age: float  # years
    qty: int = 1

    @property
    def pnew(self) -> float:
        return CLASSES[self.cls]["pnew"]

    @property
    def tau(self) -> float:
        return CLASSES[self.cls]["tau"]

    @property
    def gf(self) -> float:
        return GRADE_F[self.grade]


class Predictor(Protocol):
    def market_value(self, a: Asset) -> float: ...
    def sale(self, a: Asset, mv: float) -> tuple[int, int]: ...  # (expected proceeds, fees and freight)
    def refurbishment(self, a: Asset, sale: int) -> tuple[int, int]: ...  # (price uplift, refurbishment cost)
    def avoided_purchase(self, a: Asset) -> int: ...
    def prep_cost(self, a: Asset) -> int: ...
    def service_cost(self, a: Asset) -> int: ...
    def residual(self, a: Asset) -> int: ...
    def lease_income(self, a: Asset) -> int: ...  # over the 30-month horizon
    def parts_value(self, a: Asset, internal: bool) -> int: ...
    def material(self, a: Asset) -> tuple[int, int]: ...  # (material value, processing and logistics)


def _box_muller(rnd: Callable[[], float]) -> float:
    """The demo's gauss(): a standard normal from two uniform draws, redrawing zeros."""
    u = 0.0
    while not u:
        u = rnd()
    v = 0.0
    while not v:
        v = rnd()
    return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)


class FormulaPredictor:
    """The demo's formulas. `rnd` returns a uniform float in [0, 1)."""

    model_version = "v1.3"

    def __init__(self, rnd: Callable[[], float] | None = None):
        self.rnd = rnd or random.Random(20261007).random  # noqa: S311 - seeded for repeatable demo numbers, not security

    def market_value(self, a: Asset) -> float:
        # depreciation by age, grade factor, quantity, and 8% log-normal market noise
        return a.pnew * math.exp(-a.age / a.tau) * a.gf * a.qty * math.exp(_box_muller(self.rnd) * 0.08)

    def sale(self, a: Asset, mv: float) -> tuple[int, int]:
        sale = js_round(mv * (0.92 + self.rnd() * 0.1))
        handling = 140 if a.cls in HEAVY else 12 * math.sqrt(a.qty)
        return sale, js_round(sale * (0.08 + self.rnd() * 0.05) + handling)

    def refurbishment(self, a: Asset, sale: int) -> tuple[int, int]:  # noqa: ARG002 - same signature as the other estimates
        return js_round(sale * (0.04 + self.rnd() * 0.14)), js_round(sale * (0.06 + self.rnd() * 0.09))

    def avoided_purchase(self, a: Asset) -> int:
        return js_round(a.pnew * a.qty * (0.78 + self.rnd() * 0.2))

    def prep_cost(self, a: Asset) -> int:
        return js_round(a.pnew * a.qty * (0.06 + self.rnd() * 0.1))

    def service_cost(self, a: Asset) -> int:
        return js_round(a.pnew * a.qty * (0.02 + self.rnd() * 0.06))

    def residual(self, a: Asset) -> int:
        return js_round(a.pnew * a.qty * 0.02)

    def lease_income(self, a: Asset) -> int:
        return js_round(a.pnew * a.qty * (0.16 + self.rnd() * 0.14) * a.gf)

    def parts_value(self, a: Asset, internal: bool) -> int:
        lo, width = (0.22, 0.16) if internal else (0.17, 0.12)
        return js_round(a.pnew * a.qty * (lo + self.rnd() * width) * max(a.gf, 0.5))

    def material(self, a: Asset) -> tuple[int, int]:
        mat = js_round(a.pnew * a.qty * (0.03 + self.rnd() * 0.025))
        return mat, js_round(mat * 0.4 + 10 * math.sqrt(a.qty))
