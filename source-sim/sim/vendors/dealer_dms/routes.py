"""The dealer mock's routes: the reads and the four idempotent writes (see the package docstring for the contract)."""

import json
from numbers import Number
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select, text

from sim.core.db import engine
from sim.vendors.dealer_dms.models import RECORD, WRITTEN
from sim.vendors.dealer_dms.seed import AS_OF, LOTS

router = APIRouter(prefix="/dealer-dms/api/v1")
API_KEY = "uc_dms-demo-key"  # demo credential, not a secret
MAX_LIMIT = 200
FILTERS = {  # route -> (query parameter -> RECORD column)
    "trade-ins": {"vin": "vin", "segment": "segment"},
    "lots": {},
    "lot-sales": {"segment": "segment", "lotId": "lot_id", "mileageBand": "mileage_band"},
    "partner-bids": {"vin": "vin"},
    "stock": {"vin": "vin", "lotId": "lot_id", "segment": "segment"},
}
LOT_IDS = {lot for lot, _n, _m in LOTS}
ID_PREFIX = {"recon-orders": ("orderId", "RO-D"), "transfers": ("transferId", "TR"), "listings": ("listingId", "LST"),
             "dealer-trades": ("dealerTradeId", "DT")}  # fmt: skip


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
        total = conn.execute(select(func.count()).select_from(RECORD).where(*where)).scalar_one()
        docs = conn.execute(select(RECORD.c.doc).where(*where).order_by(RECORD.c.ord).offset(offset).limit(limit)).scalars()
        items = list(docs)
    return {"items": items, "next": offset + limit if offset + limit < total else None, "total": total}


@router.get("/trade-ins")
def trade_ins(request: Request):
    return _read("trade-ins", request)


@router.get("/lots")
def lots(request: Request):
    return _read("lots", request)


@router.get("/lot-sales")
def lot_sales(request: Request):
    return _read("lot-sales", request)


@router.get("/partner-bids")
def partner_bids(request: Request):
    return _read("partner-bids", request)


@router.get("/stock")
def stock(request: Request):
    return _read("stock", request)


# ------------------------------------------------------------------ writes
def _text(body: dict, name: str) -> str | None:
    v = body.get(name)
    return v if isinstance(v, str) and v.strip() else None


def _amount(body: dict, name: str, positive: bool = False) -> bool:
    v = body.get(name)
    return isinstance(v, Number) and not isinstance(v, bool) and (v > 0 if positive else v >= 0)


def _problem(kind: str, b: dict) -> str | None:
    """Why the body is not a valid `kind` request, or None."""
    if _text(b, "vin") is None:
        return "vin is required."
    if kind == "recon-orders":
        ok = _amount(b, "estimate") and isinstance(b.get("lines"), list)
        return None if ok else "estimate (a number) and lines (a list) are required."
    if kind == "transfers":
        if _text(b, "fromLot") is None or _text(b, "toLot") is None:
            return "fromLot and toLot are required."
        if b["fromLot"] not in LOT_IDS or b["toLot"] not in LOT_IDS:
            return "fromLot and toLot must be lots of this dealer group."
        return "fromLot and toLot must differ." if b["fromLot"] == b["toLot"] else None
    if kind == "listings":
        if _text(b, "lotId") not in LOT_IDS:
            return "lotId must be a lot of this dealer group."
        ok = _amount(b, "price", True) and isinstance(b.get("disclosures"), list)
        return None if ok else "price (a number) and disclosures (a list) are required."
    if _text(b, "partner") is None or _text(b, "titleRef") is None or not _amount(b, "price", True):
        return "partner, price (a number) and titleRef are required."
    return None


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
    key = request.headers.get("idempotency-key") or None
    id_field, prefix = ID_PREFIX[kind]
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"dealer_dms:{kind}"})
        if key is not None:
            first = conn.execute(select(WRITTEN.c.doc).where(WRITTEN.c.kind == kind, WRITTEN.c.idem_key == key)).scalar()
            if first is not None:
                return JSONResponse(first, status_code=200)  # a repeat: the first document, nothing new
        seq = conn.execute(select(func.coalesce(func.max(WRITTEN.c.seq), 0) + 1).where(WRITTEN.c.kind == kind)).scalar_one()
        doc = {id_field: f"{prefix}-{seq:04d}", **body, "status": "accepted", "createdAt": AS_OF.isoformat()}
        conn.execute(insert(WRITTEN).values(kind=kind, seq=seq, idem_key=key, doc=doc))
    return JSONResponse(doc, status_code=201)


@router.post("/recon-orders")
async def recon_orders(request: Request):
    return await _write("recon-orders", request)


@router.post("/transfers")
async def transfers(request: Request):
    return await _write("transfers", request)


@router.post("/listings")
async def listings(request: Request):
    return await _write("listings", request)


@router.post("/dealer-trades")
async def dealer_trades(request: Request):
    return await _write("dealer-trades", request)
