"""The test bench mock's routes: reads of the results, three writes, and the scheduled end of a wipe re-run (see the package
docstring for the contract)."""

import json
from datetime import UTC, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.engine import Connection

from sim.core import clock, events, scheduler
from sim.core.db import engine
from sim.vendors.test_bench import seed
from sim.vendors.test_bench.models import REFURB_ORDER, RESULT, TEARDOWN, WIPE_JOB

router = APIRouter(prefix="/test-bench/api")
API_KEY = "tn_bench-demo-key"  # demo credential, not a secret
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


def _stamp(conn: Connection) -> str:
    return clock.now(conn).astimezone(UTC).isoformat()


@scheduler.handler(seed.HANDLER)
def _complete_wipe(conn: Connection, payload: dict) -> None:
    """The re-run ends: the unit's wipe is verified with one more attempt, once, with one `bench.wipe.completed` event."""
    job = conn.execute(select(WIPE_JOB).where(WIPE_JOB.c.seq == payload["seq"])).first()
    if job is None or job.status != "running":
        return
    doc = conn.execute(select(RESULT.c.doc).where(RESULT.c.serial == job.serial).with_for_update()).scalar_one()
    old = doc["wipe"]
    n = int(job.serial.rsplit("-", 1)[1])
    now = clock.now(conn).astimezone(UTC)
    doc["wipe"] = {
        "status": "verified", "attempts": old["attempts"] + 1, "tool": seed.TOOL, "toolVersion": seed.TOOL_VERSION,
        "scope": list(seed.SCOPE), "verifiedAt": now.isoformat(), "certificateRef": seed.certificate(n),
    }  # fmt: skip
    conn.execute(update(RESULT).where(RESULT.c.serial == job.serial).values(doc=doc))
    done = job.doc | {"status": "completed", "completedAt": now.isoformat()}
    conn.execute(update(WIPE_JOB).where(WIPE_JOB.c.seq == job.seq).values(status="completed", doc=done))
    events.emit(conn, seed.SOURCE, "bench.wipe.completed", job.serial, {"serial": job.serial, "jobId": done["jobId"]})


@router.get("/results")
def results(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    serial = request.query_params.get("serial")
    with engine.connect() as conn:
        if serial:
            doc = conn.execute(select(RESULT.c.doc).where(RESULT.c.serial == serial)).scalar()
            return doc if doc is not None else error(404, "not_found", f"No bench result for {serial}.")
        try:
            limit, offset = _whole(request, "limit", 50, 1, MAX_LIMIT), _whole(request, "offset", 0, 0)
        except ValueError as e:
            return error(400, "bad_request", str(e))
        total = conn.execute(select(func.count()).select_from(RESULT)).scalar_one()
        docs = conn.execute(select(RESULT.c.doc).order_by(RESULT.c.serial).offset(offset).limit(limit)).scalars()
        rows = list(docs)
    return {"results": rows, "next": offset + limit if offset + limit < total else None}


async def _body(request: Request) -> dict[str, Any] | JSONResponse:
    try:
        body: Any = json.loads(await request.body())
    except ValueError:
        return error(400, "bad_request", "The request body is not valid JSON.")
    if not isinstance(body, dict):
        return error(422, "invalid", "The request body must be a JSON object.")
    return body


def _serial(body: dict) -> str | None:
    v = body.get("serial")
    return v.strip() if isinstance(v, str) and v.strip() else None


def _result(conn: Connection, serial: str) -> dict | None:
    return conn.execute(select(RESULT.c.doc).where(RESULT.c.serial == serial)).scalar()


@router.post("/wipe-jobs")
async def wipe_jobs(request: Request):
    """A re-run of the wipe, completing 4 simulated hours later. Idempotent while a job for the serial runs."""
    if (denied := _unauthorized(request)) is not None:
        return denied
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body
    serial = _serial(body)
    if serial is None:
        return error(422, "invalid", "serial is required.")
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('test_bench:wipe'))"))
        if _result(conn, serial) is None:
            return error(404, "not_found", f"No bench result for {serial}.")
        running = conn.execute(select(WIPE_JOB.c.doc).where(WIPE_JOB.c.serial == serial, WIPE_JOB.c.status == "running")).scalar()
        if running is not None:
            return JSONResponse(running, status_code=200)
        seq = conn.execute(select(func.coalesce(func.max(WIPE_JOB.c.seq), 0) + 1)).scalar_one()
        now = clock.now(conn)
        due = now + timedelta(hours=seed.WIPE_HOURS)
        doc = {
            "jobId": f"WJ-{seq:04d}", "serial": serial, "status": "running", "createdAt": now.astimezone(UTC).isoformat(),
            "completesAt": due.astimezone(UTC).isoformat(),
        }  # fmt: skip
        conn.execute(insert(WIPE_JOB).values(seq=seq, serial=serial, status="running", doc=doc, created_at=now))
        scheduler.schedule(conn, due, seed.HANDLER, {"seq": seq}, seed.SOURCE)
    return JSONResponse(doc, status_code=201)


@router.post("/refurb-orders")
async def refurb_orders(request: Request):
    """Idempotent on the serial."""
    if (denied := _unauthorized(request)) is not None:
        return denied
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body
    serial = _serial(body)
    if serial is None:
        return error(422, "invalid", "serial is required.")
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('test_bench:refurb'))"))
        if _result(conn, serial) is None:
            return error(404, "not_found", f"No bench result for {serial}.")
        first = conn.execute(select(REFURB_ORDER.c.doc).where(REFURB_ORDER.c.serial == serial)).scalar()
        if first is not None:
            return JSONResponse(first, status_code=200)
        seq = conn.execute(select(func.coalesce(func.max(REFURB_ORDER.c.seq), 0) + 1)).scalar_one()
        doc = {"orderId": f"RF-{seq:04d}", "serial": serial, "status": "created", "createdAt": _stamp(conn)}
        conn.execute(insert(REFURB_ORDER).values(seq=seq, serial=serial, doc=doc))
    return JSONResponse(doc, status_code=201)


@router.post("/teardowns")
async def teardowns(request: Request):
    """Idempotent on the serial and the set of boards (their order does not matter)."""
    if (denied := _unauthorized(request)) is not None:
        return denied
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body
    serial, boards = _serial(body), body.get("boards")
    if serial is None or not isinstance(boards, list) or not boards or not all(isinstance(b, str) and b for b in boards):
        return error(422, "invalid", "serial and a non-empty list of board ids are required.")
    chosen = sorted(set(boards))
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('test_bench:teardown'))"))
        unit = _result(conn, serial)
        if unit is None:
            return error(404, "not_found", f"No bench result for {serial}.")
        unknown = [b for b in chosen if b not in {x["boardId"] for x in unit["boards"]}]
        if unknown:
            return error(422, "unknown_board", f"{serial} has no board {', '.join(unknown)}.")
        key = ",".join(chosen)
        first = conn.execute(select(TEARDOWN.c.doc).where(TEARDOWN.c.serial == serial, TEARDOWN.c.boards_key == key)).scalar()
        if first is not None:
            return JSONResponse(first, status_code=200)
        seq = conn.execute(select(func.coalesce(func.max(TEARDOWN.c.seq), 0) + 1)).scalar_one()
        doc = {"teardownId": f"TD-{seq:04d}", "serial": serial, "boards": chosen, "status": "created", "createdAt": _stamp(conn)}
        conn.execute(insert(TEARDOWN).values(seq=seq, serial=serial, boards_key=key, doc=doc))
    return JSONResponse(doc, status_code=201)
