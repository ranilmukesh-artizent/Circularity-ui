"""The decommission tracker mock's routes: two reads (see the package docstring for the contract)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.decommission_tracker.models import REMOVAL_JOB, SITE_DEMAND

router = APIRouter(prefix="/decommission/api/v2")
API_KEY = "tn_decom-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorized(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


@router.get("/removal-jobs")
def removal_jobs(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        docs = list(conn.execute(select(REMOVAL_JOB.c.doc).order_by(REMOVAL_JOB.c.job_id)).scalars())
    return {"jobs": docs}


@router.get("/site-demand")
def site_demand(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        return list(conn.execute(select(SITE_DEMAND.c.doc).order_by(SITE_DEMAND.c.demand_id)).scalars())
