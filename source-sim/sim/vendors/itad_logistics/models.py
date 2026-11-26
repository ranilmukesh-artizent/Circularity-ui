"""The ITAD logistics mock's tables (schema `itad_logistics`): the pickups and the erasure records as JSON."""

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="itad_logistics")

PICKUP = Table(
    "pickup",
    metadata,
    Column("pickup_id", String(20), primary_key=True),
    Column("doc", JSONB, nullable=False),
)

ERASURE = Table(
    "erasure",
    metadata,
    Column("media_serial", String(40), primary_key=True),
    Column("doc", JSONB, nullable=False),
)
