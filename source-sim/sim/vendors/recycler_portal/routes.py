"""The recycler portal mock's routes: two reads, one idempotent write, and the scheduled issue of disposal certificates
(see the package docstring for the contract)."""

import json
from datetime import UTC, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import Connection

from sim.core import clock, events, scheduler
from sim.core.db import engine
from sim.vendors.recycler_portal import seed
from sim.vendors.recycler_portal.models import CERTIFICATE, PICKUP, VENDOR

router = APIRouter(prefix="/recycler-portal/api")
API_KEY = "tn_recycler-demo-key"  # demo credential, not a secret
CERTIFICATE_DELAY = timedelta(days=2)


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorized(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


@scheduler.handler(seed.HANDLER)
def _issue_certificates(conn: Connection, payload: dict) -> None:
    """One disposal certificate per serial of the pickup, once: nothing happens when the pickup already has them."""
    pickup_id = payload["pickupId"]
    pickup = conn.execute(select(PICKUP.c.doc).where(PICKUP.c.doc["pickupId"].astext == pickup_id)).scalar()
    if pickup is None or conn.execute(select(CERTIFICATE.c.seq).where(CERTIFICATE.c.pickup_id == pickup_id)).first():
        return
    stamp = clock.now(conn).astimezone(UTC).isoformat()
    for serial in pickup["serials"]:
        seq = conn.execute(select(func.coalesce(func.max(CERTIFICATE.c.seq), 0) + 1)).scalar_one()
        doc = {
            "certificateId": f"DC-{seq:04d}", "serial": serial, "pickupId": pickup_id, "vendorId": pickup["vendorId"],
            "issuedAt": stamp,
        }  # fmt: skip
        conn.execute(insert(CERTIFICATE).values(seq=seq, serial=serial, pickup_id=pickup_id, doc=doc))
        events.emit(conn, seed.SOURCE, "recycler.certificate.issued", serial, {"certificateId": doc["certificateId"], "serial": serial})


@router.get("/vendors")
def vendors(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    with engine.connect() as conn:
        return list(conn.execute(select(VENDOR.c.doc).order_by(VENDOR.c.vendor_id)).scalars())


@router.get("/certificates")
def certificates(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    where = [CERTIFICATE.c.serial == s for s in [request.query_params.get("serial")] if s]
    with engine.connect() as conn:
        return list(conn.execute(select(CERTIFICATE.c.doc).where(*where).order_by(CERTIFICATE.c.seq)).scalars())


@router.post("/pickups")
async def pickups(request: Request):
    """Idempotent on the recycler and the set of serials: a repeat gets the first pickup back (200), a new one is 201."""
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        body: Any = json.loads(await request.body())
    except ValueError:
        return error(400, "bad_request", "The request body is not valid JSON.")
    if not isinstance(body, dict):
        return error(422, "invalid", "The request body must be a JSON object.")
    serials, vendor_id, category, weight = body.get("serials"), body.get("vendorId"), body.get("weeeCategory"), body.get("weightKg")
    valid = (
        isinstance(serials, list) and serials and all(isinstance(s, str) and s.strip() for s in serials)
        and isinstance(vendor_id, str) and vendor_id.strip()
        and isinstance(category, str) and category.strip()
        and isinstance(weight, int | float) and not isinstance(weight, bool) and weight > 0
    )  # fmt: skip
    if not valid:
        return error(422, "invalid", "serials (a non-empty list), vendorId, weeeCategory and weightKg (above 0) are required.")
    ordered = sorted(set(serials))
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('recycler_portal:pickup'))"))
        row = conn.execute(select(VENDOR.c.lapsed, VENDOR.c.doc).where(VENDOR.c.vendor_id == vendor_id)).first()
        if row is None:
            return error(404, "not_found", f"No recycler {vendor_id}.")
        now = clock.now(conn)
        if row.lapsed or row.doc["certificate"]["expires"] < now.date().isoformat():
            return error(422, "certificate_expired", f"The certificate of {vendor_id} has expired.")
        idem = f"{vendor_id}|{','.join(ordered)}"
        first = conn.execute(select(PICKUP.c.doc).where(PICKUP.c.idem == idem)).scalar()
        if first is not None:
            return JSONResponse(first, status_code=200)
        seq = conn.execute(select(func.coalesce(func.max(PICKUP.c.seq), 0) + 1)).scalar_one()
        doc = {
            "pickupId": f"PU-{seq:04d}", "vendorId": vendor_id, "serials": ordered, "weeeCategory": category.strip(),
            "weightKg": weight, "status": "scheduled", "createdAt": now.astimezone(UTC).isoformat(),
        }  # fmt: skip
        conn.execute(insert(PICKUP).values(seq=seq, idem=idem, doc=doc))
        scheduler.schedule(conn, now + CERTIFICATE_DELAY, seed.HANDLER, {"pickupId": doc["pickupId"]}, seed.SOURCE)
    return JSONResponse(doc, status_code=201)
