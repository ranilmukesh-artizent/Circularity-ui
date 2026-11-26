"""The legacy body-shop mock's routes: a paged list of repairs and the description of the API (see the package docstring)."""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from sim.core.db import engine
from sim.vendors.body_shop_legacy.models import REPAIR

router = APIRouter(prefix="/body-shop")
API_KEY = "uc_bodyshop-demo-key"  # demo credential, not a secret
MAX_SIZE, DEFAULT_SIZE = 100, 50

_REPAIR = {
    "type": "object",
    "required": ["repairId", "vin", "damageArea", "repairDate", "cost", "insuranceClaim"],
    "properties": {
        "repairId": {"type": "string"},
        "vin": {"type": "string"},
        "damageArea": {"type": "string"},
        "repairDate": {"type": "string", "format": "date"},
        "cost": {"type": "number"},
        "insuranceClaim": {"type": "boolean"},
    },
}
OPENAPI: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Legacy body-shop system (synthetic)", "version": "1.0.0"},
    "servers": [{"url": "/body-shop"}],
    "security": [{"apiKey": []}],
    "paths": {
        "/repairs": {
            "get": {
                "operationId": "listRepairs",
                "summary": "The repairs of every car, oldest first",
                "parameters": [
                    {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}},
                    {
                        "name": "size",
                        "in": "query",
                        "schema": {"type": "integer", "minimum": 1, "maximum": MAX_SIZE, "default": DEFAULT_SIZE},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "One page of repairs",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/RepairPage"}}},
                    }
                },
            }
        }
    },
    "components": {
        "schemas": {
            "Repair": _REPAIR,
            "RepairPage": {
                "type": "object",
                "required": ["repairs", "page", "pages", "total"],
                "properties": {
                    "repairs": {"type": "array", "items": {"$ref": "#/components/schemas/Repair"}},
                    "page": {"type": "integer"},
                    "pages": {"type": "integer"},
                    "total": {"type": "integer"},
                },
            },
        },
        "securitySchemes": {"apiKey": {"type": "apiKey", "in": "header", "name": "x-api-key"}},
    },
}


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _whole(request: Request, name: str, default: int, low: int, high: int | None = None) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    if not raw.isdigit() or int(raw) < low or (high is not None and int(raw) > high):
        span = f"{low} to {high}" if high is not None else f"{low} or more"
        raise ValueError(f"{name} must be a whole number, {span}.")
    return int(raw)


@router.get("/openapi.json")
def openapi() -> dict[str, Any]:
    return OPENAPI


@router.get("/repairs")
def repairs(request: Request):
    if request.headers.get("x-api-key", "") != API_KEY:
        return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})
    try:
        page, size = _whole(request, "page", 1, 1), _whole(request, "size", DEFAULT_SIZE, 1, MAX_SIZE)
    except ValueError as e:
        return error(400, "bad_request", str(e))
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(REPAIR)).scalar_one()
        docs = conn.execute(select(REPAIR.c.doc).order_by(REPAIR.c.n).offset((page - 1) * size).limit(size)).scalars()
        items = list(docs)
    return {"repairs": items, "page": page, "pages": -(-total // size), "total": total}
