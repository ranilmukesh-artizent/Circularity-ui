"""The network inventory mock's routes: one list, two idempotent writes, and the scheduled arrival of one element (see
the package docstring for the contract)."""

import json
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import Connection

from sim.core import clock, events, scheduler
from sim.core.db import engine
from sim.vendors.network_inventory import seed
from sim.vendors.network_inventory.models import ELEMENT, RETIREMENT, TRANSFER_ORDER

router = APIRouter(prefix="/network-inventory/api")
API_KEY = "tn_inv-demo-key"  # demo credential, not a secret
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


@scheduler.handler(seed.HANDLER)
def _create_element(conn: Connection, payload: dict) -> None:
    """The element that joins the inventory later: inserted once, with one `inventory.element.created` event."""
    doc = seed.late_element()
    present = conn.execute(select(ELEMENT.c.serial).where(ELEMENT.c.serial == doc["serial"])).first()
    if doc["serial"] != payload["serial"] or present is not None:
        return
    seed.insert_element(conn, doc)
    events.emit(conn, seed.SOURCE, "inventory.element.created", doc["serial"], {"serial": doc["serial"], "site": doc["site"]})


@router.get("/elements")
def elements(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        limit, offset = _whole(request, "limit", 50, 1, MAX_LIMIT), _whole(request, "offset", 0, 0)
    except ValueError as e:
        return error(400, "bad_request", str(e))
    where = [ELEMENT.c.serial == v for v in [request.query_params.get("serial")] if v]
    where += [ELEMENT.c.site == v for v in [request.query_params.get("site")] if v]
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(ELEMENT).where(*where)).scalar_one()
        docs = conn.execute(select(ELEMENT.c.doc).where(*where).order_by(ELEMENT.c.serial).offset(offset).limit(limit)).scalars()
        rows = list(docs)
    return {"elements": rows, "next": offset + limit if offset + limit < total else None}


async def _body(request: Request) -> dict[str, Any] | JSONResponse:
    try:
        body: Any = json.loads(await request.body())
    except ValueError:
        return error(400, "bad_request", "The request body is not valid JSON.")
    if not isinstance(body, dict):
        return error(422, "invalid", "The request body must be a JSON object.")
    return body


def _text(body: dict, name: str) -> str | None:
    v = body.get(name)
    return v.strip() if isinstance(v, str) and v.strip() else None


def _known(conn: Connection, serial: str) -> bool:
    return conn.execute(select(ELEMENT.c.serial).where(ELEMENT.c.serial == serial)).first() is not None


@router.post("/transfer-orders")
async def transfer_orders(request: Request):
    """Idempotent on the serial and the destination: a repeat gets the first order back (200), a new one is 201."""
    if (denied := _unauthorized(request)) is not None:
        return denied
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body
    serial, site, pool = _text(body, "serial"), _text(body, "toSite"), _text(body, "toPool")
    if serial is None or (site is None) == (pool is None):
        return error(422, "invalid", "serial and exactly one of toSite or toPool are required.")
    destination = f"site:{site}" if site else f"pool:{pool}"
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('network_inventory:transfer'))"))
        if not _known(conn, serial):
            return error(404, "not_found", f"No network element {serial}.")
        first = conn.execute(
            select(TRANSFER_ORDER.c.doc).where(TRANSFER_ORDER.c.serial == serial, TRANSFER_ORDER.c.destination == destination)
        ).scalar()
        if first is not None:
            return JSONResponse(first, status_code=200)
        seq = conn.execute(select(func.coalesce(func.max(TRANSFER_ORDER.c.seq), 0) + 1)).scalar_one()
        doc = {
            "orderId": f"TO-{seq:04d}", "serial": serial, "toSite": site, "toPool": pool, "status": "created",
            "createdAt": clock.now(conn).astimezone(UTC).isoformat(),
        }  # fmt: skip
        conn.execute(insert(TRANSFER_ORDER).values(seq=seq, serial=serial, destination=destination, doc=doc))
    return JSONResponse(doc, status_code=201)


@router.post("/retirements")
async def retirements(request: Request):
    """Idempotent on the serial. The element's own record is not changed: the retirement is a ledger entry."""
    if (denied := _unauthorized(request)) is not None:
        return denied
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body
    serial = _text(body, "serial")
    if serial is None:
        return error(422, "invalid", "serial is required.")
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('network_inventory:retirement'))"))
        if not _known(conn, serial):
            return error(404, "not_found", f"No network element {serial}.")
        first = conn.execute(select(RETIREMENT.c.doc).where(RETIREMENT.c.serial == serial)).scalar()
        if first is not None:
            return JSONResponse(first, status_code=200)
        seq = conn.execute(select(func.coalesce(func.max(RETIREMENT.c.seq), 0) + 1)).scalar_one()
        now = clock.now(conn)
        stamp = now.astimezone(UTC).isoformat()
        doc = {"retirementId": f"RT-{seq:04d}", "serial": serial, "status": "retired", "createdAt": stamp}
        conn.execute(insert(RETIREMENT).values(seq=seq, serial=serial, doc=doc, created_at=now))
    return JSONResponse(doc, status_code=201)
