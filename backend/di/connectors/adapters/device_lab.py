"""Device lab (dvlab, plan 9 P9-6.2): trade-in intake, diagnostics, cosmetic grading, data-wipe certificates, parts
declarations and grading disputes of the device-recommerce flow. Read only.

Written against source-sim's synthetic lab mock (source-sim/sim/generic/specs/device_lab.py): no real lab system is
connected. OAuth client credentials (bearer token); offset paging (`items`, `next`, `total`); `?updated_since=` delta
reads. A `devicelab.wipe.created` event reaches the existing webhook path (di.connectors.webhook), which queues a delta
sync of this source.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its
own: it fills the canonical models `asset` and `condition` (the evidence the device pack reads, entry I-3) and lands two
tables, `device_tradein` and `device_dispute` (migration 0047). Rows are upserts on the source's id, so a sync twice is a
sync once, and a row's `case_id` (set when a case opens) is never overwritten. After the last resource is read, the
post-sync hook (`open_cases`, P9-6.4) opens a case for each pending trade-in (di.services.device.intake), in the same
session: a dry or failed run undoes the cases with the rows. The rows are landed by the readers in the
sync's own session (`client.session`), so a failed, dry or sample run undoes them with it; `map` makes only facts.
Nothing is ever written to the source.

Resources and facts, keyed `IMEI:<imei>` (snake case of the source's camelCase fields)
    tradeins          asset.imei, asset.sku_key (`<model>|<storageGb>`); the row of device_tradein
    diagnostics       condition.imei_read, model_read, storage_read_gb, functional_fails, battery_health_pct
    gradings          condition.cosmetic_grade, photo_refs (the photo ids)
    wipes             condition.wipe_certificate {certificate_id, method, tool_version, verification, operator, at}
    partsDeclarations condition.parts_status
    disputes          the row of device_dispute (no fact)
    repairQuotes      no fact (kept in the raw records)
    photos            not read: the grading names them (photo_refs); the images are large
"""

import json
import logging
from collections.abc import Iterator
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.connectors.adapters.device_registry import imei_key
from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.store import Fact

log = logging.getLogger("di.dvlab")
SOURCE = "dvlab"
PATHS = {  # resource: (path, id field)
    "tradeins": ("/tradeins", "tradeInId"),
    "diagnostics": ("/diagnostics", "imei"),
    "gradings": ("/gradings", "imei"),
    "wipes": ("/wipes", "certificateId"),
    "partsDeclarations": ("/parts-declarations", "imei"),
    "repairQuotes": ("/repair-quotes", "quoteId"),
    "disputes": ("/disputes", "disputeId"),
}  # fmt: skip
DIAGNOSTIC = {
    "imeiRead": "imei_read", "modelRead": "model_read", "storageReadGb": "storage_read_gb",
    "functionalFails": "functional_fails", "batteryHealthPct": "battery_health_pct",
}  # fmt: skip
WIPE = {
    "certificateId": "certificate_id", "method": "method", "toolVersion": "tool_version", "verification": "verification",
    "operator": "operator", "at": "at",
}  # fmt: skip
CAMEL = "Camel case to snake case"


def sku_key(sku: dict[str, Any]) -> str:
    """`<model>|<storageGb>`: the key the market feed prices a device by."""
    return f"{sku['model']}|{sku['storageGb']}"


def land_tradein(s: Session, doc: dict[str, Any], org: str | None = None) -> None:
    """Upsert one trade-in in `s` (the sync's session). `case_id` stays; the payout is replaced only while it is the lab's
    own (or empty). A new row takes the source's org unit; an existing row keeps its own."""
    payout = None
    if doc.get("payoutAmount") is not None:
        payout = {"amount": doc["payoutAmount"], "currency": (doc.get("quote") or {}).get("currency", "USD"), "source": SOURCE}
    s.execute(
        text(
            "INSERT INTO device_tradein "
            "(trade_in_id, org_unit_id, imei, sku, quote, partner, batch_id, bulk, received_at, payout, source) "
            "VALUES (:id, :org, :imei, CAST(:sku AS jsonb), CAST(:quote AS jsonb), :partner, :batch, :bulk, "
            "CAST(:at AS timestamptz), CAST(:payout AS jsonb), :src) "
            "ON CONFLICT (trade_in_id) DO UPDATE SET imei = EXCLUDED.imei, sku = EXCLUDED.sku, quote = EXCLUDED.quote, "
            "partner = EXCLUDED.partner, batch_id = EXCLUDED.batch_id, bulk = EXCLUDED.bulk, "
            "received_at = EXCLUDED.received_at, "
            "payout = CASE WHEN device_tradein.payout IS NULL OR device_tradein.payout->>'source' = :src "
            "THEN EXCLUDED.payout ELSE device_tradein.payout END"
        ),
        {
            "id": doc["tradeInId"], "org": org, "imei": doc["imei"], "sku": json.dumps(doc["sku"]),
            "quote": json.dumps(doc["quote"]), "partner": doc["partner"], "batch": doc.get("batchId"),
            "bulk": bool(doc.get("bulk")), "at": doc["receivedAt"], "payout": json.dumps(payout) if payout else None,
            "src": SOURCE,
        },
    )  # fmt: skip


def land_dispute(s: Session, doc: dict[str, Any]) -> None:
    """Upsert one grading dispute in `s` (the lab's `status` is its outcome)."""
    s.execute(
        text(
            "INSERT INTO device_dispute (id, imei, partner, reason, opened_at, outcome) "
            "VALUES (:id, :imei, :partner, :reason, CAST(:at AS timestamptz), :outcome) "
            "ON CONFLICT (id) DO UPDATE SET imei = EXCLUDED.imei, partner = EXCLUDED.partner, reason = EXCLUDED.reason, "
            "opened_at = EXCLUDED.opened_at, outcome = EXCLUDED.outcome"
        ),
        {
            "id": doc["disputeId"], "imei": doc["imei"], "partner": doc["partner"], "reason": doc["reason"],
            "at": doc["raisedAt"], "outcome": doc["status"],
        },
    )  # fmt: skip


LAST = list(PATHS)[-1]  # the resource read last: the post-sync hook runs after it


def open_cases(s: Session) -> None:
    """The post-sync hook (P9-6.4): one case per pending trade-in (a lot case per bulk batch) of each org whose device flow is
    published (di.services.device.intake). In the sync's session, in a savepoint, so a dry or failed run undoes the cases
    with the rows, and a case that cannot open never fails the sync."""
    from di.services.device.intake import open_all_pending  # services import the connectors' tables, not the reverse

    try:
        with s.begin_nested():
            open_all_pending(s)
    except Exception:
        log.exception("dvlab: opening the cases of the received devices failed")


class DeviceLabAdapter(GenericAdapter):
    source_id = SOURCE
    base_path = "/device-lab/v1"
    auth_kind = "oauth"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Device lab (synthetic)"
    source_type = "dvlab"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        return [Resource(name, self.read(name, path, id_field)) for name, (path, id_field) in PATHS.items()]

    def read(self, name: str, path: str, id_field: str):
        def reader(client: SourceClient, since: str | None) -> Iterator[Record]:
            org = None
            if name in ("tradeins", "disputes"):
                org = client.session.execute(
                    text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}
                ).scalar()
            for rec in self.flat(client, name, path, id_field, since):
                if name == "tradeins":  # in the sync's own session: a failed or dry run undoes the rows with it
                    land_tradein(client.session, rec.payload, org)
                elif name == "disputes":
                    land_dispute(client.session, rec.payload)
                yield rec
            if name == LAST:  # every resource has been read: open the cases of the trade-ins that have none (P9-6.4)
                open_cases(client.session)

        return reader

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        res = record.resource
        if res == "tradeins":
            key = imei_key(p["imei"])
            return [
                Fact("asset", key, "imei", p["imei"], "imei", p["imei"], CAMEL),
                Fact("asset", key, "sku_key", sku_key(p["sku"]), "sku", p["sku"], "Model and storage joined as <model>|<GB>"),
            ]
        if res == "disputes":
            return []
        if res not in PATHS or res == "repairQuotes":
            return []
        key = imei_key(p["imei"])
        if res == "diagnostics":
            return keep([Fact("condition", key, to, p.get(src), src, p.get(src), CAMEL) for src, to in DIAGNOSTIC.items()])
        if res == "gradings":
            return keep(
                [
                    Fact(
                        "condition", key, "cosmetic_grade", p.get("cosmeticGrade"), "cosmeticGrade", p.get("cosmeticGrade"), CAMEL
                    ),
                    Fact("condition", key, "photo_refs", p.get("photoIds"), "photoIds", p.get("photoIds"), CAMEL),
                    Fact(  # a retail partner's second grading (P9-6.14)
                        "condition",
                        key,
                        "cosmetic_grade_second",
                        p.get("secondCosmeticGrade"),
                        "secondCosmeticGrade",
                        p.get("secondCosmeticGrade"),
                        CAMEL,
                    ),
                ]
            )
        if res == "wipes":
            cert = {to: p.get(src) for src, to in WIPE.items()}
            return [
                Fact("condition", key, "wipe_certificate", cert, "certificateId", p.get("certificateId"), "Certificate fields")
            ]
        return keep(
            [Fact("condition", key, "parts_status", p.get("status"), "status", p.get("status"), CAMEL)]
        )  # partsDeclarations


ADAPTER = DeviceLabAdapter()
