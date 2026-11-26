"""The battery management mock's table (schema `battery_bms`): the packs as JSON."""

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="battery_bms")

PACK = Table(
    "pack",
    metadata,
    Column("pack_id", String(20), primary_key=True),
    Column("doc", JSONB, nullable=False),
)
