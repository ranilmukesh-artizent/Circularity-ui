"""The network inventory mock's tables (schema `network_inventory`): the elements as JSON, the transfer orders, the
retirements."""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="network_inventory")

ELEMENT = Table(
    "element",
    metadata,
    Column("serial", String(20), primary_key=True),
    Column("site", String(20), nullable=False, index=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)

TRANSFER_ORDER = Table(
    "transfer_order",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("serial", String(20), nullable=False),
    Column("destination", String(60), nullable=False),  # `site:<id>` or `pool:<id>`: the idempotency key with the serial
    Column("doc", JSONB, nullable=False),
    UniqueConstraint("serial", "destination"),
)

RETIREMENT = Table(
    "retirement",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("serial", String(20), nullable=False, unique=True),
    Column("doc", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
