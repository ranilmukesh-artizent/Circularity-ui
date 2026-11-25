"""The title mock's routes: two reads and the release request (see the package docstring for the contract)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select

from sim.core.db import engine
from sim.vendors.title_lien.models import REQUEST, TITLE

router = APIRouter(prefix="/title-lien/api/v2")
API_KEY = "uc_title-demo-key"  # demo credential, not a secret
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


@router.get("/titles")
def titles(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        limit, offset, since = _whole(request, "limit", 25, 1, MAX_LIMIT), _whole(request, "offset", 0, 0), _since(request)
    except ValueError as e:
        return error(400, "bad_request", str(e))
    where = [] if since is None else [TITLE.c.updated_at > since]
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(TITLE).where(*where)).scalar_one()
        docs = conn.execute(select(TITLE.c.doc).where(*where).order_by(TITLE.c.vin).offset(offset).limit(limit)).scalars()
        items = list(docs)
    return {"items": items, "next": offset + limit if offset + limit < total else None, "total": total}


@router.get("/titles/{vin}")
def title(vin: str, request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        doc = conn.execute(select(TITLE.c.doc).where(TITLE.c.vin == vin)).scalar()
    return doc if doc is not None else error(404, "not_found", f"No title for {vin}.")


@router.post("/lien-release-requests")
async def lien_release_request(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        body = await request.json()
    except ValueError:
        return error(400, "bad_request", "The body must be JSON.")
    vin, lien_id = (body.get("vin"), body.get("lienId")) if isinstance(body, dict) else (None, None)
    if not isinstance(vin, str) or not isinstance(lien_id, str):
        return error(422, "invalid_request", "vin and lienId are required.")
    key = request.headers.get("Idempotency-Key")
    with engine.begin() as conn:
        doc = conn.execute(select(TITLE.c.doc).where(TITLE.c.vin == vin)).scalar()
        if doc is None:
            return error(404, "not_found", f"No title for {vin}.")
        lien = next((x for x in doc["liens"] if x["lienId"] == lien_id), None)
        if lien is None:
            return error(404, "not_found", f"No lien {lien_id} on {vin}.")
        if lien["released"]:
            return error(409, "already_released", f"Lien {lien_id} is already released.")
        if key:
            seen = conn.execute(select(REQUEST.c.id).where(REQUEST.c.idem_key == key)).scalar()
            if seen is not None:
                return JSONResponse({"requestId": f"LRR-{seen:04d}"}, status_code=202)
        rid = conn.execute(insert(REQUEST).values(vin=vin, lien_id=lien_id, idem_key=key).returning(REQUEST.c.id)).scalar_one()
    return JSONResponse({"requestId": f"LRR-{rid:04d}"}, status_code=202)
