"""The repair estimate replayed on held-out repairs (plan 9, P9-4.5, story SD-08; measures I-14 `RepairCostModel`).

    holdout(history, cards_at, as_of, weeks, model, *, params, bar, only) -> [FamilyAccuracy]   pure: rows in, figures out
    compute(s, as_of, *, model) -> [AccuracyRow]                                  the Session wrapper; stores the day's rows
    bar() -> Bar                                                                  the pack's bar (GR-S1)

- **Held out.** Every repair closed in `(as_of - weeks, as_of]` with a known actual cost is estimated again as if it were a new
  ticket: from the repairs closed **before it** (never on or after its close day) inside the 3-year window, priced at the cards
  valid on its close day for its market. A repair whose market has no cards that day is left out (nothing to price it with).
- **Figures per tool class.** `n`; `mae`, the mean absolute difference of the estimate's `point` and the actual cost (converted
  to the estimate's currency at the fixed demo rates below); `mae_share`, the MAE over the median actual; `coverage`, the share
  of actuals inside `[p10, p90]`; `auto_share`, the share the estimate would have priced without a technician.
- **Instant pricing.** `instant` = `coverage >= min_coverage and mae_share <= max_mae_share`; the estimate never auto-prices a
  family whose newest row says otherwise (`service_desk.estimate`). Both numbers and `holdout_weeks` are GR-S1 parameters of the
  pack (`valuer.params.service_desk.gr_s1`).
- **Per org unit.** A row is for an org unit (its repairs are held out; its and the shared rows are the history) or, with org
  unit None, for the shared repairs alone.
- **Computed, never read by a model (R16).** Every figure is arithmetic on rows; no language model judges the estimate.

Never does: approve, promote, delete or change a model, a table or the bar, and it writes only `repair_accuracy` through
`repair_accuracy.replace_day`. The same routine is the "Estimate accuracy" replay Phase 7 reuses.
"""

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from sqlalchemy.orm import Session

from di.repositories import repair_accuracy as repo
from di.repositories.repair_accuracy import AccuracyRow
from di.repositories.repair_history import RepairRow
from di.services.modeler.pack import load_pack
from di.services.models.cost import PACK, Estimate, GrS1Params, PriceCards, RepairCostModel, RepairKey, age_band
from di.services.service_desk.estimate import _cards, _since, gr_s1

CardsAt = Callable[[date, str], PriceCards | None]
PER_USD = {"USD": Decimal(1), "EUR": Decimal("0.92"), "GBP": Decimal("0.79"), "AUD": Decimal("1.52")}  # demo rates, units per USD
FOUR = Decimal("0.0001")
CENT = Decimal("0.01")
MAX_SHARE = Decimal("99.9999")  # numeric(6,4)


@dataclass(frozen=True)
class Bar:
    """The bar of GR-S1 for instant pricing, and how many weeks are held out."""

    min_coverage: Decimal
    max_mae_share: Decimal
    holdout_weeks: int


@dataclass(frozen=True)
class FamilyAccuracy:
    model_class: str
    n: int
    mae: Decimal
    mae_share: Decimal
    coverage: Decimal
    auto_share: Decimal
    instant: bool


def bar() -> Bar:
    p = load_pack(PACK).valuer.params["service_desk"]["gr_s1"]
    return Bar(Decimal(str(p["min_coverage"])), Decimal(str(p["max_mae_share"])), int(p["holdout_weeks"]))


def _convert(amount: float, src: str | None, dst: str) -> Decimal | None:
    a, s, d = Decimal(str(amount)), PER_USD.get((src or "USD").upper()), PER_USD.get(dst.upper())
    return None if s is None or d is None else a / s * d


def holdout(
    history: Sequence[RepairRow],
    cards_at: CardsAt,
    as_of: date,
    weeks: int,
    model: RepairCostModel,
    *,
    params: GrS1Params,
    bar: Bar,
    only: Callable[[RepairRow], bool] | None = None,
) -> list[FamilyAccuracy]:
    """The held-out figures per tool class of `history`; `only` narrows which repairs are held out (they are all history)."""
    since = as_of - timedelta(days=7 * weeks)
    pool: dict[tuple[str, str | None], list[RepairRow]] = defaultdict(list)
    for r in sorted(history, key=lambda r: (r.closed_on, r.repair_number)):
        pool[(r.model_class, r.fault_code)].append(r)
    dates = {k: [r.closed_on for r in v] for k, v in pool.items()}
    seen: dict[str, list[tuple[Estimate, Decimal]]] = defaultdict(list)
    for r in sorted(history, key=lambda r: (r.closed_on, r.repair_number)):
        if not (since < r.closed_on <= as_of) or r.actual_cost is None or (only is not None and not only(r)):
            continue
        cards = cards_at(r.closed_on, r.market or "")
        if cards is None:
            continue
        key = (r.model_class, r.fault_code)
        rows = pool[key][bisect_left(dates[key], _since(r.closed_on, params.window_years)) : bisect_left(dates[key], r.closed_on)]
        e = model.estimate(rows, RepairKey(r.model_class, r.fault_code, age_band(r.age_months) or ""), cards, params, None)
        actual = _convert(r.actual_cost, r.currency, e.currency)
        if actual is not None:
            seen[r.model_class].append((e, actual))
    return [_family(cls, rows, bar) for cls, rows in sorted(seen.items())]


def _share(x: Decimal) -> Decimal:
    return min(x, MAX_SHARE).quantize(FOUR, ROUND_HALF_UP)


def _family(cls: str, rows: list[tuple[Estimate, Decimal]], bar: Bar) -> FamilyAccuracy:
    n = len(rows)
    mae = (sum((abs(e.point - a) for e, a in rows), Decimal(0)) / n).quantize(CENT, ROUND_HALF_UP)
    mid = Decimal(median(a for _, a in rows))
    mae_share = _share(mae / mid) if mid > 0 else MAX_SHARE
    coverage = _share(Decimal(sum(e.p10 <= a <= e.p90 for e, a in rows)) / n)
    auto = _share(Decimal(sum(e.auto for e, _ in rows)) / n)
    return FamilyAccuracy(
        cls, n, mae, mae_share, coverage, auto,
        coverage >= bar.min_coverage and mae_share <= bar.max_mae_share,
    )  # fmt: skip


def compute(s: Session, as_of: date, *, model: RepairCostModel | None = None) -> list[AccuracyRow]:
    """Replay the held-out repairs of every org unit with repairs (and the shared ones) and store the day's rows."""
    b, params = bar(), gr_s1()
    pairs = repo.window(s, _since(as_of - timedelta(days=7 * b.holdout_weeks), params.window_years), as_of + timedelta(days=1))
    out: list[AccuracyRow] = []
    for org in sorted({o for o, _ in pairs}, key=lambda o: (o is not None, o or "")):
        mine = [r for o, r in pairs if o is None or o == org]
        own = {r.repair_number for o, r in pairs if o == org}
        found = holdout(mine, _cards_at(s, org), as_of, b.holdout_weeks, model or RepairCostModel(), params=params, bar=b,
                        only=_of(own))  # fmt: skip
        for f in found:
            out.append(AccuracyRow(org, as_of, f.model_class, f.n, f.mae, f.mae_share, f.coverage, f.auto_share, f.instant))
    repo.replace_day(s, as_of, out)
    return out


def _of(numbers: set[str]) -> Callable[[RepairRow], bool]:
    return lambda r: r.repair_number in numbers


def _cards_at(s: Session, org: str | None) -> CardsAt:
    """The cards in force on a day for a market of the org unit (its own version first), read once per day and market."""
    cache: dict[tuple[date, str], PriceCards | None] = {}

    def cards_at(d: date, market: str) -> PriceCards | None:
        if (d, market) not in cache:
            cache[(d, market)] = _cards(s, org, market, d) if market else None
        return cache[(d, market)]

    return cards_at
