"""Rental system (mr_rental, plan 9 P9-11.2): returns, open requests, depots and demand of the device rental company. Read only.

Written against source-sim's synthetic rental mock (source-sim/sim/vendors/medical_rental_system): no real rental system is
connected. API key in `x-api-key`; plain JSON arrays (no paging, no change stamps, so every resource is read in full:
Resource.delta False). The mock's dispatch write (`POST /dispatches`) is for the actions of later tasks; nothing is written
here.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own:
it fills the canonical models `asset` and `demand` for a device, keyed by the source's org unit (schema.tag_key), which the
medical rental pack's intake trigger and gates read. The device's class, age and values come from asset management
(mr_assets), under the same key.

Resources and facts (snake case of the source's camelCase fields)
    returns      asset.<tag key>    tag, depot, checked_in_at, hospital (hospitalId), ward_type (wardType)
    demand       demand.<tag key>   rental_requests: every open request as {req_id, hospital_id, device_class, start_date,
                                    days, region, requested_at, distance_miles}; the distance is from the device's depot to
                                    the hospital, by the haversine formula on their coordinates, whole miles.
                                    region_forecast: the depot's region, {week_start, requests} per week
    turnaround   asset.<tag key>    turnaround, an object for the device's depot over the last 14 days: depot, window_days,
                                    returns, avg_days, by_cause_avg_days {decon_queue, service, transport}, and the device's
                                    own own_days and own_waiting_days (only a device returned in the window has it)
One record per return for each resource (a device returned twice would keep the later one). `ward` and
`previousRentalEnd` stay in the raw record: no fact.
"""

from collections.abc import Iterator
from math import asin, cos, radians, sin, sqrt
from typing import Any

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import tag_key
from di.services.canonical.store import Fact

EARTH_RADIUS_MILES = 3958.8
WINDOW_DAYS = 14
CAUSES = ("decon_queue", "service", "transport")
RETURN_ASSET = {  # source field -> asset field
    "tag": "tag", "depot": "depot", "checkedInAt": "checked_in_at", "hospitalId": "hospital", "wardType": "ward_type",
}  # fmt: skip


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """The great-circle distance in miles between two points given in degrees (earth radius 3,958.8 miles)."""
    p1, p2 = radians(lat1), radians(lat2)
    h = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(h))


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 1)


class MedicalRentalSystemAdapter(GenericAdapter):
    source_id = "mr_rental"
    base_path = "/rental-system/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Rental system (synthetic)"
    source_type = "rental"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        return [
            Resource("returns", self.read_returns, delta=False),
            Resource("demand", self.read_demand, delta=False),
            Resource("turnaround", self.read_turnaround, delta=False),
        ]

    # ------------------------------------------------------------- reading
    @staticmethod
    def _list(client: SourceClient, path: str, **params: Any) -> list[dict]:
        rows = client.get_json(path, params=params or None)
        client.note_records(len(rows))
        return rows

    def read_returns(self, client: SourceClient, _since: str | None) -> Iterator[Record]:
        org = _org(client)
        url = client.url("/returns")
        for r in self._list(client, "/returns"):
            yield Record("returns", str(r["returnId"]), r | {"org_unit_id": org}, url)

    def read_demand(self, client: SourceClient, _since: str | None) -> Iterator[Record]:
        org = _org(client)
        depots = {d["depotId"]: d for d in self._list(client, "/depots")}
        hospitals = {h["hospitalId"]: h for h in self._list(client, "/hospitals")}
        requests = [
            q | {"latitude": hospitals[q["hospitalId"]]["latitude"], "longitude": hospitals[q["hospitalId"]]["longitude"]}
            for q in self._list(client, "/requests")
            if q["hospitalId"] in hospitals
        ]
        forecast = self._list(client, "/demand-forecast")
        for r in self._list(client, "/returns"):
            depot = depots.get(r["depot"])
            if depot is None:
                continue
            payload = {
                "tag": r["tag"], "depot": depot, "requests": requests, "org_unit_id": org,
                "forecast": [w for w in forecast if w["region"] == depot["region"]],
            }  # fmt: skip
            yield Record("demand", str(r["tag"]), payload, client.url("/requests"))

    def read_turnaround(self, client: SourceClient, _since: str | None) -> Iterator[Record]:
        org = _org(client)
        for depot in self._list(client, "/depots"):
            rows = self._list(client, "/turnaround", depot=depot["depotId"], days=WINDOW_DAYS)
            for row in rows:
                payload = {"tag": row["tag"], "depot": depot["depotId"], "days": WINDOW_DAYS, "own": row, "rows": rows}
                yield Record("turnaround", str(row["returnId"]), payload | {"org_unit_id": org}, client.url("/turnaround"))

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = tag_key(p.get("org_unit_id"), p["tag"])
        if record.resource == "returns":
            return keep(
                [
                    Fact("asset", key, to, p.get(src), src, p.get(src), "Camel case to snake case")
                    for src, to in RETURN_ASSET.items()
                ]
            )
        if record.resource == "demand":
            return self._demand(key, p)
        if record.resource == "turnaround":
            return self._turnaround(key, p)
        return []

    @staticmethod
    def _demand(key: str, p: dict[str, Any]) -> list[Fact]:
        depot = p["depot"]
        requests = [
            {
                "req_id": q["reqId"], "hospital_id": q["hospitalId"], "device_class": q["deviceClass"],
                "start_date": q["startDate"], "days": q["days"], "region": q["region"], "requested_at": q["requestedAt"],
                "distance_miles": round(haversine_miles(depot["latitude"], depot["longitude"], q["latitude"], q["longitude"])),
            }
            for q in p["requests"]
        ]  # fmt: skip
        weeks = [{"week_start": w["weekStart"], "requests": w["requests"]} for w in p["forecast"]]
        return [
            Fact("demand", key, "rental_requests", requests, "requests", p["requests"],
                 "Open requests; distance in whole miles from the depot, haversine on the coordinates"),
            Fact("demand", key, "region_forecast", weeks, "demand-forecast", p["forecast"], "Camel case to snake case"),
        ]  # fmt: skip

    @staticmethod
    def _turnaround(key: str, p: dict[str, Any]) -> list[Fact]:
        rows, own = p["rows"], p["own"]
        if not rows:
            return []
        value = {
            "depot": p["depot"], "window_days": p["days"], "returns": len(rows),
            "avg_days": _mean([r["totalDays"] for r in rows]),
            "by_cause_avg_days": {c: _mean([r["waitingDays"][c] for r in rows]) for c in CAUSES},
            "own_days": own["totalDays"], "own_waiting_days": own["waitingDays"],
        }  # fmt: skip
        rule = "Depot averages over the window and the device's own wait"
        return [Fact("asset", key, "turnaround", value, "turnaround", rows, rule)]


ADAPTER = MedicalRentalSystemAdapter()
