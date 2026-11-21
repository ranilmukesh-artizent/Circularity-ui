"""Change events from the source systems (docs/backend-steps.md, B9).

source-sim delivers every change as a signed CloudEvent (B6). The intake verifies the HMAC signature and queues a
delta sync of the source that changed; a burst of events for one source queues one sync. The worker makes the
subscription at start-up and checks it on every periodic tick (it is put back if source-sim lost it).

B13b: before the sync is queued, an event that completes an instruction's step acknowledges it
(di/instructions/events.py: which event completes which step, and how it is matched). Every event still queues the
delta sync, matched or not.

Plan 6 A7, one source's own webhook: POST /api/webhooks/{source_id}. The body is a CloudEvent with an `id` and a
`time`, signed `X-Signature: sha256=<HMAC-SHA256 of the body>` (source-sim's `X-Sim-Signature` is accepted too) with the
source's webhook secret (`source_secret` kind `webhook`), or with the global DI_WEBHOOK_SECRET when it has none (the
demo sources). Answers: 401 `bad_signature`; 404 for an unknown or deleted source; 400 `validation_error` without an id
or a readable time; 400 `stale_event` for a `time` more than REPLAY_WINDOW_S behind the workspace clock; 200
`{"duplicate": true}` for an id this source already sent (table `webhook_event`); else 202 as /source-sim.
The window is measured on di/clock.py, the clock the event's `time` comes from: source-sim stamps its events with its
simulated clock, which the running api follows (DI_CLOCK=sim), so the demo's events are judged on simulated time,
however fast or far that clock was moved. An event that looks stale is checked once more against a fresh reading of
the clock (the clock is cached for clock_cache_seconds and may just have been moved). Events ahead of the clock are not
refused: the cached clock lags behind a clock that was just advanced.
The shared source-sim route keeps its behaviour (no dedupe, no window): source-sim redelivers an event for up to an
hour of retries, and its deliveries are idempotent (a sync, an acknowledgement matched once).
"""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from di import clock
from di.config import get_settings
from di.connectors import lifecycle
from di.connectors.registry import ADAPTERS
from di.connectors.secrets import active_secret
from di.connectors.sync import enqueue_sync
from di.db import SessionLocal
from di.instructions import events as instructions_events

REPLAY_WINDOW_S = 300  # an event older than this (on the workspace clock) is refused
KEEP_EVENTS_DAYS = 7  # received event ids are remembered this long (far beyond the window)

log = logging.getLogger("di.webhook")
router = APIRouter(prefix="/api/webhooks", tags=["Connectors"])


def ensure_subscription() -> None:
    s = get_settings()
    base = s.source_sim_url.rstrip("/")
    subs = httpx.get(f"{base}/_sim/webhooks", timeout=5).json()
    if any(x["url"] == s.webhook_url for x in subs):
        return
    httpx.post(
        f"{base}/_sim/webhooks",
        json={"url": s.webhook_url, "sources": [], "secret": s.webhook_secret.get_secret_value()},
        timeout=5,
    ).raise_for_status()
    log.info("subscribed to source-sim events at %s", s.webhook_url)


def valid_signature(body: bytes, signature: str | None) -> bool:
    expected = "sha256=" + hmac.new(get_settings().webhook_secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
    if not signature:
        return False
    return hmac.compare_digest(expected, signature)


@router.post("/source-sim", status_code=202)
async def source_event(request: Request, x_sim_signature: Annotated[str | None, Header()] = None):
    body = await request.body()
    if not valid_signature(body, x_sim_signature):
        raise HTTPException(401, {"code": "bad_signature", "message": "The event signature does not match."})
    try:
        ev = json.loads(body)
        source_id = ev["source"].rsplit("/", 1)[-1]
    except (ValueError, KeyError, AttributeError) as e:
        raise HTTPException(400, {"code": "validation_error", "message": "Not a CloudEvent from source-sim."}) from e
    if source_id not in ADAPTERS:
        return {"accepted": False, "reason": f"no connector for {source_id}"}
    # the body must be read here, as received (the signature covers its exact bytes); the database work below blocks,
    # so it runs in the thread pool instead of on the event loop
    return await run_in_threadpool(_accept, ev, source_id)


def _accept(ev: dict, source_id: str) -> dict:
    instruction = None
    try:
        instruction = instructions_events.handle(ev)  # B13b: a completion acknowledges its step
    except Exception:  # an acknowledgement that fails must not stop the sync below
        log.exception("instruction acknowledgement from %s %s failed", source_id, ev.get("type"))
    with SessionLocal() as s:
        if ev.get("type") == "sim.reset":
            # the simulation rewound this system: its delta cursors no longer mean anything, so read everything again
            s.execute(text("DELETE FROM sync_cursor WHERE source_id = :i"), {"i": source_id})
        status = s.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": source_id}).scalar()
        job = None if status in ("paused", "disconnected", "unavailable") else enqueue_sync(s, source_id, "webhook")
        s.commit()
    out = {"accepted": True, "source_id": source_id, "type": ev.get("type"), "queued_job": job}
    return out | ({"instruction": instruction} if instruction else {})


# ---------------------------------------------------------------- one source's own webhook (plan 6 A7)
def _bad(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def _signed_by(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), signature.encode("utf-8", "replace"))


def _event_time(ev: dict) -> datetime:
    raw = ev.get("time")
    if not isinstance(raw, str):
        raise ValueError("no time")
    t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _stale(t: datetime) -> bool:
    if (clock.now() - t).total_seconds() <= REPLAY_WINDOW_S:
        return False
    clock.invalidate()  # the cached simulated clock may be behind a clock that was just moved: read it again
    return (clock.now() - t).total_seconds() > REPLAY_WINDOW_S


@router.post("/{source_id}", status_code=202)
async def own_source_event(
    source_id: str,
    request: Request,
    x_signature: Annotated[str | None, Header()] = None,
    x_sim_signature: Annotated[str | None, Header()] = None,
):
    body = await request.body()  # as received: the signature covers its exact bytes
    return await run_in_threadpool(_intake, source_id, body, x_signature or x_sim_signature)


def _intake(source_id: str, body: bytes, signature: str | None):
    with SessionLocal() as s:
        secret = active_secret(s, source_id, "webhook") or get_settings().webhook_secret.get_secret_value()
        if not _signed_by(secret, body, signature):
            raise _bad(401, "bad_signature", "The event signature does not match.")
        known = s.execute(text("SELECT 1 FROM source_system WHERE id = :i"), {"i": source_id}).first()
        if known is None or lifecycle.is_deleted(s, source_id):
            raise _bad(404, "not_found", f"No source {source_id}.")
        connector = source_id in ADAPTERS  # TODO(A3): registry.adapter_for, for configured sources too
    try:
        ev = json.loads(body)
        event_id = ev["id"]
        if not isinstance(event_id, str) or not event_id or len(event_id) > 200:
            raise ValueError("bad id")
        at = _event_time(ev)
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise _bad(400, "validation_error", "Not a CloudEvent with an id and a time.") from e
    if _stale(at):
        raise _bad(400, "stale_event", f"The event is older than {REPLAY_WINDOW_S} seconds.")
    if not connector:
        return {"accepted": False, "reason": f"no connector for {source_id}"}
    with SessionLocal() as s:
        s.execute(
            text("DELETE FROM webhook_event WHERE received_at < now() - make_interval(days => :d)"), {"d": KEEP_EVENTS_DAYS}
        )
        new = s.execute(
            text(
                "INSERT INTO webhook_event (source_id, event_id, event_type, event_time) VALUES (:s, :e, :t, :at) "
                "ON CONFLICT (source_id, event_id) DO NOTHING RETURNING 1"
            ),
            {"s": source_id, "e": event_id, "t": str(ev.get("type"))[:200] if ev.get("type") else None, "at": at},
        ).first()
        if new is None:
            s.commit()
            return JSONResponse({"duplicate": True, "source_id": source_id, "id": event_id}, status_code=200)
        # the id is committed only once the event was handled: a delivery that failed here can be sent again. A
        # concurrent copy of the same event waits on this row and is then answered as a duplicate.
        out = _accept(ev, source_id)
        s.commit()
    return out
