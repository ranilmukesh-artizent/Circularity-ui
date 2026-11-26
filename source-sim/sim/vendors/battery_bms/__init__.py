"""Battery management data mock (plan 9, P9-12.7): the state of health of battery packs read from the BMS, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `bat_bms`, schema `battery_bms`). di reads it
through its adapter (backend/di/connectors/adapters/battery_bms.py), which maps each pack to `asset` and `condition` facts keyed by
the pack id. No real battery management system or cloud is behind it.

    GET /battery-bms/api/packs     [{packId, vinRef, chemistry, sohPct, expectedLifeYears, readAt, thermalEvent, damaged,
                                     safetyClass, market}]

`chemistry` is `NMC`, `LFP` or `NCA`; `vinRef` is the VIN of the car the pack came from (null for an industrial pack); `market`
is `EU` or `US`; `safetyClass` is the UN class of the pack's transport (`9`, or `damaged` for a pack needing the dangerous-goods
lane). Auth: API key in `x-api-key` (demo key `bat_bms-demo-key`).

Data in Postgres schema `battery_bms` (fixed, no randomness): `BP-044` (VIN SYNUC000000000044, NMC, state of health 74 percent,
EU) is the pack of the car whose assessment says replace it; `BP-101` is a healthy industrial LFP pack (86 percent, US), `BP-102`
a second-life one (66 percent, EU), `BP-103` damaged and `BP-104` with a thermal event (both need the dangerous-goods lane).
"""

from sim.core.mock import Mock
from sim.vendors.battery_bms import routes, seed

MOCK = Mock("bat_bms", routes.router, seed.ensure, seed.reset, "Battery management data (synthetic)")
