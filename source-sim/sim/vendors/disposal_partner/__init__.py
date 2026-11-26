"""Disposal partner mock (plan 9, P9-11.5): collects devices for disposal, sanitises patient-data devices and issues disposal
certificates, for the medical-device rental company. Synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `mr_disposal`, schema
`disposal_partner`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its adapter
(backend/di/connectors/adapters/disposal_partner.py), which maps a sanitisation record and a certificate to
`condition.sanitisation_record_ref` and `condition.disposal_certificate_ref`, keyed by device tag. It reads like an ordinary
JSON API (camelCase); no real disposal company is behind it.

    POST /disposal-partner/api/collections      {tags: [tag, ...], sanitisationRef?}   201 {collectionId, tags,
                                                  sanitisationRef, status: "collected", createdAt, certificatesDueAt}
    GET  /disposal-partner/api/certificates?tag=  [{certificateId, tag, collectionId, issuedAt}] the certificates already
                                                  issued (all of them without the parameter)
    POST /disposal-partner/api/sanitisations    {tag}   201 {sanitisationId, tag, status: "pending", requestedAt,
                                                  completesAt}; the same tag again answers 200 with the first record
    GET  /disposal-partner/api/sanitisations?tag= [{sanitisationId, tag, status: "completed", requestedAt, completedAt}]
                                                  the records already completed

Auth: API key in `x-api-key` (demo key `mr_disposal-demo-key`); 401 with an error body otherwise. Errors are
`{"error": {"code", "message"}}`. The lists are plain JSON arrays (no paging).

Time: the mock follows source-sim's simulated clock (`/_sim/clock`). A certificate is issued 2 simulated days after its
collection and a sanitisation record completes 1 simulated day after its request; until then neither is listed.

Rules: a collection of a device that holds patient data answers 422 `sanitisation_missing` unless `sanitisationRef` is given
(not blank); a tag must look like `SYN-MR-IP-0001`, `tags` must be a non-empty list (422 `invalid` otherwise); a body that
is not JSON answers 400. Patient monitors (class code `PM`) hold patient data, as in the asset management mock.

Data in Postgres schema `disposal_partner` (models.py, seed.py): empty after a reset; the POST routes fill it.
`COL-0001` ..., `SAN-0001` ... number in order of arrival; a certificate is `DC-<collection number>-<position in tags>`.

ASSUMPTION: `sanitisationRef` is only checked for being present, not looked up (the record may still be pending when the
    collection is booked).
ASSUMPTION: the sanitisation record is one per tag (a repeat request is idempotent).
"""

from sim.core.mock import Mock
from sim.vendors.disposal_partner import routes, seed

MOCK = Mock("mr_disposal", routes.router, seed.ensure, seed.reset, "Disposal partner (synthetic)")
