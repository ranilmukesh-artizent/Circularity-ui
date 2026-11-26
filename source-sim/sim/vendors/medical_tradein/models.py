"""The trade-in register mock's table (schema `medical_tradein`): the trade-ins as JSON."""

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="medical_tradein")

TRADEIN = Table(
    "tradein",
    metadata,
    Column("tag", String(20), primary_key=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)
