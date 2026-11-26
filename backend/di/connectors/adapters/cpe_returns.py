"""Subscriber returns and CPE refurbishment (cpe_bss, plan 9 P9-12.6): returned home routers, their factory-reset records, the lots
built from them and the new-subscriber forecast. Read only.

Written against source-sim's synthetic mock (source-sim/sim/vendors/cpe_returns): no real billing or refurbishment system is
connected. API key in `x-api-key`; four unpaged lists, read in full (Resource.delta False). Subscriber references are codes only.

Not one of the demo's 21 sources: it starts unregistered (di.connectors.extra registers it), so every demo screen is unchanged.
It is the `telecom_cpe` pack's system of record: the pack decides per lot, and a lot's lines are the serials this source names.

Resources and facts, keyed by the source's org unit (schema.serial_key)
    returns            asset.<serial key>   serial, model, return_reason (reason), subscriber_ref, returned_at, owner_tenant
    factory_resets     condition.<serial key>  factory_reset ({method, firmwareRefreshed, at}); a record per serial that was reset
    lot_grades         asset.<lot key>      lot_id, model, lot_week, lot_serials, qty (the number of serials), owner_tenant
                       condition.<lot key>  grade (the lot's grade: one model and grade per lot)
    new_subscriber_forecast  demand.<model key>  new_subscriber_forecast (units for the week)
A lot is keyed by its id the way a serial is (`serial_key(org, lot id)`): the lot is the case (`di.services.cases.cpe_lot`).
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


def _rows(client: SourceClient, name: str, path: str, key: str) -> Iterator[Record]:
    org, url = _org(client), client.url(path)
    rows = client.get_json(path)
    client.note_records(len(rows))
    for r in rows:
        yield Record(name, str(r[key]), {**r, "org_unit_id": org}, url)


class CpeReturnsAdapter(GenericAdapter):
    source_id = "cpe_bss"
    base_path = "/cpe-returns/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Subscriber returns and CPE refurbishment (synthetic)"
    source_type = "cpe_bss"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def returns(client: SourceClient, _since: str | None) -> Iterator[Record]:
            return _rows(client, "returns", "/returns", "serial")

        def factory_resets(client: SourceClient, _since: str | None) -> Iterator[Record]:
            return _rows(client, "factory_resets", "/factory-resets", "serial")

        def lot_grades(client: SourceClient, _since: str | None) -> Iterator[Record]:
            return _rows(client, "lot_grades", "/lot-grades", "lotId")

        def forecast(client: SourceClient, _since: str | None) -> Iterator[Record]:
            return _rows(client, "new_subscriber_forecast", "/new-subscriber-forecast", "week")

        return [
            Resource("returns", returns, delta=False),
            Resource("factory_resets", factory_resets, delta=False),
            Resource("lot_grades", lot_grades, delta=False),
            Resource("new_subscriber_forecast", forecast, delta=False),
        ]

    def map(self, record: Record) -> list[Fact]:
        p: dict[str, Any] = record.payload
        org = p.get("org_unit_id")
        if record.resource == "factory_resets":
            rec = {"method": p["method"], "firmwareRefreshed": p["firmwareRefreshed"], "at": p["at"]}
            return [Fact("condition", serial_key(org, p["serial"]), "factory_reset", rec, "factory_reset", p, "A reset record")]
        if record.resource == "lot_grades":
            key, serials = serial_key(org, p["lotId"]), list(p["serials"])
            return keep(
                [
                    Fact("asset", key, "lot_id", p["lotId"], "lotId", p["lotId"], "The lot"),
                    Fact("asset", key, "model", p["model"], "model", p["model"], "One model per lot"),
                    Fact("asset", key, "lot_week", p["week"], "week", p["week"], "One lot per week"),
                    Fact("asset", key, "lot_serials", serials, "serials", serials, "The devices of the lot"),
                    Fact("asset", key, "qty", len(serials), "serials", serials, "The number of devices"),
                    Fact("asset", key, "owner_tenant", org, "org_unit_id", org, "The source's org unit"),
                    Fact("condition", key, "grade", p["grade"], "grade", p["grade"], "One grade per lot"),
                ]
            )
        if record.resource == "new_subscriber_forecast":
            key = serial_key(org, p["model"])
            return [Fact("demand", key, "new_subscriber_forecast", p["units"], "units", p["units"], f"Units for {p['week']}")]
        key = serial_key(org, p["serial"])
        return keep(
            [
                Fact("asset", key, "serial", p["serial"], "serial", p["serial"], "The device"),
                Fact("asset", key, "model", p["model"], "model", p["model"], "The model"),
                Fact("asset", key, "return_reason", p["reason"], "reason", p["reason"], "Why it came back"),
                Fact("asset", key, "subscriber_ref", p["subscriberRef"], "subscriberRef", p["subscriberRef"], "A code, no name"),
                Fact("asset", key, "returned_at", p["returnedAt"], "returnedAt", p["returnedAt"], "When it came back"),
                Fact("asset", key, "owner_tenant", org, "org_unit_id", org, "The source's org unit"),
            ]
        )


ADAPTER = CpeReturnsAdapter()
