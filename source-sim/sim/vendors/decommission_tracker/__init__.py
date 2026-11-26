"""Decommission tracker mock (plan 9, P9-10.2): the removal jobs of a telecom operator's sites and the demand of
sites for equipment, synthetic. Read only.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `tn_decom`, schema
`decommission_tracker`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its
adapter (backend/di/connectors/adapters/decommission_tracker.py), which maps a removed unit to `asset.*` facts keyed by
serial and a site demand to a `demand.site_demand` fact. The field service app stays the existing `fsm` source: this
tracker carries the removal jobs, so the demo's service management seed is not touched. No real system, no real company.

    GET /decommission/api/v2/removal-jobs   {jobs: [{jobId, siteId, removedAt, programme, units: [{serial, model}]}]}
    GET /decommission/api/v2/site-demand    [{demandId, siteId, model, minFirmwareMajor, needBy, region}]

`programme` is `site_swap`, `decommission` or `reimbursement_programme`. Auth: API key in `x-api-key` (demo key
`tn_decom-demo-key`); 401 with an error body otherwise. Neither list is paged.

Data in Postgres schema `decommission_tracker` (models.py, seed.py): 12 jobs and 2 site demands, fixed. Job `RJ-09`
removes `SN-TN-0201` ... `0208`, serials the network inventory does not hold (`0201` joins it one simulated day after a
reset). `SD-112` needs an `RRU-4410` (any firmware) at `SITE-112`, North; `SD-207` needs an `RTR-880` with firmware 7 or
later at `SITE-207`.

ASSUMPTION: `SITE-207` is in the East region (the spec names none).
ASSUMPTION: `removedAt` is a date, three days apart from job to job, the last on 2026-10-04.
"""

from sim.core.mock import Mock
from sim.vendors.decommission_tracker import routes, seed

MOCK = Mock("tn_decom", routes.router, seed.ensure, seed.reset, "Decommission tracker (synthetic)")
