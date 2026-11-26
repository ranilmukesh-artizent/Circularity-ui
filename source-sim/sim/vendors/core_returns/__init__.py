"""Core returns system mock (plan 9, P9-12.8): the automotive cores that dealers send back for a deposit, with the inspection
result of each, and the dealers' return history, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `core_ret`, schema `core_returns`), so the
demo's 21 systems stay as they were. di reads it through its adapter (backend/di/connectors/adapters/core_returns.py), which
maps a core to `asset.*`, `condition.core_checks`, `condition.dealer_rejects` and `market.core_deposit` facts. No real core
program, remanufacturer or dealer is behind it.

    GET /core-returns/api/cores                    [{coreId, dealerId, declaredPartNumber, observedPartNumber, deposit,
                                                     checks: {housing_intact, no_cracks, complete, family_match}, receivedAt}]
    GET /core-returns/api/dealer-history?dealerId= [{dealerId, coreId, outcome, at}]

`outcome` is `accepted` or `rejected`. Auth: API key in `x-api-key` (demo key `core_ret-demo-key`). Errors are
`{"error": {"code", "message"}}`.

Data in Postgres schema `core_returns` (fixed, no randomness): `C-0001` a clean alternator core; `C-0002` the bracket is missing
(`complete` false); `C-0003` cracked (`no_cracks` false); `C-0004` declared `ALT-1450` but a starter (`STR-2210`) arrived
(`family_match` false); `C-0005` a clean core from dealer `D-17`, who had four rejected returns, three of them in the 90 days
before it (2026-11-20).
"""

from sim.core.mock import Mock
from sim.vendors.core_returns import routes, seed

MOCK = Mock("core_ret", routes.router, seed.ensure, seed.reset, "Core returns system (synthetic)")
