"""Legacy body-shop system mock (plan 9, P9-9.13, story UC-04): the repair history of a used car, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `uc_bodyshop`, schema
`body_shop_legacy`, style `generic-rest`), so the demo's 21 systems, its screens and its counts stay as they were. It has no
adapter in di: the system is the one a customer's IT connects once from its API description, the connector is configuration
(an OpenAPI 3 document read by `registry.importSpec`), never code. This mock is synthetic and claims no connection to any
real product.

    GET /body-shop/openapi.json                 the API description (OpenAPI 3.0), open: a connector is built from it
    GET /body-shop/repairs?page=&size=          {repairs: [{repairId, vin, damageArea, repairDate, cost, insuranceClaim}],
                                                 page, pages, total}

`page` starts at 1; `size` is 1-100 (default 50); a page past the last one has no repairs. Errors are
`{"error": {"code", "message"}}`. Auth: API key in `x-api-key` (demo key `uc_bodyshop-demo-key`), 401 otherwise; the
description needs no key.

Data in Postgres schema `body_shop_legacy` (models.py, seed.py), fixed: 600 repairs `BS-0001` to `BS-0600` over the cars
`SYNUC...001` to `...100`, six each (repair n belongs to car ((n - 1) mod 100) + 1), damage areas, dates and costs from
fixed tables (no randomness), every date before the demo's as-of time (7 Oct 2026).

ASSUMPTION: the system lists repairs oldest first by id and has no delta read (a legacy system: whole pages only).
ASSUMPTION: `cost` is in US dollars and `insuranceClaim` is true for the repairs over 3,000.
"""

from sim.core.mock import Mock
from sim.vendors.body_shop_legacy import routes, seed

MOCK = Mock("uc_bodyshop", routes.router, seed.ensure, seed.reset, "Legacy body-shop system (synthetic)")
