"""The biomedical service mock's tables (schema `biomed_service`): documents as JSON, plus the service orders written."""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="biomed_service")

SERVICE = Table(
    "service",
    metadata,
    Column("tag", String(40), primary_key=True),
    Column("ord", Integer, nullable=False),  # the order the API lists them in
    Column("doc", JSONB, nullable=False),
)
CORRECTION = Table(
    "correction",
    metadata,
    Column("notice_id", String(40), primary_key=True),
    Column("ord", Integer, nullable=False),
    Column("doc", JSONB, nullable=False),
)
ASSESSMENT = Table(
    "assessment",
    metadata,
    Column("tag", String(40), primary_key=True),
    Column("ord", Integer, nullable=False),
    Column("doc", JSONB, nullable=False),
)
SERVICE_ORDER = Table(
    "service_order",
    metadata,
    Column("seq", Integer, primary_key=True),  # 1, 2 ... (the number in the order id)
    Column("tag", String(40), nullable=False),
    Column("kind", String(20), nullable=False),  # pm | certification | repair | refurbish
    Column("due_by", String(10), nullable=False),
    Column("doc", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("tag", "kind", "due_by", name="service_order_natural_key"),
)
