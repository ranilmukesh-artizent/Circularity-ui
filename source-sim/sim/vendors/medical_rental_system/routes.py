"""The rental system mock's routes: six reads and the dispatch write (see the package docstring for the contract)."""

import json
import re
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select, text

from sim.core.db import engine
from sim.vendors.medical_rental_system.models import DISPATCH, RECORD
from sim.vendors.medical_rental_system.seed import AS_OF

router = APIRouter(prefix="/rental-system/api")
API_KEY = "mr_rental-demo-key"  # demo credential, not a secret
TAG = re.compile(r"^SYN-MR-[A-Z]{2}-\d{4}$")
EVIDENCE_FIELDS = ("serviceRef", "certExpiry", "deconRef")


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorized(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


def _docs(*where) -> list[dict]:
    with engine.connect() as conn:
        return list(conn.execute(select(RECORD.c.doc).where(*where).order_by(RECORD.c.kind, RECORD.c.ord)).scalars())


def _known(kind: str, column, value: str) -> bool:
    with engine.connect() as conn:
        return (
            conn.execute(select(func.count()).select_from(RECORD).where(RECORD.c.kind == kind, column == value)).scalar_one() > 0
        )


@router.get("/hospitals")
def hospitals(request: Request):
    return _unauthorized(request) or _docs(RECORD.c.kind == "hospitals")


@router.get("/depots")
def depots(request: Request):
    return _unauthorized(request) or _docs(RECORD.c.kind == "depots")


@router.get("/requests")
def open_requests(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        taken = set(conn.execute(select(DISPATCH.c.req_id)).scalars())
    return [d for d in _docs(RECORD.c.kind == "requests") if d["reqId"] not in taken]


@router.get("/returns")
def returns(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    depot = request.query_params.get("depot")
    return _docs(RECORD.c.kind == "returns", *([RECORD.c.depot == depot] if depot else []))


@router.get("/demand-forecast")
def demand_forecast(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    region = request.query_params.get("region")
    if region and not _known("forecast", RECORD.c.region, region):
        return error(404, "not_found", f"No region {region}.")
    return _docs(RECORD.c.kind == "forecast", *([RECORD.c.region == region] if region else []))


@router.get("/turnaround")
def turnaround(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    raw = request.query_params.get("days", "14")
    if not raw.isdigit() or not 1 <= int(raw) <= 365:
        return error(400, "bad_request", "days must be a whole number, 1 to 365.")
    depot = request.query_params.get("depot")
    if depot and not _known("depots", RECORD.c.rec_id, depot):
        return error(404, "not_found", f"No depot {depot}.")
    since = AS_OF - timedelta(days=int(raw))
    where = [RECORD.c.kind == "turnaround", RECORD.c.checked_in_at >= since] + ([RECORD.c.depot == depot] if depot else [])
    return _docs(*where)


# ------------------------------------------------------------------ the write
def _problem(b: dict) -> str | None:
    """Why the body is not a valid dispatch, or None."""
    if not isinstance(b.get("tag"), str) or not TAG.match(b["tag"]):
        return "tag must look like SYN-MR-IP-0001."
    if not isinstance(b.get("reqId"), str) or not b["reqId"].strip():
        return "reqId is required."
    ev = b.get("evidence")
    if not isinstance(ev, dict) or any(not isinstance(ev.get(f), str) or not ev[f].strip() for f in EVIDENCE_FIELDS):
        return "evidence needs serviceRef, certExpiry and deconRef."
    try:
        date.fromisoformat(ev["certExpiry"])
    except ValueError:
        return "evidence.certExpiry must be an ISO 8601 date."
    return None


@router.post("/dispatches")
async def dispatches(request: Request):
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
    if not _known("requests", RECORD.c.rec_id, body["reqId"]):
        return error(404, "not_found", f"No request {body['reqId']}.")
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('medical_rental_system:dispatches'))"))
        first = conn.execute(select(DISPATCH.c.tag, DISPATCH.c.doc).where(DISPATCH.c.req_id == body["reqId"])).first()
        if first is not None:  # a repeat answers with the first document; another tag for the request is a conflict
            if first.tag == body["tag"]:
                return JSONResponse(first.doc, status_code=200)
            return error(409, "conflict", f"Request {body['reqId']} is already dispatched with {first.tag}.")
        seq = conn.execute(select(func.coalesce(func.max(DISPATCH.c.seq), 0) + 1)).scalar_one()
        doc = {
            "dispatchId": f"DSP-{seq:04d}", "tag": body["tag"], "reqId": body["reqId"], "evidence": body["evidence"],
            "status": "dispatched", "createdAt": AS_OF.isoformat(),
        }  # fmt: skip
        conn.execute(insert(DISPATCH).values(seq=seq, req_id=body["reqId"], tag=body["tag"], doc=doc))
    return JSONResponse(doc, status_code=201)
