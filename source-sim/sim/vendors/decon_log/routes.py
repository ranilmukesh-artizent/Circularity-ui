"""The decontamination log mock's routes: the cycle list and the schedule write (see the package docstring)."""

import json
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, text

from sim.core import clock, scheduler
from sim.core.db import engine
from sim.vendors.decon_log.models import CYCLE
from sim.vendors.decon_log.seed import CYCLE_LENGTH, HANDLER, SOURCE, pending_doc

router = APIRouter(prefix="/decon-log/api")
API_KEY = "mr_decon-demo-key"  # demo credential, not a secret
TAG = re.compile(r"^SYN-MR-[A-Z]{2}-\d{4}$")


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _unauthorized(request: Request) -> JSONResponse | None:
    if request.headers.get("x-api-key", "") == API_KEY:
        return None
    return error(401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "ApiKey"})


def _since(request: Request) -> datetime | None:
    raw = request.query_params.get("updatedSince")
    if raw is None:
        return None
    try:
        d = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError("updatedSince must be an ISO 8601 date or timestamp.") from e
    return d if d.tzinfo else d.replace(tzinfo=UTC)


@router.get("/cycles")
def cycles(request: Request):
    if (denied := _unauthorized(request)) is not None:
        return denied
    try:
        since = _since(request)
    except ValueError as e:
        return error(400, "bad_request", str(e))
    where = [CYCLE.c.status == "done"]
    if (tag := request.query_params.get("tag")) is not None:
        where.append(CYCLE.c.tag == tag)
    if since is not None:
        where.append(CYCLE.c.updated_at > since)
    with engine.connect() as conn:
        return list(conn.execute(select(CYCLE.c.doc).where(*where).order_by(CYCLE.c.ended_at, CYCLE.c.cycle_id)).scalars())


def _problem(b: dict) -> str | None:
    """Why the body is not a valid schedule request, or None."""
    if not isinstance(b.get("tag"), str) or not TAG.match(b["tag"]):
        return "tag must look like SYN-MR-IP-0001."
    if "enhanced" in b and not isinstance(b["enhanced"], bool):
        return "enhanced must be true or false."
    return None


def _scheduled_body(doc: dict) -> dict:
    return {
        "cycleId": doc["cycleId"], "tag": doc["tag"], "enhanced": doc["enhanced"], "status": "scheduled",
        "scheduledEndAt": doc["cycleEndedAt"],
    }  # fmt: skip


@router.post("/cycles")
async def schedule_cycle(request: Request):
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
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('decon_log:cycles'))"))
        first = conn.execute(select(CYCLE.c.doc).where(CYCLE.c.tag == body["tag"], CYCLE.c.status == "scheduled")).scalar()
        if first is not None:  # a repeat answers with the cycle already scheduled and schedules nothing
            return JSONResponse(_scheduled_body(first), status_code=200)
        now = clock.now(conn)
        n = conn.execute(text("SELECT coalesce(max(substr(cycle_id, 4)::int), 1000) + 1 FROM decon_log.cycle")).scalar_one()
        doc = pending_doc(f"DC-{max(n, 1001)}", body["tag"], bool(body.get("enhanced", False)), now, now + CYCLE_LENGTH)
        conn.execute(
            insert(CYCLE).values(
                cycle_id=doc["cycleId"], tag=doc["tag"], status="scheduled", ended_at=now + CYCLE_LENGTH, updated_at=now, doc=doc
            )
        )
        scheduler.schedule(conn, now + CYCLE_LENGTH, HANDLER, {"cycleId": doc["cycleId"]}, SOURCE)
    return JSONResponse(_scheduled_body(doc), status_code=202)
