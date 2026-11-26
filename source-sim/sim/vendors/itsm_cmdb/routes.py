"""The CMDB mock's route: one list of configuration items, optionally for one serial (see the package docstring)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.itsm_cmdb.models import CI

router = APIRouter(prefix="/itsm-cmdb/api")
API_KEY = "it_cmdb-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


@router.get("/now/cis")
def cis(request: Request):
    if request.headers.get("x-api-key", "") != API_KEY:
        return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})
    q = select(CI.c.doc).order_by(CI.c.serial)
    if serial := request.query_params.get("serial"):
        q = q.where(CI.c.serial == serial)
    with engine.connect() as conn:
        return list(conn.execute(q).scalars())
