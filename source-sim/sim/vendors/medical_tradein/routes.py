"""The trade-in register mock's route: one list of trade-ins, optionally for one tag (see the package docstring)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.medical_tradein.models import TRADEIN

router = APIRouter(prefix="/medical-tradein/api")
API_KEY = "mc_tradein-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


@router.get("/tradeins")
def tradeins(request: Request):
    if request.headers.get("x-api-key", "") != API_KEY:
        return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})
    q = select(TRADEIN.c.doc).order_by(TRADEIN.c.tag)
    if tag := request.query_params.get("tag"):
        q = q.where(TRADEIN.c.tag == tag)
    with engine.connect() as conn:
        return list(conn.execute(q).scalars())
