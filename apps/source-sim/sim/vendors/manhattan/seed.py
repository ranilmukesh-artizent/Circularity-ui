"""Manhattan Active WM data in Postgres schema `manhattan`, and the seed (see the package docstring).

Every entity is one table of documents (the entity exactly as the REST API returns it) keyed by its id, with the
facility it belongs to (the `SelectedLocation` scope) and its UpdatedTimestamp. Values follow the generic mock this
replaces (facility codes WH01/WH02/RC01/ST01-08, bins WH01-RT-09, one inventory record and one receipt per case).
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, MetaData, String, Table, delete, insert, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from sim.seed import Seed

SCHEMA = "manhattan"
ORG = "NORTHFIELD"  # the SelectedOrganization of the demo tenant
FACILITY = {"Warehouse 1": "WH01", "Warehouse 2": "WH02", "Repair centre": "RC01"}
UOM = "UNIT"

metadata = MetaData(schema=SCHEMA)


def _doc_table(name: str) -> Table:
    return Table(
        name,
        metadata,
        Column("id", String(60), primary_key=True),
        Column("facility", String(20), index=True),
        Column("doc", JSONB, nullable=False),
        Column("updated", DateTime(timezone=True), nullable=False, index=True),
    )


# entity -> table; the order is the load order
ENTITIES = ("facility", "item", "location", "inventory", "pix", "reservation", "order", "task", "shipment")
TABLES = {e: _doc_table(e) for e in ENTITIES}
COUNTERS = Table("counters", metadata, Column("name", String(40), primary_key=True), Column("value", String(20)))


def facility_id(location: str) -> str:
    """The demo's location name -> Manhattan facility id (Warehouse 1 -> WH01, Site 3 -> ST03)."""
    return FACILITY.get(location) or "ST" + location.split()[-1].zfill(2)


def ts(d: datetime) -> str:
    """Manhattan timestamps: ISO 8601 UTC with milliseconds, no offset ("2026-10-03T00:00:00.000")."""
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}"


def parse_ts(v: str) -> datetime:
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def audit(doc: dict, at: datetime, user: str = "system") -> dict:
    stamp = ts(at)
    doc.setdefault("CreatedTimestamp", stamp)
    doc.setdefault("CreatedBy", user)
    doc["UpdatedTimestamp"] = stamp
    doc["UpdatedBy"] = user
    doc.setdefault("Extended", {})
    return doc


def bin_of(case_id: str, fid: str) -> str:
    return f"{fid}-RT-{int(case_id.split('-')[1]) % 40 + 1:02d}"


# ------------------------------------------------------------------ seed
def build(s: Seed) -> dict[str, list[dict]]:
    at = s.world.as_of
    facilities = [
        {
            "FacilityId": fid,
            "Description": name,
            "FacilityTypeId": "REPAIR_CENTER" if fid.startswith("RC") else "DISTRIBUTION_CENTER",
            "OrganizationId": ORG,
            "TimeZone": "Asia/Kolkata",
            "IsActive": True,
        }
        for name, fid in FACILITY.items()
    ] + [
        {
            "FacilityId": facility_id(site.id),
            "Description": site.name,
            "FacilityTypeId": "CUSTOMER_SITE",
            "OrganizationId": ORG,
            "TimeZone": "Asia/Kolkata",
            "IsActive": True,
        }
        for site in s.world.sites
    ]
    items, locations, inventory, pix = {}, {}, [], []
    for case in s.cases.values():
        f = case.facts
        fid = facility_id(f.location)
        loc = bin_of(f.id, fid)
        items[f.asset_id] = {
            "ItemId": f.asset_id,
            "Description": f"{f.product} · {f.mfr}",
            "ShortDescription": f.product,
            "BaseUom": UOM,
            "ProductClass": f.cls.upper(),
            "IsSerialNumberRequired": True,
        }
        locations[loc] = {
            "LocationId": loc,
            "FacilityId": fid,
            "LocationTypeId": "RESERVE",
            "Zone": "RETURNS",
            "Aisle": "RT",
            "Bay": loc[-2:],
            "IsLocked": False,
        }
        inventory.append(
            {
                "InventoryId": f"INV-{f.asset_id}",
                "ItemId": f.asset_id,
                "FacilityId": fid,
                "LocationId": loc,
                "InventoryContainerId": f"ILPN-{f.id}",
                "OnHand": f.qty,
                "Allocated": 0,
                "Available": f.qty if f.readiness == "ready" else 0,
                "Uom": UOM,
                "ProductStatusId": "AVAILABLE" if f.readiness == "ready" else "HOLD",
                "SerialNumber": f.asset_id,
                "ReceivedDate": f.received.date().isoformat(),
                "InventoryAttribute1": f.id,  # return reference (case)
                "InventoryAttribute2": f.owner,  # owner
                "_at": f.received,
            }
        )
        pix.append(
            {
                "PixId": f"PIX-{f.id}-RCV",
                "TransactionType": "RECEIPT",
                "ReasonCode": "RETURN_RECEIPT",
                "ItemId": f.asset_id,
                "Quantity": f.qty,
                "Uom": UOM,
                "FacilityId": fid,
                "FromLocationId": "INBOUND-DOCK",
                "ToLocationId": loc,
                "InventoryId": f"INV-{f.asset_id}",
                "ReferenceId": f.id,
                "TransactionTimestamp": ts(f.received),
                "_at": f.received,
            }
        )
    out = {
        "facility": [d | {"_at": at} for d in facilities],
        "item": [d | {"_at": at} for d in items.values()],
        "location": [d | {"_at": at} for d in locations.values()],
        "inventory": inventory,
        "pix": pix,
    }
    return out


ID_FIELD = {
    "facility": "FacilityId",
    "item": "ItemId",
    "location": "LocationId",
    "inventory": "InventoryId",
    "pix": "PixId",
    "reservation": "ReservationId",
    "order": "OrderId",
    "task": "TaskId",
    "shipment": "ShipmentId",
}


def create(conn: Connection) -> None:
    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    metadata.create_all(conn)


def load(conn: Connection, s: Seed) -> dict[str, int]:
    counts = {}
    for entity, docs in build(s).items():
        rows = []
        for d in docs:
            at = d.pop("_at")
            audit(d, at, "seed")
            rows.append({"id": d[ID_FIELD[entity]], "facility": d.get("FacilityId"), "doc": d, "updated": at})
        if rows:
            conn.execute(insert(TABLES[entity]), rows)
        counts[entity] = len(rows)
    conn.execute(insert(COUNTERS), [{"name": n, "value": "0"} for n in ("reservation", "order", "task", "shipment", "pix")])
    return counts


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text(f"SELECT count(*) FROM {SCHEMA}.facility")).scalar_one() == 0:
        load(conn, s)


# ------------------------------------------------------------------ storage helpers used by api.py
def next_no(conn: Connection, name: str) -> int:
    v = int(conn.execute(select(COUNTERS.c.value).where(COUNTERS.c.name == name).with_for_update()).scalar_one()) + 1
    conn.execute(update(COUNTERS).where(COUNTERS.c.name == name).values(value=str(v)))
    return v


def all_docs(conn: Connection, entity: str, facility: str | None = None) -> list[dict]:
    t = TABLES[entity]
    q = select(t.c.doc).order_by(t.c.id)
    if facility is not None:
        q = q.where(t.c.facility == facility)
    return [r.doc for r in conn.execute(q)]


def get_doc(conn: Connection, entity: str, id_: str, lock: bool = False) -> dict | None:
    t = TABLES[entity]
    q = select(t.c.doc).where(t.c.id == id_)
    if lock:
        q = q.with_for_update()
    r = conn.execute(q).first()
    return r.doc if r else None


def put_doc(conn: Connection, entity: str, doc: dict, at: datetime, user: str = "system") -> dict:
    audit(doc, at, user)
    t = TABLES[entity]
    id_ = doc[ID_FIELD[entity]]
    conn.execute(delete(t).where(t.c.id == id_))
    conn.execute(insert(t).values(id=id_, facility=doc.get("FacilityId"), doc=doc, updated=at))
    return doc
