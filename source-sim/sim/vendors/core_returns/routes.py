"""The core returns mock's routes: the cores and the dealers' return history (see the package docstring)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.core_returns.models import CORE, DEALER_EVENT

router = APIRouter(prefix="/core-returns/api")
API_KEY = "core_ret-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _denied(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


@router.get("/cores")
def cores(request: Request):
    if (denied := _denied(request)) is not None:
        return denied
    with engine.connect() as conn:
        return list(conn.execute(select(CORE.c.doc).order_by(CORE.c.core_id)).scalars())


@router.get("/dealer-history")
def dealer_history(request: Request):
    if (denied := _denied(request)) is not None:
        return denied
    q = select(DEALER_EVENT.c.doc).order_by(DEALER_EVENT.c.dealer_id, DEALER_EVENT.c.core_id)
    if dealer := request.query_params.get("dealerId"):
        q = q.where(DEALER_EVENT.c.dealer_id == dealer)
    with engine.connect() as conn:
        return list(conn.execute(q).scalars())
