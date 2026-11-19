"""Load the seed (B2) into the Aras Innovator item store, as Innovator would hold it at the demo's as-of time.

ItemTypes (Aras Product Engineering): Part, Part BOM (Part -> Part), Manufacturer, Manufacturer Part, Part AML
(Part -> Manufacturer Part, the approved manufacturer list), User. One row per item in `aras.item`, properties as
Innovator names them; item properties (source_id, related_id, manufacturer, created_by_id, ...) hold the referenced id.

Three levels per product configuration (the product Part's item_number is Teamcenter's ITEM_ID): the product -> its
major assemblies (the harvestable components the intparts / extparts routes recover) -> spare parts (the demo's class
BOMs, EX_BOM, priced in INR as in its SAP Ariba contracts). Motor assemblies are shared per power rating, e.g.
RT-1048's 55 kW motor has Rotor assembly P-55-ROT-01 (MAPPINGS.bom: Part.item_number P-55-ROT-01, Part BOM.quantity
1, Part.state Released). Every part is Released; ids are 32-character upper-case hex, stable per business key.
"""

import hashlib
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import Column, DateTime, MetaData, String, Table, insert, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.assetwise.seed import hash_id
from sim.vendors.teamcenter.seed import items_by_config, revision

metadata = MetaData(schema="aras")
ITEM = Table(
    "item",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("itemtype", String(40), nullable=False),  # the ItemType name: Part, Part BOM, ...
    Column("data", JSONB, nullable=False),
    Column("modified_on", DateTime(timezone=True), nullable=False),
)

# ItemType -> property -> kind ("string", "text", "decimal", "integer", "boolean", "date", "item:<ItemType>");
# relationship ItemTypes have source_id / related_id.
COMMON = {
    "id": "string",
    "config_id": "string",
    "keyed_name": "string",
    "itemtype": "string",
    "created_on": "date",
    "modified_on": "date",
    "created_by_id": "item:User",
    "modified_by_id": "item:User",
    "generation": "integer",
    "is_current": "boolean",
}
ITEMTYPES: dict[str, dict[str, str]] = {
    "Part": COMMON
    | {
        "item_number": "string",
        "name": "string",
        "description": "text",
        "classification": "string",
        "state": "string",
        "major_rev": "string",
        "is_released": "boolean",
        "make_buy": "string",
        "unit": "string",
        "cost": "decimal",
        "release_date": "date",
        "effective_date": "date",
        "nf_asset_class": "string",
        "nf_harvestable": "boolean",
        "nf_cost_currency": "string",
    },
    "Part BOM": COMMON
    | {
        "source_id": "item:Part",
        "related_id": "item:Part",
        "quantity": "decimal",
        "sort_order": "integer",
        "reference_designator": "string",
    },
    "Manufacturer": COMMON | {"name": "string", "state": "string"},
    "Manufacturer Part": COMMON
    | {"item_number": "string", "description": "text", "manufacturer": "item:Manufacturer", "state": "string"},
    "Part AML": COMMON
    | {"source_id": "item:Part", "related_id": "item:Manufacturer Part", "sort_order": "integer", "state": "string"},
    "User": COMMON | {"login_name": "string", "first_name": "string", "last_name": "string"},
}
RELATIONSHIPS = {"Part": ["Part BOM", "Part AML"]}  # source ItemType -> relationship ItemTypes
ITEMTYPE_IDS = {"Part": "4F1AC04A2B484F3ABA4E20DB63808A88"}  # Part's id as the Aras documentation shows it
ADMIN_ID = "30B991F927274FA3829655F50C99472E"  # Innovator Admin
CONNECTOR_ID = "8F2E6E8E5E3B4C0C9E1A2B3C4D5E6F70"

# class -> [(code, assembly name, harvestable, [EX_BOM components it holds])]
ASSEMBLIES = {
    "motor": [
        ("ROT", "Rotor assembly", False, ["Rotor and shaft"]),
        ("STA", "Stator assembly", True, ["Stator winding"]),
        ("BRG", "Bearing set", True, ["Bearings"]),
        ("HSG", "Housing, frame and fan cover", True, ["Housing and frame"]),
        ("TBX", "Terminal box", True, ["Terminal box"]),
        ("ENC", "Encoder module", True, []),
    ],
    "pump": [
        ("RGP", "Rotating group (pistons and barrel)", True, ["Pistons and barrel"]),
        ("SSL", "Shaft seal", True, ["Shaft seal"]),
        ("BRG", "Bearing set", True, ["Bearings"]),
        ("HSG", "Housing", False, ["Housing"]),
        ("PRT", "Ports and fittings", False, ["Ports and fittings"]),
    ],
    "control": [
        ("CPU", "Processor module", True, ["Processor module"]),
        ("IOM", "I/O modules", True, ["I/O modules"]),
        ("PSU", "Power supply", True, ["Power supply"]),
        ("CON", "Connectors and terminals", False, ["Connectors"]),
        ("FW", "Firmware and licence", False, ["Firmware"]),
    ],
    "drill": [
        ("MOT", "Motor", True, ["Motor"]),
        ("GBX", "Gearbox", True, ["Gearbox"]),
        ("CHK", "Chuck", True, ["Chuck"]),
        ("HSG", "Housing", False, ["Housing"]),
        ("BAT", "Battery pack", True, ["Battery"]),
    ],
    "batch": [
        ("DRV", "Driver motors", True, ["Drivers"]),
        ("BAT", "Battery packs", True, ["Battery packs"]),
        ("CHK", "Chucks", True, ["Chucks"]),
        ("HSG", "Housings", False, ["Housings"]),
        ("CHG", "Chargers", True, ["Chargers"]),
    ],
    "it": [
        ("BAT", "Battery", True, ["Battery"]),
        ("DSP", "Display", True, ["Display"]),
        ("KBD", "Keyboard", True, ["Keyboard"]),
        ("STO", "Storage", True, ["Storage"]),
        ("CHS", "Chassis", False, ["Chassis"]),
    ],
}
# the demo's EX_BOM: part, part number, component it serves, unit price (INR), quantity per unit
EX_BOM = {
    "motor": [
        ("Bearing 6316-2Z/C3 (drive end)", "SKF-6316-2Z/C3", "Bearings", 13400, 1),
        ("Bearing 6314-2Z/C3 (non-drive end)", "SKF-6314-2Z/C3", "Bearings", 11600, 1),
        ("Seal kit", "VLT-SK-250M", "Bearings", 1850, 2),
        ("Shaft repair sleeve", "VLT-SRS-250M", "Rotor and shaft", 9900, 1),
        ("Cooling fan and cowl", "VLT-FC-250M", "Housing and frame", 14200, 1),
        ("Terminal block and gasket", "VLT-TB-55", "Terminal box", 9600, 1),
        ("PT100 winding sensor (RTD)", "RTD-PT100-3W", "Stator winding", 4800, 3),
        ("Varnish and consumables", "VRN-H-LOT", "Stator winding", 16600, 1),
    ],
    "pump": [
        ("Piston and slipper set", "HH-PS-9", "Pistons and barrel", 28500, 1),
        ("Valve plate", "HH-VP-9", "Pistons and barrel", 9800, 1),
        ("Shaft seal kit", "HH-SSK-9", "Shaft seal", 2400, 1),
        ("Bearing set", "HH-BS-9", "Bearings", 6900, 1),
        ("Housing O-ring and gasket kit", "HH-OR-9", "Housing", 1900, 1),
        ("Port fittings and O-rings", "HH-PF-9", "Ports and fittings", 2200, 1),
        ("Hydraulic oil and filters", "HH-OIL-20", "Housing", 3600, 1),
    ],
    "control": [
        ("CPU module (exchange)", "OC-CPU-7", "Processor module", 22000, 1),
        ("I/O module 16-channel", "OC-IO-16", "I/O modules", 8400, 1),
        ("Power supply 24 V 10 A", "OC-PS-24", "Power supply", 6200, 1),
        ("Connector and terminal set", "OC-CN-SET", "Connectors", 1800, 1),
        ("Firmware licence transfer", "OC-FW-LT", "Firmware", 2500, 1),
        ("Backup battery", "OC-BAT-3V", "Power supply", 450, 1),
    ],
    "drill": [
        ("Carbon brushes (pair)", "TT-CB-18", "Motor", 380, 1),
        ("Armature", "TT-ARM-18", "Motor", 2600, 1),
        ("Gearbox assembly", "TT-GB-18", "Gearbox", 1900, 1),
        ("Keyless chuck 13 mm", "TT-CH-13", "Chuck", 950, 1),
        ("Housing shell", "TT-HS-18", "Housing", 700, 1),
        ("Battery pack 18 V 4 Ah", "TT-BP-4", "Battery", 5400, 1),
    ],
    "batch": [
        ("Driver motor", "BR-DM-18", "Drivers", 1800, 1),
        ("Battery pack 18 V 2 Ah", "BR-BP-2", "Battery packs", 3200, 1),
        ("Chuck", "BR-CH-10", "Chucks", 650, 1),
        ("Housing shell", "BR-HS-18", "Housings", 600, 1),
        ("Charger", "BR-CG-18", "Chargers", 1900, 1),
    ],
    "it": [
        ("Battery 4-cell", "LD-BAT-4C", "Battery", 4200, 1),
        ("Display panel 14 in", "LD-LCD-14", "Display", 7800, 1),
        ("Keyboard", "LD-KB-14", "Keyboard", 1900, 1),
        ("SSD 512 GB", "LD-SSD-512", "Storage", 3600, 1),
        ("Chassis bottom cover", "LD-CH-14", "Chassis", 1500, 1),
        ("Data erasure licence", "LD-ERASE", "Storage", 350, 1),
    ],
}
PN_MFR = {
    "SKF": "SKF",
    "VLT": "Voltara",
    "RTD": "Voltara",
    "VRN": "Voltara",
    "HH": "Halden Hydraulics",
    "OC": "Orbis Control",
    "TT": "Tessen Tools",
    "BR": "Brava",
    "LD": "Lumeo Devices",
}


def aras_id(*key: str) -> str:
    return hashlib.md5("|".join(key).encode()).hexdigest().upper()


def itemtype_id(name: str) -> str:
    return ITEMTYPE_IDS.get(name) or aras_id("ItemType", name)


def stamp(d: datetime) -> str:
    """Innovator's OData date-time: ISO 8601 without an offset, in the server's zone (UTC here)."""
    return d.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def items(s: Seed) -> list[dict]:
    as_of = s.world.as_of
    out: dict[str, dict] = {}

    def add(itemtype: str, key: tuple, props: dict, when: datetime) -> dict:
        iid = aras_id(itemtype, *key)
        if iid in out:
            return out[iid]["data"]
        data = {
            "id": iid,
            "config_id": iid,
            "itemtype": itemtype_id(itemtype),
            "generation": 1,
            "is_current": "1",
            "created_on": stamp(when - timedelta(days=20)),
            "modified_on": stamp(when),
            "created_by_id": ADMIN_ID,
            "modified_by_id": ADMIN_ID,
        } | props
        data.setdefault("keyed_name", props.get("item_number") or props.get("name") or iid)
        out[iid] = {"id": iid, "itemtype": itemtype, "data": data, "modified_on": when}
        return data

    base = datetime(2024, 1, 10, 9, 0, tzinfo=UTC)
    add(
        "User",
        ("admin",),
        {"login_name": "admin", "first_name": "Innovator", "last_name": "Admin", "keyed_name": "Innovator Admin"},
        base,
    )
    out[ADMIN_ID] = out.pop(aras_id("User", "admin")) | {"id": ADMIN_ID}
    out[ADMIN_ID]["data"] |= {"id": ADMIN_ID, "config_id": ADMIN_ID}
    add(
        "User",
        ("di-connector",),
        {
            "login_name": "di-connector",
            "first_name": "Circularity",
            "last_name": "Connector",
            "keyed_name": "Circularity Connector",
        },
        base,
    )
    out[CONNECTOR_ID] = out.pop(aras_id("User", "di-connector")) | {"id": CONNECTOR_ID}
    out[CONNECTOR_ID]["data"] |= {"id": CONNECTOR_ID, "config_id": CONNECTOR_ID}

    def released(key: str) -> datetime:
        return datetime.combine((as_of - timedelta(days=40 + hash_id(key) % 300)).date(), time(10, 15), UTC)

    def part(num: str, name: str, cls: str, classification: str, **kw) -> dict:
        when = released(num)
        cost = kw.pop("cost", None)
        return add(
            "Part",
            (num,),
            {
                "item_number": num,
                "name": name,
                "description": kw.pop("description", name),
                "classification": classification,
                "state": "Released",
                "major_rev": kw.pop("major_rev", "A"),
                "is_released": "1",
                "make_buy": kw.pop("make_buy", "Make"),
                "unit": "EA",
                "cost": cost,
                "release_date": stamp(when),
                "effective_date": stamp(when),
                "nf_asset_class": cls,
                "nf_harvestable": "1" if kw.pop("harvestable", False) else "0",
                "nf_cost_currency": "INR" if cost is not None else None,
            },
            when,
        )

    def manufacturer(name: str) -> dict:
        return add("Manufacturer", (name,), {"name": name, "state": "Released"}, base)

    def bom(parent: dict, child: dict, qty: int, order: int) -> None:
        when = max(released(parent["item_number"]), released(child["item_number"]))
        add(
            "Part BOM",
            (parent["item_number"], child["item_number"]),
            {
                "source_id": parent["id"],
                "related_id": child["id"],
                "quantity": qty,
                "sort_order": order,
                "reference_designator": None,
                "keyed_name": child["item_number"],
            },
            when,
        )

    def aml(p: dict, mfr: str, mpn: str, order: int) -> None:
        m = manufacturer(mfr)
        when = released(p["item_number"])
        mp = add(
            "Manufacturer Part",
            (mfr, mpn, p["item_number"]),
            {
                "item_number": mpn,
                "description": p["name"],
                "manufacturer": m["id"],
                "state": "Released",
            },
            when,
        )
        add(
            "Part AML",
            (p["item_number"], mp["id"]),
            {
                "source_id": p["id"],
                "related_id": mp["id"],
                "sort_order": order,
                "state": "Approved",
                "keyed_name": mpn,
            },
            when,
        )

    for item_id, it in items_by_config(s).items():
        cls, cfg = it["cls"], it["config"]
        top = part(item_id, f"{it['product']} {cfg['name']}", cls, "Product", major_rev=revision(item_id))
        for n, mfr in enumerate(dict.fromkeys(f.mfr for f in it["facts"]), 1):
            aml(top, mfr, f"{mfr[:3].upper()}-{item_id.split('-', 1)[1]}", n * 10)
        for i, (code, name, harvest, comps) in enumerate(ASSEMBLIES[cls], 1):
            asm = part(f"P-{cfg['size']}-{code}-01", name, cls, "Assembly", harvestable=harvest)
            bom(top, asm, 1, i * 10)
            for j, (pname, pn, _comp, inr, qty) in enumerate((r for r in EX_BOM[cls] if r[2] in comps), 1):
                sp = part(pn, pname, cls, "Component", make_buy="Buy", cost=float(inr))
                bom(asm, sp, qty, j * 10)
                aml(sp, PN_MFR.get(pn.split("-")[0], "Voltara"), pn.removeprefix("SKF-"), 10)
    return list(out.values())


def load(conn: Connection, s: Seed) -> dict[str, int]:
    rows = items(s)
    conn.execute(insert(ITEM), rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["itemtype"]] = counts.get(r["itemtype"], 0) + 1
    return counts


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS aras"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM aras.item")).scalar_one() == 0:
        load(conn, s)
