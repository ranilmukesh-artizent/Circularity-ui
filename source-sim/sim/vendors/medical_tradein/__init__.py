"""Medical trade-in register mock (plan 9, P9-12.9): capital medical equipment a hospital trades in, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `mc_tradein`, schema `medical_tradein`), so
the demo's 21 systems stay as they were. di reads it through its adapter (backend/di/connectors/adapters/medical_tradein.py),
which maps a trade-in to `asset.*` facts keyed by the device tag (schema.tag_key). The service records and the corrections of a
device come from the biomedical system mock (`mr_biomed`), not from here. There is no real register behind it.

    GET /medical-tradein/api/tradeins?tag=   [{tag, deviceClass, model, udi, singleUse, hasPatientData, market, targetMarket,
                                               serviceRecordRef, recallsClosed}]

Auth: API key in `x-api-key` (demo key `mc_tradein-demo-key`); 401 with an error body otherwise. The list is not paged (12 items).
Errors are `{"error": {"code", "message"}}`.

Data in Postgres schema `medical_tradein` (models.py, seed.py): `SYN-MC-0001` ... `0012`, fixed (no randomness). Imaging systems
and patient monitors hold patient data; every sixth device is single-use; every third is for another market than it came from;
some have no UDI or an open recall.
"""

from sim.core.mock import Mock
from sim.vendors.medical_tradein import routes, seed

MOCK = Mock("mc_tradein", routes.router, seed.ensure, seed.reset, "Medical trade-in register (synthetic)")
