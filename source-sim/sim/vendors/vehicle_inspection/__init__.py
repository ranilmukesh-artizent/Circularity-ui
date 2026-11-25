"""Vehicle inspection app mock (plan 9, P9-9.4): the condition evidence of the used-car segment, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `uc_insp`, schema
`vehicle_inspection`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its
adapter (backend/di/connectors/adapters/vehicle_inspection.py), which maps an inspection and a battery assessment to
`condition.*` facts keyed by VIN. There is no real inspection app behind it.

    GET  /vehicle-inspection/api/inspections?vin=&updatedSince=&limit=&offset=          {data, next}
    GET  /vehicle-inspection/api/battery-assessments?vin=&updatedSince=&limit=&offset=  {data, next}
    GET  /vehicle-inspection/api/battery-assessments/{assessmentId}                     one assessment
    POST /vehicle-inspection/api/battery-assessments  {vin}     201 {assessmentId, status: "scheduled", ...}

The assessment completes one simulated day later (sim/core/scheduler.py): `batterySoh` (the car's pack reading) and
`result` (`fit_for_retail` from 80, else `pack_replacement_needed`), and the mock emits `inspection.battery.completed`.
A POST with an `Idempotency-Key` repeats as the first assessment (200, no second one).

Auth: API key in `x-api-key` (demo key `uc_insp-demo-key`); 401 with an error body otherwise. Errors are
`{"error": {"code", "message"}}`. Paging: `limit` 1-200 (default 25), `offset`; `next` is the next offset or null.

Data in Postgres schema `vehicle_inspection` (models.py, seed.py): one inspection per VIN `SYNUC000000000001` ...
`...100` (the lease system's VINs and the dealer's trade-ins), fixed, no randomness. VINs ...090-...093 are `scheduled`
(late: no score, no photos, no estimate). The score runs 1-5 and 5 is best (the mock's truth; UC-03 makes a person
confirm it). Cars the later tasks lean on: ...001 score 4, recon 1,200 (paint and panel 700 with excess wear, tyres
500); ...004's odometer photo reads 61,240; ...007 recon 2,800; ...008 recon 16,500; EVs ...041-...048 carry
`batterySoh` (...044: 74); ...030-...034 have hail damage with recon under 2,500; ...015-...019 have paired devices.

ASSUMPTION: the odometer photo reading of VINs ...001-...060 equals the lease system's reading at return (so only
...004's mismatch with the lease record is a story); VINs ...061-...100 get a plain figure.
ASSUMPTION: a battery assessment is for an EV only (a VIN with a pack reading): another known VIN is 422, an unknown
VIN 404.
ASSUMPTION: the completed assessment reads the pack's `batterySoh` from the inspection (74 for ...044).
"""

from sim.core.mock import Mock
from sim.vendors.vehicle_inspection import routes, seed

MOCK = Mock("uc_insp", routes.router, seed.ensure, seed.reset, "Vehicle inspection app (synthetic)")
