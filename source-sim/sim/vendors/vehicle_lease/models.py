"""The vehicle lease mock's table (schema `vehicle_lease`): one row per lease return, the document as JSON."""

from sqlalchemy import Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="vehicle_lease")

LEASE_RETURN = Table(
    "lease_return",
    metadata,
    Column("lease_id", String(20), primary_key=True),
    Column("vin", String(17), nullable=False, unique=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
    Column("updated_at", DateTime(timezone=True), nullable=False, index=True),
)
