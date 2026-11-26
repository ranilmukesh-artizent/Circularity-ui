"""The battery management mock's route: the packs (see the package docstring)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.battery_bms.models import PACK

router = APIRouter(prefix="/battery-bms/api")
API_KEY = "bat_bms-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


@router.get("/packs")
def packs(request: Request):
    if request.headers.get("x-api-key", "") != API_KEY:
        return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})
    with engine.connect() as conn:
        return list(conn.execute(select(PACK.c.doc).order_by(PACK.c.pack_id)).scalars())
