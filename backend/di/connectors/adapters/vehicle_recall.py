"""Vehicle recall database (uc_recall, plan 9 P9-9.5): open and remedied recalls by VIN. Read only.

Written against source-sim's synthetic recall mock (source-sim/sim/vendors/vehicle_recall): no real recall database is
connected. API key in `x-api-key`; the bulk list pages as `items`, `next`, `total` with `?updatedSince=` delta reads.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it (as uc_lease). It implements no registry
entry of its own: it fills the canonical model `condition` for a car, keyed by the source's org unit (schema.vin_key).
Nothing is ever written to the source.

Two ways in, one mapping (`facts`):
    sync    resource `recalls`: the bulk list names the VINs that changed; each VIN is then looked up in full, so a
            record always holds every campaign of the car (the list has one row per campaign and VIN).
    lookup  `lookup(client, vin, org_unit_id=None) -> list[Fact]`: a fresh per-VIN check, the call `evidence.refresh`
            (P9-9.9) makes. `checkedAt` is the source's simulated now of that call. org_unit_id is the car's org unit
            (None: shared, as the key of a source with no org unit).

Facts (condition.<vin key>)
    recall_open          true when any campaign is open
    recall_campaigns     the open campaigns, as the source gives them ({campaignId, component, summary, remedyAvailable})
    recall_checked_at    the source's `checkedAt`
    recall_remedy_ref    the remedy reference of a remedied campaign (the last one); absent when none is remedied
    recall_remedied      the campaign ids of the remedied campaigns (P9-9.9: the gate compares them with the open ones)
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import vin_key
from di.services.canonical.store import Fact


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


def facts(doc: dict[str, Any], org_unit_id: str | None) -> list[Fact]:
    """The condition facts of one per-VIN document `{vin, checkedAt, openRecalls, remedied}`."""
    key = vin_key(org_unit_id, doc["vin"])
    open_recalls, remedied = doc.get("openRecalls") or [], doc.get("remedied") or []
    rule = "Recall lookup by VIN"
    return keep(
        [
            Fact("condition", key, "recall_open", bool(open_recalls), "openRecalls", open_recalls, "Open if any is open"),
            Fact("condition", key, "recall_campaigns", open_recalls, "openRecalls", open_recalls, rule),
            Fact("condition", key, "recall_checked_at", doc.get("checkedAt"), "checkedAt", doc.get("checkedAt"), rule),
            Fact(
                "condition",
                key,
                "recall_remedy_ref",
                remedied[-1].get("remedyRef") if remedied else None,
                "remedied",
                remedied,
                "Remedy reference of the last remedied campaign",
            ),
            Fact(
                "condition",
                key,
                "recall_remedied",
                [r.get("campaignId") for r in remedied if r.get("campaignId")],
                "remedied",
                remedied,
                "Campaign ids of the remedied campaigns",
            ),  # fmt: skip
        ]
    )


def lookup(client: Any, vin: str, org_unit_id: str | None = None) -> list[Fact]:
    """A fresh recall check of one VIN: GET /recalls/vin/{vin}, mapped to `condition` facts."""
    return facts(client.get_json(f"/recalls/vin/{vin}"), org_unit_id)


class VehicleRecallAdapter(GenericAdapter):
    source_id = "uc_recall"
    base_path = "/vehicle-recall/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    since_param = "updatedSince"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Vehicle recall database (synthetic)"
    source_type = "recall"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def recalls(client: SourceClient, since: str | None) -> Iterator[Record]:
            org = _org(client)
            now = self.source_now(client)
            vins = sorted({row["vin"] for row, _ in self.pages(client, "/recalls", since)})
            for v in vins:
                doc = client.get_json(f"/recalls/vin/{v}")
                yield Record("recalls", v, doc | {"org_unit_id": org}, client.url(f"/recalls/vin/{v}"), now)

        return [Resource("recalls", recalls)]

    def map(self, record: Record) -> list[Fact]:
        return facts(record.payload, record.payload.get("org_unit_id"))


ADAPTER = VehicleRecallAdapter()
