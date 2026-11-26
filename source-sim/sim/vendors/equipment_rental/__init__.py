"""Equipment rental system mock (plan 9, P9-12.4): a rental and construction fleet's off-rent machines, branch utilisation,
used price index, check-in damage claims, branch purchase plans and idle machines, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `rf_rental`, schema `equipment_rental`),
so the demo's 21 systems stay as they were. di reads it through its adapter (backend/di/connectors/adapters/equipment_rental.py),
which maps a machine to `asset.*`, `demand.*`, `market.price_index` and `condition.damage_claims` facts keyed by machine id.
No real rental company or product is behind it.

    GET /equipment-rental/api/off-rent        [{machineId, assetClass, hours, branch, ageYears, bookValue, offRentAt}]
    GET /equipment-rental/api/utilisation     [{branch, assetClass, utilisation}]
    GET /equipment-rental/api/price-index?class=&hoursBand=   {assetClass, hoursBand, price}  ({} when the band has no price)
    GET /equipment-rental/api/damage-claims   [{claimId, machineId, renterRef, amount, photosRef}]
    GET /equipment-rental/api/purchase-plans  [{planId, branch, assetClass, qty}]
    GET /equipment-rental/api/idle            [{machineId, assetClass, branch, idleDays}]

Auth: API key in `x-api-key` (demo key `rf_rental-demo-key`); 401 with an error body otherwise.

Data in Postgres schema `equipment_rental` (seed.py, fixed, no randomness): eight off-rent machines `M-0001` ... `M-0008`.
`M-0001` is an excavator 20 t, 6,200 h, 8 years, at BR-1 (utilisation 0.72, book value 52,000; its price band 6,000-7,000 h is
61,000). `M-0003` is a wheel loader idle 44 days at BR-2 while BR-3 plans to buy one. `M-0005` came back with a damage claim of
2,350 against renter `R-0042`.
"""

from sim.core.mock import Mock
from sim.vendors.equipment_rental import routes, seed

MOCK = Mock("rf_rental", routes.router, seed.ensure, seed.reset, "Equipment rental system (synthetic)")
