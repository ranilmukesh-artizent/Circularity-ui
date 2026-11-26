"""The parts supplier portal mock's route: one read (see the package docstring for the contract)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from sim.core.db import engine
from sim.vendors.parts_portal.models import PART

router = APIRouter(prefix="/parts-portal/api")
API_KEY = "mr_parts-demo-key"  # demo credential, not a secret


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorized(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


@router.get("/parts")
def parts(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    model = request.query_params.get("model")
    with engine.connect() as conn:
        query = select(PART.c.doc).order_by(PART.c.model, PART.c.ord)
        if model:
            if not conn.execute(select(func.count()).select_from(PART).where(PART.c.model == model)).scalar_one():
                return error(404, "not_found", f"No device model {model}.")
            query = query.where(PART.c.model == model)
        return list(conn.execute(query).scalars())
