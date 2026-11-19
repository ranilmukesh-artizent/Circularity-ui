"""Manhattan Active WM (wms): stock location, availability, quantity, stock age, reservations, movements (SOURCES.wms).

OAuth 2.0 client credentials; page paging (?page=&size=, body {data, nextPage, totalCount}); every list takes
?updated_since= for delta reads. The facility names come from GET /locations (WH01 → Warehouse 1), read at the start
of each run as a lookup.

Facts
    asset.<itemId>   location (facility name; wms has authority), facility_id, bin_location, availability, qty,
                     allocated_qty, stock_age_days, stock_received_date, case_ref (returnReference)
                     last_movement_ref/_type/_at (movements), reservation_ref/_status/_qty/_for (reservations),
                     transfer_ref/_status/_to (transfers)
The demo's mapping (MAPPINGS.wms): LOC → asset.location "Warehouse 1", "Zone collapsed to facility" (seeded bins are
WH01-RT-09, not WH1-A-04); QTY_UOM → asset.qty "UoM normalised"; RSV_ID → asset.reservation_ref "Pass-through";
MV_TS → last_movement_at "Timestamp to UTC" (seeded movement times are already UTC).

The generic-mock helpers below (`generic_pages`, `source_clock`, `utc`) are shared by the other generic-mock adapters
of this batch (depot_repair, safetyculture, optoro, shiplane).
"""

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import generic_pages, source_clock, utc
from di.connectors.http import OAuthClientCredentials, SourceClient

PAGE = 200
FACILITIES = {"WH01": "Warehouse 1", "WH02": "Warehouse 2", "RC01": "Repair centre"}  # fallback when /locations fails
AVAILABILITY = {"AVAILABLE": "available", "HOLD": "on_hold", "ALLOCATED": "allocated", "DAMAGED": "damaged"}


# ------------------------------------------------------------------ the adapter
class ManhattanAdapter(Adapter):
    source_id = "wms"
    base_path = "/manhattan/wms/api"

    def __init__(self):
        self.facilities: dict[str, str] = dict(FACILITIES)

    def auth(self):
        return OAuthClientCredentials("/oauth/token", "di-connector", "wms-demo-secret")

    def resources(self):
        return [
            Resource("inventory", self.reader("inventory", "/inventory", "inventoryId")),
            Resource("movements", self.reader("movements", "/movements", "movementId")),
            Resource("reservations", self.reader("reservations", "/reservations", "reservationId")),
            Resource("transfers", self.reader("transfers", "/transfers", "transferId")),
        ]

    def _pages(self, client, path, since):
        return generic_pages(client, path, since, items_key="data", next_key="nextPage", next_param="page", size_param="size")

    def _load_facilities(self, client: SourceClient) -> None:
        for loc, _ in self._pages(client, "/locations", None):
            if loc.get("facilityId") and loc.get("description"):
                self.facilities[loc["facilityId"]] = loc["description"]

    def reader(self, name: str, path: str, id_field: str):
        def read(client: SourceClient, since: str | None):
            if name == "inventory":
                self._load_facilities(client)
            stamp = source_clock(client)
            for doc, url in self._pages(client, path, since):
                yield Record(name, str(doc[id_field]), doc, url, stamp)

        return read

    def facility(self, fid: str | None) -> str | None:
        if not fid:
            return None
        return self.facilities.get(fid) or FACILITIES.get(fid) or fid

    # ------------------------------------------------------------------ mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = p.get("itemId")
        if not key:
            return []
        out: list[Fact] = []

        def fact(field, value, sf, sv, transform):
            if value is not None:
                out.append(Fact("asset", key, field, value, sf, sv, transform))

        if record.resource == "inventory":
            fid = p.get("facilityId")
            fact("location", self.facility(fid), "locationId", p.get("locationId"), "Zone collapsed to facility")
            fact("facility_id", fid, "facilityId", fid, "Pass-through")
            fact("bin_location", p.get("locationId"), "locationId", p.get("locationId"), "Pass-through")
            st = p.get("inventoryStatus")
            fact(
                "availability",
                AVAILABILITY.get(st, (st or "").lower() or None),
                "inventoryStatus",
                st,
                "Status map (AVAILABLE → available, HOLD → on_hold)",
            )
            qty = p.get("onHandQuantity")
            if qty is not None:
                fact("qty", qty, "onHandQuantity", f"{qty} {p.get('uom') or ''}".strip(), "UoM normalised")
            fact("allocated_qty", p.get("allocatedQuantity"), "allocatedQuantity", p.get("allocatedQuantity"), "Integer")
            fact("stock_age_days", p.get("stockAgeDays"), "stockAgeDays", p.get("stockAgeDays"), "Integer days")
            fact("stock_received_date", p.get("receivedDate"), "receivedDate", p.get("receivedDate"), "Date")
            fact("case_ref", p.get("returnReference"), "returnReference", p.get("returnReference"), "Pass-through")
        elif record.resource == "movements":
            fact("last_movement_ref", p.get("movementId"), "movementId", p.get("movementId"), "Pass-through")
            fact("last_movement_type", p.get("movementType"), "movementType", p.get("movementType"), "Pass-through")
            fact("last_movement_at", utc(p.get("movementDate")), "movementDate", p.get("movementDate"), "Timestamp to UTC")
        elif record.resource == "reservations":
            fact("reservation_ref", p.get("reservationId"), "reservationId", p.get("reservationId"), "Pass-through")
            fact("reservation_status", p.get("status"), "status", p.get("status"), "Pass-through")
            fact("reserved_qty", p.get("quantity"), "quantity", p.get("quantity"), "Integer")
            ref = p.get("orderReference") or p.get("reference")
            fact("reserved_for", ref, "orderReference", ref, "Pass-through")
        elif record.resource == "transfers":
            fact("transfer_ref", p.get("transferId"), "transferId", p.get("transferId"), "Pass-through")
            fact("transfer_status", p.get("status"), "status", p.get("status"), "Pass-through")
            to = p.get("toFacilityId")
            fact("transfer_to", self.facility(to), "toFacilityId", to, "Facility lookup")
        return out


ADAPTER = ManhattanAdapter()
