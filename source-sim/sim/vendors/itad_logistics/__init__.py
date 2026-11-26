"""ITAD logistics and chain of custody mock (plan 9, P9-12.2): pickups with their manifests, custody events, and media
erasure records, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `it_logistics`, schema
`itad_logistics`). di reads it through its adapter (backend/di/connectors/adapters/itad_logistics.py), which maps each
manifest serial and each received serial to `asset.pickup` / `asset.custody` facts and the erasures to `condition.erasures`.
No real logistics or ITAD provider is behind it.

    GET /itad-logistics/api/pickups                      [{pickupId, manifest: [serial], custody: [{event, at, by}],
                                                           received: [serial]}]
    GET /itad-logistics/api/erasures?mediaSerial=        [{mediaSerial, method, tool, toolVersion, verification,
                                                           operatorRef, at}]

`custody.event` is `picked_up`, `in_transit` or `received`; `method` is `clear`, `purge` or `destruct`; `verification` is
`passed` or `failed`. Auth: API key in `x-api-key` (demo key `it_logistics-demo-key`).

Data in Postgres schema `itad_logistics` (fixed, no randomness): pickup `PU-01` lists 50 serials (`SN-IT-0001` ... `0050`);
48 are received (`SN-IT-0017` and `SN-IT-0042` are not) plus `SN-IT-9999`, which is on no manifest. Pickup `PU-02` lists 20
(`SN-IT-0101` ... `0120`), all received. Erasures cover the media of the received serials: SSDs are purged, hard disks are
cleared, except `SN-IT-0004` (SSD cleared only) and `SN-IT-0008` (SSD purge failed verification).
"""

from sim.core.mock import Mock
from sim.vendors.itad_logistics import routes, seed

MOCK = Mock("it_logistics", routes.router, seed.ensure, seed.reset, "ITAD logistics and chain of custody (synthetic)")
