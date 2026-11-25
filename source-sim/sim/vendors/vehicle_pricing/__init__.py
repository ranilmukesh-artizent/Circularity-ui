"""Vehicle pricing guide mock (plan 9, P9-9.6): retail and wholesale guide values per VIN, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `uc_price`, schema
`vehicle_pricing`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its
adapter (backend/di/connectors/adapters/vehicle_pricing.py). It reads like an ordinary JSON API (camelCase); no real
price guide is behind it, and every value is synthetic.

    GET /vehicle-pricing/v3/values?vin=   {vin, retail, wholesale, segment, band, asOf}
        one value per car: the lease mock's VINs SYNUC000000000001 ... 060 and the dealer mock's trade-ins ... 061 to
        100. VIN ...001 is retail 24,000 and wholesale 21,500 (a 2022 SUV, 38,000 miles, band 0-40k); VIN ...008 is
        retail 21,000. 404 `not_found` for any other VIN; 400 `bad_request` without `vin`.

Auth: API key in `x-api-key` (demo key `uc_price-demo-key`); 401 with an error body otherwise. Errors are
`{"error": {"code", "message"}}`.

Data in Postgres schema `vehicle_pricing` (models.py, seed.py): fixed, no randomness.

ASSUMPTION: retail is the dealer mock's base price for the car's segment, times its mileage band's factor, times 1 plus 3
    percent for each model year after 2022 (minus for earlier years), to the nearest 100; wholesale is 89.6 percent of
    retail, to the nearest 100. `asOf` is the demo's as-of time.
"""

from sim.core.mock import Mock
from sim.vendors.vehicle_pricing import routes, seed

MOCK = Mock("uc_price", routes.router, seed.ensure, seed.reset, "Vehicle pricing guide (synthetic)")
