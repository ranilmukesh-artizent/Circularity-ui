"""Closed repairs and released refurbished units from Oracle Depot Repair (rephist, plan 9 P9-4.1). Read only.

Written against source-sim's Depot Repair mock (query service `xxcsdroquery`, method `get_repair_history`), a synthetic
stand-in: no real Oracle Depot Repair is connected. It reads like the `repair` adapter (adapters/depot_repair.py): the
same Integrated SOA Gateway REST under /depot-repair/webservices/rest, HTTP Basic, P_START_INDEX / P_MAX_RECORDS paging
until X_HAS_MORE = N, and a delta on P_LAST_UPDATE_DATE_FROM (Record.changed is the row's own LAST_UPDATE_DATE).

`repair` (the demo's source) reads the open repair orders into canonical facts; `rephist` is a different source for a
different table. It starts unregistered (no source_system row), so every demo screen and count is unchanged.
di.connectors.extra registers it, source.reconnect connects it.

It writes plain tables, not canonical facts (`map` makes none; the sync still keeps every record raw):
    history   REPAIR_TYPE `Repair and Return`  repair_history  id (REPAIR_NUMBER), serial, model_class, age_months,
                                               fault_code, market, parts, labour_hours, test_fee, turnaround_days,
                                               actual_cost, currency, closed_on
              REPAIR_TYPE `Refurbishment`      refurb_unit     serial, model_class, grade, market, released_on; only a
                                               unit released to service and not issued; `reserved_case` is never
                                               touched by a sync (a case holding the unit keeps it)
Rows are landed in the sync's own session, 500 at a time, so a failed or dry run undoes them with it. They are idempotent
on the source key and belong to the source's org unit (None: shared).
"""

import json
from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.adapters.depot_repair import DepotRepairAdapter
from di.connectors.base import Adapter, Record, Resource
from di.connectors.http import Basic, SourceClient
from di.services.canonical.store import Fact

UPSERT_HISTORY = text(
    "INSERT INTO repair_history (id, org_unit_id, serial, model_class, age_months, fault_code, market, parts, labour_hours, "
    "test_fee, turnaround_days, actual_cost, currency, closed_on, source) VALUES (:id, :org, :serial, :cls, :age, :fault, "
    ":market, CAST(:parts AS jsonb), :hours, :fee, :days, :cost, :cur, CAST(:closed AS date), :src) "
    "ON CONFLICT (id) DO UPDATE SET org_unit_id = EXCLUDED.org_unit_id, serial = EXCLUDED.serial, "
    "model_class = EXCLUDED.model_class, age_months = EXCLUDED.age_months, fault_code = EXCLUDED.fault_code, "
    "market = EXCLUDED.market, parts = EXCLUDED.parts, labour_hours = EXCLUDED.labour_hours, test_fee = EXCLUDED.test_fee, "
    "turnaround_days = EXCLUDED.turnaround_days, actual_cost = EXCLUDED.actual_cost, currency = EXCLUDED.currency, "
    "closed_on = EXCLUDED.closed_on, source = EXCLUDED.source"
)
UPSERT_UNIT = text(
    "INSERT INTO refurb_unit (serial, org_unit_id, model_class, grade, market, released_on) VALUES (:serial, :org, :cls, "
    ":grade, :market, CAST(:released AS date)) ON CONFLICT (serial) DO UPDATE SET org_unit_id = EXCLUDED.org_unit_id, "
    "model_class = EXCLUDED.model_class, grade = EXCLUDED.grade, market = EXCLUDED.market, "
    "released_on = EXCLUDED.released_on"
)
FLUSH = 500


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


def history_params(row: dict, org: str | None, source: str) -> dict:
    return {
        "id": row["REPAIR_NUMBER"], "org": org, "serial": row.get("SERIAL_NUMBER"), "cls": row["MODEL_CLASS"],
        "age": row.get("AGE_MONTHS"), "fault": row.get("FAULT_CODE"), "market": row.get("MARKET"),
        "parts": json.dumps(row.get("PARTS") or []), "hours": row.get("LABOUR_HOURS"),
        "fee": row.get("TEST_FEE_APPLIED"), "days": row.get("TURNAROUND_DAYS"), "cost": row.get("ACTUAL_COST"),
        "cur": row.get("CURRENCY"), "closed": row["DATE_CLOSED"][:10], "src": source,
    }  # fmt: skip


def unit_params(row: dict, org: str | None) -> dict:
    released = (row.get("RELEASE_TO_SERVICE") or {}).get("RELEASED_AT") or row["DATE_CLOSED"]
    return {
        "serial": row["SERIAL_NUMBER"], "org": org, "cls": row["MODEL_CLASS"], "grade": row.get("GRADE"),
        "market": row.get("MARKET"), "released": released[:10],
    }  # fmt: skip


def is_released_unit(row: dict) -> bool:
    """A refurbishment released to service and not issued to anyone."""
    release = row.get("RELEASE_TO_SERVICE") or {}
    return row.get("REPAIR_TYPE") == "Refurbishment" and release.get("STATUS") == "RELEASED" and not row.get("ISSUED")


class RepairHistoryAdapter(Adapter):
    source_id = "rephist"
    base_path = "/depot-repair/webservices/rest"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Oracle Depot Repair history (synthetic)"
    source_type = "rephist"
    interval = 60
    owner = "Integration Engineering"

    def __init__(self) -> None:
        self.reader = DepotRepairAdapter()  # the gateway's paging and fault handling

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return Basic("DI_CONNECTOR", secret or "repair-demo-password")

    def resources(self):
        return [Resource("history", self.read_history)]

    def read_history(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        org = _org(client)
        batch: list[tuple[dict, str]] = []
        for pair in self.reader.pages(client, "get_repair_history", "X_REPAIR_HISTORY", since):
            batch.append(pair)
            if len(batch) >= FLUSH:
                yield from self._land(client, org, batch)
                batch = []
        yield from self._land(client, org, batch)

    def _land(self, client: SourceClient, org: str | None, batch: list[tuple[dict, str]]) -> Iterator[Record]:
        rows = [r for r, _ in batch]
        repairs = [history_params(r, org, client.source_id) for r in rows if r.get("REPAIR_TYPE") == "Repair and Return"]
        units = [unit_params(r, org) for r in rows if is_released_unit(r)]
        if repairs:
            client.session.execute(UPSERT_HISTORY, repairs)
        if units:
            client.session.execute(UPSERT_UNIT, units)
        for row, url in batch:
            yield Record("history", row["REPAIR_NUMBER"], row, url, row.get("LAST_UPDATE_DATE"))

    def map(self, record: Record) -> list[Fact]:  # noqa: ARG002 - the rows are landed as they are read
        return []


ADAPTER = RepairHistoryAdapter()
