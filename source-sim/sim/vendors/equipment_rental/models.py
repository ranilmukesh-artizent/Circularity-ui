"""The equipment rental mock's table (schema `equipment_rental`): every document the API serves, by kind and key."""

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="equipment_rental")

DOC = Table(
    "doc",
    metadata,
    Column("kind", String(20), primary_key=True),  # off_rent, utilisation, price, damage, plan, idle
    Column("key", String(60), primary_key=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)
