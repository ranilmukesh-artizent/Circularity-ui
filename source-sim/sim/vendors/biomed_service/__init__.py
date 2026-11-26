"""Biomedical service system mock (plan 9, P9-11.4): the medical-device rental company's service records, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `mr_biomed`, schema `biomed_service`),
so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its adapter
(backend/di/connectors/adapters/biomed_service.py), which maps a device's service record, the manufacturer's field safety
notices that cover it and its servicing assessment to `condition.*` and `intervention.repair_estimate` facts, keyed by device
tag. It reads like an ordinary JSON API (camelCase); there is no real biomedical system behind it.

    GET  /biomed-service/api/assets                   every device's service record (a JSON array, as the next one)
    GET  /biomed-service/api/assets/{tag}/service     {tag, model, serialNo, pmDue, pmCode, lastPm, certificationExpiry,
                                                       functionalTest {result, at}, electricalSafety {standard: "IEC 62353",
                                                       result, at}, notes [{text, kind: cosmetic|fault}], repairEstimate,
                                                       faults [text]}
    GET  /biomed-service/api/corrections              [{noticeId, model, serialFrom, serialTo, status: open|closed,
                                                        correctionRef}]
    GET  /biomed-service/api/assessments              every assessment; one: GET .../assessments/{tag}
                                                      {tag, plannedWork, result: servicing|remanufacturing|
                                                       full_refurbishment, assessedBy, at}
    POST /biomed-service/api/service-orders           {tag, kind: pm|certification|repair|refurbish, dueBy} -> 201 with
                                                      {orderId, ..., status: "accepted"}; the same (tag, kind, dueBy) again
                                                      -> 200 with the first order, nothing new (idempotent)

Auth: API key in `x-api-key` (demo key `mr_biomed-demo-key`); 401 with an error body otherwise. Errors are
`{"error": {"code", "message"}}`. Lists are plain JSON arrays (no paging).

Data in Postgres schema `biomed_service` (models.py, seed.py): one service record per device of the asset management mock
(80), fixed (no randomness). Pinned: SYN-MR-IP-0001 (certified to 31 Mar 2027, PM due 15 Feb 2027, tests passed, note
"Housing scuff", cosmetic), SYN-MR-IP-0002 (certified to 7 Dec 2026), SYN-MR-PM-0007 (monitor, repair estimate 1,350, a
display fault); notice FSN-031 (open, model IP-300, serials 3000 to 3099) covers SYN-MR-IP-0030; assessments for beds
SYN-MR-EB-0040 (servicing) and SYN-MR-EB-0041 (full_refurbishment). IEC 62353:2014 is named as the standard of the recorded
electrical safety test; the mock holds no text of the standard.

ASSUMPTION: `model` and `serialNo` (the manufacturer's model code and numeric serial the notices are written against) are
    not in the spec's service document; they are added so a notice's range can be matched to a device. The other pumps are
    model IP-200 (serial 2000 + n), SYN-MR-IP-0031 is IP-300 with serial 3131 (just outside the notice's range), the rest of
    a class is model <code>-100, serial 1000 + n.
ASSUMPTION: the two beds of the assessments are not in the asset management mock (it has 8 beds); an assessment is by tag.
ASSUMPTION: the other devices' dates count from the demo's as-of date (7 Oct 2026) and are computed from the tag's number.
"""

from sim.core.mock import Mock
from sim.vendors.biomed_service import routes, seed

MOCK = Mock("mr_biomed", routes.router, seed.ensure, seed.reset, "Biomedical service system (synthetic)")
