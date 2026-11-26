"""IT service management and CMDB (it_cmdb, plan 9 P9-12.2): the configuration items of an IT estate. Read only.

Written against source-sim's synthetic CMDB mock (source-sim/sim/vendors/itsm_cmdb): no real CMDB is connected. API key in
`x-api-key`; one unpaged list (`GET /now/cis`), read in full (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged (di.connectors.extra registers it, source.reconnect connects it). It implements no registry entry of its own: it
fills the canonical model for a unit, keyed by the source's org unit (schema.serial_key), which the ITAD pack's gates read.

Resource and facts (snake case of the source's camelCase fields)
    cis   asset.<serial key>    serial, model, asset_class (assetClass), owner_org (ownerOrg), owner_tenant (ownerOrg),
                                security_level, lease_ref, lessor_return_required, consent_to_resell, media (the list of
                                {mediaSerial, type})
          market.<serial key>   new_price (newPrice)
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import serial_key
from di.services.canonical.store import Fact

ASSET = {
    "serial": "serial", "model": "model", "assetClass": "asset_class", "ownerOrg": "owner_org", "securityLevel": "security_level",
    "leaseRef": "lease_ref", "lessorReturnRequired": "lessor_return_required", "consentToResell": "consent_to_resell",
    "media": "media",
}  # fmt: skip


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class ItsmCmdbAdapter(GenericAdapter):
    source_id = "it_cmdb"
    base_path = "/itsm-cmdb/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "IT service management and CMDB (synthetic)"
    source_type = "itsm_cmdb"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def cis(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org, url = _org(client), client.url("/now/cis")
            rows = client.get_json("/now/cis")
            client.note_records(len(rows))
            for row in rows:
                yield Record("cis", str(row["serial"]), row | {"org_unit_id": org}, url)

        return [Resource("cis", cis, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = serial_key(p.get("org_unit_id"), p["serial"])
        facts = [Fact("asset", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in ASSET.items()]
        facts.append(Fact("asset", key, "owner_tenant", p.get("ownerOrg"), "ownerOrg", p.get("ownerOrg"), "The owning org"))
        facts.append(Fact("market", key, "new_price", p.get("newPrice"), "newPrice", p.get("newPrice"), "The catalogue price"))
        return keep(facts)


ADAPTER = ItsmCmdbAdapter()
