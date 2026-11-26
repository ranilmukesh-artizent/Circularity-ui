"""The vehicle inspection mock's routes: the reads and the battery assessment (see the package docstring)."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.engine import Connection

from sim.core import clock, events, scheduler
from sim.core.db import engine
from sim.vendors.vehicle_inspection.models import BATTERY_ASSESSMENT, INSPECTION
from sim.vendors.vehicle_inspection.seed import FIT_FROM

SOURCE = "uc_insp"
HANDLER = "uc_insp.battery.complete"
EVENT = "inspection.battery.completed"
router = APIRouter(prefix="/vehicle-inspection/api")
API_KEY = "uc_insp-demo-key"  # demo credential, not a secret
MAX_LIMIT = 200


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorized(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


def _whole(request: Request, name: str, default: int, low: int, high: int | None = None) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    if not raw.isdigit() or int(raw) < low or (high is not None and int(raw) > high):
        span = f"{low} to {high}" if high is not None else f"{low} or more"
        raise ValueError(f"{name} must be a whole number, {span}.")
    return int(raw)


def _since(request: Request) -> datetime | None:
    raw = request.query_params.get("updatedSince")
    if raw is None:
        return None
    try:
        d = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError("updatedSince must be an ISO 8601 date or timestamp.") from e
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _list(table, order, request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        limit, offset, since = _whole(request, "limit", 25, 1, MAX_LIMIT), _whole(request, "offset", 0, 0), _since(request)
    except ValueError as e:
        return error(400, "bad_request", str(e))
    where = [] if since is None else [table.c.updated_at > since]
    if (vin := request.query_params.get("vin")) is not None:
        where.append(table.c.vin == vin)
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(table).where(*where)).scalar_one()
        docs = conn.execute(select(table.c.doc).where(*where).order_by(order).offset(offset).limit(limit)).scalars()
        data = list(docs)
    return {"data": data, "next": offset + limit if offset + limit < total else None}


@router.get("/inspections")
def inspections(request: Request):
    return _list(INSPECTION, INSPECTION.c.inspection_id, request)


@router.get("/battery-assessments")
def battery_assessments(request: Request):
    return _list(BATTERY_ASSESSMENT, BATTERY_ASSESSMENT.c.seq, request)


@router.get("/battery-assessments/{assessment_id}")
def battery_assessment(assessment_id: str, request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        doc = conn.execute(select(BATTERY_ASSESSMENT.c.doc).where(BATTERY_ASSESSMENT.c.assessment_id == assessment_id)).scalar()
    return doc if doc is not None else error(404, "not_found", f"No battery assessment {assessment_id}.")


@router.post("/battery-assessments")
async def post_battery_assessment(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        body: Any = json.loads(await request.body())
    except ValueError:
        return error(400, "bad_request", "The request body is not valid JSON.")
    vin = body.get("vin") if isinstance(body, dict) else None
    if not isinstance(vin, str) or not vin.strip():
        return error(422, "invalid", "vin is required.")
    key = request.headers.get("idempotency-key") or None
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('uc_insp:battery'))"))
        if key is not None:
            first = conn.execute(select(BATTERY_ASSESSMENT.c.doc).where(BATTERY_ASSESSMENT.c.idem_key == key)).scalar()
            if first is not None:
                return JSONResponse(first, status_code=200)  # a repeat: the first assessment, nothing new
        car = conn.execute(select(INSPECTION.c.doc).where(INSPECTION.c.vin == vin)).scalar()
        if car is None:
            return error(404, "not_found", f"No inspection for VIN {vin}.")
        if car.get("batterySoh") is None:
            return error(422, "invalid", "The car has no traction battery to assess.")
        now = clock.now(conn)
        seq = conn.execute(select(func.coalesce(func.max(BATTERY_ASSESSMENT.c.seq), 0) + 1)).scalar_one()
        doc = {
            "assessmentId": f"BA-{seq:04d}", "vin": vin, "status": "scheduled", "batterySoh": None, "result": None,
            "requestedAt": now.isoformat(), "completedAt": None, "updatedAt": now.isoformat(),
        }  # fmt: skip
        conn.execute(
            insert(BATTERY_ASSESSMENT).values(
                assessment_id=doc["assessmentId"], seq=seq, vin=vin, idem_key=key, doc=doc, updated_at=now
            )
        )
        scheduler.schedule(conn, now + timedelta(days=1), HANDLER, {"assessment_id": doc["assessmentId"]}, SOURCE)
    return JSONResponse(doc, status_code=201)


@scheduler.handler(HANDLER)
def _complete(conn: Connection, payload: dict) -> None:
    row = conn.execute(
        select(BATTERY_ASSESSMENT.c.doc).where(BATTERY_ASSESSMENT.c.assessment_id == payload["assessment_id"])
    ).scalar()
    if row is None or row["status"] != "scheduled":
        return
    car = conn.execute(select(INSPECTION.c.doc).where(INSPECTION.c.vin == row["vin"])).scalar() or {}
    soh = car.get("batterySoh")
    now = clock.now(conn)
    result = "fit_for_retail" if soh is not None and soh >= FIT_FROM else "pack_replacement_needed"
    done = {
        "status": "complete",
        "batterySoh": soh,
        "result": result,
        "completedAt": now.isoformat(),
        "updatedAt": now.isoformat(),
    }
    doc = row | done
    conn.execute(
        update(BATTERY_ASSESSMENT)
        .where(BATTERY_ASSESSMENT.c.assessment_id == doc["assessmentId"])
        .values(doc=doc, updated_at=now)
    )
    data = {"assessmentId": doc["assessmentId"], "vin": doc["vin"], "batterySoh": soh, "result": result}
    events.emit(conn, SOURCE, EVENT, doc["assessmentId"], data, now)
