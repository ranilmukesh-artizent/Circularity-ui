"""Work that happens later on the simulated clock (docs/BACKEND_STEPS.md, B6).

A mock registers a handler once, and schedules it when something starts:

    @handler("maximo.complete_workorder")
    def complete(conn, payload): ...           # update the mock's tables, events.emit(...) the completion

    schedule(conn, clock.now(conn) + timedelta(days=3), "maximo.complete_workorder", {"wonum": "1048001"})

`tick()` runs every handler whose time has come, in time order, each in its own transaction. The service calls it
every second; tests call it directly after advancing the clock.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Column, DateTime, MetaData, String, Table, insert, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from sim import clock
from sim.db import engine

log = logging.getLogger("sim.scheduler")

metadata = MetaData(schema="sim")
SCHEDULED = Table(
    "scheduled",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("due_at", DateTime(timezone=True), nullable=False, index=True),
    Column("handler", String(100), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("source", String(40)),  # the system that scheduled it (for reset)
    Column("done", Boolean, nullable=False, server_default=text("false")),
    Column("error", String(500)),
)

Handler = Callable[[Connection, dict[str, Any]], None]
HANDLERS: dict[str, Handler] = {}


def handler(name: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn

    return register


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS sim"))
    metadata.create_all(conn)


def schedule(conn: Connection, due_at: datetime, name: str, payload: dict[str, Any], source: str | None = None) -> None:
    if name not in HANDLERS:
        raise KeyError(f"No scheduler handler {name!r}")
    conn.execute(insert(SCHEDULED).values(due_at=due_at, handler=name, payload=payload, source=source))


def tick(limit: int = 100) -> int:
    """Run due work. Returns how many items ran."""
    ran = 0
    for _ in range(limit):
        with engine.begin() as conn:
            row = conn.execute(
                select(SCHEDULED)
                .where(SCHEDULED.c.done.is_(False), SCHEDULED.c.due_at <= clock.now(conn))
                .order_by(SCHEDULED.c.due_at, SCHEDULED.c.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if row is None:
                return ran
            fn = HANDLERS.get(row.handler)
            try:
                if fn is None:
                    raise KeyError(f"No handler {row.handler!r}")
                with conn.begin_nested():
                    fn(conn, row.payload)
                conn.execute(update(SCHEDULED).where(SCHEDULED.c.id == row.id).values(done=True))
            except Exception as e:  # noqa: BLE001 - recorded on the row; the next item still runs
                log.exception("scheduled %s (%s) failed", row.id, row.handler)
                conn.execute(
                    update(SCHEDULED).where(SCHEDULED.c.id == row.id).values(done=True, error=f"{type(e).__name__}: {e}"[:500])
                )
            ran += 1
    return ran


def pending(conn: Connection) -> list[dict]:
    rows = conn.execute(select(SCHEDULED).where(SCHEDULED.c.done.is_(False)).order_by(SCHEDULED.c.due_at)).all()
    return [
        {"id": r.id, "due_at": r.due_at.isoformat(), "handler": r.handler, "payload": r.payload, "source": r.source} for r in rows
    ]


def clear(conn: Connection, sources: list[str]) -> None:
    conn.execute(text("DELETE FROM sim.scheduled WHERE source = ANY(:s)"), {"s": sources})
