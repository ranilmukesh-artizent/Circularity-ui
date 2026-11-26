"""CO2e a tool-fleet path avoids, from the pack's versioned factor table (plan 9, P9-3.14, story TF-13; B 5.7).

Owns the arithmetic of one path's avoided kg, per tool class (`valuer.params.co2`, version `tf-co2-2026.1`: embodied kg of a
new tool, mass, prep, refurbish, teardown, recycling credit per kg, treatment, road kg per tonne-km, lane km). Pure and
computed: never a language model, never a figure without its factor (None when the class, the path or the table is missing).
The figure is information beside the net: it never enters `net` and never changes a route. The sample factors are
synthetic; a real set needs review by Kinective's Legal team before any report (the table says `legal_review: pending`).

    release, redeploy, refurb: E_new x d - E_prep (E_refurb for refurb) - E_log, d 1 on a committed named order else 0.5
    resell:   as release, d 1 on a firm bid, 0.5 on an outlet estimate
    harvest:  parts x E_new x 0.08 - E_teardown
    exit:     mass x credit - E_treat
    E_log:    mass / 1000 x lane_km x road when the destination is at another site (`dest["other_site"]`), else 0

Separate from `modeler/carbon.py` (the cfs set on every route card, P9-1.12): this figure is the mass-based one the case
panel's Paths section shows beside the sample factors it used.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

COMMITTED = frozenset({"lease", "so", "proj"})  # a named order that is committed (the valuer's CONFIRMED_KINDS)
PART_SHARE = 0.08  # the share of a new tool's embodied kg a certified part stands for


@dataclass(frozen=True)
class Co2Line:
    kg: float
    formula: str
    source: str
    version: str


def _n(x: float) -> str:
    return f"{round(x, 4):g}"


def co2_avoided(
    path: str, cls: str, dest: Mapping[str, Any] | None, harvested_parts: int, factors: Mapping[str, Any]
) -> Co2Line | None:
    """Avoided kg CO2e of `path` for one tool of class `cls` (module docstring); None without a factor to compute it."""
    f = (factors.get("classes") or {}).get(cls)
    if not f:
        return None
    kind = (dest or {}).get("kind")
    log = 0.0
    if dest and dest.get("other_site"):
        log = f["mass_kg"] / 1000 * f["lane_km"] * f["road_kg_per_tkm"]
    if path in ("release", "redeploy", "refurb", "resell"):
        d = 1 if kind in COMMITTED or (path == "resell" and kind == "bid") else 0.5
        prep = f["refurb_kg"] if path == "refurb" else f["prep_kg"]
        kg = f["embodied_new_kg"] * d - prep - log
        formula = f"{_n(f['embodied_new_kg'])} x {_n(d)} - {_n(prep)} - {_n(log)}"
    elif path == "harvest":
        kg = harvested_parts * f["embodied_new_kg"] * PART_SHARE - f["teardown_kg"]
        formula = f"{harvested_parts} x {_n(f['embodied_new_kg'])} x {PART_SHARE} - {_n(f['teardown_kg'])}"
    elif path == "exit":
        kg = f["mass_kg"] * f["recycle_credit_kg_per_kg"] - f["treat_kg"]
        formula = f"{_n(f['mass_kg'])} x {_n(f['recycle_credit_kg_per_kg'])} - {_n(f['treat_kg'])}"
    else:
        return None
    return Co2Line(round(kg, 1), formula, str(factors.get("source", "")), str(factors.get("version", "")))
