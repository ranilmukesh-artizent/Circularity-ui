"""Persefoni (esg): emission factors and footprints (the demo's SOURCES.esg). Read only.

OAuth client credentials, page/per_page paging, `?updated_since=` deltas (see oracle_lease.GenericAdapter).
- emission-factors: one record per factor; a short reference list, read in full (delta=False).
- footprints: one record per asset holding all of its footprints (route estimates of a live case, closed decisions);
  a delta re-reads the whole set of an asset with a change.

Facts (esg has authority over emission factors)
    sustainability.class:<cls>     emission_factor (kgCO2e per unit, cradle-to-gate), factor_unit, boundary,
                                   factor_ref, factor_version, methodology
    sustainability.route:<route>   avoided_share (share of embodied carbon a route avoids), boundary, factor_ref,
                                   factor_version
    sustainability.<asset>         footprint {route: avoided kgCO2e} (estimates), footprint_method, case_ref, period,
                                   decision_footprints (closed decisions: estimated and measured kgCO2e)
RT-1048 (MTR-2041): emission_factor 420 for motors, footprint redeploy 294 (420 x 1 x 0.7).
The demo's mapping examples (factor_kgco2e 312.4 → embodied_carbon) are not in the seed (see the spec); the transforms
are the demo's: "Unit kept", scope Cradle-to-gate → boundary cradle-to-gate ("Boundary map").
"""

from di.canonical.store import Fact
from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep


def boundary(scope: str | None) -> str | None:
    """Cradle-to-gate → cradle-to-gate."""
    return scope.strip().lower() if scope else None


class PersefoniAdapter(GenericAdapter):
    source_id = "esg"
    base_path = "/persefoni/v1"
    items_key, next_key, next_param, size_param, page_size = "data", "next_page", "page", "per_page", 500

    def resources(self):
        return [
            Resource(
                "emission-factors", lambda c, s: self.flat(c, "emission-factors", "/emission-factors", "id", None), delta=False
            ),
            Resource("footprints", lambda c, s: self.grouped(c, "footprints", "/footprints", "asset_id", s)),
        ]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource == "emission-factors":
            return keep(self._factor(p))
        return keep(self._footprints(p))

    def _factor(self, p: dict) -> list[Fact]:
        common = [
            ("boundary", boundary(p.get("scope")), "scope", p.get("scope"), "Boundary map"),
            ("factor_ref", p["id"], "id", p["id"], "Pass-through"),
            ("factor_version", p.get("version"), "version", p.get("version"), "Pass-through"),
            ("methodology", p.get("methodology"), "methodology", p.get("methodology"), "Pass-through"),
        ]
        if p.get("category") == "embodied_carbon" and p.get("asset_class"):
            key = f"class:{p['asset_class']}"
            rows = [
                ("emission_factor", p.get("factor_kgco2e"), "factor_kgco2e", p.get("factor_kgco2e"), "Unit kept"),
                ("factor_unit", p.get("unit"), "unit", p.get("unit"), "Pass-through"),
                *common,
            ]
        elif p.get("route"):
            key = f"route:{p['route']}"
            rows = [
                ("avoided_share", p.get("share_of_embodied"), "share_of_embodied", p.get("share_of_embodied"), "Ratio"),
                *common,
            ]
        else:
            return []
        return [Fact("sustainability", key, f, v, sf, sv, t) for f, v, sf, sv, t in rows]

    def _footprints(self, p: dict) -> list[Fact]:
        key = p["asset_id"]
        rows = sorted(p["items"], key=lambda r: r["id"])
        estimates = [r for r in rows if r.get("activity_type") == "route_estimate"]
        decisions = [r for r in rows if r.get("activity_type") == "closed_decision"]
        facts = []
        if estimates:
            facts += [
                Fact(
                    "sustainability",
                    key,
                    "footprint",
                    {r["route"]: r.get("avoided_co2e_kg") for r in estimates},
                    "avoided_co2e_kg",
                    [f"{r['route']}: {r.get('avoided_co2e_kg')}" for r in estimates],
                    "Unit kept (kgCO2e avoided per route)",
                ),
                Fact(
                    "sustainability",
                    key,
                    "footprint_method",
                    estimates[0].get("methodology"),
                    "methodology",
                    estimates[0].get("methodology"),
                    "Pass-through",
                ),
                Fact(
                    "sustainability",
                    key,
                    "case_ref",
                    estimates[0].get("activity_id"),
                    "activity_id",
                    estimates[0].get("activity_id"),
                    "Pass-through",
                ),
                Fact(
                    "sustainability",
                    key,
                    "period",
                    estimates[0].get("period"),
                    "period",
                    estimates[0].get("period"),
                    "Pass-through",
                ),
            ]
        if decisions:
            facts.append(
                Fact(
                    "sustainability",
                    key,
                    "decision_footprints",
                    [
                        {
                            "decision_id": r["activity_id"],
                            "route": r.get("route"),
                            "period": r.get("period"),
                            "estimated_kg": r.get("avoided_co2e_kg"),
                            "measured_kg": r.get("measured_co2e_kg"),
                            "method": r.get("methodology"),
                            "status": r.get("status"),
                        }
                        for r in decisions
                    ],
                    "avoided_co2e_kg / measured_co2e_kg",
                    [[r.get("avoided_co2e_kg"), r.get("measured_co2e_kg")] for r in decisions],
                    "Unit kept",
                )
            )
        return facts


ADAPTER = PersefoniAdapter()
