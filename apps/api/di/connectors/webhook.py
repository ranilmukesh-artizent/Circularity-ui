"""Change events from the source systems (docs/BACKEND_STEPS.md, B9).

source-sim delivers every change as a signed CloudEvent (B6). The intake verifies the HMAC signature and queues a
delta sync of the source that changed; a burst of events for one source queues one sync. The subscription is made
once by the worker at start-up.
"""

import hashlib
import hmac
import json
import logging

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import text

from di.config import get_settings
from di.connectors.registry import ADAPTERS
from di.connectors.sync import enqueue_sync
from di.db import SessionLocal

log = logging.getLogger("di.webhook")
router = APIRouter(prefix="/api/webhooks", tags=["Connectors"])


def ensure_subscription() -> None:
    s = get_settings()
    base = s.source_sim_url.rstrip("/")
    subs = httpx.get(f"{base}/_sim/webhooks", timeout=5).json()
    if any(x["url"] == s.webhook_url for x in subs):
        return
    httpx.post(
        f"{base}/_sim/webhooks", json={"url": s.webhook_url, "sources": [], "secret": s.webhook_secret}, timeout=5
    ).raise_for_status()
    log.info("subscribed to source-sim events at %s", s.webhook_url)


def valid_signature(body: bytes, signature: str | None) -> bool:
    expected = "sha256=" + hmac.new(get_settings().webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)


@router.post("/source-sim", status_code=202)
async def source_event(request: Request, x_sim_signature: str | None = Header(default=None)):
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
    with SessionLocal() as s:
        if ev.get("type") == "sim.reset":
            # the simulation rewound this system: its delta cursors no longer mean anything, so read everything again
            s.execute(text("DELETE FROM sync_cursor WHERE source_id = :i"), {"i": source_id})
        status = s.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": source_id}).scalar()
        job = None if status in ("paused", "disconnected", "unavailable") else enqueue_sync(s, source_id, "webhook")
        s.commit()
    return {"accepted": True, "source_id": source_id, "type": ev.get("type"), "queued_job": job}
