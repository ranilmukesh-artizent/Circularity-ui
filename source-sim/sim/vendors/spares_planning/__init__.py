"""Spares planning mock (plan 9, P9-10.4): the spares catalogue with list prices, the stock targets, the six-month need,
the spares pool and the open purchase requisitions of a telecom operator, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `tn_spares`, schema
`spares_planning`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its
adapter (backend/di/connectors/adapters/spares_planning.py). No real planning system, no real company.

    GET  /spares-planning/api/catalogue      [{model, newPrice, generation: "current" | "previous", failureRate12m}]
    GET  /spares-planning/api/targets        [{region, model, target, stock, useProbability12m}]
    GET  /spares-planning/api/forecast6m     [{region, model, need}]   (no row for a model no region needs)
    GET  /spares-planning/api/stock          [{serial, model, region, idleDays}]   the spares pool, one row per unit
    GET  /spares-planning/api/requisitions   [{reqId, region, model, quantity, status: "open", createdAt}]
    POST /spares-planning/api/requisitions/{reqId}/reduce   {qty, reason} -> the requisition after the cut

Catalogue: `RRU-4410` 9,800 current; `BBU-2200` 4,200 previous; `RTR-880` 6,500 current; `PSU-48` 1,100 current;
`RAD-7700` 7,300 current. Four regions (North, South, East, West) hold a target and a stock of each model: North
`RRU-4410` has target 4, stock 2, use probability 0.55; North holds three `PSU-48` units idle 41, 50 and 60 days (every
other unit 5 to 29 days). The six-month forecast never lists `BBU-2200`. Open requisitions: `PR-3301` West `PSU-48`
quantity 3, `PR-3302` North `RRU-4410` quantity 1. The stock listing agrees with the targets (a cell's stock is its
number of units).

Reduce: `qty` is the quantity to take off (a whole number, 1 up to the open quantity; taking all of it closes the
requisition and it leaves the open list) and `reason` is required. It is idempotent on the `Idempotency-Key` header
(no header: on requisition and quantity): a repeat answers 200 with the first answer and cuts nothing more. Unknown
requisition 404 `not_found`; a closed one 409 `not_open`; a bad body 422 `invalid`.

Auth: API key in `x-api-key` (demo key `tn_spares-demo-key`); 401 with an error body otherwise. None of the lists is
paged.

Data in Postgres schema `spares_planning` (models.py, seed.py): fixed, no randomness. A reset restores the requisitions.

ASSUMPTION: the catalogue's `newPrice` stands in for the ERP purchase-order price, so the demo's S/4HANA seed stays
    untouched.
ASSUMPTION: `qty` of a reduce is the amount cut, not the new quantity (the spec names no meaning).
"""

from sim.core.mock import Mock
from sim.vendors.spares_planning import routes, seed

MOCK = Mock("tn_spares", routes.router, seed.ensure, seed.reset, "Spares planning (synthetic)")
