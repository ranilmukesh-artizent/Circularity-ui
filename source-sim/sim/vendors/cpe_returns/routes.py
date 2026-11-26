"""The CPE returns mock's routes: returns, factory resets, lot grades and the new-subscriber forecast (package docstring)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.cpe_returns.models import FORECAST, LOT, RESET, RETURN

router = APIRouter(prefix="/cpe-returns/api")
API_KEY = "cpe_bss-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _denied(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


def _docs(table, order, where=None):
    q = select(table.c.doc).order_by(order)
    if where is not None:
        q = q.where(where)
    with engine.connect() as conn:
        return list(conn.execute(q).scalars())


@router.get("/returns")
def returns(request: Request):
    return _denied(request) or _docs(RETURN, RETURN.c.serial)


@router.get("/factory-resets")
def factory_resets(request: Request):
    if (denied := _denied(request)) is not None:
        return denied
    serial = request.query_params.get("serial")
    return _docs(RESET, RESET.c.serial, RESET.c.serial == serial if serial else None)


@router.get("/lot-grades")
def lot_grades(request: Request):
    return _denied(request) or _docs(LOT, LOT.c.lot_id)


@router.get("/new-subscriber-forecast")
def new_subscriber_forecast(request: Request):
    return _denied(request) or _docs(FORECAST, FORECAST.c.week)
