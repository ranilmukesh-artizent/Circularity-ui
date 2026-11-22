"""Persefoni (esg): emission factors and footprints (the demo's SOURCES.esg). Read only.
Written against source-sim's full Persefoni mock (source-sim/sim/vendors/persefoni).

OAuth 2.0 client credentials (POST /oauth/token, client and audience in the form); lists page with ?page= /
?per_page= (body {"data", "meta", "links": {"next"}}), deltas with ?updated_since= against each record's updated_at.
- emission-factors: one record per factor. Delta.
- footprints: one record per asset holding all of its footprints (route estimates of a live case, closed decisions);
  a delta re-reads the whole set of an asset with a change.

Facts (esg has authority over emission factors)
    sustainability.class:<cls>     emission_factor (kgCO2e per unit, cradle-to-gate), factor_unit, boundary,
                                   factor_ref, factor_version, methodology
    sustainability.route:<route>   avoided_share (share of embodied carbon a route avoids), boundary, factor_ref,
                                   factor_version
    sustainability.<asset>         footprint {route: avoided kgCO2e} (estimates), footprint_method, case_ref, period,
                                   decision_footprints (closed decisions: estimated and measured kgCO2e)
Persefoni reports footprints in mtCO2e; they are converted to kgCO2e (x 1000), the unit of the factors and of the demo.
RT-1048 (MTR-2041): emission_factor 420 for motors, footprint redeploy 294 kg (0.294 mtCO2e = 1 x 420 x 0.7 / 1000).
The demo's mapping transforms: factor_kgco2e "Unit kept", scope Cradle-to-gate → boundary cradle-to-gate ("Boundary map").
"""

from collections.abc import Iterator

import httpx

from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import keep
from di.connectors.http import OAuthClientCredentials, SourceClient
from di.services.canonical.store import Fact

PER_PAGE = 500
MT_TO_KG = "mtCO2e → kgCO2e (x1000)"


def boundary(scope: str | None) -> str | None:
    """Cradle-to-gate → cradle-to-gate."""
    return scope.strip().lower() if scope else None


def kg(mt: float | None) -> float | None:
    return None if mt is None else round(mt * 1000, 3)


class PersefoniAdapter(Adapter):
    source_id = "esg"
    base_path = "/persefoni"

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return OAuthClientCredentials(
            "/oauth/token",
            "circularity-di-connector",
            secret or "circularity-demo-persefoni-secret",
            form=True,
            extra={"audience": "https://api.persefoni.com"},
        )

    def resources(self):
        return [Resource("emission-factors", self.read_factors), Resource("footprints", self.read_footprints)]

    # ------------------------------------------------------------- reading
    def pages(self, client: SourceClient, path: str, since: str | None = None, **params) -> Iterator[tuple[dict, str]]:
        page = 1
        while True:
            q = {**params, "page": str(page), "per_page": str(PER_PAGE)} | ({"updated_since": since} if since else {})
            body = client.get_json(path, params=q)
            rows = body["data"]
            client.note_records(len(rows))
            url = str(httpx.URL(client.url(path), params=q))
            for row in rows:
                yield row, url
            if not (body.get("links") or {}).get("next") or not rows:
                return
            page += 1

    def read_factors(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        for row, url in self.pages(client, "/v1/emission-factors", since):
            yield Record("emission-factors", row["id"], row, url, row["updated_at"])

    def read_footprints(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        groups: dict[str, list[dict]] = {}
        urls: dict[str, str] = {}
        for row, url in self.pages(client, "/v1/footprints", since):
            if row.get("asset_id"):
                groups.setdefault(row["asset_id"], []).append(row)
                urls.setdefault(row["asset_id"], url)
        for asset in sorted(groups):
            rows, url = groups[asset], urls[asset]
            if since:  # the whole set of the asset, not only what changed
                rows = [r for r, _ in self.pages(client, "/v1/footprints", asset_id=asset)]
                url = str(httpx.URL(client.url("/v1/footprints"), params={"asset_id": asset}))
            changed = max(r["updated_at"] for r in rows)
            yield Record("footprints", asset, {"asset_id": asset, "items": rows}, url, changed)

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        if record.resource == "emission-factors":
            return keep(self._factor(record.payload))
        return keep(self._footprints(record.payload))

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
        elif p.get("category") == "avoided_emissions" and p.get("route"):
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
        estimates = [r for r in rows if r.get("activity_type") == "route_estimate" and r.get("route")]
        decisions = [r for r in rows if r.get("activity_type") == "closed_decision"]
        facts = []
        if estimates:
            first = estimates[0]
            facts += [
                Fact(
                    "sustainability",
                    key,
                    "footprint",
                    {r["route"]: kg(r.get("avoided_co2e")) for r in estimates},
                    "avoided_co2e",
                    [f"{r['route']}: {r.get('avoided_co2e')} {r.get('co2e_unit')}" for r in estimates],
                    MT_TO_KG + ", avoided per route",
                ),
                Fact(
                    "sustainability",
                    key,
                    "footprint_method",
                    first.get("methodology"),
                    "methodology",
                    first.get("methodology"),
                    "Pass-through",
                ),
                Fact(
                    "sustainability",
                    key,
                    "case_ref",
                    first.get("external_reference"),
                    "external_reference",
                    first.get("external_reference"),
                    "Pass-through",
                ),
                Fact("sustainability", key, "period", first.get("period"), "period", first.get("period"), "Pass-through"),
            ]
        if decisions:
            facts.append(
                Fact(
                    "sustainability",
                    key,
                    "decision_footprints",
                    [
                        {
                            "decision_id": r.get("external_reference"),
                            "route": r.get("route"),
                            "period": r.get("period"),
                            "estimated_kg": kg(r.get("avoided_co2e")),
                            "measured_kg": kg(r.get("measured_co2e")),
                            "method": r.get("methodology"),
                            "status": r.get("status"),
                        }
                        for r in decisions
                    ],
                    "avoided_co2e / measured_co2e",
                    [[r.get("avoided_co2e"), r.get("measured_co2e")] for r in decisions],
                    MT_TO_KG,
                )
            )
        return facts


ADAPTER = PersefoniAdapter()
