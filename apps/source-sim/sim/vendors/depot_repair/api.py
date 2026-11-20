"""Oracle Depot Repair mock: HTTP surface (docs/BACKEND_STEPS.md, B5b). See the package docstring for the contract."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Connection

from sim import clock, events, scheduler
from sim.db import engine
from sim.vendors.depot_repair import tables as t
from sim.vendors.depot_repair.isg import (
    Gateway,
    IsgFault,
    dispatch,
    ebs_ts,
    input_parameters,
    output,
    paging,
    parse_ts,
    table,
)
from sim.vendors.depot_repair.plan import BENCH_TESTS, LABOUR, OPS
from sim.vendors.depot_repair.seed import FLOW, STATUS, task_doc, test_doc

SOURCE = "repair"
PRODUCT = "csd"
GW = Gateway("/depot-repair", {"DI_CONNECTOR": "repair-demo-password"}, "EBSDRP1")
QUERY, PUB = "xxcsdroquery", "csdrepairs"
REPAIR_TYPES = ("Refurbishment", "Repair and Return", "Evaluation", "Teardown", "Walk-in Repair")
GRADES = ("A", "B", "C", "D")

router = APIRouter()
GW.routes(router)


def expire_all_tokens() -> int:
    return GW.expire_all_tokens()


# ------------------------------------------------------------------ reads (custom query package XXCSD_RO_QUERY)
def _since(params, method: str) -> datetime | None:
    return parse_ts(params.get("P_LAST_UPDATE_DATE_FROM"), "P_LAST_UPDATE_DATE_FROM", QUERY, method)


def _page(rows: list[dict], params, method: str, name: str) -> dict:
    start, size = paging(params, QUERY, method)
    chunk = rows[start - 1 : start - 1 + size]
    return output(
        PRODUCT,
        QUERY,
        method,
        {
            "X_TOTAL_COUNT": str(len(rows)),
            "X_HAS_MORE": "Y" if start - 1 + size < len(rows) else "N",
            name: table(name, chunk),
        },
    )


def _changed(rows: list[dict], since: datetime | None) -> list[dict]:
    """Rows whose LAST_UPDATE_DATE (as shown, to the millisecond) is after `since`."""
    if since is None:
        return rows
    return [r for r in rows if datetime.fromisoformat(r["LAST_UPDATE_DATE"]) > since]


def _order(r) -> dict:
    return {**r.doc, "CREATION_DATE": ebs_ts(r.creation_date), "LAST_UPDATE_DATE": ebs_ts(r.last_update_date)}


def get_repair_orders(request: Request, conn: Connection):
    p = request.query_params
    stmt = select(t.CSD_REPAIRS).order_by(t.CSD_REPAIRS.c.repair_line_id)
    if v := p.get("P_SERIAL_NUMBER"):
        stmt = stmt.where(t.CSD_REPAIRS.c.serial_number == v)
    if v := p.get("P_REPAIR_NUMBER"):
        stmt = stmt.where(t.CSD_REPAIRS.c.repair_number == v)
    rows = [_order(r) for r in conn.execute(stmt).all()]
    for name in ("ORIGINAL_SOURCE_REFERENCE", "FLOW_STATUS_CODE", "STATUS", "REPAIR_ORG"):
        if v := p.get("P_" + name):
            rows = [r for r in rows if str(r.get(name)) == v]
    return _page(_changed(rows, _since(p, "get_repair_orders")), p, "get_repair_orders", "X_REPAIR_ORDERS")


def _children(request: Request, conn: Connection, tbl, key: str, method: str, name: str):
    p = request.query_params
    ro = t.CSD_REPAIRS
    stmt = select(tbl, ro.c.repair_number, ro.c.serial_number).join(ro, ro.c.repair_line_id == tbl.c.repair_line_id)
    if v := p.get("P_REPAIR_NUMBER"):
        stmt = stmt.where(ro.c.repair_number == v)
    if v := p.get("P_SERIAL_NUMBER"):
        stmt = stmt.where(ro.c.serial_number == v)
    stmt = stmt.order_by(tbl.c.repair_line_id, tbl.c[key])
    rows = [{key.upper(): getattr(r, key), **r.doc, "LAST_UPDATE_DATE": ebs_ts(r.last_update_date)} for r in conn.execute(stmt)]
    return _page(_changed(rows, _since(p, method)), p, method, name)


def get_repair_tasks(request: Request, conn: Connection):
    return _children(request, conn, t.CSD_TASKS, "task_id", "get_repair_tasks", "X_REPAIR_TASKS")


def get_test_results(request: Request, conn: Connection):
    return _children(request, conn, t.QA_RESULTS, "collection_id", "get_test_results", "X_TEST_RESULTS")


# ------------------------------------------------------------------ writes (CSD_REPAIRS_PUB)
def _error(method: str, msg: str) -> dict:
    return output(PRODUCT, PUB, method, {}, "E", [msg])


def create_repair_order(params: dict, conn: Connection) -> dict:
    """CSD_REPAIRS_PUB.CREATE_REPAIR_ORDER: the refurbishment work order of an approved instruction."""
    m = "create_repair_order"
    if str(params.get("P_API_VERSION_NUMBER") or "") not in ("1.0", "1"):
        return _error(m, "FND_AS_INCOMPATIBLE_API_CALL: P_API_VERSION_NUMBER must be 1.0.")
    rec = params.get("P_REPLN_REC")
    if not isinstance(rec, dict):
        return _error(m, "CSD_API_INV_REPLN_REC: P_REPLN_REC (the repair order record) is required.")
    serial = str(rec.get("SERIAL_NUMBER") or "").strip()
    if not serial:
        return _error(m, "CSD_API_SERIAL_NUM_MISSING: SERIAL_NUMBER is required for a serialized item.")
    rtype = rec.get("REPAIR_TYPE") or "Refurbishment"
    if rtype not in REPAIR_TYPES:
        return _error(m, f"CSD_API_INV_REP_TYPE: Repair type {rtype} is not valid. Valid: {', '.join(REPAIR_TYPES)}.")
    qty = rec.get("QUANTITY", 1)
    try:
        qty = int(qty)
        if qty < 1:
            raise ValueError(qty)
    except (TypeError, ValueError):
        return _error(m, "CSD_API_INV_QUANTITY: QUANTITY must be a positive whole number.")
    cost = rec.get("ATTRIBUTE2")
    if cost not in (None, ""):
        try:
            cost = round(float(cost), 2)
            if cost < 0:
                raise ValueError(cost)
        except (TypeError, ValueError):
            return _error(m, "CSD_API_INV_DFF: ATTRIBUTE2 (estimate amount) must be a non-negative number.")
    else:
        cost = None
    grade = rec.get("ATTRIBUTE3") or None
    if grade is not None and grade not in GRADES:
        return _error(m, "CSD_API_INV_DFF: ATTRIBUTE3 (predicted grade) must be A, B, C or D.")
    promise = rec.get("PROMISE_DATE")
    if promise:
        try:
            promise = datetime.fromisoformat(str(promise).replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return _error(m, f"CSD_API_INV_PROMISE_DATE: {promise} is not a valid date.")
    rn = params.get("P_REPAIR_NUMBER") or None
    if rn and conn.execute(select(t.CSD_REPAIRS.c.repair_line_id).where(t.CSD_REPAIRS.c.repair_number == rn)).first():
        return _error(m, f"CSD_API_RO_NUM_EXISTS: Repair number {rn} already exists.")
    busy = conn.execute(
        select(t.CSD_REPAIRS.c.repair_number).where(
            t.CSD_REPAIRS.c.serial_number == serial, t.CSD_REPAIRS.c.doc["FLOW_STATUS_CODE"].astext == "IN_PROGRESS"
        )
    ).first()
    if busy:
        return _error(m, f"CSD_RO_SERIAL_IN_REPAIR: Serial number {serial} is in repair on {busy.repair_number}.")

    now = clock.now(conn)
    n = conn.execute(select(func.count()).select_from(t.CSD_REPAIRS).where(t.CSD_REPAIRS.c.repair_line_id >= 400000)).scalar_one()
    line_id = 400001 + n
    rn = rn or f"RO-{70001 + n}"
    prior = conn.execute(
        select(t.CSD_REPAIRS.c.doc).where(t.CSD_REPAIRS.c.serial_number == serial).order_by(t.CSD_REPAIRS.c.repair_line_id.desc())
    ).first()
    prior = prior.doc if prior else {}
    cls = (prior.get("ITEM_CATEGORY") or "").lower() or None
    labour = dict(prior.get("LABOUR") or {})
    if not labour:
        rate, std, role = LABOUR.get(cls or "", (520, 4, "Bench technician"))
        labour = {"ROLE": role, "RATE": float(rate), "CURRENCY_CODE": "INR", "STANDARD_HOURS": std}
    parts = [{**p, "ISSUED": False} for p in (prior.get("PARTS") or {}).get("PARTS_ITEM", [])]
    doc = {
        "REPAIR_LINE_ID": line_id,
        "REPAIR_NUMBER": rn,
        "INCIDENT_NUMBER": rec.get("INCIDENT_NUMBER") or prior.get("INCIDENT_NUMBER"),
        "SERIAL_NUMBER": serial,
        "ITEM_DESCRIPTION": rec.get("ITEM_DESCRIPTION") or prior.get("ITEM_DESCRIPTION"),
        "ITEM_CATEGORY": prior.get("ITEM_CATEGORY"),
        "ITEM_SPEC": prior.get("ITEM_SPEC"),
        "QUANTITY": qty,
        "CUSTOMER_NAME": prior.get("CUSTOMER_NAME"),
        "RMA_NUMBER": prior.get("RMA_NUMBER"),
        "ORIGINAL_SOURCE_REFERENCE": rec.get("ORIGINAL_SOURCE_REFERENCE") or prior.get("ORIGINAL_SOURCE_REFERENCE"),
        "PROBLEM_DESCRIPTION": rec.get("PROBLEM_DESCRIPTION"),
        "REPAIR_TYPE": rtype,
        "REPAIR_MODE": "WIP",
        "REPAIR_ORG": "RC01",
        "REPAIR_ORG_LOCATION": "RC-HSR-01",
        "CURRENT_LOCATION": prior.get("CURRENT_LOCATION") or "RC01",
        "STATUS": "O",
        "STATUS_MEANING": STATUS["O"],
        "FLOW_STATUS_CODE": "OPEN",
        "FLOW_STATUS": FLOW["OPEN"],
        "RECEIVED_DATE": prior.get("RECEIVED_DATE"),
        "PROMISE_DATE": promise or (now + timedelta(days=7)).date().isoformat(),
        "DATE_CLOSED": None,
        "RECEIVING_INSPECTION": prior.get("RECEIVING_INSPECTION"),
        "TEARDOWN_FINDINGS": prior.get("TEARDOWN_FINDINGS") or {"TEARDOWN_FINDINGS_ITEM": []},
        "SCOPE": rec.get("ATTRIBUTE1") or None,
        "REPAIR_COST": cost,
        "CURRENCY_CODE": rec.get("CURRENCY_CODE") or "USD",
        "ESTIMATE_ROUTE": prior.get("ESTIMATE_ROUTE"),
        "RESULT_STATE": grade,
        "PARTS": {"PARTS_ITEM": parts},
        "LABOUR": labour,
        "RELEASE_TO_SERVICE": {"STATUS": "NOT_RELEASED", "RELEASED_AT": None, "CERTIFICATE": None},
        "ATTRIBUTE_CATEGORY": rec.get("ATTRIBUTE_CATEGORY"),
    }
    conn.execute(
        insert(t.CSD_REPAIRS).values(
            repair_line_id=line_id, repair_number=rn, serial_number=serial, doc=doc, creation_date=now, last_update_date=now
        )
    )
    std = float(labour["STANDARD_HOURS"])
    plan = [(f"Repair labour · {labour['ROLE']}", "Labour", labour["ROLE"], std, labour["RATE"])]
    plan += [(f"Machine · {name}", "Machine", name, h, r) for name, h, r in OPS.get(cls or "", [])]
    for i, (name, kind, resource, hours, rate) in enumerate(plan, 1):
        conn.execute(
            insert(t.CSD_TASKS).values(
                repair_line_id=line_id,
                operation_seq_num=i * 10,
                doc=task_doc(rn, serial, i * 10, name, kind, resource, hours, rate, "PLANNED", None),
                last_update_date=now,
            )
        )
    data = {
        "REPAIR_NUMBER": rn,
        "REPAIR_LINE_ID": line_id,
        "SERIAL_NUMBER": serial,
        "FLOW_STATUS_CODE": "OPEN",
        "SCOPE": doc["SCOPE"],
        "ORIGINAL_SOURCE_REFERENCE": doc["ORIGINAL_SOURCE_REFERENCE"],
    }
    events.emit(conn, SOURCE, "oracle.apps.csd.repair.create", rn, data | {"REPAIR_COST": cost}, now)
    start = now + timedelta(hours=1)
    done = start + timedelta(hours=sum(p[3] for p in plan))
    scheduler.schedule(conn, start, "csd.repair.start", {"repair_line_id": line_id}, SOURCE)
    scheduler.schedule(conn, done, "csd.repair.complete", {"repair_line_id": line_id}, SOURCE)
    scheduler.schedule(conn, done + timedelta(hours=2), "csd.repair.close", {"repair_line_id": line_id}, SOURCE)
    return output(PRODUCT, PUB, m, {"X_REPAIR_LINE_ID": str(line_id), "X_REPAIR_NUMBER": rn})


SERVICES = {
    QUERY: {
        "get_repair_orders": ("GET", get_repair_orders),
        "get_repair_tasks": ("GET", get_repair_tasks),
        "get_test_results": ("GET", get_test_results),
    },
    PUB: {"create_repair_order": ("POST", create_repair_order)},
}


async def _call(alias: str, method: str, request: Request):
    try:
        GW.user(request)
        fn = dispatch(GW, request, alias, method, SERVICES)
        if request.method == "GET":
            with engine.connect() as conn:
                return fn(request, conn)
        params = await input_parameters(request, method, alias)
        with engine.begin() as conn:
            return fn(params, conn)
    except IsgFault as e:
        if not e.service:
            e.service, e.operation = alias, method
        return e.response


@router.api_route(GW.rest + "/{alias}/{method}/", methods=["GET", "POST", "PUT", "DELETE"])
async def call(alias: str, method: str, request: Request):
    return await _call(alias, method, request)


@router.api_route(GW.rest + "/{alias}/{method}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def call_no_slash(alias: str, method: str, request: Request):
    return await _call(alias, method, request)


# ------------------------------------------------------------------ scheduled: the repair order's progress
def _load(conn: Connection, line_id: int):
    return conn.execute(select(t.CSD_REPAIRS).where(t.CSD_REPAIRS.c.repair_line_id == line_id).with_for_update()).first()


def _move(conn: Connection, ro, flow: str, now: datetime, **changes) -> None:
    old = ro.doc["FLOW_STATUS_CODE"]
    doc = {**ro.doc, "FLOW_STATUS_CODE": flow, "FLOW_STATUS": FLOW[flow], **changes}
    conn.execute(
        update(t.CSD_REPAIRS).where(t.CSD_REPAIRS.c.repair_line_id == ro.repair_line_id).values(doc=doc, last_update_date=now)
    )
    events.emit(
        conn,
        SOURCE,
        "oracle.apps.csd.repair.status.update",
        ro.repair_number,
        _refs(ro) | {"FROM_FLOW_STATUS": old, "TO_FLOW_STATUS": flow},
        now,
    )


def _refs(ro) -> dict:
    """The references a caller matches an event by: its repair number (P_REPAIR_NUMBER) and source reference."""
    return {
        "REPAIR_NUMBER": ro.repair_number,
        "REPAIR_LINE_ID": ro.repair_line_id,
        "SERIAL_NUMBER": ro.serial_number,
        "ORIGINAL_SOURCE_REFERENCE": ro.doc.get("ORIGINAL_SOURCE_REFERENCE"),
    }


def _tasks(conn: Connection, line_id: int, status: str, now: datetime) -> None:
    for task in conn.execute(select(t.CSD_TASKS).where(t.CSD_TASKS.c.repair_line_id == line_id)).all():
        if task.doc["STATUS"] == "COMPLETE":
            continue
        doc = {**task.doc, "STATUS": status}
        if status == "COMPLETE":
            doc |= {"ACTUAL_HOURS": doc["PLANNED_HOURS"], "COMPLETED_DATE": ebs_ts(now)}
        conn.execute(update(t.CSD_TASKS).where(t.CSD_TASKS.c.task_id == task.task_id).values(doc=doc, last_update_date=now))


@scheduler.handler("csd.repair.start")
def _start(conn: Connection, payload: dict) -> None:
    ro = _load(conn, payload["repair_line_id"])
    if ro is None or ro.doc["FLOW_STATUS_CODE"] != "OPEN":
        return
    now = clock.now(conn)
    _tasks(conn, ro.repair_line_id, "IN_PROGRESS", now)
    parts = [{**p, "ISSUED": True} for p in ro.doc["PARTS"]["PARTS_ITEM"]]  # material issued to the WIP job
    _move(conn, ro, "IN_PROGRESS", now, PARTS={"PARTS_ITEM": parts})


@scheduler.handler("csd.repair.complete")
def _complete(conn: Connection, payload: dict) -> None:
    ro = _load(conn, payload["repair_line_id"])
    if ro is None or ro.doc["FLOW_STATUS_CODE"] != "IN_PROGRESS":
        return
    now = clock.now(conn)
    _tasks(conn, ro.repair_line_id, "COMPLETE", now)
    grade = ro.doc.get("RESULT_STATE") or "B"
    cls = (ro.doc.get("ITEM_CATEGORY") or "").lower()
    tests = BENCH_TESTS.get(cls) or [
        ("Functional test", "pass/fail", "= PASS", dict.fromkeys(("A", "B", "C"), "PASS") | {"D": "FAIL"})
    ]
    for j, (name, unit, limit, by_grade) in enumerate(tests, 1):
        conn.execute(
            insert(t.QA_RESULTS).values(
                repair_line_id=ro.repair_line_id,
                doc=test_doc(
                    f"TR-{ro.repair_number[3:]}-F{j}",
                    ro.repair_number,
                    ro.serial_number,
                    "Final bench test",
                    name,
                    unit,
                    limit,
                    by_grade[grade],
                    "PASS" if grade != "D" else "FAIL",
                    now,
                    "RC-HSR-01 bench 2",
                ),
                last_update_date=now,
            )
        )
    passed = grade != "D"
    release = {
        "STATUS": "RELEASED" if passed else "NOT_RELEASED",
        "RELEASED_AT": ebs_ts(now) if passed else None,
        "CERTIFICATE": f"RTS-{ro.repair_number}" if passed else None,
    }
    _move(conn, ro, "REPAIR_COMPLETE", now, RESULT_STATE=grade, RELEASE_TO_SERVICE=release)
    events.emit(
        conn,
        SOURCE,
        "oracle.apps.csd.repair.complete",
        ro.repair_number,
        _refs(ro) | {"RESULT_STATE": grade, "RELEASE_TO_SERVICE": release},
        now,
    )


@scheduler.handler("csd.repair.close")
def _close(conn: Connection, payload: dict) -> None:
    ro = _load(conn, payload["repair_line_id"])
    if ro is None or ro.doc["FLOW_STATUS_CODE"] != "REPAIR_COMPLETE":
        return
    now = clock.now(conn)
    _move(conn, ro, "CLOSED", now, STATUS="C", STATUS_MEANING=STATUS["C"], DATE_CLOSED=ebs_ts(now))
