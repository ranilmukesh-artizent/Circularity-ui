"""The broker marketplace mock's tables (schema `broker_marketplace`): the bids and cleared sales as JSON, the listings."""

from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="broker_marketplace")

BID = Table(
    "bid",
    metadata,
    Column("bid_id", String(30), primary_key=True),
    Column("model", String(30), nullable=False, index=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)

CLEARED = Table(
    "cleared",
    metadata,
    Column("sale_id", String(30), primary_key=True),
    Column("model", String(30), nullable=False, index=True),
    Column("doc", JSONB, nullable=False),
)

LISTING = Table(
    "listing",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("idem", String(500), nullable=False, unique=True),  # the bid and the sorted serials: the idempotency key
    Column("doc", JSONB, nullable=False),
)
