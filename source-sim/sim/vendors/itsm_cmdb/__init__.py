"""IT service management and CMDB mock (plan 9, P9-12.2): the configuration items of an enterprise's IT estate, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `it_cmdb`, schema `itsm_cmdb`), so the
demo's 21 systems stay as they were. di reads it through its adapter (backend/di/connectors/adapters/itsm_cmdb.py), which
maps a configuration item to `asset.*` and `market.new_price` facts keyed by serial (schema.serial_key). It reads like an
ordinary ITSM table API (camelCase); there is no real CMDB behind it and no real company.

    GET /itsm-cmdb/api/now/cis?serial=   [{ciId, serial, model, assetClass, ownerOrg, securityLevel, leaseRef,
                                           lessorReturnRequired, consentToResell, newPrice, media: [{mediaSerial, type}]}]

Auth: API key in `x-api-key` (demo key `it_cmdb-demo-key`); 401 with an error body otherwise. The list is not paged: the
CMDB is small (70 items). Errors are `{"error": {"code", "message"}}`.

Data in Postgres schema `itsm_cmdb` (models.py, seed.py): `SN-IT-0001` ... `0050` (pickup PU-01 of the logistics mock) and
`SN-IT-0101` ... `0120` (PU-02), fixed (no randomness). Every fifth item of the first pickup is under a lease
(`leaseRef`, `lessorReturnRequired` true, `consentToResell` false). `SN-IT-9999` (received but on no manifest) is not in
the CMDB.
"""

from sim.core.mock import Mock
from sim.vendors.itsm_cmdb import routes, seed

MOCK = Mock("it_cmdb", routes.router, seed.ensure, seed.reset, "IT service management and CMDB (synthetic)")
