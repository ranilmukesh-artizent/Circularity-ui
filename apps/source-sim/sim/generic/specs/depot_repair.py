"""Oracle Depot Repair (the demo's SOURCES.repair): receiving inspection and grade, teardown findings, repair and
refurbishment orders, operations and hours, parts used, bench test results, release to service.
Read: GET /repair-orders?serial={sn}, /repair-orders/{id}/tasks, /repair-orders/{id}/test-results.
Write: POST /repair-orders.

Framework gap: the generic mock has no nested paths, so the demo's /repair-orders/{id}/tasks and
/repair-orders/{id}/test-results are served as /repair-tasks?repair_number={id} and
/repair-test-results?repair_number={id}.

A repair order exists for every case whose inspection or photo evidence comes from "MRO" (the demo's evidence source
for the depot; "Inspection" evidence lives in SafetyCulture). The repair centre is RC01 (RC-HSR-01, Hosur). The
estimate is the preparation term of the case's first repair-bearing route (redeploy, re-lease or refurbish-then-sell):
RT-1048 -> $1,800 "Light repair + test", result grade B, as in the demo's MAPPINGS.repair. Parts, labour rates,
standard hours and machine operations are the demo's EX_BOM / EX_LAB / EX_OPS; RT-1048's parts are its workshop
diagnosis (EX_SCOPE).
"""

import re
from datetime import timedelta

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs.manhattan import facility_id
from sim.generic.specs.safetyculture import component_findings, inspected_at
from sim.generic.specs.shiplane import as_hex, case_no, jround, rma
from sim.seed import Seed
from sim.seed.model import CaseFacts, RouteFacts

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


def seed(s: Seed) -> dict[str, list[dict]]:
    orders, tasks, tests = [], [], []
    for case in s.cases.values():
        f = case.facts
        ev = {e.k: e for e in f.evidence}
        mro = [e for e in (ev.get("insp"), ev.get("photo")) if e and e.source == "MRO"]
        if not mro:
            continue
        insp = ev.get("insp") if ev.get("insp") and ev["insp"].source == "MRO" else None
        state = insp.state if insp else "missing"
        graded = state == "ready" and f.grade is not None
        rn = repair_number(f)
        received = f.received + timedelta(hours=10)
        at = inspected_at(f, s.world.as_of)
        findings = component_findings(f) if graded else []
        parts = _parts(f, findings) if graded else []
        rate, std, role = LABOUR[f.cls]
        std_h = round(std * max(0.4, _size(f)) * (f.qty if f.cls in ("drill", "batch", "it") else 1), 1)
        est = repair_route(f)
        flow = "ESTIMATE_PENDING_APPROVAL" if graded else "INSPECTION_PARTIAL" if state == "partial" else "AWAITING_INSPECTION"
        orders.append(
            {
                "repair_number": rn,
                "repair_line_id": 300000 + case_no(f.id),
                "incident_number": f"SR-{70000 + case_no(f.id)}",
                "serial": f.asset_id,
                "item_description": f"{f.product} · {f.mfr}",
                "item_spec": f.spec,
                "quantity": f.qty,
                "customer": f.owner,
                "rma_number": rma(f),
                "return_reference": f.id,
                "repair_type": "Refurbishment" if est else "Evaluation",
                "repair_org": "RC01",
                "repair_org_code": "RC-HSR-01",
                "current_location": facility_id(f.location),
                "status": "OPEN",
                "flow_status": flow,
                "received_date": received.isoformat(),
                "receiving_inspection": {
                    "inspected_at": at.isoformat() if state != "missing" else None,
                    "inspector": "Repair centre lead (Engineer)",
                    "grade": f.grade if graded else None,
                    "condition": f.condition,
                    "result": "PASS" if graded and f.grade != "D" else "FAIL" if graded else None,
                    "note": insp.note if insp else "",
                    "photo_count": (4 + as_hex(f.id, "|mro|ph") % 9)
                    if ev.get("photo") and ev["photo"].source == "MRO" and ev["photo"].state == "ready"
                    else 0,
                },
                "teardown_findings": findings,
                "scope": SCOPE_TEXT[f.grade] if graded and est else ("Evaluation only" if graded else None),
                "repair_cost": round(est[1], 2) if graded and est else None,
                "repair_cost_currency": "USD",
                "estimate_route": (est[0].plan if est else None) if graded else None,
                "result_state": RESULT_GRADE[f.grade] if graded and est else None,
                "parts": parts,
                "labour": {"role": role, "rate": float(rate), "currency_code": "INR", "standard_hours": std_h},
                "promise_date": (received + timedelta(days=7)).date().isoformat(),
                "release_to_service": {"status": "NOT_RELEASED", "released_at": None, "certificate": None},
            }
        )
        # tasks: receiving inspection, teardown/diagnosis, then the planned labour and machine operations
        plan = [
            (
                "Receiving inspection",
                "Inspection",
                0.5 + as_hex(f.id, "|mro|t") % 3 * 0.25,
                0,
                "COMPLETE" if state != "missing" else "PLANNED",
            )
        ]
        plan.append(("Teardown and diagnosis", "Diagnosis", round(std_h * 0.25, 1), 0, "COMPLETE" if graded else "PLANNED"))
        if graded and est:
            plan.append((f"Repair labour · {role}", "Labour", std_h, rate, "PLANNED"))
            plan += [(f"Machine · {name}", "Machine", h, mrate, "PLANNED") for name, h, mrate in OPS[f.cls]]
        for i, (name, kind, hours, hrate, status) in enumerate(plan, 1):
            tasks.append(
                {
                    "task_id": f"{rn}-{i * 10:03d}",
                    "repair_number": rn,
                    "serial": f.asset_id,
                    "operation_seq": i * 10,
                    "description": name,
                    "task_type": kind,
                    "resource": role if kind != "Machine" else name.removeprefix("Machine · "),
                    "planned_hours": hours,
                    "actual_hours": hours if status == "COMPLETE" else None,
                    "rate": float(hrate) if hrate else None,
                    "currency_code": "INR",
                    "status": status,
                    "completed_at": (at + timedelta(minutes=45 * i)).isoformat() if status == "COMPLETE" else None,
                }
            )
        # bench tests at receiving: measured when graded; functional checks not run when the inspection is partial
        if state != "missing":
            for j, (name, unit, limit, by_grade) in enumerate(BENCH_TESTS[f.cls], 1):
                run = graded and not (state == "partial")
                val = by_grade[f.grade] if run else None
                tests.append(
                    {
                        "test_result_id": f"TR-{60000 + case_no(f.id)}-{j}",
                        "repair_number": rn,
                        "serial": f.asset_id,
                        "test_plan": "Receiving bench test",
                        "measurement": name,
                        "unit": unit,
                        "limit": limit,
                        "value": val,
                        "result": ("PASS" if f.grade != "D" else "FAIL") if run else "NOT_RUN",
                        "tested_at": (at + timedelta(hours=1, minutes=10 * j)).isoformat() if run else None,
                        "station": "RC-HSR-01 bench 2",
                    }
                )
    return {"repair_orders": orders, "tasks": tasks, "test_results": tests}


SPEC = Spec(
    source_id="repair",
    title="Oracle Depot Repair",
    schema="depot_repair",
    base_path="/depot-repair/webservices/rest/csd",
    auth=Auth("oauth_cc"),
    paging=Paging(
        "offset", limit_param="limit", offset_param="offset", items_key="items", next_key="nextOffset", total_key="totalResults"
    ),
    resources=(
        Resource(
            "repair_orders",
            "/repair-orders",
            "repair_number",
            filters=("serial", "return_reference", "rma_number", "flow_status", "status", "repair_org", "customer"),
            create=True,
            id_format="RO-7{n:04d}",
            event="oracle.csd.repair_order",
        ),
        # the demo's /repair-orders/{id}/tasks and /test-results: no nested paths in the generic mock
        Resource("tasks", "/repair-tasks", "task_id", filters=("repair_number", "serial", "status", "task_type")),
        Resource("test_results", "/repair-test-results", "test_result_id", filters=("repair_number", "serial", "result")),
    ),
    seed=seed,
)
