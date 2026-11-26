"""The asset management mock's routes: two reads (see the package docstring for the contract)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.medical_asset_mgmt.models import DEVICE

router = APIRouter(prefix="/asset-management/api")
API_KEY = "mr_assets-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorized(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


@router.get("/devices")
def devices(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    cls = request.query_params.get("deviceClass")
    with engine.connect() as conn:
        query = select(DEVICE.c.doc).order_by(DEVICE.c.ord)
        if cls:
            query = query.where(DEVICE.c.device_class == cls)
        return list(conn.execute(query).scalars())


@router.get("/devices/{tag}")
def device(tag: str, request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        doc = conn.execute(select(DEVICE.c.doc).where(DEVICE.c.tag == tag)).scalar()
    return doc if doc is not None else error(404, "not_found", f"No device {tag}.")
