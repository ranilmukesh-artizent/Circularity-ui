"""Vehicle recall database mock (plan 9, P9-9.5): open and remedied safety recalls by VIN, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `uc_recall`, schema
`vehicle_recall`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its
adapter (backend/di/connectors/adapters/vehicle_recall.py): the per-VIN lookup is the evidence a used-car case gates on
(UC-08), the bulk list feeds the sync. A public recall lookup by VIN exists in real life; this mock is synthetic and
claims no connection to it. Campaign ids are `SYN-...`, never a real campaign.

    GET /vehicle-recall/api/recalls/vin/{vin}                      {vin, checkedAt, openRecalls, remedied}
    GET /vehicle-recall/api/recalls?limit=&offset=&updatedSince=   {items, next, total}

A lookup is a fresh check: `checkedAt` is the simulated now (sim/core/clock.py) of the call, so it moves with the
clock. `openRecalls` rows are `{campaignId, component, summary, remedyAvailable}`; `remedied` rows are
`{campaignId, remedyRef, remediedAt}` (the field is spelled as the plan's interface has it). A VIN with no recall gets
two empty lists. A VIN is 17 letters and digits, else 400.
The bulk list has one row per (campaign, VIN): `{campaignId, vin, status: open|remedied, component, summary,
remedyAvailable, remedyRef, remediedAt, updatedAt}`.

Auth: API key in `x-api-key` (demo key `uc_recall-demo-key`); 401 with an error body otherwise.
Paging: `limit` 1-200 (default 25) and `offset`; `next` is the next offset or null. Errors are
`{"error": {"code", "message"}}`.

Data in Postgres schema `vehicle_recall` (models.py, seed.py), fixed: campaign SYN-24V-001 open on the cars `SYNUC...002`,
`...050` and `...055`; campaign SYN-25V-014 on `...060`, remedied with `RR-0060`. Every other VIN has no recall.

ASSUMPTION: remedy parts are available (`remedyAvailable` true) for the open campaign.
ASSUMPTION: `updatedAt` of a row runs one minute apart in seed order, ending at the demo's as-of time.
"""

from sim.core.mock import Mock
from sim.vendors.vehicle_recall import routes, seed

MOCK = Mock("uc_recall", routes.router, seed.ensure, seed.reset, "Vehicle recall database (synthetic)")
