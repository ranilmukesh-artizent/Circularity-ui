"""Persefoni seed: emission factors, activities and their calculated footprints (docs/backend-steps.md, B5b).

Values are those of the replaced generic mock (sim/generic/specs/persefoni.py):
- embodied-carbon factors per asset class (kgCO2e per unit, cradle-to-gate, version 2026.2) and the share of it each
  route avoids;
- one factor-based activity per route of every live case: quantity x embodied factor x route share
  (RT-1048 redeploy: 1 unit x 420 kgCO2e/unit x 0.7 = 294 kgCO2e = 0.294 mtCO2e);
- one reported activity per closed decision, carrying the demo's estimated co2e and, where reconciled, the measured co2m.
Footprints are calculated from activities by `calculate` (also used by POST /v1/activities).
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.persefoni import models as t

EMB = {"motor": 420, "pump": 260, "control": 90, "drill": 24, "batch": 18, "it": 230}
CO2S = {"redeploy": 0.7, "resale": 0.55, "intparts": 0.3, "relase": 0.65, "material": 0.08, "extparts": 0.25, "exit": 0}
VERSION = "2026.2"
VALID_FROM = "2026-01-01"
CO2E_UNIT = "mtCO2e"  # Persefoni reports emissions in metric tonnes CO2e
KG_PER = {"kgCO2e": Decimal(1), "mtCO2e": Decimal(1000), "tCO2e": Decimal(1000)}


def iso(d: datetime) -> str:
    return d.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def to_mt(kg: Decimal | float) -> float:
    return float((Decimal(str(kg)) / 1000).quantize(Decimal("0.000001")))


def calculate(activity: dict, factors: dict[str, dict], at: datetime) -> dict:
    """The footprint of one activity.

    factor_based: avoided kgCO2e = quantity [activity_unit] x factor_kgco2e [kgCO2e per activity_unit] x share_of_embodied
                  (the route's avoidance factor; 1 without one), reported in mtCO2e.
    reported:     the reported (and measured) amounts, converted to mtCO2e.
    """
    method = activity["calculation_method"]
    ef = factors.get(activity.get("emission_factor_id") or "")
    av = factors.get(activity.get("avoidance_factor_id") or "")
    measured = None
    if method == "factor_based":
        share = Decimal(str(av["share_of_embodied"])) if av else Decimal(1)
        kg = Decimal(str(activity["quantity"])) * Decimal(str(ef["factor_kgco2e"])) * share
        avoided = to_mt(kg)
    else:
        unit = KG_PER[activity["reported_co2e_unit"]]
        avoided = to_mt(Decimal(str(activity["reported_co2e"])) * unit)
        if activity.get("measured_co2e") is not None:
            measured = to_mt(Decimal(str(activity["measured_co2e"])) * unit)
    return {
        "id": "fp_" + activity["id"].removeprefix("act_"),
        "activity_id": activity["id"],
        "activity_type": activity["activity_type"],
        "calculation_method": method,
        "external_reference": activity.get("external_reference"),
        "asset_id": activity.get("asset_id"),
        "asset_class": activity.get("asset_class"),
        "route": activity.get("route"),
        "quantity": activity.get("quantity"),
        "quantity_unit": activity.get("quantity_unit"),
        "tenant": activity.get("tenant"),
        "site": activity.get("site"),
        "period": activity.get("period"),
        "emission_factor_id": ef["id"] if ef else activity.get("emission_factor_id"),
        "emission_factor_value": ef["factor_kgco2e"] if ef else None,
        "emission_factor_unit": ef["unit"] if ef else None,
        "avoidance_factor_id": av["id"] if av else None,
        "avoidance_share": av["share_of_embodied"] if av else None,
        "avoided_co2e": avoided,
        "measured_co2e": measured,
        "co2e_unit": CO2E_UNIT,
        "methodology": "measured" if measured is not None else "estimated",
        "status": activity.get("status"),
        "calculated_at": iso(at),
        "updated_at": iso(at),
    }


def factor_docs(s: Seed, at: datetime) -> list[dict]:
    stamp = iso(at)
    embodied = [
        {
            "id": f"ef_embodied_{cls}",
            "name": f"Embodied carbon · {s.world.classes[cls].label}",
            "category": "embodied_carbon",
            "asset_class": cls,
            "route": None,
            "factor_kgco2e": float(v),
            "share_of_embodied": None,
            "activity_unit": "unit",
            "unit": "kgCO2e per unit",
            "scope": "Cradle-to-gate",
            "gwp_set": "IPCC AR5",
            "source": "Supplier EPD averages",
            "methodology": "Supplier EPD averages, estimated factor (no measured telemetry)",
            "version": VERSION,
            "valid_from": VALID_FROM,
            "valid_to": None,
            "created_at": stamp,
            "updated_at": stamp,
        }
        for cls, v in EMB.items()
    ]
    routes = [
        {
            "id": f"ef_route_{route}",
            "name": f"Avoided embodied carbon · {next(r.name for r in s.world.routes if r.id == route)}",
            "category": "avoided_emissions",
            "asset_class": None,
            "route": route,
            "factor_kgco2e": None,
            "share_of_embodied": share,
            "activity_unit": None,
            "unit": "share of embodied carbon avoided",
            "scope": "Avoided emissions vs new purchase",
            "gwp_set": "IPCC AR5",
            "source": "Substitution method",
            "methodology": "Substitution method",
            "version": VERSION,
            "valid_from": VALID_FROM,
            "valid_to": None,
            "created_at": stamp,
            "updated_at": stamp,
        }
        for route, share in CO2S.items()
    ]
    return embodied + routes


def activity_docs(s: Seed, at: datetime) -> list[dict]:
    stamp = iso(at)
    out = [
        {
            "id": f"act_{d.id}",
            "activity_type": "closed_decision",
            "calculation_method": "reported",
            "external_reference": d.id,
            "asset_id": d.asset_id,
            "asset_class": d.cls,
            "route": d.route,
            "quantity": d.q,
            "quantity_unit": "unit",
            "tenant": d.tenant,
            "site": d.site,
            "period": d.date.strftime("%Y-%m"),
            "emission_factor_id": f"ef_embodied_{d.cls}",
            "avoidance_factor_id": None,
            "reported_co2e": d.co2e,
            "measured_co2e": d.co2m,
            "reported_co2e_unit": "kgCO2e",
            "status": d.status,
            "created_at": stamp,
            "updated_at": stamp,
        }
        for d in s.decisions
    ]
    for case in s.cases.values():
        f = case.facts
        for i, r in enumerate(f.routes):
            out.append(
                {
                    "id": f"act_{f.id}_{i + 1}",
                    "activity_type": "route_estimate",
                    "calculation_method": "factor_based",
                    "external_reference": f.id,
                    "asset_id": f.asset_id,
                    "asset_class": f.cls,
                    "route": r.id,
                    "quantity": f.qty,
                    "quantity_unit": "unit",
                    "tenant": f.owner,
                    "site": f.demand.site,
                    "period": s.world.as_of.strftime("%Y-%m"),
                    "emission_factor_id": f"ef_embodied_{f.cls}",
                    "avoidance_factor_id": f"ef_route_{r.id}" if r.id in CO2S else None,
                    "reported_co2e": None,
                    "measured_co2e": None,
                    "reported_co2e_unit": None,
                    "status": "estimate",
                    "created_at": stamp,
                    "updated_at": stamp,
                }
            )
    return out


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    at = seed.world.as_of
    at = at.replace(microsecond=at.microsecond // 1000 * 1000)
    factors = factor_docs(seed, at)
    by_id = {f["id"]: f for f in factors}
    acts = activity_docs(seed, at)
    fps = [calculate(a, by_id, at) for a in acts]
    conn.execute(insert(t.EMISSION_FACTOR), [{"id": f["id"], "doc": f, "updated_at": at} for f in factors])
    conn.execute(insert(t.ACTIVITY), [{"id": a["id"], "doc": a, "updated_at": at} for a in acts])
    conn.execute(insert(t.FOOTPRINT), [{"id": f["id"], "activity_id": f["activity_id"], "doc": f, "updated_at": at} for f in fps])
    return {"emission_factor": len(factors), "activity": len(acts), "footprint": len(fps)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS persefoni"))
    t.metadata.create_all(conn)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    t.metadata.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM persefoni.emission_factor")).scalar_one() == 0:
        load(conn, seed)
