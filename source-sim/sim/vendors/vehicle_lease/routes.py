"""The vehicle lease mock's routes: two reads and the idempotent charge write (see the package docstring for the contract)."""

import json
from datetime import UTC, datetime
from numbers import Number
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select, text

from sim.core.db import engine
from sim.vendors.vehicle_lease.models import LEASE_RETURN, WRITTEN
from sim.vendors.vehicle_lease.seed import AS_OF

router = APIRouter(prefix="/vehicle-lease/api/v1")
API_KEY = "uc_lease-demo-key"  # demo credential, not a secret
MAX_LIMIT = 200
CHARGE_KINDS = ("excess_mileage", "excess_wear")


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


@router.get("/lease-returns")
def lease_returns(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        limit, offset, since = _whole(request, "limit", 25, 1, MAX_LIMIT), _whole(request, "offset", 0, 0), _since(request)
    except ValueError as e:
        return error(400, "bad_request", str(e))
    where = [] if since is None else [LEASE_RETURN.c.updated_at > since]
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(LEASE_RETURN).where(*where)).scalar_one()
        docs = conn.execute(
            select(LEASE_RETURN.c.doc).where(*where).order_by(LEASE_RETURN.c.lease_id).offset(offset).limit(limit)
        ).scalars()
        items = list(docs)
    return {"items": items, "next": offset + limit if offset + limit < total else None, "total": total}


@router.get("/lease-returns/{lease_id}")
def lease_return(lease_id: str, request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        doc = conn.execute(select(LEASE_RETURN.c.doc).where(LEASE_RETURN.c.lease_id == lease_id)).scalar()
    return doc if doc is not None else error(404, "not_found", f"No lease return {lease_id}.")


@router.post("/charges")
async def charges(request: Request):
    """A charge to the lessee (excess mileage or excess wear) on a lease return. Idempotent: the `Idempotency-Key` header's, else
    the lease and kind, answers 200 with the first charge instead of a second one."""
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        body: Any = json.loads(await request.body())
    except ValueError:
        return error(400, "bad_request", "The request body is not valid JSON.")
    if not isinstance(body, dict):
        return error(422, "invalid", "The request body must be a JSON object.")
    amount = body.get("amount")
    if not isinstance(body.get("leaseId"), str) or body.get("kind") not in CHARGE_KINDS:
        return error(422, "invalid", f"leaseId and kind ({' or '.join(CHARGE_KINDS)}) are required.")
    if not isinstance(amount, Number) or isinstance(amount, bool) or amount <= 0:
        return error(422, "invalid", "amount must be a number above zero.")
    key = request.headers.get("idempotency-key") or f"{body['leaseId']}:{body['kind']}"
    with engine.begin() as conn:
        if conn.execute(select(LEASE_RETURN.c.lease_id).where(LEASE_RETURN.c.lease_id == body["leaseId"])).scalar() is None:
            return error(404, "not_found", f"No lease return {body['leaseId']}.")
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vehicle_lease:charges'))"))
        first = conn.execute(select(WRITTEN.c.doc).where(WRITTEN.c.kind == "charges", WRITTEN.c.idem_key == key)).scalar()
        if first is not None:
            return JSONResponse(first, status_code=200)  # a repeat: the first charge, nothing new
        seq = conn.execute(select(func.coalesce(func.max(WRITTEN.c.seq), 0) + 1).where(WRITTEN.c.kind == "charges")).scalar_one()
        doc = {"chargeId": f"CH-{seq:04d}", "leaseId": body["leaseId"], "kind": body["kind"], "amount": amount,
               "status": "accepted", "createdAt": AS_OF.isoformat()}  # fmt: skip
        conn.execute(insert(WRITTEN).values(kind="charges", seq=seq, idem_key=key, doc=doc))
    return JSONResponse(doc, status_code=201)
