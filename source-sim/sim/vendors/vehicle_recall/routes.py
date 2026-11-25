"""The vehicle recall mock's routes: a per-VIN lookup and a bulk list (see the package docstring for the contract)."""

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from sim.core import clock
from sim.core.db import engine
from sim.vendors.vehicle_recall.models import RECALL

router = APIRouter(prefix="/vehicle-recall/api")
API_KEY = "uc_recall-demo-key"  # demo credential, not a secret
MAX_LIMIT = 200
VIN = re.compile(r"^[A-Za-z0-9]{17}$")


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


@router.get("/recalls")
def recalls(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        limit, offset, since = _whole(request, "limit", 25, 1, MAX_LIMIT), _whole(request, "offset", 0, 0), _since(request)
    except ValueError as e:
        return error(400, "bad_request", str(e))
    where = [] if since is None else [RECALL.c.updated_at > since]
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(RECALL).where(*where)).scalar_one()
        docs = conn.execute(
            select(RECALL.c.doc).where(*where).order_by(RECALL.c.updated_at, RECALL.c.campaign_id).offset(offset).limit(limit)
        ).scalars()
        items = list(docs)
    return {"items": items, "next": offset + limit if offset + limit < total else None, "total": total}


@router.get("/recalls/vin/{vin}")
def recalls_by_vin(vin: str, request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    if not VIN.match(vin):
        return error(400, "bad_request", "A VIN is 17 letters and digits.")
    with engine.connect() as conn:
        docs = list(conn.execute(select(RECALL.c.doc).where(RECALL.c.vin == vin).order_by(RECALL.c.campaign_id)).scalars())
        checked = clock.now(conn)  # a lookup is a fresh check: the simulated now of this call
    return {
        "vin": vin,
        "checkedAt": checked.isoformat(),
        "openRecalls": [
            {k: d[k] for k in ("campaignId", "component", "summary", "remedyAvailable")} for d in docs if d["status"] == "open"
        ],
        "remedied": [
            {"campaignId": d["campaignId"], "remedyRef": d["remedyRef"], "remediedAt": d["remediedAt"]}
            for d in docs
            if d["status"] == "remedied"
        ],
    }
