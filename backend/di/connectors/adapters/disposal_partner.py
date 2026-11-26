"""Disposal partner (mr_disposal, plan 9 P9-11.5): sanitisation records and disposal certificates. Read only.

Written against source-sim's synthetic disposal partner mock (source-sim/sim/vendors/disposal_partner): no real disposal
company is connected. API key in `x-api-key`; plain JSON arrays (no paging, no change stamps, so each resource is read in
full: Resource.delta False). The source lists only the records and certificates already issued (they follow the booking by
1 and 2 simulated days), so a device without one has no fact yet.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own:
it fills the canonical model `condition` for a device, keyed by the source's org unit and the tag (schema.tag_key), which
the medical rental gates read. Booking a collection or a sanitisation is a write to the source and is not done here.

Resources and facts
    sanitisations  condition.<tag key>  sanitisation_record_ref (sanitisationId)
    certificates   condition.<tag key>  disposal_certificate_ref (certificateId)
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import tag_key
from di.services.canonical.store import Fact

REFS = {  # resource -> (id field of the source, condition field)
    "sanitisations": ("sanitisationId", "sanitisation_record_ref"),
    "certificates": ("certificateId", "disposal_certificate_ref"),
}


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class DisposalPartnerAdapter(GenericAdapter):
    source_id = "mr_disposal"
    base_path = "/disposal-partner/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Disposal partner (synthetic)"
    source_type = "disposal"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def reader(name: str):
            id_field = REFS[name][0]

            def read(client: SourceClient, _since: str | None) -> Iterator[Record]:
                org = _org(client)
                rows = client.get_json(f"/{name}")
                client.note_records(len(rows))
                url = client.url(f"/{name}")
                for r in rows:
                    yield Record(name, str(r[id_field]), r | {"org_unit_id": org}, url)

            return read

        return [Resource(name, reader(name), delta=False) for name in REFS]

    def map(self, record: Record) -> list[Fact]:
        id_field, field = REFS[record.resource]
        p = record.payload
        key = tag_key(p.get("org_unit_id"), p["tag"])
        return keep([Fact("condition", key, field, p.get(id_field), id_field, p.get(id_field), "Camel case to snake case")])


ADAPTER = DisposalPartnerAdapter()
