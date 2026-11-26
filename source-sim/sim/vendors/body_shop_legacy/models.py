"""The legacy body-shop mock's table (schema `body_shop_legacy`): one row per repair, the document as JSON."""

from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="body_shop_legacy")

REPAIR = Table(
    "repair",
    metadata,
    Column("n", Integer, primary_key=True),  # the order the system lists them in
    Column("repair_id", String(12), nullable=False, unique=True),
    Column("vin", String(17), nullable=False, index=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)
