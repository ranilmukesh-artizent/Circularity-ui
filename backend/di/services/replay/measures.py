"""The four measures of a replay (plan 9, P9-7.2; registry entry I-16; story X-06; A section 3.2): pure arithmetic over what
the replay decided, so a number is always code, never a model's.

Owns: the route mix (actual vs flow), the straight-through share, approvals and exceptions per business day, and the
uplift with its secondary estimate (`bias`) and the conservative figure. Never does: decide anything, read the database or
the clock, or write text. Percentages are 0 to 100 with one decimal; an uplift is a percentage with two decimals.

Uplift (A section 3.2, exact):
- primary = sum(flow net - actual net) / sum(abs(actual net));
- bias = median(realised value / actual net) over the agreement set (flow route = actual route, actual net not 0);
- secondary = sum(flow net x bias - realised value) / sum(abs(realised value));
- conservative = the lower of the two. Both are estimates of the counterfactual ("modelled"), as E section 5.1 says.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from statistics import median
from typing import Any


def pct(part: float, whole: float) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def business_days(first: date, last: date) -> int:
    """The Monday to Friday days from `first` to `last` inclusive (at least 1: a replay of one weekend day is one day)."""
    n, d = 0, first
    while d <= last:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return max(n, 1)


def route_mix(actual: Sequence[str | None], flow: Sequence[str | None], order: Iterable[str] = ()) -> list[dict[str, Any]]:
    """[{route, actual_pct, flow_pct}] over the routes either side used, the pack's `order` first. Items the flow left with no
    recommendation count in the base, so the flow side may add up to less than 100."""
    a, f = Counter(x for x in actual if x), Counter(x for x in flow if x)
    ids = [r for r in order if r in a or r in f]
    ids += sorted((set(a) | set(f)) - set(ids))
    return [{"route": r, "actual_pct": pct(a[r], len(actual)), "flow_pct": pct(f[r], len(flow))} for r in ids]


def per_day(count: int, days: int) -> float:
    return round(count / max(days, 1), 2)


def bias(pairs: Iterable[tuple[float, float]]) -> float:
    """The median of realised value / actual net over (actual net, realised) pairs of the agreement set; 1.0 with none."""
    ratios = [real / net for net, real in pairs if net]
    return round(median(ratios), 4) if ratios else 1.0


def ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


def uplift(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    """primary, secondary, bias and conservative (percent, two decimals; bias a ratio) of rows
    `{actual_net, flow_net, realised, agree}`."""
    b = bias((r["actual_net"], r["realised"]) for r in rows if r["agree"] and r["actual_net"])
    primary = ratio(sum(r["flow_net"] - r["actual_net"] for r in rows), sum(abs(r["actual_net"]) for r in rows))
    secondary = ratio(sum(r["flow_net"] * b - r["realised"] for r in rows), sum(abs(r["realised"]) for r in rows))
    return {
        "primary": round(100 * primary, 2), "secondary": round(100 * secondary, 2), "bias": b,
        "conservative": round(100 * min(primary, secondary), 2),
    }  # fmt: skip
