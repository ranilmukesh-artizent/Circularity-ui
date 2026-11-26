"""Recycler portal mock (plan 9, P9-10.5): certified recyclers, pickups and disposal certificates, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `tn_recycler`, schema
`recycler_portal`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its adapter
(backend/di/connectors/adapters/recycler_portal.py), which maps a recycler to `vendor.*` facts (certificate, dangerous-goods
lane) keyed by its id and a disposal certificate to `condition.disposal_record_ref` keyed by serial. No real recycler.

    GET  /recycler-portal/api/vendors                 [{vendorId, label, certificate: {scheme, ref, expires}, dgLane, regions}]
    POST /recycler-portal/api/pickups                 {serials, vendorId, weeeCategory, weightKg}  idempotent
    GET  /recycler-portal/api/certificates?serial=    [{certificateId, serial, pickupId, vendorId, issuedAt}]

`scheme` is `R2v3` or `e-Stewards`. A pickup answers 201 with the new document, or 200 with the first one for a repeat (same
vendor and set of serials); 422 `certificate_expired` for a recycler whose certificate has lapsed; 404 for an unknown
recycler; 422 `invalid` for a bad body (invalid JSON 400). Two simulated days after a pickup, one disposal certificate per
serial is issued (scheduler handler `tn_recycler.certificates.issue`, one event `recycler.certificate.issued` each).
Auth: API key in `x-api-key` (demo key `tn_recycler-demo-key`); 401 with an error body otherwise. Lists are not paged.

Data in Postgres schema `recycler_portal` (models.py, seed.py): `RV-1` certificate valid to 2027-06-30, with a
dangerous-goods lane; `RV-2` certificate expires 2026-10-31 and is lapsed (see below).

ASSUMPTION: the simulated clock starts on 2026-10-07, before `RV-2`'s date, so the lapse is stored (`vendor.lapsed`), not
computed from the date; a pickup is also refused when a certificate's date is past on the simulated clock.
ASSUMPTION: `dgLane` is a boolean; the spec names no regions, so `RV-1` serves North and South, `RV-2` East and West.
ASSUMPTION: a pickup does not check the dangerous-goods lane or the regions.
"""

from sim.core.mock import Mock
from sim.vendors.recycler_portal import routes, seed

MOCK = Mock("tn_recycler", routes.router, seed.ensure, seed.reset, "Recycler portal (synthetic)")
