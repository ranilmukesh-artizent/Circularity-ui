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


# ---------------------------------------------------------------- the report page (P9-7.6, A section 3.5)
METHOD_NOTE = (
    "As-of rule: every past item is decided on the facts known at its own decision date; a reading dated later is left out "
    "and listed. Yardstick: the flow and the route actually taken are valued by the same valuer, so the comparison is "
    "estimated against estimated, never against the realised value alone. Leakage test: the replay refuses any fact dated "
    "after the decision, and the report lists each one it dropped. Bias caveats: the uplift is modelled, the conservative "
    "figure is the lower of two estimates, past routes were chosen with information the flow may lack, and realised values "
    "exist only for routes that were taken. Sensitivity runs are not included."
)


def method_note() -> str:
    """The fixed method text of the report page: the page shows this string from the action output, never its own copy."""
    return METHOD_NOTE


def waterfall(report: dict[str, Any]) -> list[dict[str, Any]]:
    """A section 3.5's waterfall: actual net; same-route repricing (bias); one step per route the flow changed to; constraint
    losses; then the net uplift. Each step is `{step, amount, kind}`: `base` (the actual net), `delta`, or `result` (the net
    uplift, flow net minus actual net). The base and the deltas sum to the flow's net. A report from before P9-7.6 has no
    totals and gives no waterfall."""
    if "flow_net" not in report or "actual_net" not in report:
        return []
    steps: list[dict[str, Any]] = [
        {"step": "Actual net", "amount": round(report["actual_net"], 4), "kind": "base"},
        {"step": "Same-route repricing (bias)", "amount": round(report.get("repricing", 0.0), 4), "kind": "delta"},
    ]
    for c in report.get("route_changes", []):
        steps.append({"step": f"Route change to {c['route']}", "amount": round(c["amount"], 4), "kind": "delta"})
    steps.append({"step": "Constraint losses", "amount": round(-report.get("constraint_loss", 0.0), 4), "kind": "delta"})
    steps.append({"step": "Net uplift", "amount": round(report["flow_net"] - report["actual_net"], 4), "kind": "result"})
    return steps


def top_flips_explained(report: dict[str, Any], n: int = 10) -> list[dict[str, Any]]:
    """The `n` largest flips (by the size of the change) with from route, to route, delta, the deciding gate or rule and the
    decision's own trace text. The reason text is the one the replay composed from the gate result."""
    flips = sorted(report.get("flips", []), key=lambda f: -abs(f["delta"]))[:n]
    return [
        {"item_id": f["item_id"], "from": f["actual"], "to": f["flow"], "delta": f["delta"], "reason": f["reason"],
         "gate": f.get("gate"), "trace": f.get("trace", "")}
        for f in flips
    ]  # fmt: skip
