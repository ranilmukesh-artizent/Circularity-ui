"""Retail returns portal mock (plan 9, P9-12.10): the items customers returned to a store or by post, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `b2c_ret`, schema `retail_returns`). di reads
it through its adapter (backend/di/connectors/adapters/retail_returns.py), which maps each item to `asset` facts for the
serialised retail returns pack. No real retailer or returns platform is behind it, and no retailer is named.

    GET /retail-returns/api/returns        [{itemId, serial, imei, itemClass: "phone" | "tablet" | "apparel" | "footwear",
                                             sku, unsold, exceptionEvidence}]  (optional `?itemClass=` filter)

`imei` is set for phones and tablets and null otherwise. `unsold` marks stock that was never sold to a customer (a store
return of new goods); `exceptionEvidence` is null or `{exception, ref}` naming a reason why such stock may be destroyed.
Auth: API key in `x-api-key` (demo key `b2c_ret-demo-key`).

Data in Postgres schema `retail_returns` (fixed, no randomness): 12 items, `RET-0001` ... `RET-0012`.
"""

from sim.core.mock import Mock
from sim.vendors.retail_returns import routes, seed

MOCK = Mock("b2c_ret", routes.router, seed.ensure, seed.reset, "Retail returns portal (synthetic)")
