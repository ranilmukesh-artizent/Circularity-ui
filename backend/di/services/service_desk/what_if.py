"""Test a credit before offering it (plan 9, P9-4.10, story SD-09): the options of a ticket run again with the levers moved.

    check(inputs, ...) -> dict      per line the options, the best, whether it flips, and the expected margin over credit 0 .. 40%

The inputs are `inputs.gather`'s snapshot of the case. A copy is changed and `decide_ticket` (P9-4.6, the same valuer the case
page uses) decides it again; nothing is read from or written to the case. The levers: the credit share (applied without the credit
table's cap, so a person can test a credit the table would not give; GR-C1 is still shown), the take-up (a flat chance replacing
the curve), the repair cost (a share of the estimate) and extra days waiting for the fix.

Never does: write, send, approve, or call a language model (every number is computed, R16).
"""

import copy
import math
from collections.abc import Mapping
from typing import Any

from di.services.modeler.valuers import service_desk

RANGES: dict[str, tuple[float, float]] = {
    "credit_pct": (0.0, 0.40),
    "take_up": (0.0, 1.0),
    "repair_cost_pct": (80.0, 150.0),
    "wait_days": (0.0, 90.0),
}
STEP = 0.05  # the curve's points
FINE = 0.01  # the crossing is found on this grid
UNCAPPED = 1e12


def out_of_range(levers: Mapping[str, Any]) -> str | None:
    """The first lever that is not a number inside its range, as a sentence; None when all are fine."""
    for k, (lo, hi) in RANGES.items():
        v = levers.get(k)
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, int | float) or not lo <= v <= hi:
            return f"{k} must be between {lo:g} and {hi:g}."
    return None


def _logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


def _moved(inputs: Mapping[str, Any], levers: Mapping[str, Any], credit: float | None, only: int | None) -> dict[str, Any]:
    """A copy of the inputs with the levers applied to line `only` (all lines when None)."""
    x = copy.deepcopy(dict(inputs))
    if levers.get("take_up") is not None:
        x["take_up"] = {"a": _logit(float(levers["take_up"])), "b": 0.0, "shift": 0.0, "source": "what-if"}
    pct = credit if credit is not None else levers.get("credit_pct")
    for ln in x["lines"]:
        if only is not None and ln["n"] != only:
            continue
        if pct is not None:
            ln["credit"] = {**ln["credit"], "credit_pct": float(pct), "credit_cap": UNCAPPED}
        if levers.get("repair_cost_pct") is not None and ln.get("estimate") and ln["estimate"].get("n"):
            f = float(levers["repair_cost_pct"]) / 100
            e = ln["estimate"]
            e["point"] = float(e["point"]) * f
            e["lines"] = [{**p, "amount": float(p["amount"]) * f} for p in e["lines"]]
        if levers.get("wait_days"):
            ln["fix_days"] = int(ln.get("fix_days") or 0) + int(levers["wait_days"])
    return x


def _opt(line: Mapping[str, Any], k: str) -> Mapping[str, Any]:
    return next(o for o in line["options"] if o["k"] == k)


def _best_margin(line: Mapping[str, Any]) -> float | None:
    return _opt(line, line["best"])["expected_margin"] if line["best"] else None


def check(inputs: Mapping[str, Any], levers: Mapping[str, Any], only: int | None = None) -> dict[str, Any]:
    base = service_desk.decide_ticket(inputs)
    new_inputs = _moved(inputs, levers, None, only)
    new = service_desk.decide_ticket(new_inputs)
    old_by = {ln["n"]: ln for ln in base["lines"]}
    lines = []
    for ln in new["lines"]:
        if only is not None and ln["n"] != only:
            continue
        before, after = old_by[ln["n"]]["best"], ln["best"]
        curve = []
        for i in range(round(RANGES["credit_pct"][1] / STEP) + 1):
            pct = round(i * STEP, 2)
            point = _line_at(inputs, levers, pct, ln["n"])
            up, fix = _opt(point, "upgrade"), _opt(point, "fix")
            curve.append(
                {
                    "credit_pct": pct,
                    "upgrade_margin": up["margin"],
                    "take_up": up["take_up"],
                    "upgrade": up["expected_margin"],
                    "fix": fix["expected_margin"],
                    "best": point["best"],
                }
            )
        lines.append(
            {
                "n": ln["n"],
                "serial": ln["serial"],
                "currency": ln["currency"],
                "options": ln["options"],
                "best": after,
                "expected_margin": _best_margin(ln),
                "flips": before != after,
                "from": before,
                "to": after,
                "curve": curve,
                "peak": _peak(curve),
                "crossing": _crossing(inputs, levers, ln["n"]),
            }
        )
    holds = service_desk.approval_holds(new, new["best"])
    gr_c1 = [h for h in service_desk.approval_holds(new, "upgrade") if h["id"] == "GR-C1"]
    return {"market": new["market"], "currency": new["currency"], "lines": lines, "holds": holds, "gr_c1": gr_c1}


def _line_at(inputs: Mapping[str, Any], levers: Mapping[str, Any], pct: float, n: int) -> Mapping[str, Any]:
    d = service_desk.decide_ticket(_moved(inputs, levers, pct, n))
    return next(ln for ln in d["lines"] if ln["n"] == n)


def _peak(curve: list[dict[str, Any]]) -> dict[str, Any] | None:
    ok = [p for p in curve if p["upgrade"] is not None]
    if not ok:
        return None
    top = max(ok, key=lambda p: p["upgrade"])
    return {"credit_pct": top["credit_pct"], "upgrade": top["upgrade"]}


def _crossing(inputs: Mapping[str, Any], levers: Mapping[str, Any], n: int) -> dict[str, Any] | None:
    """Where the best option at credit 0 stops being the best: the last credit it still wins (`credit_pct`) and the first it
    loses (`next_pct`), on a 1% grid; None when it wins all the way to 40%."""
    start = _line_at(inputs, levers, 0.0, n)["best"]
    if start is None:
        return None
    prev = 0.0
    for i in range(1, round(RANGES["credit_pct"][1] / FINE) + 1):
        pct = round(i * FINE, 2)
        b = _line_at(inputs, levers, pct, n)["best"]
        if b != start:
            return {"from": start, "to": b, "credit_pct": prev, "next_pct": pct}
        prev = pct
    return None
