"""Persefoni (the demo's SOURCES.esg): embodied-carbon factors, emission factors, footprint methodology.
Read: GET /emission-factors, /footprints. No writes.

Factors are the demo's own: embodied carbon per unit by asset class (EMB, kgCO2e, cradle-to-gate) and the share of it
each route avoids (CO2S). Footprints:
- one per closed decision, carrying the demo's estimated `co2e` and, where reconciled, the measured `co2m`;
- one estimate per route of every live case: EMB[class] x qty x CO2S[route] (RT-1048 redeploy: 420 x 1 x 0.7 = 294).
"""

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

EMB = {"motor": 420, "pump": 260, "control": 90, "drill": 24, "batch": 18, "it": 230}
CO2S = {"redeploy": 0.7, "resale": 0.55, "intparts": 0.3, "relase": 0.65, "material": 0.08, "extparts": 0.25, "exit": 0}
VERSION = "2026.2"


def seed(s: Seed) -> dict[str, list[dict]]:
    factors = [
        {
            "id": f"ef_embodied_{cls}",
            "name": f"Embodied carbon · {s.world.classes[cls].label}",
            "category": "embodied_carbon",
            "asset_class": cls,
            "route": None,
            "factor_kgco2e": float(v),
            "unit": "kgCO2e per unit",
            "scope": "Cradle-to-gate",
            "methodology": "Supplier EPD averages, estimated factor (no measured telemetry)",
            "version": VERSION,
            "valid_from": "2026-01-01",
        }
        for cls, v in EMB.items()
    ] + [
        {
            "id": f"ef_route_{route}",
            "name": f"Avoided embodied carbon · {next(r.name for r in s.world.routes if r.id == route)}",
            "category": "avoided_emissions",
            "asset_class": None,
            "route": route,
            "factor_kgco2e": None,
            "share_of_embodied": share,
            "unit": "share of embodied carbon avoided",
            "scope": "Avoided emissions vs new purchase",
            "methodology": "Substitution method",
            "version": VERSION,
            "valid_from": "2026-01-01",
        }
        for route, share in CO2S.items()
    ]
    footprints = [
        {
            "id": f"fp_{d.id}",
            "activity_id": d.id,
            "activity_type": "closed_decision",
            "asset_id": d.asset_id,
            "asset_class": d.cls,
            "route": d.route,
            "quantity": d.q,
            "tenant": d.tenant,
            "site": d.site,
            "period": d.date.strftime("%Y-%m"),
            "avoided_co2e_kg": d.co2e,
            "measured_co2e_kg": d.co2m,
            "methodology": "measured" if d.co2m is not None else "estimated",
            "factor_id": f"ef_embodied_{d.cls}",
            "status": d.status,
        }
        for d in s.decisions
    ]
    for case in s.cases.values():
        f = case.facts
        for i, r in enumerate(f.routes):
            footprints.append(
                {
                    "id": f"fp_{f.id}_{i + 1}",
                    "activity_id": f.id,
                    "activity_type": "route_estimate",
                    "asset_id": f.asset_id,
                    "asset_class": f.cls,
                    "route": r.id,
                    "quantity": f.qty,
                    "tenant": f.owner,
                    "site": f.demand.site,
                    "period": s.world.as_of.strftime("%Y-%m"),
                    "avoided_co2e_kg": float(round(EMB[f.cls] * f.qty * CO2S.get(r.id, 0))),
                    "measured_co2e_kg": None,
                    "methodology": "estimated",
                    "factor_id": f"ef_embodied_{f.cls}",
                    "status": "estimate",
                }
            )
    return {"emission-factors": factors, "footprints": footprints}


SPEC = Spec(
    source_id="esg",
    title="Persefoni",
    schema="persefoni",
    base_path="/persefoni/v1",
    auth=Auth("oauth_cc"),
    paging=Paging(
        "page",
        page_param="page",
        size_param="per_page",
        items_key="data",
        next_key="next_page",
        total_key="total_count",
        default_size=100,
        max_size=500,
    ),
    resources=(
        Resource("emission-factors", "/emission-factors", "id", filters=("category", "asset_class", "route", "scope")),
        Resource(
            "footprints",
            "/footprints",
            "id",
            filters=("activity_id", "asset_id", "activity_type", "route", "methodology"),
        ),
    ),
    seed=seed,
)
