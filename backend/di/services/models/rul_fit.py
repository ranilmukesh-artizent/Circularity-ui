"""Fit the remaining-life model on teardown verdicts (plan 9, P9-3.10, I-14, stories TF-06 and TF-15).

    fit_rated_life(rows: Sequence[TeardownRow], cls: str) -> RatedLifeCandidate

Per component of the class a Weibull (`lifelines.WeibullFitter`) on the run hours of its verdicts: `worn_out` is the event,
`serviceable` is right-censored (the component was still good at that many hours). The result is, per component,
`{name, shape, scale, median_hours, n, events}` (`rho_` the shape, `lambda_` the scale; `RulModel` does the math on them).

- A component needs at least 30 verdicts (and 5 worn out), else it is skipped, keeps the rating it has (PLM, then the pack's
  table) and `skipped` says why.
- Metrics: the fit is repeated on the verdicts before the last 3 months (before the newest verdict's date minus 90 days) and
  tested on the verdicts after them. `mae` is the mean absolute difference, in run hours, of the predicted median life and the
  observed run hours of the held-out worn-out components; `concordance` is lifelines' concordance index of the predicted median
  against the held-out run hours (censored rows included), pooled over the class's components. Each is None without enough
  rows on both sides of the cut.

The only module that imports lifelines (and pandas, numpy through it); `model.fit` imports this one inside its handler, so no
other request loads them. Never does: read the database, learn without a person promoting the result, or call a language model.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from lifelines import WeibullFitter  # type: ignore[import-untyped]
from lifelines.utils import concordance_index  # type: ignore[import-untyped]

from di.services.models.rul import TeardownRow, life_at

MIN_VERDICTS = 30
MIN_WORN = 5
HELD_OUT = timedelta(days=90)
FEW = f"Needs at least {MIN_VERDICTS} verdicts; it keeps its current rating."


@dataclass(frozen=True)
class RatedLifeCandidate:
    cls: str
    components: list[dict[str, Any]]
    skipped: list[dict[str, Any]]
    n: int
    held_out: int = 0
    mae: float | None = None
    concordance: float | None = None
    notes: list[str] = field(default_factory=list)


def _weibull(rows: Sequence[TeardownRow]) -> tuple[float, float] | None:
    """(shape, scale) of the rows' run hours, or None when the fit does not converge."""
    try:
        w = WeibullFitter().fit([r.run_hours for r in rows], event_observed=[r.verdict == "worn_out" for r in rows])
        shape, scale = float(w.rho_), float(w.lambda_)
    except Exception:  # noqa: BLE001 - lifelines raises its own errors and numpy's; any of them means "no model for this one"
        return None
    return (shape, scale) if shape > 0 and scale > 0 and math.isfinite(shape) and math.isfinite(scale) else None


def fit_rated_life(rows: Sequence[TeardownRow], cls: str) -> RatedLifeCandidate:
    usable = [r for r in rows if r.run_hours > 0 and r.verdict in ("worn_out", "serviceable")]
    by: dict[str, list[TeardownRow]] = {}
    for r in usable:
        by.setdefault(r.component, []).append(r)
    comps: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    fitted: dict[str, tuple[float, float]] = {}
    for name, rs in sorted(by.items()):
        worn = sum(r.verdict == "worn_out" for r in rs)
        reason = None
        if len(rs) < MIN_VERDICTS:
            reason = FEW
        elif worn < MIN_WORN:
            reason = f"Needs at least {MIN_WORN} worn-out verdicts; it keeps its current rating."
        wb = None if reason else _weibull(rs)
        if wb is None:
            why = reason or "The fit did not converge; it keeps its current rating."
            skipped.append({"name": name, "n": len(rs), "reason": why})
            continue
        fitted[name] = wb
        median = round(life_at(*wb, 0.5), 1)
        comps.append({"name": name, "shape": wb[0], "scale": wb[1], "median_hours": median, "n": len(rs), "events": worn})
    if not fitted:
        return RatedLifeCandidate(cls, comps, skipped, len(usable))
    cut = max(r.observed_at for r in usable) - HELD_OUT
    errs: list[float] = []
    dur: list[float] = []
    score: list[float] = []
    ev: list[bool] = []
    for name in fitted:
        train = [r for r in by[name] if r.observed_at <= cut]
        test = [r for r in by[name] if r.observed_at > cut]
        if len(train) < 10 or sum(r.verdict == "worn_out" for r in train) < 3 or not test:
            continue
        wb = _weibull(train)
        if wb is None:
            continue
        median = life_at(*wb, 0.5)
        errs += [abs(median - r.run_hours) for r in test if r.verdict == "worn_out"]
        dur += [r.run_hours for r in test]
        score += [median] * len(test)
        ev += [r.verdict == "worn_out" for r in test]
    mae = sum(errs) / len(errs) if errs else None
    try:
        conc: float | None = float(concordance_index(dur, score, ev)) if dur else None
    except ZeroDivisionError:  # no comparable pair in the held-out rows
        conc = None
    notes = [] if mae is not None else ["Too few verdicts in the last 3 months to hold out: no error figure."]
    return RatedLifeCandidate(cls, comps, skipped, len(usable), len(dur), mae, conc, notes)
