"""Parts supplier portal (mr_parts, plan 9 P9-11.5): replacement part prices, lead times and harvest values. Read only.

Written against source-sim's synthetic parts portal mock (source-sim/sim/vendors/parts_portal): no real supplier is
connected. API key in `x-api-key`; a plain JSON array (no paging, no change stamps, so the resource is read in full:
Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own:
it fills the canonical model `market` for a device model, keyed by the source's org unit and the model name
(schema.tag_key(org, model)), which the medical rental valuer reads for every device of that model. Nothing is ever written
to the source.

Resource and facts (one record per device model; the source's camelCase fields in snake case)
    parts   market.<tag key of the model>   part_prices [{part_no, label, price, lead_days}]
                                             harvest_values [{part_no, label, harvest_value}]
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import tag_key
from di.services.canonical.store import Fact


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class PartsPortalAdapter(GenericAdapter):
    source_id = "mr_parts"
    base_path = "/parts-portal/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Parts supplier portal (synthetic)"
    source_type = "parts"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def parts(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org = _org(client)
            rows = client.get_json("/parts")
            client.note_records(len(rows))
            url = client.url("/parts")
            by_model: dict[str, list[dict]] = {}
            for r in rows:
                by_model.setdefault(str(r["model"]), []).append(r)
            for model, items in by_model.items():
                yield Record("parts", model, {"model": model, "parts": items, "org_unit_id": org}, url)

        return [Resource("parts", parts, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = tag_key(p.get("org_unit_id"), p["model"])
        items = p["parts"]
        prices = [{"part_no": r["partNo"], "label": r["label"], "price": r["price"], "lead_days": r["leadDays"]} for r in items]
        harvest = [{"part_no": r["partNo"], "label": r["label"], "harvest_value": r["harvestValue"]} for r in items]
        return keep(
            [
                Fact("market", key, "part_prices", prices, "parts", items, "Camel case to snake case; price, lead time"),
                Fact("market", key, "harvest_values", harvest, "parts", items, "Camel case to snake case; harvest value"),
            ]
        )


ADAPTER = PartsPortalAdapter()
