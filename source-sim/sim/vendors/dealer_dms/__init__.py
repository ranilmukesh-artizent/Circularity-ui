"""Dealer management system mock (plan 9, P9-9.2): trade-ins, the lots, what each lot sells and the cars on them,
synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `uc_dms`, schema `dealer_dms`),
so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its adapter
(backend/di/connectors/adapters/dealer_dms.py). It reads like an ordinary JSON API (camelCase); no real dealer, store or
partner is behind it.

Reads (all `{items, next, total}`, `limit` 1-200 default 25 and `offset`):
    GET /dealer-dms/api/v1/trade-ins     40 trade-ins, VINs SYNUC000000000061 ... 100; VIN ...062 has no confirmed payoff
    GET /dealer-dms/api/v1/lots          LOT-N "North lot" 12 miles from the return centre, LOT-C "Central lot" 40,
                                         LOT-S "South lot" 95
    GET /dealer-dms/api/v1/lot-sales     ?segment=&lotId=&mileageBand= : each lot's own sales history per segment
                                         (compact | midsize | suv | ev_crossover | truck) and mileage band (0-40k |
                                         40-80k | 80-120k | 120k+): {avgPrice, avgDaysToSale, count, spread}; 60 rows
    GET /dealer-dms/api/v1/partner-bids  ?vin= : partner dealers' bids for a car (VINs ...001 to ...060, 7 percent over
                                         the residual value of the lease mock, to the 100)
    GET /dealer-dms/api/v1/stock         30 cars on the lots, daysOnLot 3 to 72; seven are over 45 days and five of them
                                         are EV crossovers at LOT-N (VINs ...041 to ...045, lease returns)
    GET /dealer-dms/api/v1/sales         ?vin=&lotId= : the listings that sold (P9-9.20): {listingId, vin, lotId, price, listedAt,
                                         soldAt, daysToSale}; none at start
Writes (JSON body; header `Idempotency-Key` makes a repeat answer 200 with the first document instead of 201 and a
second one; a bad body is 422, one that is not JSON 400):
    POST /recon-orders {vin, estimate, lines}   POST /transfers {vin, fromLot, toLot}
    POST /listings {vin, lotId, price, disclosures}   POST /dealer-trades {vin, partner, price, titleRef}
A new listing sells later on the simulated clock (sim/core/scheduler.py, handler `dealer_dms.listing.sold`): after the lot's
average days to sale for a car of its segment and mileage band, at that lot's average price (VIN ...001 at LOT-S: 24,300 after
15 days). The sale joins `sales` and the event `dms.listing.sold {vin, price, soldAt}` is emitted. A repeated listing schedules
nothing; a VIN of neither the lease nor the trade-in mock never sells.
Auth: API key in `x-api-key` (demo key `uc_dms-demo-key`); 401 with an error body otherwise.

Data in Postgres schema `dealer_dms` (models.py, seed.py): fixed, no randomness. A reset drops the written documents.

ASSUMPTION: the pinned cells are SUV 0-40k (North 23,600 / 34 days / 12 sales / spread 1,500; Central 24,000 / 21 / 22 /
    1,300; South 24,300 / 15 / 18 / 1,200) and EV crossovers, whose average is 58 days at LOT-N, 33 at LOT-C and 29 at
    LOT-S in every mileage band; the other cells follow from them by fixed factors (seed.py).
ASSUMPTION: the lease-mock cars on the lots (...041 to ...048) read as EV crossovers here too.
"""

from sim.core.mock import Mock
from sim.vendors.dealer_dms import routes, seed

MOCK = Mock("uc_dms", routes.router, seed.ensure, seed.reset, "Dealer management system (synthetic)")
