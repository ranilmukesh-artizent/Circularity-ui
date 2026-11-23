"""The preparation and service terms as cost lines (the demo's EX_BOM, EX_LAB, EX_OPS, EX_PACK, EX_SCOPE, exPrepParts,
EX_SVC, exSvc), and the asset facts they read (assetHealth, asSC).

Sources hold rupees; decisions are in dollars at ₹83.5 (EX_FX). Everything derives from the case: no random draws.
"""

import math
from typing import Any

from di.repositories.common import CLASSES, EX_FX, Case, as_hex, inr
from di.services.engine.jsmath import js_round, js_sum
from di.services.engine.predictor import GRADE_F, engine_class
from di.services.execution.lanes import ex_move_legs_for
from di.services.execution.util import js_str, num_or, parse_float

EX_FX_AT = "2026-10-06"

# class bills of materials (K12, assumed): part, number, component it serves, unit price in ₹ (SAP Ariba contract),
# quantity per unit; motor prices scale with motor size
EX_BOM: dict[str, list[tuple[str, str, str, int, int]]] = {
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
# labour at RC-HSR-01 (rate ₹/h, standard hours, role), machine operations (name, hours, ₹/h) and packing per class
# (K13, assumed)
EX_LAB = {
    "motor": (850, 22, "Electromechanical technician"),
    "pump": (850, 14, "Hydraulics technician"),
    "control": (950, 6, "Electronics technician"),
    "drill": (520, 1.2, "Bench technician"),
    "batch": (520, 0.8, "Bench technician"),
    "it": (520, 1, "Bench technician"),
}
EX_OPS: dict[str, list[tuple[str, float, int]]] = {
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
EX_PACK = {"motor": 8500, "pump": 3800, "control": 1200, "drill": 150, "batch": 120, "it": 180}
# the workshop's diagnosed repair scope, where one exists (else the parts of the components not rated good)
EX_SCOPE = {
    "RT-1048": ["SKF-6316-2Z/C3", "SKF-6314-2Z/C3", "VLT-SK-250M", "VLT-FC-250M", "VLT-TB-55", "RTD-PT100-3W", "VRN-H-LOT"]
}
# service exposure per class: call-out ₹, field hours, downtime handling ₹, parts ₹ per intervention
EX_SVC = {
    "motor": (6500, 12, 7500, 22900),
    "pump": (4500, 8, 5000, 12000),
    "control": (3500, 4, 3000, 9000),
    "drill": (0, 0.5, 0, 700),
    "batch": (0, 0.4, 0, 600),
    "it": (0, 0.6, 0, 1200),
}
FIELD_RATE = 1100  # ₹/h, ServiceNow FSM
# the components assessed per class (the demo's AS_COMPS)
AS_COMPS = {
    "motor": ["Stator winding", "Rotor and shaft", "Bearings", "Housing and frame", "Terminal box"],
    "pump": ["Pistons and barrel", "Shaft seal", "Bearings", "Housing", "Ports and fittings"],
    "control": ["Processor module", "I/O modules", "Power supply", "Connectors", "Firmware"],
    "drill": ["Motor", "Gearbox", "Chuck", "Housing", "Battery"],
    "batch": ["Drivers", "Battery packs", "Chucks", "Housings", "Chargers"],
    "it": ["Battery", "Display", "Keyboard", "Storage", "Chassis"],
}


def ex_inr(usd: float) -> int:
    """The demo's exInr: dollars to whole rupees (magnitude)."""
    return js_round(abs(usd) * EX_FX)


def _clamp(v: float, a: float, b: float) -> float:
    return max(a, min(b, v))


def asset_health(c: Case) -> dict:
    """The demo's assetHealth (score and per-component state; the band counts only draw the ring on screen)."""
    g = GRADE_F[c.get("grade") or "C"] * (1 if c.get("grade") else 0.92)
    life = math.exp(-c["age"] / CLASSES[engine_class(c)]["tau"])
    comps = []
    for n in AS_COMPS[engine_class(c)]:
        h = _clamp(g + ((as_hex(c, n) % 40) - 18) / 100, 0.22, 1)
        st = "Good" if h >= 0.85 else "Moderate wear" if h >= 0.65 else "Replace soon"
        comps.append({"n": n, "h": h, "st": st, "cls": "ok" if h >= 0.85 else "warn" if h >= 0.65 else "bad"})
    return {"score": _clamp(js_round(100 * (0.62 * g + 0.38 * life)), 24, 97), "comps": comps, "est": not c.get("grade")}


def as_sc(c: Case) -> str:
    """The demo's asSC: the supplier contract the parts are bought under."""
    return f"SC-{7000 + as_hex(c, 'sc') % 900}"


def ex_size(c: Case) -> float:
    """The demo's exSize: a motor's size relative to 55 kW (prices and hours scale with it)."""
    if c["cls"] != "motor":
        return 1
    return min(1.4, max(0.25, num_or(parse_float((c.get("spec") or {}).get("Rated power")), 22) / 55))


def ex_per_unit(c: Case) -> bool:
    """The demo's exPerUnit: small tools and IT lots are worked unit by unit."""
    return c["cls"] in ("drill", "batch", "it")


def ex_prep_parts(c: Case, r: dict) -> dict[str, Any] | None:
    """The demo's exPrepParts: the preparation term as parts, labour, machine time, transport legs and packing. Labour
    hours are solved last, so the lines add up exactly to the term (K2)."""
    t = next((x for x in r["terms"] if x["kind"] == "prep" and x["amt"] < 0), None)
    if not t:
        return None
    rid = r.get("id")
    if rid in ("intparts", "extparts"):
        mode = "teardown"
    elif rid in ("redeploy", "relase") or r.get("variant") == "refurb":
        mode = "refurb"
    else:
        return None
    B = ex_inr(t["amt"])
    f = ex_size(c)
    u = c["qty"] if ex_per_unit(c) else 1
    rate, std_h, role = EX_LAB[engine_class(c)]
    std = js_round((std_h * 0.45 if mode == "teardown" else std_h) * max(0.4, f) * u * 10) / 10
    h = asset_health(c) if c.get("grade") else None
    bad = [x["n"] for x in h["comps"] if x["cls"] != "ok"] if h else []
    bom: list[dict[str, Any]] = [
        {
            "name": p[0],
            "pn": p[1],
            "comp": p[2],
            "unit": js_round(p[3] * f / 50) * 50 if c["cls"] == "motor" else p[3],
            "qty": p[4] * u,
        }
        for p in EX_BOM[engine_class(c)]
    ]
    if mode == "teardown":
        parts, extra = [], []
    else:
        scope = EX_SCOPE.get(c["id"])
        parts = [p for p in bom if p["pn"] in scope] if scope else [p for p in bom if p["comp"] in bad]
        extra = [p for p in bom if not any(p is q for q in parts)]
    ops: list[dict[str, Any]] = []
    for name, oh, orate in EX_OPS[engine_class(c)]:
        hh = js_round(oh * (u if oh < 1 else max(1, u * 0.6)) * 10) / 10
        ops.append({"name": name, "h": hh, "rate": orate, "inr": js_round(hh * orate)})
    if mode == "teardown":
        ops = ops[-1:]
    pack = js_round(EX_PACK[engine_class(c)] * (max(0.35, f) if c["cls"] == "motor" else 1) * u / 10) * 10
    mv = ex_move_legs_for(c, r) if mode == "refurb" else []
    legs: list[dict[str, Any]] = [
        {"n": x["n"], "from": x["from"], "to": x["to"], "inr": x["inr"], "calc": x["calc"], "share": 1} for x in mv
    ]

    def P() -> float:
        return js_sum(p["unit"] * p["qty"] for p in parts)

    def F() -> float:
        return P() + js_sum(o["inr"] for o in ops) + js_sum(x["inr"] for x in legs) + pack

    min_lab, max_lab = min(std * rate * 0.5, B * 0.3), std * rate * 2
    # add parts while labour would be implausibly high; drop them, then machine time, then share the freight, then
    # scale everything while labour would be implausibly low
    while B - F() > max_lab and extra:
        parts.append(extra.pop(0))
    while F() > B - min_lab and len(parts) > 1:
        parts.pop()
    if F() > B - min_lab and len(ops) > 1:
        ops = ops[-1:]
    if F() > B - min_lab and legs:
        room = max(0, B - min_lab - P() - js_sum(o["inr"] for o in ops) - pack)
        tot = js_sum(x["inr"] for x in legs)
        s = max(0.05, min(1, room / tot))
        for x in legs:
            x["share"], x["full"], x["inr"] = s, x["inr"], js_round(x["inr"] * s / 10) * 10
    if F() > B - min_lab:
        s = max(0, (B - min_lab) / F())
        for p in parts:
            p["unit"] = math.floor(p["unit"] * s / 10) * 10
        for o in ops:
            o["inr"] = math.floor(o["inr"] * s / 10) * 10
        for x in legs:
            x["inr"] = math.floor(x["inr"] * s / 10) * 10
        pack = math.floor(pack * s / 10) * 10
    lab = B - F()
    return {
        "mode": mode, "B": B, "parts": parts, "ops": ops, "legs": legs, "pack": pack, "lab": lab,
        "labH": js_round(lab / rate * 10) / 10, "rate": rate, "std": std, "role": role, "P": P(),
    }  # fmt: skip


def ex_svc(c: Case, B: int, months: int) -> dict:
    """The demo's exSvc: service exposure as expected interventions x (call-out, field labour, downtime, parts)."""
    T = EX_SVC.get(c["cls"]) or EX_SVC["motor"]
    f = ex_size(c) if c["cls"] == "motor" else 1
    u = c["qty"] if ex_per_unit(c) else 1
    co = js_round(T[0] * f / 100) * 100
    fh = js_round(T[1] * f * u * 10) / 10
    dt = js_round(T[2] * f / 100) * 100
    pt = js_round(T[3] * f / 100) * 100 * u
    lab = js_round(fh * FIELD_RATE)
    per = co + lab + dt + pt
    n = max(0.5, js_round(B / per * 2) / 2)

    def fixed() -> float:
        return n * (co + lab + dt)

    while n > 0.5 and fixed() > B:
        n -= 0.5
    sc = B / fixed() if fixed() > B else 1

    ns = js_str(n)
    lines: list[list[Any]] = [
        ["Call-out", f"{ns} × {inr(co * sc)}", js_round(n * co * sc)],
        ["Field labour", f"{ns} × {js_str(fh)} h × {inr(FIELD_RATE)}", js_round(n * lab * sc)],
        ["Downtime handling", f"{ns} × {inr(dt * sc)}", js_round(n * dt * sc)],
    ]
    lines = [x for x in lines if x[2] > 0]
    parts = B - js_sum(x[2] for x in lines)
    lines.append(["Parts", f"{ns} × {inr(parts / n)}", parts])
    return {"n": n, "per": js_round(B / n), "months": months, "lines": lines}
