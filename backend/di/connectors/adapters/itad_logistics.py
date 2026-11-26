"""ITAD logistics and chain of custody (it_logistics, plan 9 P9-12.2): pickups, manifests, custody, media erasures. Read only.

Written against source-sim's synthetic logistics mock (source-sim/sim/vendors/itad_logistics): no real logistics or ITAD
provider is connected. API key in `x-api-key`; two unpaged lists, read in full (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered (di.connectors.extra registers it). It is the pack's manifest (the
`itad` pack's `data.record_match` names it), which di.services.cases.record_match reads at the end of each of its syncs.

Resources and facts, keyed by the source's org unit (schema.serial_key)
    pickups   one record per serial on a manifest or received (a pickup lists both)
              asset.pickup (only for a serial on the manifest), asset.disposition ("received", or "in_transit" while the
              serial is on a manifest and not received), asset.received_at (the received event's time, else the pick-up's),
              asset.custody (the pickup's custody events up to what happened to this serial), asset.owner_tenant (the source's
              org unit)
    erasures  one record per serial, from its media serials (the mock names a media `MS-<serial suffix>-<n>`)
              condition.erasures (the list of the erasure records of that serial's media)
A serial on a manifest and not received keeps `in_transit`; the end of the sync opens its exception when no case follows.
ASSUMPTION: a media serial `MS-IT-0001-1` belongs to serial `SN-IT-0001` (the mock's naming; a real system carries the link).
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import serial_key
from di.services.canonical.store import Fact


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


def serial_of_media(media_serial: str) -> str:
    """`MS-IT-0001-2` -> `SN-IT-0001`."""
    return "SN-" + media_serial[3:].rsplit("-", 1)[0]


class ItadLogisticsAdapter(GenericAdapter):
    source_id = "it_logistics"
    base_path = "/itad-logistics/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "ITAD logistics and chain of custody (synthetic)"
    source_type = "itad_logistics"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def pickups(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org, url = _org(client), client.url("/pickups")
            rows = client.get_json("/pickups")
            client.note_records(sum(len(set(p["manifest"]) | set(p["received"])) for p in rows))
            for p in rows:
                listed, got = list(p["manifest"]), set(p["received"])
                for serial in [*listed, *[s for s in p["received"] if s not in listed]]:
                    events = list(p["custody"]) if serial in got else [e for e in p["custody"] if e["event"] != "received"]
                    payload = {"pickupId": p["pickupId"], "serial": serial, "onManifest": serial in listed,
                               "received": serial in got, "custody": events, "org_unit_id": org}  # fmt: skip
                    yield Record("pickups", f"{p['pickupId']}:{serial}", payload, url)

        def erasures(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org, url = _org(client), client.url("/erasures")
            rows = client.get_json("/erasures")
            client.note_records(len(rows))
            by: dict[str, list[dict[str, Any]]] = {}
            for r in rows:
                by.setdefault(serial_of_media(r["mediaSerial"]), []).append(r)
            for serial, recs in by.items():
                yield Record("erasures", serial, {"serial": serial, "erasures": recs, "org_unit_id": org}, url)

        return [Resource("pickups", pickups, delta=False), Resource("erasures", erasures, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p: dict[str, Any] = record.payload
        key = serial_key(p.get("org_unit_id"), p["serial"])
        if record.resource == "erasures":
            return [
                Fact(
                    "condition", key, "erasures", p["erasures"], "erasures", p["erasures"], "Every erasure of the serial's media"
                )
            ]
        events = p["custody"]
        at = next((e["at"] for e in events if e["event"] == "received"), events[0]["at"] if events else None)
        pickup, org = p["pickupId"], p.get("org_unit_id")
        state = "received" if p["received"] else "in_transit"
        facts = [
            Fact("asset", key, "pickup", pickup if p["onManifest"] else None, "manifest", pickup, "Listed on the manifest"),
            Fact("asset", key, "disposition", state, "received", p["received"], "Received, or still on the way"),
            Fact("asset", key, "received_at", at, "custody", at, "The received event, else the pick-up"),
            Fact("asset", key, "custody", events, "custody", events, "The custody events, whole"),
            Fact("asset", key, "owner_tenant", org, "org_unit_id", org, "The source's org unit"),
        ]
        return keep(facts)


ADAPTER = ItadLogisticsAdapter()
