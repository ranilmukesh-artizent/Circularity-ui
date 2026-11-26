"""The biomedical service mock's routes: the reads and the idempotent service order (see the package docstring)."""

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select, text

from sim.core.db import engine
from sim.vendors.biomed_service.models import ASSESSMENT, CORRECTION, SERVICE, SERVICE_ORDER
from sim.vendors.biomed_service.seed import AS_OF

router = APIRouter(prefix="/biomed-service/api")
API_KEY = "mr_biomed-demo-key"  # demo credential, not a secret
ORDER_KINDS = ("pm", "certification", "repair", "refurbish")


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorized(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


def _all(table, request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        return list(conn.execute(select(table.c.doc).order_by(table.c.ord)).scalars())


def _one(table, tag: str, request: Request, what: str):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        doc = conn.execute(select(table.c.doc).where(table.c.tag == tag)).scalar()
    return doc if doc is not None else error(404, "not_found", f"No {what} for {tag}.")


@router.get("/assets")
def assets(request: Request):
    return _all(SERVICE, request)


@router.get("/assets/{tag}/service")
def service(tag: str, request: Request):
    return _one(SERVICE, tag, request, "service record")


@router.get("/corrections")
def corrections(request: Request):
    return _all(CORRECTION, request)


@router.get("/assessments")
def assessments(request: Request):
    return _all(ASSESSMENT, request)


@router.get("/assessments/{tag}")
def assessment(tag: str, request: Request):
    return _one(ASSESSMENT, tag, request, "assessment")


def _problem(body: dict[str, Any]) -> str | None:
    tag = body.get("tag")
    if not isinstance(tag, str) or not tag.strip():
        return "tag is required."
    if body.get("kind") not in ORDER_KINDS:
        return f"kind must be one of {', '.join(ORDER_KINDS)}."
    due = body.get("dueBy")
    if isinstance(due, str) and len(due) == 10:
        try:
            date.fromisoformat(due)
            return None
        except ValueError:
            pass
    return "dueBy is required, as a date (YYYY-MM-DD)."


@router.post("/service-orders")
async def service_orders(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        body: Any = json.loads(await request.body())
    except ValueError:
        return error(400, "bad_request", "The request body is not valid JSON.")
    if not isinstance(body, dict):
        return error(422, "invalid", "The request body must be a JSON object.")
    if (why := _problem(body)) is not None:
        return error(422, "invalid", why)
    tag, kind, due = body["tag"].strip(), body["kind"], body["dueBy"]
    same = (SERVICE_ORDER.c.tag == tag, SERVICE_ORDER.c.kind == kind, SERVICE_ORDER.c.due_by == due)
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('biomed_service:orders'))"))
        first = conn.execute(select(SERVICE_ORDER.c.doc).where(*same)).scalar()
        if first is not None:
            return JSONResponse(first, status_code=200)  # a repeat: the first order, nothing new
        seq = conn.execute(select(func.coalesce(func.max(SERVICE_ORDER.c.seq), 0) + 1)).scalar_one()
        doc = {"orderId": f"SO-{seq:04d}", "tag": tag, "kind": kind, "dueBy": due, "status": "accepted",
               "createdAt": AS_OF.isoformat()}  # fmt: skip
        conn.execute(insert(SERVICE_ORDER).values(seq=seq, tag=tag, kind=kind, due_by=due, doc=doc))
    return JSONResponse(doc, status_code=201)
