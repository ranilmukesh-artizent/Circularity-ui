"""The ITAD logistics mock's routes: the pickups and the erasure records (see the package docstring)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.itad_logistics.models import ERASURE, PICKUP

router = APIRouter(prefix="/itad-logistics/api")
API_KEY = "it_logistics-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _denied(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


@router.get("/pickups")
def pickups(request: Request):
    if (denied := _denied(request)) is not None:
        return denied
    with engine.connect() as conn:
        return list(conn.execute(select(PICKUP.c.doc).order_by(PICKUP.c.pickup_id)).scalars())


@router.get("/erasures")
def erasures(request: Request):
    if (denied := _denied(request)) is not None:
        return denied
    q = select(ERASURE.c.doc).order_by(ERASURE.c.media_serial)
    if media := request.query_params.get("mediaSerial"):
        q = q.where(ERASURE.c.media_serial == media)
    with engine.connect() as conn:
        return list(conn.execute(q).scalars())
