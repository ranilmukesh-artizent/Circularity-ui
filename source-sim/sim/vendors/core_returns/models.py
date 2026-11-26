"""The core returns mock's tables (schema `core_returns`): the returned cores and the dealers' return events as JSON."""

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="core_returns")

CORE = Table(
    "core",
    metadata,
    Column("core_id", String(20), primary_key=True),
    Column("doc", JSONB, nullable=False),
)

DEALER_EVENT = Table(
    "dealer_event",
    metadata,
    Column("core_id", String(20), primary_key=True),
    Column("dealer_id", String(20), nullable=False),
    Column("doc", JSONB, nullable=False),
)
