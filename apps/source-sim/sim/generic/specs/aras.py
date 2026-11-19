"""Aras Innovator (the demo's SOURCES.bom): multi-level bill of materials, part structures, manufacturer parts.
Read: GET /Part, /Part_BOM, /Manufacturer_Part. No writes.

The demo lists the item types as "Part BOM" and "Manufacturer Part"; their URL-safe paths here are /Part_BOM and
/Manufacturer_Part. Items are keyed by Aras-style 32-hex `id`s (deterministic), with `item_number` as the business key.

Three levels per product configuration (Teamcenter ITEM_ID): the product -> its major assemblies (the harvestable
components the intparts / extparts routes recover) -> spare parts (the demo's class BOMs, EX_BOM, priced in INR as in
its SAP Ariba contracts). Motor assemblies are shared per power rating, e.g. RT-1048's 55 kW motor has Rotor assembly
P-55-ROT-01 (MAPPINGS.bom: Part.item_number P-55-ROT-01, Part BOM.quantity 1, Part.state Released).
"""

import hashlib

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs.teamcenter import items_by_config, revision
from sim.seed import Seed

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
# part-number prefix -> manufacturer
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


def seed(s: Seed) -> dict[str, list[dict]]:
    as_of = s.world.as_of.isoformat()
    parts: dict[str, dict] = {}  # by item_number
    bom: dict[str, dict] = {}
    mparts: dict[str, dict] = {}

    def part(num: str, name: str, cls: str, classification: str, **kw) -> dict:
        if num not in parts:
            parts[num] = {
                "id": aras_id("Part", num),
                "item_number": num,
                "name": name,
                "classification": classification,
                "asset_class": cls,
                "state": "Released",
                "major_rev": kw.pop("major_rev", "A"),
                "unit": "EA",
                "make_buy": kw.pop("make_buy", "Make"),
                "cost": kw.pop("cost", None),
                "cost_currency": "INR" if classification == "Component" else None,
                "harvestable": kw.pop("harvestable", False),
                "modified_on": as_of,
            } | kw
        return parts[num]

    def line(parent: dict, child: dict, qty: int, order: int) -> None:
        bid = aras_id("Part BOM", parent["item_number"], child["item_number"])
        bom[bid] = {
            "id": bid,
            "source_id": parent["id"],
            "related_id": child["id"],
            "source_item_number": parent["item_number"],
            "related_item_number": child["item_number"],
            "quantity": qty,
            "sort_order": order,
            "state": "Released",
        }

    def mpart(p: dict, mfr: str, mpn: str) -> None:
        mid = aras_id("Manufacturer Part", mfr, mpn, p["item_number"])
        mparts[mid] = {
            "id": mid,
            "item_number": mpn,
            "manufacturer": mfr,
            "description": p["name"],
            "part_id": p["id"],
            "part_item_number": p["item_number"],
            "preferred": True,
            "state": "Released",
        }

    for item_id, it in items_by_config(s).items():
        cls, cfg = it["cls"], it["config"]
        top = part(item_id, f"{it['product']} {cfg['name']}", cls, "Product", major_rev=revision(item_id))
        for f in it["facts"]:
            mpart(top, f.mfr, f"{f.mfr[:3].upper()}-{item_id.split('-', 1)[1]}")
        for i, (code, name, harvest, comps) in enumerate(ASSEMBLIES[cls], 1):
            asm = part(f"P-{cfg['size']}-{code}-01", name, cls, "Assembly", harvestable=harvest)
            line(top, asm, 1, i * 10)
            for j, (pname, pn, _comp, inr, qty) in enumerate((r for r in EX_BOM[cls] if r[2] in comps), 1):
                sp = part(pn, pname, cls, "Component", make_buy="Buy", cost=float(inr))
                line(asm, sp, qty, j * 10)
                prefix = pn.split("-")[0]
                mpart(sp, PN_MFR.get(prefix, "Voltara"), pn.removeprefix("SKF-"))
    return {"Part": list(parts.values()), "Part_BOM": list(bom.values()), "Manufacturer_Part": list(mparts.values())}


SPEC = Spec(
    source_id="bom",
    title="Aras Innovator",
    schema="aras",
    base_path="/aras/InnovatorServer/odata",
    auth=Auth("oauth_cc", token_path="/oauthserver/connect/token"),
    paging=Paging(
        "cursor",
        limit_param="$top",
        cursor_param="$skiptoken",
        items_key="value",
        next_key="@odata.skipToken",
        total_key="@odata.count",
    ),
    resources=(
        Resource("Part", "/Part", "id", filters=("item_number", "classification", "asset_class", "state")),
        Resource(
            "Part_BOM",
            "/Part_BOM",
            "id",
            filters=("source_id", "related_id", "source_item_number", "related_item_number"),
        ),
        Resource("Manufacturer_Part", "/Manufacturer_Part", "id", filters=("item_number", "manufacturer", "part_item_number")),
    ),
    seed=seed,
)
