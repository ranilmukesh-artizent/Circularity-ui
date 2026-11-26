"""The canary's report, in numbers (plan 9, P9-7.4; registry entry I-17; story X-06): arm statistics, the band of the
difference, the sample the comparison needs, and the stop rules.

Pure: no database, no clock, no model. Every figure here is computed by code (R16: a model never invents a number; the report
has no free text beyond the fixed breach and note sentences below). The rows come from di.repositories.rollouts.arm_rows, one
per case assigned to the canary or its control (the rest of the same region in the same period, E 11.6). A breach only ever
moves towards the known-good version (an automatic pause, di.services.actions.rollout `rollout.autoPause`); widening, adding
a region and going full are never decided here.

    arm_stats(rows)                         n, override_rate, exception_rate, hold_rate, mean_net, mean_realised
    diff_band(canary_nets, control_nets)    80 % and 95 % bands of the difference of means (bootstrap, fixed seed)
    n_needed(control_nets, delta_share)     cases per arm to see a `delta_share` change of the mean net
    stop_check(canary, control, rules)      the first breach sentence, or None
"""

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

DEFAULT_RULES: dict[str, float] = {"exception_margin": 0.05, "override_margin": 0.05, "hold_margin": 0.05, "min_cases": 30}
TOO_FEW = "Too few cases to tell a difference yet"
_RULE_OF = (
    ("exception_rate", "exception_margin", "exceptions"),
    ("override_rate", "override_margin", "overrides"),
    ("hold_rate", "hold_margin", "holds"),
)


def rules_of(stored: Mapping[str, Any] | None) -> dict[str, float]:
    """The rules a canary was started with: the stored ones over the defaults (a row from before the rules has none)."""
    out = dict(DEFAULT_RULES)
    for k in DEFAULT_RULES:
        v = (stored or {}).get(k)
        if isinstance(v, int | float) and not isinstance(v, bool) and v >= 0:
            out[k] = v
    return out


def _mean(xs: Sequence[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def arm_stats(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The arm's figures over its cases. A row is {decided, override, exception, hold, net, realised}; the override rate is of
    the decided cases, the exception and hold rates of every case in the arm; the means are over the cases that have the value."""
    n = len(rows)
    decided = sum(1 for r in rows if r.get("decided"))
    overrides = sum(1 for r in rows if r.get("override"))
    nets = [float(r["net"]) for r in rows if r.get("net") is not None]
    real = [float(r["realised"]) for r in rows if r.get("realised") is not None]
    return {
        "n": n,
        "decided": decided,
        "override_rate": overrides / decided if decided else 0.0,
        "exception_rate": sum(1 for r in rows if r.get("exception")) / n if n else 0.0,
        "hold_rate": sum(1 for r in rows if r.get("hold")) / n if n else 0.0,
        "mean_net": _mean(nets),
        "mean_realised": _mean(real),
    }


def _pct(xs: list[float], p: float) -> float:
    k = (len(xs) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def diff_band(
    canary_nets: Sequence[float], control_nets: Sequence[float], n: int = 1000, seed: int = 2611
) -> dict[str, Any] | None:
    """Bootstrap of the difference of means (canary minus control): {diff, band80, band95}, each band [low, high]. None while
    an arm has no values. The same inputs always give the same bands (fixed seed)."""
    if not canary_nets or not control_nets:
        return None
    rng = random.Random(seed)  # noqa: S311 - a bootstrap, not a secret: the fixed seed repeats the report
    c, k = list(canary_nets), list(control_nets)
    diffs = sorted(sum(rng.choices(c, k=len(c))) / len(c) - sum(rng.choices(k, k=len(k))) / len(k) for _ in range(n))
    return {
        "diff": sum(c) / len(c) - sum(k) / len(k),
        "band80": [_pct(diffs, 0.10), _pct(diffs, 0.90)],
        "band95": [_pct(diffs, 0.025), _pct(diffs, 0.975)],
    }


def n_needed(control_nets: Sequence[float], delta_share: float = 0.05) -> int:
    """Cases per arm to see a `delta_share` change of the mean net: ceil(16 x variance / (delta_share x mean)^2). 0 when the
    control has fewer than two values or a mean of 0 (nothing to size against)."""
    if len(control_nets) < 2:
        return 0
    m = sum(control_nets) / len(control_nets)
    if m == 0:
        return 0
    var = sum((x - m) ** 2 for x in control_nets) / (len(control_nets) - 1)
    return math.ceil(16 * var / (delta_share * m) ** 2)


def stop_check(canary: Mapping[str, Any], control: Mapping[str, Any], rules: Mapping[str, Any]) -> str | None:
    """The first breach of the stop rules, as a sentence, once both arms have `min_cases`; else None."""
    need = rules.get("min_cases", DEFAULT_RULES["min_cases"])
    if canary["n"] < need or control["n"] < need:
        return None
    for rate, margin, word in _RULE_OF:
        m = rules.get(margin, DEFAULT_RULES[margin])
        if canary[rate] - control[rate] > m + 1e-9:
            return (
                f"Canary {word} {canary[rate] * 100:.0f} % exceed control {control[rate] * 100:.0f} % "
                f"by more than {m * 100:g} points."
            )
    return None


def sample_note(canary: Mapping[str, Any], control: Mapping[str, Any], needed: int, rules: Mapping[str, Any]) -> str | None:
    """TOO_FEW while either arm is below the cases the comparison needs (or the stop rules' minimum), else None."""
    floor = max(needed, int(rules.get("min_cases", DEFAULT_RULES["min_cases"])))
    return TOO_FEW if canary["n"] < floor or control["n"] < floor else None
