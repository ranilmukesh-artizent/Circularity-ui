"""The spares planning mock's routes: five reads and one idempotent write (see the package docstring)."""

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, text, update

from sim.core.db import engine
from sim.vendors.spares_planning.models import RECORD, REQUISITION, WRITTEN

router = APIRouter(prefix="/spares-planning/api")
API_KEY = "tn_spares-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorized(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


def _records(request: Request, kind: str):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        return list(conn.execute(select(RECORD.c.doc).where(RECORD.c.kind == kind).order_by(RECORD.c.ord)).scalars())


@router.get("/catalogue")
def catalogue(request: Request):
    return _records(request, "catalogue")


@router.get("/targets")
def targets(request: Request):
    return _records(request, "targets")


@router.get("/forecast6m")
def forecast6m(request: Request):
    return _records(request, "forecast6m")


@router.get("/stock")
def stock(request: Request):
    return _records(request, "stock")


@router.get("/requisitions")
def requisitions(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        docs = conn.execute(select(REQUISITION.c.doc).order_by(REQUISITION.c.req_id)).scalars()
        return [d for d in docs if d["status"] == "open"]


@router.post("/requisitions/{req_id}/reduce")
async def reduce(req_id: str, request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        body: Any = json.loads(await request.body())
    except ValueError:
        return error(400, "bad_request", "The request body is not valid JSON.")
    qty, reason = (body.get("qty"), body.get("reason")) if isinstance(body, dict) else (None, None)
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
        return error(422, "invalid", "qty must be a whole number, 1 or more.")
    if not isinstance(reason, str) or not reason.strip():
        return error(422, "invalid", "reason is required.")
    key = request.headers.get("idempotency-key") or f"{req_id}:{qty}"
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "spares_planning:reduce"})
        first = conn.execute(select(WRITTEN.c.doc).where(WRITTEN.c.req_id == req_id, WRITTEN.c.idem_key == key)).scalar()
        if first is not None:
            return JSONResponse(first, status_code=200)  # a repeat: the first answer, nothing more cut
        doc = conn.execute(select(REQUISITION.c.doc).where(REQUISITION.c.req_id == req_id)).scalar()
        if doc is None:
            return error(404, "not_found", "No such requisition.")
        if doc["status"] != "open":
            return error(409, "not_open", "The requisition is closed.")
        if qty > doc["quantity"]:
            return error(422, "invalid", f"qty is more than the open quantity ({doc['quantity']}).")
        left = doc["quantity"] - qty
        out = doc | {"quantity": left, "status": "open" if left else "cancelled", "reducedBy": qty, "reason": reason}
        conn.execute(update(REQUISITION).where(REQUISITION.c.req_id == req_id).values(doc=out))
        conn.execute(insert(WRITTEN).values(req_id=req_id, idem_key=key, doc=out))
    return JSONResponse(out, status_code=200)
