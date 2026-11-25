"""Network inventory (tn_inv, plan 9 P9-10.2): the installed network elements of a telecom operator. Read only.

Written against source-sim's synthetic inventory mock (source-sim/sim/vendors/network_inventory): no real inventory system
is connected. API key in `x-api-key`; offset paging (`elements`, `next`). The mock has no change stamps, so the one
resource is read in full (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own:
it fills the canonical model `asset` for a unit, keyed by the source's org unit (schema.serial_key), which the telecom
network pack's gates read. Nothing is ever written to the source here (its two write routes are for later tasks).

Resource and facts (snake case of the source's camelCase fields)
    elements   asset.<serial key>   serial, model, part_number, hw_revision, firmware, manufacturer, site, site_kind, region,
                                    inventory_status (status), export_class (exportClassConfirmed), export_class_inferred
The two export classes are different facts on purpose: `export_class` holds only a class the source confirmed, and is
absent when it did not; the class inferred from the part number goes to `export_class_inferred` and is never promoted.
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import serial_key
from di.services.canonical.store import Fact

ASSET = {
    "serial": "serial", "model": "model", "partNumber": "part_number", "hwRevision": "hw_revision", "firmware": "firmware",
    "manufacturer": "manufacturer", "site": "site", "siteKind": "site_kind", "region": "region",
    "status": "inventory_status", "exportClassConfirmed": "export_class", "exportClassInferred": "export_class_inferred",
}  # fmt: skip


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class NetworkInventoryAdapter(GenericAdapter):
    source_id = "tn_inv"
    base_path = "/network-inventory/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    items_key = "elements"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Network inventory (synthetic)"
    source_type = "network_inventory"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def elements(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org = _org(client)
            for row, url in self.pages(client, "/elements"):
                yield Record("elements", str(row["serial"]), row | {"org_unit_id": org}, url)

        return [Resource("elements", elements, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = serial_key(p.get("org_unit_id"), p["serial"])
        facts = [Fact("asset", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in ASSET.items()]
        return keep(facts)


ADAPTER = NetworkInventoryAdapter()
