"""The move (the demo's exMove, N1/N6/K5/K7): stops, legs on the rate card, ETD and ETA per leg, staging, and the
slack against the need-by date. Times are epoch milliseconds (the demo's Dates).

The demo memoises exMove per case, route kind and approval time (EX_SEQ); the function is pure, so the port computes
it each time.
"""

import math

from di.engine.jsmath import js_round, js_sum
from di.execution.lanes import LOCS, RATE_CARD, ex_kg, ex_move_raw, ex_stage, transit_h
from di.execution.prep import ex_prep_parts
from di.execution.util import HOUR_MS, hours, js_day, midnight
from di.reads.common import AS_OF, DAY_MS, Case, case_demand, ms


def ex_day0(c: Case) -> int:
    """The demo's exDay0: Day 0 of the move is the approval day, or today for an approval less than 36 hours old."""
    x = c.get("exec")
    a = ms(x["approvedAt"]) if x and x.get("approvedAt") else AS_OF
    return midnight(a if a < AS_OF - 36 * HOUR_MS else AS_OF)


def ex_move(c: Case, r: dict | None = None) -> dict | None:
    """The demo's exMove. Each leg leaves at 08:00 the day after the unit is ready; an arrival outside the receiving
    window moves to the next window and the departure moves with it. At the Repair centre the unit is ready after the
    refurbishment's labour hours (whole days of 8 hours, finished at 18:00)."""
    r = r or c.get("chosen") or c.get("recommendation")
    if not r:
        return None
    raw = ex_move_raw(c, r)
    if not raw:
        return None
    M = case_demand(c)
    stops = raw["stops"]
    to = stops[-1] if r.get("id") == "redeploy" else None
    P = ex_prep_parts(c, r)
    lab_h = P["labH"] if P else 0
    d0 = ex_day0(c)

    def rep(n: int) -> int:
        return max(1, math.ceil(lab_h / 8)) + n

    ready, repair_at, legs = d0 + DAY_MS + 8 * HOUR_MS, None, []
    if stops[0] == "RC-HSR-01" and lab_h:
        repair_at = d0 + rep(0) * DAY_MS + 18 * HOUR_MS
        ready = midnight(repair_at) + DAY_MS + 8 * HOUR_MS
    for leg in raw["legs"]:
        B, tr = LOCS[leg["to"]], transit_h(leg["km"])
        # `new Date(ms)` truncates a fractional time; the sum is taken in floating point as in the demo
        etd = ready
        eta = int(etd + tr * HOUR_MS)
        h, ok = hours(eta), js_day(eta) in B["days"]
        if not (ok and B["hrs"][0] <= h <= B["hrs"][1]):
            t = midnight(eta) + (0 if ok and h < B["hrs"][0] else 1) * DAY_MS + B["hrs"][0] * HOUR_MS
            while js_day(t) not in B["days"]:
                t += DAY_MS
            eta, etd = t, int(t - tr * HOUR_MS)
        out = {
            **leg,
            "etd": etd,
            "eta": eta,
            "transit": tr,
            "carrier": "Partner vehicle" if leg["to"] == "PTN-MAA" else RATE_CARD["carrier"],
        }
        if leg["to"] == "RC-HSR-01" and lab_h:
            repair_at = midnight(eta) + rep(-1 if hours(eta) < 12 else 0) * DAY_MS + 18 * HOUR_MS
            out["readyAt"] = repair_at
            ready = midnight(repair_at) + DAY_MS + 8 * HOUR_MS
        else:
            ready = midnight(eta) + DAY_MS + 8 * HOUR_MS
        legs.append(out)
    last = legs[-1] if legs else None
    need = ms(M["needBy"]) if r.get("id") == "redeploy" and M and M.get("needBy") else None
    return {
        "stops": stops,
        "legs": legs,
        "stage": ex_stage(to) if to else None,
        "to": to,
        "src": stops[0],
        "kg": ex_kg(c),
        "d0": d0,
        "repairAt": repair_at,
        "need": need,
        "eta": last["eta"] if last else None,
        "slack": js_round((need - midnight(last["eta"])) / DAY_MS) if need is not None and last else None,
        "inr": js_sum(x["inr"] for x in legs),
    }


def ex_day(m: dict, t: int) -> int:
    """The move's day(): the day number of a time, counted from Day 0."""
    return js_round((midnight(t) - m["d0"]) / DAY_MS)
