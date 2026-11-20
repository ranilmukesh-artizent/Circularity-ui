"""Routes: a route's net and range, a failed gate, and ranking (the demo's mkRoute, fail and rankRoutes).

A route is a plain dict in the demo's shape (the shape of `fixtures/golden/cases.json`), so it serialises as is:
`id`, `plan`, `terms` ([{label, amt, kind}]), `sigma`, `gates`, `excluded`, `failGate`, `failReason`, `net`, `p10`,
`p90`, `rank`, and text fields (demandLabel, demandStatus, unc, why, gateNotes, target ...).
"""

from typing import Any

from di.engine.jsmath import js_round, js_sum

Route = dict[str, Any]

GATES = ["Condition & life", "Post-intervention", "Policy & certification", "Demand fit", "Economics", "Sustainability"]
CONDITION, POST_INTERVENTION, POLICY, DEMAND, ECONOMICS, SUSTAINABILITY = range(6)

# The range is the net plus or minus 1.28 standard deviations (the P10 and P90 of a normal), sigma being relative to
# the net, with a floor of $12. The upside is damped (x 0.82) and the downside can be skewed (`skew`, default 1).
Z_P10_P90 = 1.28
MIN_SPREAD = 12
UPSIDE = 0.82


def term(label: str, amt: int, kind: str) -> dict:
    return {"label": label, "amt": amt, "kind": kind}


def term_sum(r: Route) -> float:
    return js_sum(t["amt"] for t in r["terms"])


def mk_route(o: Route) -> Route:
    """Normalise a route draft: defaults, the net (sum of its terms) and the P10/P90 range around it (P50 = net)."""
    r: Route = {
        "gates": ["pass"] * 6,
        "gateNotes": [],
        "excluded": False,
        "failGate": -1,
        "failReason": "",
        "demandStatus": "confirmed",
        "p": 1,
        "sigma": 0.12,
    }
    r.update(o)
    r["gates"] = list(r["gates"])
    r["net"] = term_sum(r)
    spread = max(abs(r["net"]) * r["sigma"] * Z_P10_P90, MIN_SPREAD)
    r["p10"] = js_round(r["net"] - spread * (r.get("skew") or 1))
    r["p90"] = js_round(r["net"] + spread * UPSIDE)
    return r


def fail(r: Route, gate: int, reason: str) -> Route:
    """Exclude a route at a gate: that gate fails and the later gates that were passing are skipped."""
    r["excluded"], r["failGate"], r["failReason"] = True, gate, reason
    r["gates"][gate] = "fail"
    for i in range(gate + 1, 6):
        if r["gates"][i] == "pass":
            r["gates"][i] = "skip"
    return r


def rank_routes(routes: list[Route], blocked: Any = None) -> Route | None:
    """Rank the eligible routes by net (highest first, ties in their listed order); excluded routes get no rank.
    Returns the recommendation: the top eligible route, or None when the case is blocked or nothing is eligible."""
    eligible = sorted((r for r in routes if not r["excluded"]), key=lambda r: -r["net"])
    for i, r in enumerate(eligible):
        r["rank"] = i + 1
    for r in routes:
        if r["excluded"]:
            r["rank"] = None
    return None if blocked else (eligible[0] if eligible else None)
