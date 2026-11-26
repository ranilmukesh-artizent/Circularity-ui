"""Retail returns portal (b2c_ret, plan 9 P9-12.10): the items customers returned. Read only.

Written against source-sim's synthetic returns mock (source-sim/sim/vendors/retail_returns): no real retailer or returns platform
is connected. API key in `x-api-key`; one unpaged list (`GET /returns`), read in full (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is unchanged
(di.connectors.extra registers it, source.reconnect connects it). It implements no registry entry of its own: it fills the
canonical `asset` of an item for the serialised retail returns pack (the `intake_trigger` mapping opens a case per serial),
keyed by the source's org unit (schema.serial_key).

Resource and facts (snake case of the source's camelCase fields)
    returns   asset.<serial key>    item_id, serial, imei (phones and tablets), item_class, sku, unsold, exception_evidence
                                    (null, or an object {exception, ref}), owner_tenant (the source's org unit)
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import serial_key
from di.services.canonical.store import Fact

ASSET = {
    "itemId": "item_id", "serial": "serial", "imei": "imei", "itemClass": "item_class", "sku": "sku", "unsold": "unsold",
    "exceptionEvidence": "exception_evidence",
}  # fmt: skip


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class RetailReturnsAdapter(GenericAdapter):
    source_id = "b2c_ret"
    base_path = "/retail-returns/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Retail returns portal (synthetic)"
    source_type = "retail_returns"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def returns(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org, url = _org(client), client.url("/returns")
            rows = client.get_json("/returns")
            client.note_records(len(rows))
            for row in rows:
                yield Record("returns", str(row["serial"]), row | {"org_unit_id": org}, url)

        return [Resource("returns", returns, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = serial_key(p.get("org_unit_id"), p["serial"])
        facts = [Fact("asset", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in ASSET.items()]
        org = p.get("org_unit_id")
        facts.append(Fact("asset", key, "owner_tenant", org, "org_unit_id", org, "The source's org unit"))
        return keep(facts)


ADAPTER = RetailReturnsAdapter()
