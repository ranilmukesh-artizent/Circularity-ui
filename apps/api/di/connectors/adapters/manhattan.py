"""Manhattan Active WM (wms): stock location, availability, quantity, stock age, reservations, movements, transfers
(the demo's SOURCES.wms), against the Manhattan Active REST API (source-sim's sim/vendors/manhattan).

Auth: OAuth 2.0 password grant at /oauth/token (client in HTTP Basic), bearer token; every call carries
SelectedOrganization, and facility-scoped calls SelectedLocation. Reads are component searches (POST .../search with
{"Query", "Size", "Page", "Sort"}; envelope {data, header.totalPages}). The facilities come first
(/facility/api/facility/facility/search: FacilityId → Description, e.g. WH01 → Warehouse 1); then each stocking
facility is searched in turn. Deltas: Query "UpdatedTimestamp > '<cursor>'" (Manhattan timestamps are UTC without an
offset); the cursor is the newest UpdatedTimestamp read.

Facts
    asset.<ItemId>   location (facility name; wms has authority), facility_id, bin_location, availability, qty,
                     allocated_qty, stock_age_days, stock_received_date, case_ref (InventoryAttribute1)   (inventory)
                     last_movement_ref/_type/_at                                                         (PIX)
                     reservation_ref/_status, reserved_qty, reserved_for                                 (reservations)
                     transfer_ref/_status/_to, transfer_shipment_ref                                     (orders)
The demo's mapping (MAPPINGS.wms): LOC → asset.location "Warehouse 1", "Zone collapsed to facility" (seeded bins are
WH01-RT-09, not WH1-A-04); QTY_UOM → asset.qty "UoM normalised"; RSV_ID → asset.reservation_ref "Pass-through";
MV_TS → last_movement_at "Timestamp to UTC".
Stock age is not stored by Manhattan: it is the days from ReceivedDate to the source's clock.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import source_clock
from di.connectors.http import OAuthClientCredentials, SourceClient

ORG = "NORTHFIELD"
SIZE = 200
STOCKING = ("DISTRIBUTION_CENTER", "REPAIR_CENTER")
FACILITIES = {"WH01": "Warehouse 1", "WH02": "Warehouse 2", "RC01": "Repair centre"}  # fallback names
AVAILABILITY: dict[str | None, str] = {
    "AVAILABLE": "available",
    "HOLD": "on_hold",
    "DAMAGED": "damaged",
    "QUARANTINE": "quarantine",
}
RESOURCES = (  # name, search path, id field
    ("inventory", "/dcinventory/api/dcinventory/inventory/search", "InventoryId"),
    ("movements", "/pix/api/pix/pix/search", "PixId"),
    ("reservations", "/dcinventory/api/dcinventory/reservation/search", "ReservationId"),
    ("transfers", "/dcorder/api/dcorder/order/search", "OrderId"),
)


def manh_ts(iso: str) -> str:
    """ISO 8601 with offset → Manhattan's UTC form without offset (2026-10-07T09:00:00.000)."""
    d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}"


def iso(manh: str | None) -> str | None:
    """Manhattan UTC timestamp → ISO 8601 UTC with +00:00 (the cursor form)."""
    if not manh:
        return None
    d = datetime.fromisoformat(manh.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC).isoformat()


def utc_z(manh: str | None) -> str | None:
    v = iso(manh)
    return datetime.fromisoformat(v).isoformat(timespec="seconds").replace("+00:00", "Z") if v else None


class ManhattanAdapter(Adapter):
    source_id = "wms"
    base_path = "/manhattan"

    def __init__(self):
        self.facilities: dict[str, str] = dict(FACILITIES)
        self.today: date | None = None

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return OAuthClientCredentials(
            "/oauth/token",
            "di-connector",
            secret or "wms-demo-secret",
            extra={"grant_type": "password", "username": "circularity.integration@northfield", "password": "wms-demo-password"},
        )

    def resources(self):
        return [Resource(name, self.reader(name, path, id_field)) for name, path, id_field in RESOURCES]

    # ------------------------------------------------------------- reading
    def search(self, client: SourceClient, path: str, query: str, location: str | None = None) -> Iterator[tuple[dict, str]]:
        headers = {"SelectedOrganization": ORG} | ({"SelectedLocation": location} if location else {})
        page = 0
        while True:
            body = {"Query": query, "Size": SIZE, "Page": page, "Sort": [{"attribute": "UpdatedTimestamp", "direction": "asc"}]}
            r = client.request("POST", path, json=body, headers=headers)
            out = r.json()
            rows = out.get("data") or []
            client.note_records(len(rows))
            for row in rows:
                yield row, str(r.request.url)
            page += 1
            if not rows or page >= int((out.get("header") or {}).get("totalPages") or 0):
                return

    def _stocking(self, client: SourceClient) -> list[str]:
        out = []
        for f, _ in self.search(client, "/facility/api/facility/facility/search", ""):
            self.facilities[f["FacilityId"]] = f.get("Description") or f["FacilityId"]
            if f.get("FacilityTypeId") in STOCKING:
                out.append(f["FacilityId"])
        return out

    def reader(self, name: str, path: str, id_field: str):
        def read(client: SourceClient, since: str | None):
            facilities = self._stocking(client)
            if name == "inventory":
                now = source_clock(client)
                self.today = datetime.fromisoformat(now).date() if now else datetime.now(UTC).date()
            query = f"UpdatedTimestamp > '{manh_ts(since)}'" if since else ""
            for fid in facilities:
                for doc, url in self.search(client, path, query, fid):
                    yield Record(name, str(doc[id_field]), doc, url, iso(doc.get("UpdatedTimestamp")))

        return read

    def facility(self, fid: str | None) -> str | None:
        return (self.facilities.get(fid) or fid) if fid else None

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        out: list[Fact] = []

        def fact(key, field, value, sf, sv, transform):
            if key and value is not None:
                out.append(Fact("asset", key, field, value, sf, sv, transform))

        if record.resource == "inventory":
            key = p.get("ItemId")
            fid, loc = p.get("FacilityId"), p.get("LocationId")
            fact(key, "location", self.facility(fid), "LocationId", loc, "Zone collapsed to facility")
            fact(key, "facility_id", fid, "FacilityId", fid, "Pass-through")
            fact(key, "bin_location", loc, "LocationId", loc, "Pass-through")
            st = p.get("ProductStatusId")
            avail = AVAILABILITY.get(st, (st or "").lower() or None)
            if st == "AVAILABLE" and not p.get("Available") and p.get("Allocated"):
                avail = "allocated"
            fact(key, "availability", avail, "ProductStatusId", st, "Status map (AVAILABLE → available, HOLD → on_hold)")
            qty = p.get("OnHand")
            if qty is not None:
                fact(key, "qty", qty, "OnHand", f"{qty} {p.get('Uom') or ''}".strip(), "UoM normalised")
            fact(key, "allocated_qty", p.get("Allocated"), "Allocated", p.get("Allocated"), "Integer")
            rd = p.get("ReceivedDate")
            fact(key, "stock_received_date", rd, "ReceivedDate", rd, "Date")
            if rd and self.today:
                fact(key, "stock_age_days", (self.today - date.fromisoformat(rd)).days, "ReceivedDate", rd, "Days to today")
            ref = p.get("InventoryAttribute1")
            fact(key, "case_ref", ref, "InventoryAttribute1", ref, "Pass-through")
        elif record.resource == "movements":
            key = p.get("ItemId")
            fact(key, "last_movement_ref", p.get("PixId"), "PixId", p.get("PixId"), "Pass-through")
            fact(key, "last_movement_type", p.get("TransactionType"), "TransactionType", p.get("TransactionType"), "Pass-through")
            ts = p.get("TransactionTimestamp")
            fact(key, "last_movement_at", utc_z(ts), "TransactionTimestamp", ts, "Timestamp to UTC")
        elif record.resource == "reservations":
            key = p.get("ItemId")
            rid = p.get("ReservationId")
            fact(key, "reservation_ref", rid, "ReservationId", rid, "Pass-through")
            fact(
                key,
                "reservation_status",
                p.get("ReservationStatus"),
                "ReservationStatus",
                p.get("ReservationStatus"),
                "Pass-through",
            )
            fact(key, "reserved_qty", p.get("Quantity"), "Quantity", p.get("Quantity"), "Integer")
            ref = p.get("OrderId") or p.get("ReferenceId")
            fact(key, "reserved_for", ref, "OrderId", ref, "Pass-through")
        elif record.resource == "transfers":
            to = p.get("DestinationFacilityId")
            for ln in p.get("OrderLine") or []:
                key = ln.get("ItemId")
                fact(key, "transfer_ref", p.get("OrderId"), "OrderId", p.get("OrderId"), "Pass-through")
                fact(
                    key,
                    "transfer_status",
                    p.get("FulfillmentStatus"),
                    "FulfillmentStatus",
                    p.get("MaxFulfillmentStatusId"),
                    "Status code → description",
                )
                fact(key, "transfer_to", self.facility(to), "DestinationFacilityId", to, "Facility lookup")
                fact(key, "transfer_shipment_ref", p.get("ShipmentId"), "ShipmentId", p.get("ShipmentId"), "Pass-through")
        return out


ADAPTER = ManhattanAdapter()
