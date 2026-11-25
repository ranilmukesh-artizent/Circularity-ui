"""Vehicle inspection app (uc_insp, plan 9 P9-9.4): the condition evidence of the used-car segment. Read only.

Written against source-sim's synthetic inspection mock (source-sim/sim/vendors/vehicle_inspection): no real inspection
app is connected. API key in `x-api-key`; offset paging (`data`, `next`); `?updatedSince=` delta reads.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its
own: it fills the canonical model `condition` for a car, keyed by the source's org unit (schema.vin_key), which the
used-car pack's gates read. Nothing is ever written to the source here (the battery assessment is requested by a later
task's action).

Resources and facts (snake case of the source's camelCase fields; a field the source leaves empty is no fact)
    inspections          condition.<vin key>  inspection_ref, inspection_status (`complete` | `scheduled`),
                                              condition_score (1-5, 5 best), odometer_photo_reading, recon_estimate,
                                              recon_lines, hail_damage, paired_devices, battery_soh, inspection_at
                                              (completedAt)
    battery_assessments  condition.<vin key>  battery_assessment_ref, and once complete battery_assessment_result and
                                              battery_soh (the pack reading of the assessment)
`photos`, `damage`, `tyres` and `brakes` stay in the raw record: no fact. An assessment's reading overwrites the
inspection's `battery_soh` (the later and more specific one, with its own provenance).
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import vin_key
from di.services.canonical.store import Fact

INSPECTION = {
    "inspectionId": "inspection_ref", "status": "inspection_status", "conditionScore": "condition_score",
    "odometerPhotoReading": "odometer_photo_reading", "reconEstimate": "recon_estimate", "reconLines": "recon_lines",
    "hailDamage": "hail_damage", "pairedDevices": "paired_devices", "batterySoh": "battery_soh",
    "completedAt": "inspection_at",
}  # fmt: skip
ASSESSMENT = {"assessmentId": "battery_assessment_ref", "result": "battery_assessment_result", "batterySoh": "battery_soh"}


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class VehicleInspectionAdapter(GenericAdapter):
    source_id = "uc_insp"
    base_path = "/vehicle-inspection/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    since_param = "updatedSince"
    items_key = "data"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Vehicle inspection app (synthetic)"
    source_type = "inspection"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def reader(name: str, path: str, id_field: str):
            def read(client: SourceClient, since: str | None) -> Iterator[Record]:
                org = _org(client)
                for r in self.flat(client, name, path, id_field, since):
                    yield Record(r.resource, r.ext_id, r.payload | {"org_unit_id": org}, r.request, r.changed)

            return read

        return [
            Resource("inspections", reader("inspections", "/inspections", "inspectionId")),
            Resource("battery_assessments", reader("battery_assessments", "/battery-assessments", "assessmentId")),
        ]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = vin_key(p.get("org_unit_id"), p["vin"])
        table = ASSESSMENT if record.resource == "battery_assessments" else INSPECTION
        facts = []
        for src, to in table.items():
            value = p.get(src)
            if to == "recon_lines" and not value:
                value = None  # a late inspection has no lines: no fact
            facts.append(Fact("condition", key, to, value, src, p.get(src), "Camel case to snake case"))
        return keep(facts)


ADAPTER = VehicleInspectionAdapter()
