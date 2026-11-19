"""The depot's planning data, from the demo (index.html): parts per class (EX_BOM), labour (EX_LAB), machine
operations (EX_OPS), RT-1048's workshop diagnosis (EX_SCOPE), bench tests per class, and the component findings
of a receiving inspection. Same values as the retired generic Depot Repair and SafetyCulture specs."""

import re
from datetime import datetime, timedelta

from sim.seed.model import CaseFacts, RouteFacts
from sim.vendors.otm.demo import as_hex, case_no, jround

# part, part number, component, unit price INR (SAP Ariba contract), qty per unit (EX_BOM)
BOM = {
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
LABOUR = {  # INR per hour, standard hours, role (EX_LAB)
    "motor": (850, 22, "Electromechanical technician"),
    "pump": (850, 14, "Hydraulics technician"),
    "control": (950, 6, "Electronics technician"),
    "drill": (520, 1.2, "Bench technician"),
    "batch": (520, 0.8, "Bench technician"),
    "it": (520, 1, "Bench technician"),
}
OPS = {  # machine operation, hours, INR per hour (EX_OPS)
    "motor": [
        ("Bake oven", 8, 350),
        ("Balancing", 1, 1600),
        ("Load test bench", 3, 1400),
        ("Surge and insulation test", 1, 1200),
    ],
    "pump": [("Test rig", 2, 1800), ("Flushing rig", 1, 900)],
    "control": [("Burn-in rack", 8, 120), ("Functional test station", 1, 1100)],
    "drill": [("Battery cycler", 2, 90), ("Function test", 0.25, 400)],
    "batch": [("Battery cycler", 2, 90), ("Function test", 0.25, 400)],
    "it": [("Imaging station", 0.5, 300), ("Battery test", 1, 90)],
}
SCOPE_PARTS = {
    "RT-1048": ["SKF-6316-2Z/C3", "SKF-6314-2Z/C3", "VLT-SK-250M", "VLT-FC-250M", "VLT-TB-55", "RTD-PT100-3W", "VRN-H-LOT"]
}
BENCH_TESTS = {  # measurement, unit, pass limit, value by grade
    "motor": [
        ("Insulation resistance (PI)", "ratio", ">= 2.0", {"A": 4.1, "B": 3.2, "C": 2.4, "D": 1.6}),
        ("Winding resistance imbalance", "%", "<= 2.0", {"A": 0.4, "B": 0.9, "C": 1.7, "D": 3.1}),
        ("Vibration at no load", "mm/s", "<= 2.8", {"A": 1.1, "B": 1.9, "C": 2.6, "D": 4.4}),
    ],
    "pump": [
        ("Case drain flow", "l/min", "<= 3.5", {"A": 1.2, "B": 2.1, "C": 3.1, "D": 5.2}),
        ("Pressure hold at 250 bar", "bar drop/min", "<= 5", {"A": 1, "B": 2, "C": 4, "D": 9}),
    ],
    "control": [
        ("I/O self-test", "channels failed", "= 0", {"A": 0, "B": 0, "C": 0, "D": 3}),
        ("Supply ripple", "mV", "<= 120", {"A": 40, "B": 65, "C": 95, "D": 160}),
    ],
    "drill": [
        ("No-load speed", "% of rated", ">= 90", {"A": 99, "B": 96, "C": 92, "D": 81}),
        ("Battery capacity", "% of rated", ">= 70", {"A": 95, "B": 86, "C": 74, "D": 52}),
    ],
    "batch": [
        ("Battery capacity (sample)", "% of rated", ">= 70", {"A": 94, "B": 85, "C": 73, "D": 50}),
        ("Function test (sample)", "units failed", "= 0", {"A": 0, "B": 0, "C": 0, "D": 2}),
    ],
    "it": [
        ("Battery health", "% of design", ">= 70", {"A": 93, "B": 84, "C": 72, "D": 55}),
        ("Storage SMART status", "reallocated sectors", "<= 10", {"A": 0, "B": 2, "C": 8, "D": 41}),
    ],
}
RESULT_GRADE = {"A": "A", "B": "B", "C": "B", "D": "C"}
SCOPE_TEXT = {"A": "Clean, test and certify", "B": "Light repair + test", "C": "Refurbishment + test", "D": "Rebuild + test"}


def _size(f: CaseFacts) -> float:
    if f.cls != "motor":
        return 1.0
    m = re.match(r"\s*([\d.]+)", str(f.spec.get("Rated power", "")))
    return min(1.4, max(0.25, (float(m.group(1)) if m else 22) / 55))


def repair_route(f: CaseFacts) -> tuple[RouteFacts, float] | None:
    """The first route that runs through the depot, and its preparation cost (USD, positive)."""
    for r in f.routes:
        if r.id in ("redeploy", "relase") or (r.id == "resale" and r.variant == "refurb"):
            prep = next((t.amt for t in r.terms if t.kind == "prep" and t.amt < 0), None)
            if prep is not None:
                return r, -prep
    return None


def repair_number(f: CaseFacts) -> str:
    return f"RO-{60000 + case_no(f.id)}"


def _parts(f: CaseFacts, findings: list[dict]) -> list[dict]:
    size, unit_qty = _size(f), (f.qty if f.cls in ("drill", "batch", "it") else 1)
    bom = BOM[f.cls]
    if f.id in SCOPE_PARTS:
        chosen = [p for p in bom if p[1] in SCOPE_PARTS[f.id]]
    else:
        bad = {x["component"] for x in findings if x["action"] != "None"}
        chosen = [p for p in bom if p[2] in bad]
    return [
        {
            "part_number": pn,
            "description": name,
            "component": comp,
            "quantity": q * unit_qty,
            "unit_price": float(jround(price * size / 50) * 50 if f.cls == "motor" else price),
            "currency_code": "INR",
            "source": "SAP Ariba contract",
            "issued": False,
        }
        for name, pn, comp, price, q in chosen
    ]


# components checked per class: the demo's EX_BOM component names, so findings line up with repair parts
COMPONENTS = {
    "motor": ["Bearings", "Rotor and shaft", "Housing and frame", "Terminal box", "Stator winding"],
    "pump": ["Pistons and barrel", "Shaft seal", "Bearings", "Housing", "Ports and fittings"],
    "control": ["Processor module", "I/O modules", "Power supply", "Connectors", "Firmware"],
    "drill": ["Motor", "Gearbox", "Chuck", "Housing", "Battery"],
    "batch": ["Drivers", "Battery packs", "Chucks", "Housings", "Chargers"],
    "it": ["Battery", "Display", "Keyboard", "Storage", "Chassis"],
}
FUNCTIONAL = {
    "motor": "No-load run and vibration",
    "pump": "Pressure and flow test",
    "control": "Functional and I/O self-test",
    "drill": "Function test under load",
    "batch": "Function test (sample)",
    "it": "Power-on self-test",
}
# RT-1048's workshop diagnosis (the demo's EX_SCOPE parts map to these components)
SCOPE_COMPONENTS = {"RT-1048": ["Bearings", "Housing and frame", "Terminal box", "Stator winding"]}


def component_findings(f: CaseFacts) -> list[dict]:
    """One finding per component, consistent with the grade: A all good, B one worn, C two worn + one replace,
    D two replace + one worn. Deterministic per case."""
    comps = COMPONENTS[f.cls]
    if f.id in SCOPE_COMPONENTS:
        bad = SCOPE_COMPONENTS[f.id]
        return [
            {"component": c, "status": "Worn" if c in bad else "Good", "action": "Replace" if c in bad else "None"} for c in comps
        ]
    start = as_hex(f.id, "|insp|c") % len(comps)
    order = comps[start:] + comps[:start]
    plan = {"A": [], "B": ["Worn"], "C": ["Replace", "Worn", "Worn"], "D": ["Replace", "Replace", "Worn"]}.get(f.grade or "", [])
    status = {c: "Good" for c in comps} | dict(zip(order, plan, strict=False))
    act = {"Good": "None", "Worn": "Repair", "Replace": "Replace"}
    return [{"component": c, "status": status[c], "action": act[status[c]]} for c in comps]


def inspected_at(f: CaseFacts, as_of: datetime) -> datetime:
    t = f.received + timedelta(days=as_hex(f.id, "|insp|d") % 2, hours=9 + as_hex(f.id, "|insp|h") % 8)
    return min(t, as_of - timedelta(hours=2))
