"""Medical trade-in register (mc_tradein, plan 9 P9-12.9): capital medical equipment a hospital trades in. Read only.

Written against source-sim's synthetic trade-in mock (source-sim/sim/vendors/medical_tradein): no real register is connected. API
key in `x-api-key`; one unpaged list (`GET /tradeins`), read in full (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is unchanged
(di.connectors.extra registers it, source.reconnect connects it). It implements no registry entry of its own: it fills the
canonical `asset` model for a device, keyed by the source's org unit (schema.tag_key), which the medical capital pack's gates
read (G-MED-2 single use, G-MED-3 the UDI, the service record and the recalls of a device sold in another market, G-DATA-3
patient data). The service records and corrections of a device come from the biomedical system (`mr_biomed`), not from here.

Resource and facts (snake case of the source's camelCase fields)
    tradeins   asset.<tag key>   tag, device_class, model, udi, single_use, has_patient_data, origin_market (market),
                                 target_market, service_record_ref, recalls_closed
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import tag_key
from di.services.canonical.store import Fact

ASSET = {
    "tag": "tag", "deviceClass": "device_class", "model": "model", "udi": "udi", "singleUse": "single_use",
    "hasPatientData": "has_patient_data", "market": "origin_market", "targetMarket": "target_market",
    "serviceRecordRef": "service_record_ref", "recallsClosed": "recalls_closed",
}  # fmt: skip


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class MedicalTradeinAdapter(GenericAdapter):
    source_id = "mc_tradein"
    base_path = "/medical-tradein/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Medical trade-in register (synthetic)"
    source_type = "medical_tradein"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def tradeins(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org, url = _org(client), client.url("/tradeins")
            rows = client.get_json("/tradeins")
            client.note_records(len(rows))
            for row in rows:
                yield Record("tradeins", str(row["tag"]), row | {"org_unit_id": org}, url)

        return [Resource("tradeins", tradeins, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = tag_key(p.get("org_unit_id"), p["tag"])
        facts = [Fact("asset", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in ASSET.items()]
        return keep(facts)


ADAPTER = MedicalTradeinAdapter()
