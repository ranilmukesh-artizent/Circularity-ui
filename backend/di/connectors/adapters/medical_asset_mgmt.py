"""Asset management (mr_assets, plan 9 P9-11.2): the medical-device rental company's device register. Read only.

Written against source-sim's synthetic asset management mock (source-sim/sim/vendors/medical_asset_mgmt): no real asset
system is connected. API key in `x-api-key`; a plain JSON array (no paging, no change stamps, so the resource is read in
full: Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own:
it fills the canonical models `asset` and `market` for a device, keyed by the source's org unit (schema.tag_key), which
the medical rental pack's gates and valuer read. Nothing is ever written to the source.

Resource and facts (snake case of the source's camelCase fields)
    devices   asset.<tag key>   tag, device_class, model, serial, in_service_date, age_years, book_value (bookValue),
                                has_patient_data
              market.<tag key>  residual_sale_value (residualSaleValue)
`age_years` is not in the source: the years from `inServiceDate` to the workspace clock (di.core.clock), one decimal.
`manufacturerCode` stays in the raw record: no fact.
"""

from collections.abc import Iterator
from datetime import date

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.core import clock
from di.services.canonical.schema import tag_key
from di.services.canonical.store import Fact

ASSET = {
    "tag": "tag", "deviceClass": "device_class", "model": "model", "serial": "serial", "inServiceDate": "in_service_date",
    "bookValue": "book_value", "hasPatientData": "has_patient_data",
}  # fmt: skip


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


def age_years(in_service: str | None) -> float | None:
    """Whole days since the in-service date, in years (365.25 days), one decimal; None for a missing or odd date."""
    try:
        since = date.fromisoformat(str(in_service)[:10])
    except ValueError:
        return None
    return round((clock.now().date() - since).days / 365.25, 1)


class MedicalAssetMgmtAdapter(GenericAdapter):
    source_id = "mr_assets"
    base_path = "/asset-management/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Asset management (synthetic)"
    source_type = "assets"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def devices(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org = _org(client)
            rows = client.get_json("/devices")
            client.note_records(len(rows))
            url = client.url("/devices")
            for d in rows:
                yield Record("devices", str(d["tag"]), d | {"org_unit_id": org}, url)

        return [Resource("devices", devices, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = tag_key(p.get("org_unit_id"), p["tag"])
        facts = [Fact("asset", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in ASSET.items()]
        facts.append(
            Fact("asset", key, "age_years", age_years(p.get("inServiceDate")), "inServiceDate", p.get("inServiceDate"),
                 "Years from the in-service date to the workspace clock")
        )  # fmt: skip
        sale = p.get("residualSaleValue")
        facts.append(Fact("market", key, "residual_sale_value", sale, "residualSaleValue", sale, "Camel case to snake case"))
        return keep(facts)


ADAPTER = MedicalAssetMgmtAdapter()
