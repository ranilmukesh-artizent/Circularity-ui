"""The retail returns mock's route: one list of returned items, optionally for one item class (see the package docstring)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.retail_returns.models import RETURN

router = APIRouter(prefix="/retail-returns/api")
API_KEY = "b2c_ret-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


@router.get("/returns")
def returns(request: Request):
    if request.headers.get("x-api-key", "") != API_KEY:
        return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})
    q = select(RETURN.c.doc).order_by(RETURN.c.item_id)
    if item_class := request.query_params.get("itemClass"):
        q = q.where(RETURN.c.doc["itemClass"].astext == item_class)
    with engine.connect() as conn:
        return list(conn.execute(q).scalars())
