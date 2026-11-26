"""Recycler portal (tn_recycler, plan 9 P9-10.5): certified recyclers and disposal certificates. Read only.

Written against source-sim's synthetic portal mock (source-sim/sim/vendors/recycler_portal): no real portal is connected.
API key in `x-api-key`; the lists are not paged and have no change stamps (Resource.delta False). Nothing is ever written to
the source here (its pickup route is for later tasks).

Not one of the demo's 21 sources: it starts unregistered, so every demo screen and count is unchanged.
di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own.

Resources and facts
    vendors       vendor.<vendorId>        recycler_certificate (object: scheme, ref, expires), dg_lane (bool), name (label)
    certificates  condition.<serial key>   disposal_record_ref: the id of the disposal certificate issued after a pickup
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter
from di.connectors.http import SourceClient
from di.services.canonical.schema import serial_key
from di.services.canonical.store import Fact


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class RecyclerPortalAdapter(GenericAdapter):
    source_id = "tn_recycler"
    base_path = "/recycler-portal/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Recycler portal (synthetic)"
    source_type = "recycler_portal"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def vendors(client: SourceClient, _since: str | None) -> Iterator[Record]:
            rows, url = client.get_json("/vendors"), client.url("/vendors")
            client.note_records(len(rows))
            for v in rows:
                yield Record("vendors", str(v["vendorId"]), v, url)

        def certificates(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org, url = _org(client), client.url("/certificates")
            rows = client.get_json("/certificates")
            client.note_records(len(rows))
            for c in rows:
                yield Record("certificates", str(c["certificateId"]), c | {"org_unit_id": org}, url)

        return [Resource("vendors", vendors, delta=False), Resource("certificates", certificates, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p: dict[str, Any] = record.payload
        if record.resource == "certificates":
            key = serial_key(p.get("org_unit_id"), p["serial"])
            cid = p["certificateId"]
            return [Fact("condition", key, "disposal_record_ref", cid, "certificateId", cid, "As served")]
        vid, cert = str(p["vendorId"]), p["certificate"]
        return [
            Fact("vendor", vid, "recycler_certificate", dict(cert), "certificate", cert, "The certificate, whole"),
            Fact("vendor", vid, "dg_lane", bool(p["dgLane"]), "dgLane", p["dgLane"], "As served"),
            Fact("vendor", vid, "name", p["label"], "label", p["label"], "As served"),
        ]


ADAPTER = RecyclerPortalAdapter()
