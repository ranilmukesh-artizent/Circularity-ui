"""Device registry (`dvreg`, P9-6.1): the IMEI check a device-recommerce buyer runs before paying out.
Read: GET /checks?imei=... (blacklist `clear|reported_lost|reported_stolen`, activationLock `on|off`, finance
`clear|balance_owed`, checkedAt). Read only. Synthetic; the data is sim/seed/devices.py (seed 4242), shared with the
device lab and the market. Not a demo source: registered in sim/core/registry.py EXTRA_SYSTEMS.
"""

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed
from sim.seed.devices import world


def seed(s: Seed) -> dict[str, list[dict]]:  # noqa: ARG001 - the world does not depend on the demo's seed
    return {"checks": world().checks}


SPEC = Spec(
    source_id="dvreg",
    title="Device Registry",
    schema="device_registry",
    base_path="/device-registry/v1",
    auth=Auth("api_key", header="X-Api-Key"),
    paging=Paging("offset", items_key="items", next_key="next", total_key="total"),
    resources=(Resource("checks", "/checks", "imei", filters=("imei", "blacklist", "activationLock", "finance")),),
    seed=seed,
)
