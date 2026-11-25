"""Device registry (dvreg, plan 9 P9-6.2): the IMEI check a device-recommerce buyer runs before paying out. Read only.

Written against source-sim's synthetic registry mock (source-sim/sim/generic/specs/device_registry.py): no real
blacklist or finance registry is connected. API key in `X-Api-Key`; offset paging (`items`, `next`, `total`);
`?updated_since=` delta reads.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It writes only facts, never a table row,
and implements no registry entry of its own: it fills the canonical model `condition` that the device pack's registry
evidence reads. Nothing is ever written to the source.

Resources and facts, keyed `IMEI:<imei>` (snake case of the source's camelCase fields)
    checks   condition.device_blacklist (`clear`, `reported_lost`, `reported_stolen`), device_lock (= activationLock,
             `on` or `off`), device_finance (`clear`, `balance_owed`), registry_checked_at (= checkedAt)
"""

from collections.abc import Iterator

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.store import Fact

CHECK = {
    "blacklist": "device_blacklist", "activationLock": "device_lock", "finance": "device_finance",
    "checkedAt": "registry_checked_at",
}  # fmt: skip


def imei_key(imei: str) -> str:
    """The canonical key of a device: `IMEI:<imei>` (shared with the device lab)."""
    return f"IMEI:{imei}"


class DeviceRegistryAdapter(GenericAdapter):
    source_id = "dvreg"
    base_path = "/device-registry/v1"
    auth_kind = "api_key"
    api_key_header = "X-Api-Key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Device registry (synthetic)"
    source_type = "dvreg"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def checks(client: SourceClient, since: str | None) -> Iterator[Record]:
            return self.flat(client, "checks", "/checks", "imei", since)

        return [Resource("checks", checks)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = imei_key(p["imei"])
        return keep(
            [Fact("condition", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in CHECK.items()]
        )


ADAPTER = DeviceRegistryAdapter()
