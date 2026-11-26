"""Network inventory mock (plan 9, P9-10.2): the installed network elements of a telecom operator, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `tn_inv`, schema
`network_inventory`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its
adapter (backend/di/connectors/adapters/network_inventory.py), which maps an element to `asset.*` facts keyed by serial
(schema.serial_key). It reads like an ordinary JSON API (camelCase); there is no real inventory system behind it and no
real company: manufacturers are codes (`MFR-A` ...).

    GET  /network-inventory/api/elements?serial=&site=&limit=&offset=   {elements, next}
    POST /network-inventory/api/transfer-orders   {serial, toSite | toPool}  one of the two; idempotent on both
    POST /network-inventory/api/retirements       {serial}                   idempotent on the serial

Auth: API key in `x-api-key` (demo key `tn_inv-demo-key`); 401 with an error body otherwise.
Paging: `limit` 1-200 (default 50) and `offset`; `next` is the next offset or null. Errors are
`{"error": {"code", "message"}}`. A write answers 201 with the new document, or 200 with the first one for a repeat.
The writes are ledgers: they do not change the elements.

Data in Postgres schema `network_inventory` (models.py, seed.py): 120 elements `SN-TN-0001` ... `0120` over regions
North, South, East, West (30 each), fixed (no randomness). The ones the later tasks lean on: every sixth serial from
`0006` is an `RAD-7700` carrying `exportClassConfirmed` "5A002"; every sixth from `0001` is an `RRU-4410` with
`exportClassInferred` "5A992" and no confirmed class; `0001`-`0033` are `removed` (the tracker's ordinary jobs took them
off their sites). The element `SN-TN-0201` (an RAD-7700 from the North) joins one simulated day after a reset
(scheduler handler `tn_inv.element.create`, event `inventory.element.created`); `0202`-`0208` never join.

ASSUMPTION: the inventory has no change stamps, so it is read in full (no `updatedSince`).
ASSUMPTION: a retirement does not change `status` (the three statuses are in_service, removed, spare).
"""

from sim.core.mock import Mock
from sim.vendors.network_inventory import routes, seed

MOCK = Mock("tn_inv", routes.router, seed.ensure, seed.reset, "Network inventory (synthetic)")
