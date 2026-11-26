"""Battery management data (bat_bms, plan 9 P9-12.7): the state of health of battery packs read from the BMS. Read only.

Written against source-sim's synthetic BMS mock (source-sim/sim/vendors/battery_bms): no real battery management system is
connected. API key in `x-api-key`; one unpaged list, read in full (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered (di.connectors.extra registers it). It implements no registry entry of its
own: it fills the canonical models `asset` and `condition` for a pack, keyed by the pack id and the source's org unit
(schema.serial_key), which the `battery` pack's gates and valuer read (G-BAT-1 to G-BAT-5).

Resource and facts
    packs   asset.<pack key>      pack_chemistry, vin_ref (the car the pack came from; no fact for an industrial pack),
                                  pack_market (`EU` or `US`), safety_class, thermal_event, pack_damaged, owner_tenant
            condition.<pack key>  soh_pct (state of health), expected_life_years, soh_read_at (the BMS's read date)
`vin_ref` is how a used-car case finds its pack (`di.services.cases.intake`, NS-BAT-01).
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import serial_key
from di.services.canonical.store import Fact

ASSET = {
    "chemistry": "pack_chemistry", "vinRef": "vin_ref", "market": "pack_market", "safetyClass": "safety_class",
    "thermalEvent": "thermal_event", "damaged": "pack_damaged",
}  # fmt: skip
CONDITION = {"sohPct": "soh_pct", "expectedLifeYears": "expected_life_years", "readAt": "soh_read_at"}


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class BatteryBmsAdapter(GenericAdapter):
    source_id = "bat_bms"
    base_path = "/battery-bms/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Battery management data (synthetic)"
    source_type = "battery_bms"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def packs(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org, url = _org(client), client.url("/packs")
            rows = client.get_json("/packs")
            client.note_records(len(rows))
            for p in rows:
                yield Record("packs", p["packId"], {**p, "org_unit_id": org}, url)

        return [Resource("packs", packs, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = serial_key(p.get("org_unit_id"), p["packId"])
        facts = [Fact("asset", key, f, p.get(s), s, p.get(s), "The BMS's pack record") for s, f in ASSET.items()]
        facts += [Fact("condition", key, f, p.get(s), s, p.get(s), "The BMS's last read") for s, f in CONDITION.items()]
        facts.append(Fact("asset", key, "owner_tenant", p.get("org_unit_id"), "org_unit_id", p.get("org_unit_id"), "Source's org"))
        return keep(facts)


ADAPTER = BatteryBmsAdapter()
