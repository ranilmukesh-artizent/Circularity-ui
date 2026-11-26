"""Subscriber returns and CPE refurbishment mock (plan 9, P9-12.6): returned home routers, their factory-reset records, the lots
built from them and the new-subscriber forecast, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `cpe_bss`, schema `cpe_returns`). di reads it
through its adapter (backend/di/connectors/adapters/cpe_returns.py), which maps each return to `asset` facts, each reset record to
`condition.factory_reset`, each lot to an `asset` record with its serials, and the forecast to `demand`. No real billing or
refurbishment system is behind it. Subscriber references are codes only.

    GET /cpe-returns/api/returns                    [{serial, model, reason: upgrade | contract_end | fault_swap, subscriberRef,
                                                      returnedAt}]
    GET /cpe-returns/api/factory-resets?serial=     [{serial, method: "factory_reset", firmwareRefreshed, at}]
    GET /cpe-returns/api/lot-grades                 [{lotId, model, grade, week, serials: [serial]}]
    GET /cpe-returns/api/new-subscriber-forecast    [{model, week, units}]

Auth: API key in `x-api-key` (demo key `cpe_bss-demo-key`).

Data in Postgres schema `cpe_returns` (fixed, no randomness): lot `LOT-R7-B-W47` holds 500 routers (`SN-CPE-R7-0001` ... `0500`),
three of them (`0101`, `0202`, `0303`) with no reset record; lot `LOT-R7-B-W48` holds 900 routers (`1001` ... `1900`), all reset.
"""

from sim.core.mock import Mock
from sim.vendors.cpe_returns import routes, seed

MOCK = Mock("cpe_bss", routes.router, seed.ensure, seed.reset, "Subscriber returns and CPE refurbishment (synthetic)")
