"""The vehicle recall mock's table (schema `vehicle_recall`): one row per (campaign, VIN), the document as JSON."""

from sqlalchemy import Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="vehicle_recall")

RECALL = Table(
    "recall",
    metadata,
    Column("campaign_id", String(20), primary_key=True),
    Column("vin", String(17), primary_key=True),
    Column("doc", JSONB, nullable=False),  # the bulk-list document exactly as the API serves it
    Column("updated_at", DateTime(timezone=True), nullable=False, index=True),
)
