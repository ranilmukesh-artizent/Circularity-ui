"""The pricing guide mock's route: one read (see the package docstring for the contract)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.vehicle_pricing.models import VALUE

router = APIRouter(prefix="/vehicle-pricing/v3")
API_KEY = "uc_price-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


@router.get("/values")
def values(request: Request):
    if request.headers.get("x-api-key", "") != API_KEY:
        return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})
    vin = request.query_params.get("vin", "").strip()
    if not vin:
        return error(400, "bad_request", "vin is required.")
    with engine.connect() as conn:
        doc = conn.execute(select(VALUE.c.doc).where(VALUE.c.vin == vin)).scalar()
    return doc if doc is not None else error(404, "not_found", f"No value for VIN {vin}.")
