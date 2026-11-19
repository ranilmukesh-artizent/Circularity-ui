"""The gate rules that exclude a route (the checks in the demo's buildRoutes), applied in the demo's order.

A route that a rule excludes keeps its terms and net, so the screens can still show what it would have been worth.
The order matters: a later rule can fail a route that an earlier one already excluded (an IT lot with pending data
erasure fails Policy even when grade D already failed Condition), and the failing gate is then the later one.
"""

import re

from di.engine.routes import CONDITION, DEMAND, ECONOMICS, POLICY, SUSTAINABILITY, Route, fail

MISSING_DEMAND = {
    "redeploy": ("internal", "No open internal requirement matches specification and timing"),
    "relase": ("lease", "No lease opportunity within the horizon"),
    "intparts": ("parts", "No open component demand matches recoverable parts"),
}
LIFE_BELOW_MINIMUM = "Remaining life below the minimum for the intended use"
DATA_ERASURE = "Data-erasure certificate not issued; sanitization required before release"
SAFETY_RATED = "Safety-rated unit: criticality restriction needs recertification"
CONSENT = "Demand belongs to another client; customer consent not on file"
HAZARDOUS = "Cell chemistry requires an approved hazardous-waste route"
NOT_POSITIVE = "Expected net contribution is not positive"


def _first(routes: list[Route], rid: str, eligible_only: bool = False) -> Route | None:
    return next((r for r in routes if r["id"] == rid and not (eligible_only and r["excluded"])), None)


def apply_gate_rules(case: dict, routes: list[Route]) -> list[Route]:
    """Run every gate rule over a case's routes, in place. `case` needs: cls, grade, spec, demand, consentGap
    (optional) and hazardousMaterial (optional: the recycler requires a hazardous-waste route for this lot)."""
    dem = case.get("demand") or {}
    spec = case.get("spec") or {}
    # Demand fit: the route needs demand of its kind
    for r in routes:
        need = MISSING_DEMAND.get(r["id"])
        if need and not dem.get(need[0]) and not r["excluded"]:
            fail(r, DEMAND, need[1])
    # Condition & life: grade D is below the minimum life for reuse
    if case.get("grade") == "D":
        for r in routes:
            if r["id"] in ("redeploy", "resale", "relase") and not r["excluded"]:
                fail(r, CONDITION, LIFE_BELOW_MINIMUM)
    # Policy & certification
    if case.get("cls") == "it" and spec.get("Data erasure") == "Pending":
        r = _first(routes, "resale")
        if r:
            fail(r, POLICY, DATA_ERASURE)
    if case.get("cls") == "control" and re.search("SIL", str(spec.get("Safety rating", ""))):
        r = _first(routes, "redeploy", eligible_only=True)
        if r:
            fail(r, POLICY, SAFETY_RATED)
    if case.get("consentGap"):
        r = _first(routes, "redeploy", eligible_only=True)
        if r:
            fail(r, POLICY, CONSENT)
    # Sustainability: lithium cells need an approved hazardous-waste route
    if case.get("cls") in ("batch", "it") and case.get("hazardousMaterial"):
        r = _first(routes, "material")
        if r:
            fail(r, SUSTAINABILITY, HAZARDOUS)
    # Economics: only routes worth something stay eligible (exit is the compliant fallback and may cost money)
    for r in routes:
        if not r["excluded"] and r["id"] != "exit" and r["net"] <= 0:
            fail(r, ECONOMICS, NOT_POSITIVE)
    return routes
