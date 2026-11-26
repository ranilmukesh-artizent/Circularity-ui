"""The broker marketplace mock's routes: two reads and one idempotent write (see the package docstring)."""

import json
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select, text

from sim.core import clock
from sim.core.db import engine
from sim.vendors.broker_marketplace.models import BID, CLEARED, LISTING

router = APIRouter(prefix="/broker-market/api")
API_KEY = "tn_broker-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorized(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


@router.get("/bids")
def bids(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    where = [BID.c.model == m for m in [request.query_params.get("model")] if m]
    with engine.connect() as conn:
        docs = list(conn.execute(select(BID.c.doc).where(*where)).scalars())
    return sorted(docs, key=lambda d: (-d["unitPrice"], d["bidId"]))


@router.get("/cleared")
def cleared(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    where = [CLEARED.c.model == m for m in [request.query_params.get("model")] if m]
    with engine.connect() as conn:
        docs = list(conn.execute(select(CLEARED.c.doc).where(*where)).scalars())
    return sorted(docs, key=lambda d: (d["soldAt"], d["saleId"]), reverse=True)


@router.post("/listings")
async def listings(request: Request):
    """Idempotent on the bid and the set of serials: a repeat gets the first listing back (200), a new one is 201."""
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        body: Any = json.loads(await request.body())
    except ValueError:
        return error(400, "bad_request", "The request body is not valid JSON.")
    if not isinstance(body, dict):
        return error(422, "invalid", "The request body must be a JSON object.")
    serials, price, bid_id = body.get("serials"), body.get("unitPrice"), body.get("bidId")
    valid = (
        isinstance(serials, list) and serials and all(isinstance(s, str) and s.strip() for s in serials)
        and isinstance(price, int | float) and not isinstance(price, bool) and price > 0
        and isinstance(bid_id, str) and bid_id.strip()
    )  # fmt: skip
    if not valid:
        return error(422, "invalid", "serials (a non-empty list), unitPrice (above 0) and bidId are required.")
    ordered = sorted(set(serials))
    idem = f"{bid_id}|{','.join(ordered)}"
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('broker_marketplace:listing'))"))
        if conn.execute(select(BID.c.bid_id).where(BID.c.bid_id == bid_id)).first() is None:
            return error(404, "not_found", f"No bid {bid_id}.")
        first = conn.execute(select(LISTING.c.doc).where(LISTING.c.idem == idem)).scalar()
        if first is not None:
            return JSONResponse(first, status_code=200)
        seq = conn.execute(select(func.coalesce(func.max(LISTING.c.seq), 0) + 1)).scalar_one()
        doc = {
            "listingId": f"LS-{seq:04d}", "bidId": bid_id, "serials": ordered, "unitPrice": price, "status": "listed",
            "createdAt": clock.now(conn).astimezone(UTC).isoformat(),
        }  # fmt: skip
        conn.execute(insert(LISTING).values(seq=seq, idem=idem, doc=doc))
    return JSONResponse(doc, status_code=201)
