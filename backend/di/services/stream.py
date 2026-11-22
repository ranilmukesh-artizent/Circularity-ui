"""Live updates (docs/backend-steps.md, B15): `GET /api/stream`, Server-Sent Events for the signed-in account. The
endpoint is di.routes.stream; this module holds the fan-out, the visibility rules and the wire format.

**Where events come from.** Database triggers copy everything that changes into `stream_event` (migration 0008):
journal events (actions and stage moves), the demo-shaped event stream, notifications, sync runs and instruction
steps. Each insert sends `NOTIFY di_stream`. So every writer (an action, the worker, the webhook receiver, another api
process) shows up on every connected stream, without the writers knowing about streams.

**Fan-out.** One listener thread per api process holds a dedicated connection with `LISTEN di_stream`, reads each new
row once and hands it to every subscriber's queue. Each stream then keeps what its account may see:
- a case's events only inside the account's tenants and, for a Warehouse Manager, its warehouse (the same rules as
  the case actions);
- sync progress only for accounts that may open Connection Fabric;
- a notification only for its addressee (and Admin);
- workflow changes and run progress (kind `workflow`, migration 0009) only for accounts that may open the Workflow
  Studio (integration/studio);
- everything else (access changes, the journal) for every signed-in account.
The account's scope is read when the stream opens; a tenant grant made later applies from the next connection.

**The wire format.** One SSE message per event: `id` (the stream_event id), `event` (journal, event, notification,
sync, step, workflow) and `data` (JSON: id, kind, case_id, at, payload). A comment line every 15 s keeps proxies from closing
the connection. A client that reconnects with `Last-Event-ID` (EventSource does this itself) gets what it missed, up to
500 events (or `?last_event_id=`).

**Signing in.** Non-browser clients send `Authorization: Bearer <access token>`. Browsers' EventSource cannot send
headers, so the web app first trades its access token for a stream ticket (POST /api/auth/stream-ticket: aud
"stream", 60 s) and opens `/api/stream?ticket=...` (F3): the access token never appears in a URL or an access log. The
ticket is checked when the stream opens only; a reconnect fetches a new one. An access token in `?ticket=` is refused,
as is a ticket used as a bearer token anywhere.
"""

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any

import psycopg
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import RowMapping, text

from di.core import auth, policy
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.repositories.context import can_see_case

log = logging.getLogger("di.services.stream")
CHANNEL = "di_stream"
HEARTBEAT_S = 15
REPLAY_MAX = 500


Event = dict[str, Any]
EventQueue = asyncio.Queue[Event]


def _row(r: RowMapping) -> Event:
    d = dict(r)
    if isinstance(d.get("at"), datetime):
        d["at"] = d["at"].isoformat()
    return d


def fetch(after: int, limit: int = REPLAY_MAX) -> list[Event]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM stream_event WHERE id > :a ORDER BY id LIMIT :n"), {"a": after, "n": limit}
        ).mappings()
        return [_row(r) for r in rows]


def latest_id() -> int:
    with engine.connect() as conn:
        last: int = conn.execute(text("SELECT coalesce(max(id), 0) FROM stream_event")).scalar_one()
        return last


class Broker:
    """One LISTEN connection per process, fanned out to every open stream's asyncio queue."""

    def __init__(self) -> None:
        self._subs: set[tuple[asyncio.AbstractEventLoop, EventQueue]] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def subscribe(self) -> EventQueue:
        q: EventQueue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subs.add((asyncio.get_running_loop(), q))
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._listen, name="di-stream", daemon=True)
                self._thread.start()
        return q

    def unsubscribe(self, q: EventQueue) -> None:
        with self._lock:
            self._subs = {s for s in self._subs if s[1] is not q}

    def subscribers(self) -> int:
        return len(self._subs)

    def _publish(self, ev: Event) -> None:
        with self._lock:
            subs = list(self._subs)
        for loop, q in subs:
            loop.call_soon_threadsafe(_offer, q, ev)

    def _listen(self) -> None:
        dsn = get_settings().database_url.replace("+psycopg", "")
        while True:
            try:
                with psycopg.connect(dsn, autocommit=True) as conn:
                    conn.execute(f"LISTEN {CHANNEL}")
                    last = latest_id()
                    for _ in conn.notifies():
                        # read every row after the last one sent (a notify can carry several commits' worth)
                        for ev in fetch(last):
                            last = ev["id"]
                            self._publish(ev)
            except Exception:  # reconnect after a database restart
                log.exception("stream listener lost its connection; reconnecting")
                threading.Event().wait(2)


def _offer(q: EventQueue, ev: Event) -> None:
    if q.full():  # a client that stops reading loses the oldest events, not the server's memory
        q.get_nowait()
    q.put_nowait(ev)


BROKER = Broker()


def visible(p: auth.Principal, ev: Event) -> bool:
    if ev["tenant"] is not None and not can_see_case(p.account, p.ctx, {"owner": ev["tenant"], "location": ev["location"] or ""}):
        return False
    kind = ev["kind"]
    if kind == "sync":
        return policy.can_page(p.account, "integration")
    if kind == "notification":
        return ev["payload"].get("to") == p.account.id or p.account.role == "Admin"
    if kind == "workflow":
        return policy.can_page(p.account, "integration", "studio")
    return True


def sse(ev: Event) -> str:
    data = {k: ev[k] for k in ("id", "kind", "case_id", "at", "payload")}
    return f"id: {ev['id']}\nevent: {ev['kind']}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def principal(authorization: str | None, ticket: str | None) -> auth.Principal:
    """A bearer access token (non-browser clients) or a stream ticket (?ticket=); each is checked for its audience."""
    with SessionLocal() as s:
        if authorization and authorization.lower().startswith("bearer "):
            return auth.principal(HTTPAuthorizationCredentials(scheme="Bearer", credentials=authorization[7:]), s)
        if ticket:
            return auth.stream_principal(ticket, s)
    raise HTTPException(401, {"code": "unauthenticated", "message": "Sign in first."})


async def events(p: auth.Principal, resume: int | None, disconnected: Callable[[], Awaitable[bool]]) -> AsyncIterator[str]:
    """The SSE lines for one open stream: the missed events after `resume` (if given), then every new event the
    account may see, with a heartbeat comment every HEARTBEAT_S seconds, until `disconnected()` says so."""
    q = BROKER.subscribe()  # subscribe before replaying, so nothing falls between the two
    sent = 0
    try:
        if resume is not None:
            for ev in await asyncio.to_thread(fetch, resume):
                sent = ev["id"]
                if visible(p, ev):
                    yield sse(ev)
        else:
            sent = await asyncio.to_thread(latest_id)
        yield f": connected as {p.account.id}\n\n"
        while not await disconnected():
            try:
                ev = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_S)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if ev["id"] <= sent:
                continue
            sent = ev["id"]
            if visible(p, ev):
                yield sse(ev)
    finally:
        BROKER.unsubscribe(q)
