"""Fit the take-up curve on past upgrade offers (plan 9, P9-4.11, story SD-11; model kind `take_up`, I-14).

    fit_curve(rows: Sequence[OfferRow], iterations: int = 25) -> TakeUpFit

A logistic regression of `accepted` on the credit share offered, `p = 1 / (1 + exp(-(a + b x credit_pct)))`, by Newton-Raphson on
the log-likelihood: both parameters from zero, a fixed number of iterations, so the same rows always give the same fit. Two
parameters need no library (the spec's choice over scikit-learn). Metrics are on the rows it was fitted on: `log_loss`,
`brier`, and eight equal-width credit bands with how many offers they held, how many were taken and how many the curve expected.
`score` gives the same two errors for any curve (the pack's prior, as the baseline the candidate must beat).

A statistical model, never a language model (R16). Never does: read the database, learn without a person promoting the result,
or look at the account (the account's own lean is a separate shift, `service_desk.inputs.account_shift`).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from di.repositories.upgrade_offers import OfferRow

MIN_OFFERS = 200
BANDS = 8
TOO_FEW = f"A take-up model needs at least {MIN_OFFERS} offers in 24 months."
_EPS = 1e-12


@dataclass(frozen=True)
class TakeUpFit:
    a: float
    b: float
    n: int
    log_loss: float
    brier: float
    bands: list[dict[str, Any]]


def _p(a: float, b: float, x: float) -> float:
    z = a + b * x
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def score(a: float, b: float, points: Sequence[tuple[float, bool]]) -> tuple[float, float]:
    """(log loss, Brier score) of the curve `{a, b}` on (credit_pct, accepted) points."""
    ll = br = 0.0
    for x, y in points:
        p = min(max(_p(a, b, x), _EPS), 1 - _EPS)
        ll -= math.log(p if y else 1 - p)
        br += (p - y) ** 2
    return ll / len(points), br / len(points)


def points_of(rows: Sequence[OfferRow]) -> list[tuple[float, bool]]:
    """The offers that carry a credit share, as (credit_pct, accepted)."""
    return [(r.credit_pct, r.accepted) for r in rows if r.credit_pct is not None]


def fit_curve(rows: Sequence[OfferRow], iterations: int = 25) -> TakeUpFit:
    pts = points_of(rows)
    if len(pts) < MIN_OFFERS:
        raise ValueError(TOO_FEW)
    a = b = 0.0
    for _ in range(iterations):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, y in pts:
            p = _p(a, b, x)
            r, w = y - p, p * (1 - p)
            g0 += r
            g1 += r * x
            h00 += w
            h01 += w * x
            h11 += w * x * x
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:  # one credit share only, or a perfect split: nothing more to learn
            break
        a += (h11 * g0 - h01 * g1) / det
        b += (h00 * g1 - h01 * g0) / det
    ll, br = score(a, b, pts)
    return TakeUpFit(a, b, len(pts), ll, br, _bands(a, b, pts))


def _bands(a: float, b: float, pts: Sequence[tuple[float, bool]]) -> list[dict[str, Any]]:
    lo, hi = min(x for x, _ in pts), max(x for x, _ in pts)
    width = (hi - lo) / BANDS or 1.0
    out = [
        {"lo": lo + k * width, "hi": lo + (k + 1) * width, "offered": 0, "accepted": 0, "predicted": 0.0} for k in range(BANDS)
    ]
    for x, y in pts:
        band = out[min(int((x - lo) / width), BANDS - 1)]
        band["offered"] += 1
        band["accepted"] += int(y)
        band["predicted"] += _p(a, b, x)
    for band in out:
        band["predicted"] = round(band["predicted"], 2)
    return out
