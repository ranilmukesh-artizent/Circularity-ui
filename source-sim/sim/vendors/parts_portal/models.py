"""The parts supplier portal mock's table (schema `parts_portal`): one row per part of a device model, the document as JSON."""

from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="parts_portal")

PART = Table(
    "part",
    metadata,
    Column("model", String(60), primary_key=True),
    Column("part_no", String(40), primary_key=True),
    Column("ord", Integer, nullable=False),  # the order the API lists them in
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)
