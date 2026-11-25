"""Vehicle auction platform mock (plan 9, P9-9.6): weekly sales per site, the fees, cleared prices, salvage bids and
buyers, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `uc_auction`, schema
`vehicle_auction`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its
adapter (backend/di/connectors/adapters/vehicle_auction.py). It reads like an ordinary JSON API (camelCase); no real
auction house or buyer is behind it, and every amount is synthetic.

Reads (lists are `{items, next, total}`, `limit` 1-200 default 25 and `offset`; errors `{"error": {"code", "message"}}`):
    GET /vehicle-auction/v1/sales          ?site= : the sales still to come (a sale date from today of the simulated
                                           clock on), each with `daysAhead`; two sites weekly: AUC-E (return centre
                                           RC-East, next sale 6 days after the demo's as-of day: VIN ...001 returns
                                           there) and AUC-W (RC-West, 2 days)
    GET /vehicle-auction/v1/fees           {sellFee: 325, transport: 120}
    GET /vehicle-auction/v1/results        ?segment=&band= : cleared prices, segment (compact | midsize | suv |
                                           ev_crossover | truck) x mileage band (0-40k | 40-80k | 80-120k | 120k+):
                                           {segment, band, avgClearedPrice, count}; 20 rows
    GET /vehicle-auction/v1/salvage-bids   ?vin= : the best salvage bid per lease-mock VIN (...001 to ...060):
                                           {bidId, vin, buyerId, amount, validUntil}; ...001 is 2,100, ...008 is 3,900
    GET /vehicle-auction/v1/buyers         [{buyerId, name, salvage, titleDbReporting}]: SB-1 and SB-3 salvage buyers that
                                           report to the national title database, SB-2 a salvage buyer that does not,
                                           RB-1 a wholesale buyer (not salvage) that does
Writes (JSON body; idempotent: a repeat answers 200 with the first document instead of 201 and a second one. The
repeat is the `Idempotency-Key` header's, or else the same body key (vin and sale date; vin and buyer). A bad body is
422, one that is not JSON 400):
    POST /consignments {vin, saleDate, titleRef, disclosures}   -> {consignmentId: CN-0001 ...}
    POST /salvage-sales {vin, buyerId}                          -> {salvageSaleId: SS-0001 ...}; 422 `buyer_not_reporting`
                                           for a buyer that does not report to the title database (SB-2),
                                           `buyer_not_salvage` for one that does not buy salvage, `invalid` for an
                                           unknown buyer
Auth: API key in `x-api-key` (demo key `uc_auction-demo-key`); 401 with an error body otherwise.

Data in Postgres schema `vehicle_auction` (models.py, seed.py): fixed, no randomness. A reset drops the written
documents.

ASSUMPTION: the sale calendar is 26 weekly sales per site from the as-of day; `daysAhead` follows the simulated clock,
    so after the clock advances past a sale the next one shows.
ASSUMPTION: the best bid of every lease-mock car but ...001 and ...008 is 14 percent of its residual value, from
    SB-1, SB-2 or SB-3 in turn (...001 and ...008 from SB-1).
"""

from sim.core.mock import Mock
from sim.vendors.vehicle_auction import routes, seed

MOCK = Mock("uc_auction", routes.router, seed.ensure, seed.reset, "Vehicle auction platform (synthetic)")
