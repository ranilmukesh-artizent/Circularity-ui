"""The equipment rental mock's routes: six lists behind an API key (see the package docstring)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.equipment_rental.models import DOC

router = APIRouter(prefix="/equipment-rental/api")
API_KEY = "rf_rental-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorised(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") != API_KEY:
        return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})
    return None


def _docs(kind: str) -> list[dict]:
    with engine.connect() as conn:
        return list(conn.execute(select(DOC.c.doc).where(DOC.c.kind == kind).order_by(DOC.c.key)).scalars())


def _list(request: Request, kind: str):
    return _unauthorised(request) or _docs(kind)


@router.get("/off-rent")
def off_rent(request: Request):
    return _list(request, "off_rent")


@router.get("/utilisation")
def utilisation(request: Request):
    return _list(request, "utilisation")


@router.get("/damage-claims")
def damage_claims(request: Request):
    return _list(request, "damage")


@router.get("/purchase-plans")
def purchase_plans(request: Request):
    return _list(request, "plan")


@router.get("/idle")
def idle(request: Request):
    return _list(request, "idle")


@router.get("/price-index")
def price_index(request: Request):
    if (bad := _unauthorised(request)) is not None:
        return bad
    cls, band = request.query_params.get("class", ""), request.query_params.get("hoursBand", "")
    with engine.connect() as conn:
        doc = conn.execute(select(DOC.c.doc).where(DOC.c.kind == "price", DOC.c.key == f"{cls}:{band}")).scalar()
    return doc or {}
