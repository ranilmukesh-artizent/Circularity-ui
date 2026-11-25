"""The asset management mock's table (schema `medical_asset_mgmt`): one row per device, the document as JSON."""

from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="medical_asset_mgmt")

DEVICE = Table(
    "device",
    metadata,
    Column("tag", String(40), primary_key=True),
    Column("ord", Integer, nullable=False),  # the order the API lists them in
    Column("device_class", String(30), nullable=False, index=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)
