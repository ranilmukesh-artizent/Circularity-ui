"""The auction mock's routes: the reads and the two idempotent writes (see the package docstring for the contract)."""

import json
from datetime import UTC, date, datetime, time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

from sim.core import clock, events, scheduler
from sim.core.db import engine
from sim.vendors.dealer_dms.seed import band_of, car_of
from sim.vendors.vehicle_auction.models import RECORD, WRITTEN
from sim.vendors.vehicle_auction.seed import AS_OF, FEES, result_cell

SOURCE = "uc_auction"
SOLD_HANDLER = "vehicle_auction.consignment.sold"
SOLD_EVENT = "auction.consignment.sold"
SALE_HOUR = time(12, 0, tzinfo=UTC)  # a sale closes at noon UTC on its sale date

router = APIRouter(prefix="/vehicle-auction/v1")
API_KEY = "uc_auction-demo-key"  # demo credential, not a secret
MAX_LIMIT = 200
FILTERS = {  # route -> (query parameter -> RECORD column)
    "sales": {"site": "site"},
    "results": {"segment": "segment", "band": "band"},
    "salvage-bids": {"vin": "vin"},
    "buyers": {},
    "sold": {"vin": "vin"},
}
ID_PREFIX = {"consignments": ("consignmentId", "CN"), "salvage-sales": ("salvageSaleId", "SS")}


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


def _read(kind: str, request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        limit, offset = _whole(request, "limit", 25, 1, MAX_LIMIT), _whole(request, "offset", 0, 0)
    except ValueError as e:
        return error(400, "bad_request", str(e))
    where = [RECORD.c.kind == kind] + [
        RECORD.c[col] == request.query_params[param] for param, col in FILTERS[kind].items() if param in request.query_params
    ]
    with engine.connect() as conn:
        docs = list(conn.execute(select(RECORD.c.doc).where(*where).order_by(RECORD.c.ord)).scalars())
        if kind == "sales":  # the sales still to come, by the simulated clock
            today = clock.now(conn).date()
            docs = [d | {"daysAhead": (date.fromisoformat(d["saleDate"]) - today).days} for d in docs]
            docs = [d for d in docs if d["daysAhead"] >= 0]
    total, items = len(docs), docs[offset : offset + limit]
    return {"items": items, "next": offset + limit if offset + limit < total else None, "total": total}


@router.get("/sales")
def sales(request: Request):
    return _read("sales", request)


@router.get("/fees")
def fees(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    return FEES


@router.get("/results")
def results(request: Request):
    return _read("results", request)


@router.get("/salvage-bids")
def salvage_bids(request: Request):
    return _read("salvage-bids", request)


@router.get("/buyers")
def buyers(request: Request):
    return _read("buyers", request)


@router.get("/sold")
def sold(request: Request):
    return _read("sold", request)


# ------------------------------------------------------------------ writes
def _text(body: dict, name: str) -> str | None:
    v = body.get(name)
    return v if isinstance(v, str) and v.strip() else None


def _is_date(v: Any) -> bool:
    try:
        return isinstance(v, str) and bool(date.fromisoformat(v))
    except ValueError:
        return False


def _problem(kind: str, b: dict) -> str | None:
    """Why the body is not a valid `kind` request, or None."""
    if _text(b, "vin") is None:
        return "vin is required."
    if kind == "consignments":
        if not _is_date(b.get("saleDate")):
            return "saleDate (an ISO 8601 date) is required."
        if _text(b, "titleRef") is None or not isinstance(b.get("disclosures"), list):
            return "titleRef and disclosures (a list) are required."
        return None
    return None if _text(b, "buyerId") else "buyerId is required."


def _natural_key(kind: str, b: dict) -> str:
    return f"{b['vin']}:{b['saleDate']}" if kind == "consignments" else f"{b['vin']}:{b['buyerId']}"


async def _write(kind: str, request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        body: Any = json.loads(await request.body())
    except ValueError:
        return error(400, "bad_request", "The request body is not valid JSON.")
    if not isinstance(body, dict):
        return error(422, "invalid", "The request body must be a JSON object.")
    if (why := _problem(kind, body)) is not None:
        return error(422, "invalid", why)
    id_field, prefix = ID_PREFIX[kind]
    key = request.headers.get("idempotency-key") or _natural_key(kind, body)
    with engine.begin() as conn:
        if kind == "salvage-sales":
            buyer = conn.execute(
                select(RECORD.c.doc).where(RECORD.c.kind == "buyers", RECORD.c.rec_id == body["buyerId"])
            ).scalar()
            if buyer is None:
                return error(422, "invalid", "buyerId is not a buyer of this platform.")
            if not buyer["salvage"]:
                return error(422, "buyer_not_salvage", "The buyer does not buy salvage vehicles.")
            if not buyer["titleDbReporting"]:
                return error(422, "buyer_not_reporting", "The buyer does not report to the national title database.")
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"vehicle_auction:{kind}"})
        first = conn.execute(select(WRITTEN.c.doc).where(WRITTEN.c.kind == kind, WRITTEN.c.idem_key == key)).scalar()
        if first is not None:
            return JSONResponse(first, status_code=200)  # a repeat: the first document, nothing new
        seq = conn.execute(select(func.coalesce(func.max(WRITTEN.c.seq), 0) + 1).where(WRITTEN.c.kind == kind)).scalar_one()
        doc = {id_field: f"{prefix}-{seq:04d}", **body, "status": "accepted", "createdAt": AS_OF.isoformat()}
        conn.execute(insert(WRITTEN).values(kind=kind, seq=seq, idem_key=key, doc=doc))
        if kind == "consignments":
            _schedule_sale(conn, doc)
    return JSONResponse(doc, status_code=201)


def _schedule_sale(conn: Connection, doc: dict) -> None:
    """A consignment sells on its sale date at the cleared price of its segment and mileage band (P9-9.20). A car the group does
    not know never sells."""
    car = car_of(doc["vin"])
    if car is None:
        return
    due = datetime.combine(date.fromisoformat(doc["saleDate"]), SALE_HOUR)
    payload = {"consignmentId": doc["consignmentId"], "vin": doc["vin"], "consignedAt": clock.now(conn).isoformat(),
               "price": result_cell(car[0], band_of(car[1]))["avgClearedPrice"]}  # fmt: skip
    scheduler.schedule(conn, due, SOLD_HANDLER, payload, SOURCE)


@scheduler.handler(SOLD_HANDLER)
def consignment_sold(conn: Connection, payload: dict) -> None:
    """The consignment sells: list the sale and tell subscribers (`auction.consignment.sold {vin, price, soldAt}`)."""
    at = clock.now(conn)
    days = max(0, (at.date() - datetime.fromisoformat(payload["consignedAt"]).date()).days)
    doc = {"consignmentId": payload["consignmentId"], "vin": payload["vin"], "price": payload["price"],
           "consignedAt": payload["consignedAt"], "soldAt": at.isoformat(), "daysToSale": days}  # fmt: skip
    n = conn.execute(select(func.count()).select_from(RECORD).where(RECORD.c.kind == "sold")).scalar_one()
    row = {"kind": "sold", "rec_id": doc["consignmentId"], "ord": n, "vin": doc["vin"], "doc": doc}
    if conn.execute(pg_insert(RECORD).values(**row).on_conflict_do_nothing()).rowcount:  # a replay sells nothing twice
        events.emit(conn, SOURCE, SOLD_EVENT, doc["consignmentId"], {k: doc[k] for k in ("vin", "price", "soldAt")}, at)


@router.post("/consignments")
async def consignments(request: Request):
    return await _write("consignments", request)


@router.post("/salvage-sales")
async def salvage_sales(request: Request):
    return await _write("salvage-sales", request)
