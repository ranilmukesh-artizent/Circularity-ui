"""Load the seed (B2) into the Oracle Depot Repair mock, as the depot holds it at the demo's as-of time.

Same values as the retired generic mock: a repair order exists for every case whose inspection or photo evidence
comes from "MRO" (the depot; "Inspection" evidence lives in SafetyCulture). Repair organisation RC01 (RC-HSR-01,
Hosur). The estimate is the preparation term of the case's first route through the depot (redeploy, re-lease or
refurbish-then-sell): RT-1048 → RO-61048, REPAIR_COST 1,800.00 USD, SCOPE "Light repair + test", RESULT_STATE B (the
demo's MAPPINGS.repair). Parts, labour, machine operations and bench tests are the demo's EX_BOM / EX_LAB / EX_OPS;
RT-1048's parts are its workshop diagnosis (EX_SCOPE). Seeded orders are open (STATUS O) in flow status
AWAITING_INSPECTION, INSPECTION_PARTIAL or ESTIMATE_PENDING_APPROVAL.
"""

from datetime import datetime, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.seed.model import CaseFacts
from sim.vendors.depot_repair import history
from sim.vendors.depot_repair import models as t
from sim.vendors.depot_repair.isg import ebs_ts
from sim.vendors.depot_repair.plan import (
    BENCH_TESTS,
    LABOUR,
    OPS,
    RESULT_GRADE,
    SCOPE_TEXT,
    _parts,
    _size,
    component_findings,
    inspected_at,
    repair_number,
    repair_route,
)
from sim.vendors.otm.demo import as_hex, case_no, facility_id, rma

FLOW = {
    "AWAITING_INSPECTION": "Awaiting Inspection",
    "INSPECTION_PARTIAL": "Inspection Partial",
    "ESTIMATE_PENDING_APPROVAL": "Estimate Pending Approval",
    "OPEN": "Open",
    "IN_PROGRESS": "In Progress",
    "REPAIR_COMPLETE": "Repair Complete",
    "CLOSED": "Closed",
}
STATUS = {"O": "Open", "C": "Closed", "H": "On Hold"}


def labour_hours(cls: str, f: CaseFacts | None = None) -> float:
    rate, std, role = LABOUR[cls]
    if f is None:
        return std
    return round(std * max(0.4, _size(f)) * (f.qty if cls in ("drill", "batch", "it") else 1), 1)


def upper(d: dict) -> dict:
    return {k.upper(): v for k, v in d.items()}


def task_doc(rn: str, serial: str, seq: int, name: str, kind: str, resource: str, hours, rate, status: str, done_at) -> dict:
    return {
        "TASK_NUMBER": f"{rn}-{seq:03d}",
        "REPAIR_NUMBER": rn,
        "SERIAL_NUMBER": serial,
        "OPERATION_SEQ_NUM": seq,
        "DESCRIPTION": name,
        "TASK_TYPE": kind,
        "RESOURCE_CODE": resource,
        "PLANNED_HOURS": hours,
        "ACTUAL_HOURS": hours if status == "COMPLETE" else None,
        "RATE": float(rate) if rate else None,
        "CURRENCY_CODE": "INR",
        "STATUS": status,
        "COMPLETED_DATE": ebs_ts(done_at) if status == "COMPLETE" else None,
    }


def test_doc(tid: str, rn: str, serial: str, plan: str, name, unit, limit, value, result, at, station) -> dict:
    return {
        "TEST_RESULT_ID": tid,
        "REPAIR_NUMBER": rn,
        "SERIAL_NUMBER": serial,
        "PLAN_NAME": plan,
        "CHARACTERISTIC": name,
        "UOM": unit,
        "SPEC_LIMIT": limit,
        "RESULT_VALUE": value,
        "RESULT": result,
        "TEST_DATE": ebs_ts(at),
        "STATION": station,
    }


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    as_of = seed.world.as_of
    orders, tasks, tests = [], [], []
    for case in seed.cases.values():
        f = case.facts
        ev = {e.k: e for e in f.evidence}
        if not [e for e in (ev.get("insp"), ev.get("photo")) if e and e.source == "MRO"]:
            continue
        insp = ev.get("insp") if ev.get("insp") and ev["insp"].source == "MRO" else None
        state = insp.state if insp else "missing"
        graded = state == "ready" and f.grade is not None
        rn = repair_number(f)
        line_id = 300000 + case_no(f.id)
        received = f.received + timedelta(hours=10)
        at = inspected_at(f, as_of)
        findings = component_findings(f) if graded else []
        parts = _parts(f, findings) if graded else []
        rate, _, role = LABOUR[f.cls]
        std_h = labour_hours(f.cls, f)
        est = repair_route(f)
        flow = "ESTIMATE_PENDING_APPROVAL" if graded else "INSPECTION_PARTIAL" if state == "partial" else "AWAITING_INSPECTION"
        updated = min(as_of - timedelta(minutes=30), max(received, at + timedelta(hours=2)))
        photos = ev.get("photo") and ev["photo"].source == "MRO" and ev["photo"].state == "ready"
        doc = {
            "REPAIR_LINE_ID": line_id,
            "REPAIR_NUMBER": rn,
            "INCIDENT_NUMBER": f"SR-{70000 + case_no(f.id)}",
            "SERIAL_NUMBER": f.asset_id,
            "ITEM_DESCRIPTION": f"{f.product} · {f.mfr}",
            "ITEM_CATEGORY": f.cls.upper(),
            "ITEM_SPEC": f.spec,
            "QUANTITY": f.qty,
            "CUSTOMER_NAME": f.owner,
            "RMA_NUMBER": rma(f),
            "ORIGINAL_SOURCE_REFERENCE": f.id,
            "REPAIR_TYPE": "Refurbishment" if est else "Evaluation",
            "REPAIR_MODE": "WIP",
            "REPAIR_ORG": "RC01",
            "REPAIR_ORG_LOCATION": "RC-HSR-01",
            "CURRENT_LOCATION": facility_id(f.location),
            "STATUS": "O",
            "STATUS_MEANING": STATUS["O"],
            "FLOW_STATUS_CODE": flow,
            "FLOW_STATUS": FLOW[flow],
            "RECEIVED_DATE": ebs_ts(received),
            "PROMISE_DATE": (received + timedelta(days=7)).date().isoformat(),
            "DATE_CLOSED": None,
            "RECEIVING_INSPECTION": {
                "INSPECTED_AT": ebs_ts(at) if state != "missing" else None,
                "INSPECTOR": "Repair centre lead (Engineer)",
                "GRADE": f.grade if graded else None,
                "CONDITION": f.condition,
                "RESULT": "PASS" if graded and f.grade != "D" else "FAIL" if graded else None,
                "NOTE": insp.note if insp else "",
                "PHOTO_COUNT": (4 + as_hex(f.id, "|mro|ph") % 9) if photos else 0,
            },
            "TEARDOWN_FINDINGS": {"TEARDOWN_FINDINGS_ITEM": [upper(x) for x in findings]},
            "SCOPE": SCOPE_TEXT[f.grade] if graded and est else ("Evaluation only" if graded else None),
            "REPAIR_COST": round(est[1], 2) if graded and est else None,
            "CURRENCY_CODE": "USD",
            "ESTIMATE_ROUTE": (est[0].plan if est else None) if graded else None,
            "RESULT_STATE": RESULT_GRADE[f.grade] if graded and est else None,
            "PARTS": {"PARTS_ITEM": [upper(p) for p in parts]},
            "LABOUR": {"ROLE": role, "RATE": float(rate), "CURRENCY_CODE": "INR", "STANDARD_HOURS": std_h},
            "RELEASE_TO_SERVICE": {"STATUS": "NOT_RELEASED", "RELEASED_AT": None, "CERTIFICATE": None},
        }
        orders.append(
            {
                "repair_line_id": line_id,
                "repair_number": rn,
                "serial_number": f.asset_id,
                "doc": doc,
                "creation_date": received,
                "last_update_date": updated,
            }
        )
        plan = [
            (
                "Receiving inspection",
                "Inspection",
                0.5 + as_hex(f.id, "|mro|t") % 3 * 0.25,
                0,
                "COMPLETE" if state != "missing" else "PLANNED",
            ),
            ("Teardown and diagnosis", "Diagnosis", round(std_h * 0.25, 1), 0, "COMPLETE" if graded else "PLANNED"),
        ]
        if graded and est:
            plan.append((f"Repair labour · {role}", "Labour", std_h, rate, "PLANNED"))
            plan += [(f"Machine · {name}", "Machine", h, mrate, "PLANNED") for name, h, mrate in OPS[f.cls]]
        for i, (name, kind, hours, hrate, st) in enumerate(plan, 1):
            resource = role if kind != "Machine" else name.removeprefix("Machine · ")
            tasks.append(
                {
                    "repair_line_id": line_id,
                    "operation_seq_num": i * 10,
                    "doc": task_doc(
                        rn, f.asset_id, i * 10, name, kind, resource, hours, hrate, st, at + timedelta(minutes=45 * i)
                    ),
                    "last_update_date": updated,
                }
            )
        if state != "missing":
            for j, (name, unit, limit, by_grade) in enumerate(BENCH_TESTS[f.cls], 1):
                run = graded
                tests.append(
                    {
                        "repair_line_id": line_id,
                        "doc": test_doc(
                            f"TR-{60000 + case_no(f.id)}-{j}",
                            rn,
                            f.asset_id,
                            "Receiving bench test",
                            name,
                            unit,
                            limit,
                            by_grade[f.grade] if run else None,
                            ("PASS" if f.grade != "D" else "FAIL") if run else "NOT_RUN",
                            at + timedelta(hours=1, minutes=10 * j) if run else None,
                            "RC-HSR-01 bench 2",
                        ),
                        "last_update_date": updated,
                    }
                )
    conn.execute(insert(t.CSD_REPAIRS), orders)
    conn.execute(insert(t.CSD_TASKS), tasks)
    conn.execute(insert(t.QA_RESULTS), tests)
    return {
        "repair_orders": len(orders),
        "tasks": len(tasks),
        "test_results": len(tests),
        "repair_history": load_history(conn),
    }


def load_history(conn: Connection) -> int:
    """The repair history (history.py): closed repairs and released refurbishments of the last three years."""
    rows = []
    for r in history.generate():
        closed = datetime.fromisoformat(r["DATE_CLOSED"])
        doc = {**r, "DATE_CLOSED": ebs_ts(closed)}
        doc.pop("LAST_UPDATE_DATE")
        if release := doc["RELEASE_TO_SERVICE"]:
            doc["RELEASE_TO_SERVICE"] = {**release, "RELEASED_AT": ebs_ts(release["RELEASED_AT"])}
        rows.append(
            {
                "repair_number": r["REPAIR_NUMBER"],
                "model_class": r["MODEL_CLASS"],
                "fault_code": r["FAULT_CODE"],
                "repair_type": r["REPAIR_TYPE"],
                "date_closed": closed,
                "doc": doc,
                "last_update_date": closed,
            }
        )
    conn.execute(insert(t.REPAIR_HISTORY), rows)
    return len(rows)


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS depot_repair"))
    t.metadata.create_all(conn)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    t.metadata.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM depot_repair.csd_repairs")).scalar_one() == 0:
        load(conn, seed)
    elif conn.execute(text("SELECT count(*) FROM depot_repair.repair_history")).scalar_one() == 0:
        load_history(conn)  # a database from before plan 9 gains the history
