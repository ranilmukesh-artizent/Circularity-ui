"""Vehicle lease system mock (plan 9, P9-9.2): the lease returns of the used-car segment's lease book, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `uc_lease`, schema `vehicle_lease`),
so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its adapter
(backend/di/connectors/adapters/vehicle_lease.py), which maps a return to `asset.*` and `condition.*` facts keyed by
VIN. It reads like an ordinary JSON API (camelCase); there is no real vehicle lease system behind it and no real
lessee: `lesseeRef` is a code (`L-0001` ...), never a name.

    GET /vehicle-lease/api/v1/lease-returns?limit=&offset=&updatedSince=   {items, next, total}
    GET /vehicle-lease/api/v1/lease-returns/{leaseId}                      one return

    POST /vehicle-lease/api/v1/charges {leaseId, kind, amount}   a charge to the lessee (P9-9.20): kind `excess_mileage` or
                                  `excess_wear`, amount above zero -> 201 {chargeId: CH-0001 ..., leaseId, kind, amount, status:
                                  "accepted"}; idempotent (the `Idempotency-Key` header's, else the lease and kind: a repeat
                                  answers 200 with the first charge); 404 for an unknown lease, 422 for a bad body, 400 for
                                  one that is not JSON. A reset drops the charges.

Auth: API key in `x-api-key` (demo key `uc_lease-demo-key`); 401 with an error body otherwise.
Paging: `limit` 1-200 (default 25) and `offset`; `next` is the next offset or null. `updatedSince` (ISO 8601) keeps
the returns changed after it. Errors are `{"error": {"code", "message"}}`.

Data in Postgres schema `vehicle_lease` (models.py, seed.py): 60 returns, VINs `SYNUC000000000001` ... `...060`, fixed
(no randomness), so a reset gives the same JSON again. The cars the later tasks lean on: VIN ...001 a 2022 petrol SUV
with 38,000 miles and residual 19,500; ...004 reads 61,240 at return against 46,240 at its last service; ...005 has
133,000 miles; ...007 is a 2022 petrol SUV (pinned: the cycle would make it a compact; with its $2,800 recon, retail
still beats the auction, P9-9.21 step 7); ...011 and ...012 say the odometer is not actual; ...041-...048 are EV crossovers; ...050 comes from a
seller with a fleet of 40; ...001-...030 return to RC-East, the rest to RC-West.

ASSUMPTION: `odometerLastService` equals `odometerAtReturn` for every car but ...004 (the mismatch UC-03 is about).
ASSUMPTION: `status` is `returned` on every row (the intake trigger of the pack fires on it); `updatedAt` runs one
    minute apart in VIN order, ending at the demo's as-of time.
"""

from sim.core.mock import Mock
from sim.vendors.vehicle_lease import routes, seed

MOCK = Mock("uc_lease", routes.router, seed.ensure, seed.reset, "Vehicle lease system (synthetic)")
