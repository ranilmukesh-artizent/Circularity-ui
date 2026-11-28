"""Rental system mock (plan 9, P9-11.2): the medical-device rental company's returns, requests, depots and demand, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `mr_rental`, schema
`medical_rental_system`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its
adapter (backend/di/connectors/adapters/medical_rental_system.py), which maps a return to `asset.*`, `demand.*` facts keyed
by device tag. It reads like an ordinary JSON API (camelCase); there is no real rental system behind it and no real
hospital: a hospital is `HOSP-A` ... `HOSP-F`, labelled "Hospital A (synthetic)".

    GET  /rental-system/api/returns?depot=            [{returnId, tag, hospitalId, ward, wardType, depot, checkedInAt,
                                                         previousRentalEnd}]  wardType is `general` or `isolation`
    GET  /rental-system/api/requests                  the open requests [{reqId, hospitalId, deviceClass, startDate, days,
                                                         region, requestedAt}] (a dispatched request is no longer open)
    GET  /rental-system/api/hospitals                 [{hospitalId, label, latitude, longitude, region}]
    GET  /rental-system/api/depots                    [{depotId, label, latitude, longitude, region, deconLines}]
    GET  /rental-system/api/demand-forecast?region=   [{region, weekStart, requests}], 8 weeks per region (all regions
                                                         without the parameter)
    GET  /rental-system/api/turnaround?depot=&days=   per return of the last `days` days (default 14, 1 to 365)
                                                         [{returnId, tag, depot, checkedInAt, waitingDays: {decon_queue,
                                                         service, transport}, totalDays}]
    POST /rental-system/api/dispatches                {tag, reqId, evidence: {serviceRef, certExpiry, deconRef}}

Auth: API key in `x-api-key` (demo key `mr_rental-demo-key`); 401 with an error body otherwise. Errors are
`{"error": {"code", "message"}}`. The lists are plain JSON arrays (small, no paging).

Dispatch: idempotent by nature. The first POST for a request makes `DSP-0001` ... and answers 201; the same tag and request
again answer 200 with that first document and write nothing; another tag for a request already dispatched answers 409.
A dispatch closes the request (it leaves GET requests). 422 for a body that is not valid (tag `SYN-MR-XX-0000` form, the
three evidence fields, `certExpiry` an ISO date), 404 for an unknown request, 400 for a body that is not JSON.

Data in Postgres schema `medical_rental_system` (models.py, seed.py), fixed (no randomness), so a reset gives the same JSON
again. The mock's own date is 26 Nov 2026 09:00 UTC (it does not follow the simulated clock). What the later tasks lean on:
requests REQ-1 (HOSP-A, 12 miles from the East depot), REQ-2 (HOSP-B, 5 miles), REQ-3 (HOSP-C, 48 miles) and REQ-4 (HOSP-B
again 17 hours after REQ-2), all for infusion pumps, and REQ-5 (HOSP-A) for a patient monitor (SYN-MR-PM-0007 is
re-rented there once its repair is approved), all 30 days from 27 Nov 2026; the East depot has one decontamination line
(West and North two); East's last 14 days average 3.4 waiting days over 13 returns (10 in the 14 days before: returns rose
30 %), West and North 1.6; East's forecast is lowest in the week of 7 Dec 2026; tags `SYN-MR-IP-0010` and `0011` come back from
HOSP-D's isolation ward; tag `SYN-MR-IP-0001` is an East return.

ASSUMPTION: a depot's region is its id (`EAST`), and so is a hospital's region; the forecast `region` filter is exact.
ASSUMPTION: the waiting days split by cause differ by depot: East's one decontamination line makes the queue 60 % of its
    wait; West and North wait mostly for service.
ASSUMPTION: REQ-4 comes from HOSP-B: the spec names the repeat request without its hospital.
"""

from sim.core.mock import Mock
from sim.vendors.medical_rental_system import routes, seed

MOCK = Mock("mr_rental", routes.router, seed.ensure, seed.reset, "Rental system (synthetic)")
