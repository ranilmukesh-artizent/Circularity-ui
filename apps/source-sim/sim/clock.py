"""The simulated clock (docs/backend-steps.md, B6).

Simulated time starts at the demo's as-of time (7 Oct 2026, 09:00 UTC) and runs at `speed` × wall time from there.
`advance()` jumps it forward, so "the work order completes in 3 days" can be played in seconds. Every mock stamps
its changes with `now()`, and scheduled work (sim/scheduler.py) fires when simulated time reaches it.
The state lives in Postgres (sim.clock), so every process sees the same time.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Column, DateTime, Float, Integer, MetaData, Table, insert, select, text, update
from sqlalchemy.engine import Connection

from sim.db import engine

AS_OF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)

metadata = MetaData(schema="sim")
CLOCK = Table(
    "clock",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("anchor_sim", DateTime(timezone=True), nullable=False),  # simulated time at anchor_wall
    Column("anchor_wall", DateTime(timezone=True), nullable=False),
    Column("speed", Float, nullable=False),  # simulated seconds per wall second; 0 = paused
)


def _wall() -> datetime:
    return datetime.now(UTC)


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS sim"))
    metadata.create_all(conn)
    if conn.execute(select(CLOCK.c.id)).first() is None:
        conn.execute(insert(CLOCK).values(id=1, anchor_sim=AS_OF, anchor_wall=_wall(), speed=1.0))


def _row(conn: Connection):
    return conn.execute(select(CLOCK).where(CLOCK.c.id == 1)).one()


def now(conn: Connection | None = None) -> datetime:
    """Current simulated time."""
    if conn is None:
        with engine.connect() as c:
            return now(c)
    r = _row(conn)
    return r.anchor_sim + (_wall() - r.anchor_wall) * r.speed


def state(conn: Connection) -> dict:
    r = _row(conn)
    return {"now": now(conn).isoformat(), "speed": r.speed, "as_of": AS_OF.isoformat()}


def _rebase(conn: Connection, sim_time: datetime, speed: float) -> None:
    conn.execute(update(CLOCK).where(CLOCK.c.id == 1).values(anchor_sim=sim_time, anchor_wall=_wall(), speed=speed))


def advance(conn: Connection, delta: timedelta) -> datetime:
    if delta < timedelta(0):
        raise ValueError("The clock only moves forward")
    target = now(conn) + delta
    _rebase(conn, target, _row(conn).speed)
    return target


def set_speed(conn: Connection, speed: float) -> None:
    if speed < 0:
        raise ValueError("Speed must be 0 (paused) or more")
    _rebase(conn, now(conn), speed)


def reset(conn: Connection) -> None:
    _rebase(conn, AS_OF, 1.0)
