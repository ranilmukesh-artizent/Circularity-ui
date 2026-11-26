"""The disposal partner mock's routes: two reads and two writes (see the package docstring for the contract)."""

import json
import re
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select, text

from sim.core import clock
from sim.core.db import engine
from sim.vendors.disposal_partner.models import COLLECTION, SANITISATION

router = APIRouter(prefix="/disposal-partner/api")
API_KEY = "mr_disposal-demo-key"  # demo credential, not a secret
TAG = re.compile(r"^SYN-MR-([A-Z]{2})-\d{4}$")
CERTIFICATE_AFTER = timedelta(days=2)  # simulated time from the collection to its certificate
SANITISATION_AFTER = timedelta(days=1)  # simulated time from the request to its record
PATIENT_DATA_CLASSES = {"PM"}  # patient monitors, as in the asset management mock


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorized(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


def _valid_tag(tag: Any) -> bool:
    return isinstance(tag, str) and TAG.match(tag) is not None


def _holds_patient_data(tag: str) -> bool:
    return TAG.match(tag).group(1) in PATIENT_DATA_CLASSES  # type: ignore[union-attr]


async def _body(request: Request) -> dict | JSONResponse:
    try:
        body: Any = json.loads(await request.body())
    except ValueError:
        return error(400, "bad_request", "The request body is not valid JSON.")
    if not isinstance(body, dict):
        return error(422, "invalid", "The request body must be a JSON object.")
    return body


# ------------------------------------------------------------------ collections and certificates
@router.post("/collections")
async def collections(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body
    tags = body.get("tags")
    if not isinstance(tags, list) or not tags or not all(_valid_tag(t) for t in tags):
        return error(422, "invalid", "tags must be a non-empty list of tags like SYN-MR-IP-0001.")
    ref = body.get("sanitisationRef")
    if ref is not None and not isinstance(ref, str):
        return error(422, "invalid", "sanitisationRef must be text.")
    ref = ref.strip() if ref else None
    needing = [t for t in tags if _holds_patient_data(t)]
    if needing and not ref:
        why = f"A sanitisation reference is required for devices with patient data: {', '.join(needing)}."
        return error(422, "sanitisation_missing", why)
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('disposal_partner:collections'))"))
        seq = conn.execute(select(func.coalesce(func.max(COLLECTION.c.seq), 0) + 1)).scalar_one()
        now = clock.now(conn)
        doc = {
            "collectionId": f"COL-{seq:04d}", "tags": tags, "sanitisationRef": ref, "status": "collected",
            "createdAt": now.isoformat(), "certificatesDueAt": (now + CERTIFICATE_AFTER).isoformat(),
        }  # fmt: skip
        conn.execute(insert(COLLECTION).values(seq=seq, doc=doc, created_at=now))
    return JSONResponse(doc, status_code=201)


@router.get("/certificates")
def certificates(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    tag = request.query_params.get("tag")
    with engine.connect() as conn:
        now = clock.now(conn)
        rows = conn.execute(select(COLLECTION.c.seq, COLLECTION.c.doc, COLLECTION.c.created_at).order_by(COLLECTION.c.seq)).all()
    out = []
    for r in rows:
        issued = r.created_at + CERTIFICATE_AFTER
        if issued > now:
            continue
        for i, t in enumerate(r.doc["tags"], start=1):
            if tag is None or t == tag:
                out.append({
                    "certificateId": f"DC-{r.seq:04d}-{i}", "tag": t, "collectionId": r.doc["collectionId"],
                    "issuedAt": issued.isoformat(),
                })  # fmt: skip
    return out


# ------------------------------------------------------------------ sanitisations
def _record(seq: int, tag: str, requested, now) -> dict:
    done = requested + SANITISATION_AFTER
    doc = {"sanitisationId": f"SAN-{seq:04d}", "tag": tag, "requestedAt": requested.isoformat()}
    if done <= now:
        return doc | {"status": "completed", "completedAt": done.isoformat()}
    return doc | {"status": "pending", "completesAt": done.isoformat()}


@router.post("/sanitisations")
async def request_sanitisation(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body
    tag = body.get("tag")
    if not _valid_tag(tag):
        return error(422, "invalid", "tag must look like SYN-MR-PM-0001.")
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('disposal_partner:sanitisations'))"))
        now = clock.now(conn)
        first = conn.execute(select(SANITISATION.c.seq, SANITISATION.c.created_at).where(SANITISATION.c.tag == tag)).first()
        if first is not None:  # idempotent: the first request's record again
            return JSONResponse(_record(first.seq, tag, first.created_at, now), status_code=200)
        seq = conn.execute(select(func.coalesce(func.max(SANITISATION.c.seq), 0) + 1)).scalar_one()
        conn.execute(insert(SANITISATION).values(seq=seq, tag=tag, created_at=now))
    return JSONResponse(_record(seq, tag, now, now), status_code=201)


@router.get("/sanitisations")
def sanitisations(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    tag = request.query_params.get("tag")
    with engine.connect() as conn:
        now = clock.now(conn)
        query = select(SANITISATION.c.seq, SANITISATION.c.tag, SANITISATION.c.created_at).order_by(SANITISATION.c.seq)
        rows = conn.execute(query.where(SANITISATION.c.tag == tag) if tag else query).all()
    docs = [_record(r.seq, r.tag, r.created_at, now) for r in rows]
    return [d for d in docs if d["status"] == "completed"]
