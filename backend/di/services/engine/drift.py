"""Drift of a fitted model against the outcomes that closed after it was trained (plan 9, P9-13.8; E section 11.5). Pure.

    psi(expected, actual, bins=10)   population stability index; equal-frequency bins on `expected`, 1e-4 floor per bin
    error_drift(train_mae, recent_mae)   the ratio of the error now to the error at training
    status(psi, ratio)               "alert" over PSI 0.25 or ratio 1.5, "watch" over PSI 0.10 or ratio 1.2, else "ok"
    rule(psi, ratio)                 the sentence that says which limit set the status
    next_due(trained_at, new_outcomes, now)   monthly, or at once when 50 new confirmed outcomes have closed
Never does: read the database or call a model; every number the Models panel shows about drift comes from here.
"""

import math
from bisect import bisect_right
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal

PSI_ALERT, PSI_WATCH = 0.25, 0.10
RATIO_ALERT, RATIO_WATCH = 1.5, 1.2
FLOOR = 1e-4
CADENCE_DAYS = 30
CADENCE_OUTCOMES = 50
CADENCE_TEXT = f"Monthly, or {CADENCE_OUTCOMES} new confirmed outcomes, whichever comes first"
Status = Literal["ok", "watch", "alert"]


def psi(expected: Sequence[float], actual: Sequence[float], bins: int = 10) -> float:
    if not expected or not actual:
        return 0.0
    xs = sorted(expected)
    edges = sorted({xs[len(xs) * k // bins] for k in range(1, bins)})

    def shares(v: Sequence[float]) -> list[float]:
        counts = [0] * (len(edges) + 1)
        for x in v:
            counts[bisect_right(edges, x)] += 1
        return [max(c / len(v), FLOOR) for c in counts]

    return sum((a - e) * math.log(a / e) for e, a in zip(shares(expected), shares(actual), strict=True))


def error_drift(train_mae: float, recent_mae: float) -> float:
    if train_mae <= 0 and recent_mae <= 0:
        return 1.0
    return recent_mae / max(train_mae, 0.01)


def status(psi_value: float, ratio: float) -> Status:
    if psi_value > PSI_ALERT or ratio > RATIO_ALERT:
        return "alert"
    return "watch" if psi_value > PSI_WATCH or ratio > RATIO_WATCH else "ok"


def rule(psi_value: float, ratio: float) -> str:
    """Which limit set the status, in words (the text of the work item and the Models panel)."""
    st = status(psi_value, ratio)
    if st == "ok":
        return f"PSI {psi_value:.2f} and error ratio {ratio:.2f} are inside the limits"
    psi_lim, ratio_lim = (PSI_ALERT, RATIO_ALERT) if st == "alert" else (PSI_WATCH, RATIO_WATCH)
    hits = []
    if psi_value > psi_lim:
        hits.append(f"PSI {psi_value:.2f} is over {psi_lim:g}")
    if ratio > ratio_lim:
        hits.append(f"error ratio {ratio:.2f} is over {ratio_lim:g}")
    return " and ".join(hits)


def next_due(trained_at: datetime, new_outcomes: int, now: datetime) -> datetime:
    return (
        min(now, trained_at + timedelta(days=CADENCE_DAYS))
        if new_outcomes >= CADENCE_OUTCOMES
        else trained_at + timedelta(days=CADENCE_DAYS)
    )
