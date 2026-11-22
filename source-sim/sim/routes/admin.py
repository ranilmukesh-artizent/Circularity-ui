"""Control endpoints for the simulation (docs/backend-steps.md, B6). Not part of any vendor API.

GET  /_sim/clock                          {"now", "speed", "as_of"}
POST /_sim/clock/advance  {"minutes"|"hours"|"days": n}
POST /_sim/clock/speed    {"speed": 60}         (0 pauses)
POST /_sim/clock/reset                          back to the as-of time, speed 1
GET  /_sim/scheduled                            pending scheduled work
POST /_sim/tick                                 run due scheduled work now
GET/POST/DELETE /_sim/faults, POST /_sim/faults/demo
GET/POST /_sim/webhooks, DELETE /_sim/webhooks/{id}, GET /_sim/webhooks/status, POST /_sim/webhooks/deliver
POST /_sim/sink, GET /_sim/sink                 a webhook receiver for demos and tests (keeps the last 200)
GET  /_sim/outbox?source=&limit=                recent events
"""

from collections import deque
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from sim.core import clock, faults, scheduler, webhooks
from sim.core.db import engine
from sim.core.events import OUTBOX

router = APIRouter(prefix="/_sim", tags=["Simulation control"])
_sink: deque[dict] = deque(maxlen=200)


class Advance(BaseModel):
    minutes: float = 0
    hours: float = 0
    days: float = 0


class Speed(BaseModel):
    speed: float


class FaultIn(BaseModel):
    system: str
    kind: str
    value: int | None = None
    every: int = 1
    minutes: float | None = None
    note: str | None = None


class SubscriptionIn(BaseModel):
    url: str
    sources: list[str] = []
    secret: str = Field(min_length=1)  # each subscriber signs with its own secret (no shared default: D2, S1)


@router.get("/clock")
def get_clock():
    with engine.connect() as conn:
        return clock.state(conn)


@router.post("/clock/advance")
def advance_clock(a: Advance):
    with engine.begin() as conn:
        clock.advance(conn, timedelta(minutes=a.minutes, hours=a.hours, days=a.days))
    ran = scheduler.tick()
    with engine.connect() as conn:
        return clock.state(conn) | {"scheduled_ran": ran}


@router.post("/clock/speed")
def clock_speed(s: Speed):
    with engine.begin() as conn:
        try:
            clock.set_speed(conn, s.speed)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return clock.state(conn)


@router.post("/clock/reset")
def clock_reset():
    with engine.begin() as conn:
        clock.reset(conn)
        return clock.state(conn)


@router.get("/scheduled")
def get_scheduled():
    with engine.connect() as conn:
        return scheduler.pending(conn)


@router.post("/tick")
def tick():
    return {"ran": scheduler.tick()}


@router.get("/faults")
def get_faults():
    with engine.connect() as conn:
        return faults.active(conn)


@router.post("/faults", status_code=201)
def add_fault(f: FaultIn):
    with engine.begin() as conn:
        try:
            return {"id": faults.add(conn, f.system, f.kind, f.value, f.every, f.minutes, f.note)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.delete("/faults")
def remove_faults(system: str | None = None):
    with engine.begin() as conn:
        return {"removed": faults.remove(conn, system)}


@router.post("/faults/demo")
def demo_faults():
    with engine.begin() as conn:
        return {"ids": faults.apply_demo(conn), "faults": faults.DEMO_FAULTS}


@router.get("/webhooks")
def get_webhooks():
    with engine.connect() as conn:
        return webhooks.subscriptions(conn)


@router.post("/webhooks", status_code=201)
def add_webhook(s: SubscriptionIn):
    with engine.begin() as conn:
        return {"id": webhooks.subscribe(conn, s.url, s.sources, s.secret)}


@router.delete("/webhooks/{sub_id}")
def delete_webhook(sub_id: int):
    with engine.begin() as conn:
        if not webhooks.unsubscribe(conn, sub_id):
            raise HTTPException(404, "No such subscription")
    return {"deleted": sub_id}


@router.get("/webhooks/status")
def webhook_status():
    with engine.connect() as conn:
        return webhooks.status(conn)


@router.post("/webhooks/deliver")
def deliver_now():
    return {"attempted": webhooks.deliver()}


@router.post("/sink")
async def sink(request: Request):
    _sink.append(
        {
            "headers": {k: v for k, v in request.headers.items() if k.startswith(("x-sim", "content-type"))},
            "event": await request.json(),
        }
    )
    return {"received": True}


@router.get("/sink")
def get_sink(clear: bool = False) -> list[dict[str, Any]]:
    out = list(_sink)
    if clear:
        _sink.clear()
    return out


@router.get("/outbox")
def outbox(source: str | None = None, limit: int = 50):
    q = select(OUTBOX).order_by(OUTBOX.c.id.desc()).limit(min(limit, 500))
    if source:
        q = q.where(OUTBOX.c.source == source)
    with engine.connect() as conn:
        return [webhooks.cloudevent(r) | {"delivered_at": r.delivered_at} for r in conn.execute(q)]
