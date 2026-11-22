"""Persefoni API v1 mock (docs/backend-steps.md, B5b): the demo's ESG & carbon source (SOURCES.esg).

API under /persefoni/v1 (the demo's url https://api.persefoni.com/v1), token at /persefoni/oauth/token; see routes.py.
Data in Postgres schema `persefoni` (models.py), seeded from the world (seed.py). Replaces sim/generic/specs/persefoni.py.

Documentation followed
- Persefoni has no public developer portal; custom API integrations are given through onboarding / partner programs:
  https://apis.io/apis/persefoni/integration-hub/ , https://www.persefoni.com/product/integration-hub ,
  https://apitracker.io/a/persefoni
- Persefoni's published methodology: emissions = activity data x emission factor, reported in metric tonnes CO2e:
  https://www.persefoni.com/blog/emission-factors-explained , https://persefoni.com/product/carbon-accounting
- The demo's own contract (index.html SOURCES.esg): OAuth 2.0 client credentials, API v1, GET /emission-factors,
  GET /footprints; MAPPINGS.esg field names (factor_kgco2e, scope); unmapped sample factor_version 2026.2.
Every request/response shape below is therefore an assumption.

Demo credentials (constants in routes.py)
    POST /persefoni/oauth/token  grant_type=client_credentials, client_id=circularity-di-connector,
    client_secret=circularity-demo-persefoni-secret, optional audience=https://api.persefoni.com (form or JSON body,
    or the client in HTTP Basic). Then Authorization: Bearer <token> (24 h).

ASSUMPTION: an Auth0-style token endpoint (audience parameter, {"error","error_description"} failures, 24 h tokens).
ASSUMPTION: snake_case JSON, list envelope {"data", "meta": {page, per_page, total_count, total_pages},
    "links": {self, next, prev}}, ?page= (1-based) / ?per_page= (max 500), deltas with ?updated_since= (strictly after).
ASSUMPTION: JSON:API-style errors {"errors": [{"status", "code", "title", "detail", "source": {"pointer"}}]}.
ASSUMPTION: the objects are emission factors, activities (activity data) and footprints (one calculated result per
    activity). Factor field names keep the demo's MAPPINGS names (factor_kgco2e, scope, version).
ASSUMPTION: footprints are reported in mtCO2e (`avoided_co2e`, `measured_co2e`, `co2e_unit`), as Persefoni reports;
    factors are kgCO2e per activity unit ("unit" = one asset).
ASSUMPTION: the circular-economy use: an embodied-carbon factor per asset class and an "avoided emissions" factor per
    route (share of embodied carbon avoided vs a new purchase); closed decisions are "reported" activities carrying the
    demo's estimated and measured kgCO2e.

Business rule (seed.calculate): factor_based footprint = quantity [unit] x factor_kgco2e [kgCO2e/unit] x route share,
/ 1000 -> mtCO2e (RT-1048 redeploy: 1 x 420 x 0.7 = 294 kg = 0.294 mtCO2e); reported amounts are converted from
kgCO2e / mtCO2e / tCO2e. POST /v1/activities validates the factor, the unit (must equal the factor's activity unit) and
the factor's validity for the period, stamps clock.now() and emits persefoni.activity.created and
persefoni.footprint.calculated.
"""

from sim.core.mock import Mock
from sim.vendors.persefoni.routes import router
from sim.vendors.persefoni.seed import ensure, reset

MOCK = Mock("esg", router, ensure, reset, "Persefoni")
