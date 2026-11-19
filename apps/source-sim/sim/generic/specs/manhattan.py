"""Manhattan Active Warehouse Management (the demo's SOURCES.wms): stock location, quantity, stock age, reservations,
physical movements. Read: GET /inventory, /locations, /movements. Write: POST /reservations, /transfers."""

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

FACILITY = {"Warehouse 1": "WH01", "Warehouse 2": "WH02", "Repair centre": "RC01"}


def facility_id(location: str) -> str:
    return FACILITY.get(location) or "ST" + location.split()[-1].zfill(2)  # Site 3 -> ST03


def seed(s: Seed) -> dict[str, list[dict]]:
    as_of = s.world.as_of
    locations = [
        {
            "locationId": fid,
            "description": name,
            "locationType": "REPAIR" if fid.startswith("RC") else "WAREHOUSE",
            "facilityId": fid,
            "zone": "RETURNS",
            "active": True,
        }
        for name, fid in FACILITY.items()
    ] + [
        {
            "locationId": facility_id(site.id),
            "description": site.name,
            "locationType": "CUSTOMER_SITE",
            "facilityId": facility_id(site.id),
            "zone": "",
            "active": True,
        }
        for site in s.world.sites
    ]
    inventory, movements = [], []
    for case in s.cases.values():
        f = case.facts
        fid = facility_id(f.location)
        inventory.append(
            {
                "inventoryId": f"INV-{f.asset_id}",
                "itemId": f.asset_id,
                "itemDescription": f"{f.product} · {f.mfr}",
                "facilityId": fid,
                "locationId": f"{fid}-RT-{int(f.id.split('-')[1]) % 40 + 1:02d}",
                "onHandQuantity": f.qty,
                "allocatedQuantity": 0,
                "uom": "EACH",
                "inventoryStatus": "AVAILABLE" if f.readiness == "ready" else "HOLD",
                "receivedDate": f.received.date().isoformat(),
                "stockAgeDays": (as_of.date() - f.received.date()).days,
                "ownerId": f.owner,
                "returnReference": f.id,
            }
        )
        movements.append(
            {
                "movementId": f"MV-{f.id}-RCV",
                "itemId": f.asset_id,
                "movementType": "RECEIPT",
                "quantity": f.qty,
                "fromLocation": "INBOUND-DOCK",
                "toFacilityId": fid,
                "movementDate": f.received.isoformat(),
                "reference": f.id,
            }
        )
    return {"locations": locations, "inventory": inventory, "movements": movements, "reservations": [], "transfers": []}


SPEC = Spec(
    source_id="wms",
    title="Manhattan Active Warehouse Management",
    schema="manhattan",
    base_path="/manhattan/wms/api",
    auth=Auth("oauth_cc"),
    paging=Paging("page", page_param="page", size_param="size", items_key="data", next_key="nextPage", total_key="totalCount"),
    resources=(
        Resource(
            "inventory", "/inventory", "inventoryId", filters=("itemId", "facilityId", "inventoryStatus", "returnReference")
        ),
        Resource("locations", "/locations", "locationId", filters=("locationType", "facilityId")),
        Resource("movements", "/movements", "movementId", filters=("itemId", "movementType", "reference")),
        Resource(
            "reservations",
            "/reservations",
            "reservationId",
            filters=("itemId", "status"),
            create=True,
            update=True,
            id_format="RSV-{n:06d}",
            event="manhattan.reservation",
        ),
        Resource(
            "transfers",
            "/transfers",
            "transferId",
            filters=("itemId", "status"),
            create=True,
            update=True,
            id_format="TRF-{n:06d}",
            event="manhattan.transfer",
        ),
    ),
    seed=seed,
)
