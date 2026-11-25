"""The pricing guide mock's table (schema `vehicle_pricing`): one row per VIN, the document as JSON."""

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="vehicle_pricing")

VALUE = Table(
    "value",
    metadata,
    Column("vin", String(17), primary_key=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)
