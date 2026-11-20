"""The outbox: every change in a mocked system records a business event here (docs/backend-steps.md, B3; delivered
as CloudEvents webhooks in B6)."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table, insert, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

metadata = MetaData(schema="sim")

OUTBOX = Table(
    "outbox",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("source", String(40), nullable=False),  # system id from sim/registry.py, e.g. "erp"
    Column("type", String(200), nullable=False),  # e.g. sap.s4.beh.reservation.v1.Reservation.Created.v1
    Column("subject", String(200)),  # the object, e.g. reservation number
    Column("data", JSONB, nullable=False),
    Column("time", DateTime(timezone=True), nullable=False),
    Column("delivered_at", DateTime(timezone=True)),
)


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS sim"))
    metadata.create_all(conn)


def emit(conn: Connection, source: str, type_: str, subject: str, data: dict[str, Any], at: datetime | None = None) -> None:
    from sim import clock  # simulated time (B6)

    conn.execute(insert(OUTBOX).values(source=source, type=type_, subject=subject, data=data, time=at or clock.now(conn)))
