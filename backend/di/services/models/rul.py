"""Remaining life of a tool's components from a fitted Weibull model (plan 9, P9-3.10, I-14, stories TF-06 and TF-15). Pure.

    RulModel(params, version="").predict(component, used_hours) -> RulEstimate   remaining life, its spread, survival of a term
    RulModel.median(component) -> hours                                           the closed-form Weibull median life
    RulModel.for_class(factors, cls, version) -> RulModel                         the stored model of one tool class
    TeardownRow                                                                   one teardown verdict, as the fit reads it

`params` is `{"components": [{name, shape, scale}], "term_hours": float}`: per component the Weibull shape `k` and scale `lam`
(run hours) that `rul_fit.fit_rated_life` stored. With survival `S(t) = exp(-(t / lam) ** k)` the life at survival `q` is
`lam * (-ln q) ** (1 / k)`: the median at q = 0.5, the P10 life (10 % of tools have worn out) at q = 0.9 and the P90 life at
q = 0.1. A component used `u` hours has `rul_pct = round(100 * (1 - u / median))`, held to 0..100 (the consumed share the
deterministic table uses, with the median as the rated life); `p10` and `p90` are the same at the P10 and P90 lives, so
`p10 <= rul_pct <= p90`. `p_survive_term` is the chance it survives `term_hours` more (default 500, about a year of duty)
given it has survived `u`: `S(u + term) / S(u)`.

Never does: load the fitting library (only `rul_fit` does, inside the `model.fit` handler, so a request never loads it), read the
database or the clock, or learn. A statistical model, not a language model: no AgentLoop. Implements I-14 `RulModel`.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

TERM_HOURS = 500.0


@dataclass(frozen=True)
class TeardownRow:
    """One teardown verdict of the depot repair log (`repair_event`, kind `teardown`)."""

    serial: str
    component: str
    run_hours: float
    verdict: str  # worn_out or serviceable
    observed_at: datetime
    org: str | None = None  # the org of the serial's contract; None: depot-wide history


@dataclass(frozen=True)
class RulEstimate:
    rul_pct: int
    p10: int
    p90: int
    p_survive_term: float


def _round(x: float) -> int:
    return int(math.floor(x + 0.5))


def life_at(shape: float, scale: float, survival: float) -> float:
    """The run hours by which a share `1 - survival` of the components has worn out."""
    return scale * (-math.log(survival)) ** (1 / shape)


class RulModel:
    def __init__(self, params: Mapping[str, Any], version: str = "") -> None:
        self.version = version
        self.term_hours = float(params.get("term_hours") or TERM_HOURS)
        self._w = {str(c["name"]): (float(c["shape"]), float(c["scale"])) for c in params.get("components") or []}

    @classmethod
    def for_class(cls, factors: Sequence[Mapping[str, Any]], tool_class: str, version: str = "") -> "RulModel":
        """The model of one tool class from a stored model's `factors` ([{cls, name, shape, scale, ...}])."""
        return cls({"components": [f for f in factors if f.get("cls") == tool_class]}, version)

    def has(self, component: str) -> bool:
        return component in self._w

    def median(self, component: str) -> float:
        shape, scale = self._w[component]
        return life_at(shape, scale, 0.5)

    def lives(self, component: str) -> tuple[float, float, float]:
        """(P10 life, median, P90 life) in run hours."""
        shape, scale = self._w[component]
        return life_at(shape, scale, 0.9), life_at(shape, scale, 0.5), life_at(shape, scale, 0.1)

    def predict(self, component: str, used_hours: float) -> RulEstimate:
        shape, scale = self._w[component]
        lo, mid, hi = self.lives(component)

        def pct(life: float) -> int:
            return max(0, min(100, _round(100 * (1 - used_hours / life))))

        def surv(t: float) -> float:
            return math.exp(-((t / scale) ** shape))

        return RulEstimate(pct(mid), pct(lo), pct(hi), round(surv(used_hours + self.term_hours) / surv(used_hours), 4))
