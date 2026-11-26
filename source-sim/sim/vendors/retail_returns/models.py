"""The retail returns mock's table (schema `retail_returns`): the returned items as JSON."""

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="retail_returns")

RETURN = Table(
    "return_item",
    metadata,
    Column("item_id", String(20), primary_key=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)
