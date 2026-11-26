"""Vehicle pricing guide (uc_price, plan 9 P9-9.6): the retail and wholesale guide value of a car. Read only.

Written against source-sim's synthetic pricing guide mock (source-sim/sim/vendors/vehicle_pricing): no real price guide
is connected. API key in `x-api-key`. The guide answers one VIN at a time (`GET /v3/values?vin=`), so there is no paging
and no delta: every sync asks for each car again.

Not one of the demo's 21 sources: it starts unregistered, so every demo screen and count is unchanged.
di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own. It
fills the canonical model `market` for a car, keyed by the source's org unit (schema.vin_key). Nothing is ever written
to the source.

Resource and facts
    values  market.<vin key>  retail_guide_price (retail), wholesale_guide_price (wholesale)
The cars asked for are the VINs of the org unit's `asset` facts already in the store (the lease and dealer systems'
`vin`), so sync those first; a VIN the guide does not know (404) is skipped. The guide's `segment`, `band` and `asOf`
stay in the raw record.
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient, SourceError
from di.services.canonical.schema import SHARED_ORG, vin_key
from di.services.canonical.store import Fact


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class VehiclePricingAdapter(GenericAdapter):
    source_id = "uc_price"
    base_path = "/vehicle-pricing/v3"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Vehicle pricing guide (synthetic)"
    source_type = "pricing"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        return [Resource("values", self.read_values, delta=False)]

    def read_values(self, client: SourceClient, since: str | None) -> Iterator[Record]:  # noqa: ARG002 - always in full
        org = _org(client)
        vins = client.session.execute(
            text(
                "SELECT DISTINCT data ->> 'vin' AS vin FROM canonical "
                "WHERE model = 'asset' AND starts_with(key, :p) AND jsonb_exists(data, 'vin') ORDER BY 1"
            ),
            {"p": f"{org or SHARED_ORG}:"},
        ).scalars()
        for vin in list(vins):
            try:
                doc = client.get_json("/values", params={"vin": vin})
            except SourceError as e:
                if e.status == 404:  # a car the guide does not value
                    continue
                raise
            client.note_records(1)
            yield Record("values", vin, doc | {"org_unit_id": org}, client.url("/values"))

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource != "values":
            return []
        key = vin_key(p.get("org_unit_id"), p["vin"])
        pairs = (("retail_guide_price", "retail"), ("wholesale_guide_price", "wholesale"))
        return keep([Fact("market", key, to, p.get(src), src, p.get(src), "Pass-through") for to, src in pairs])


ADAPTER = VehiclePricingAdapter()
