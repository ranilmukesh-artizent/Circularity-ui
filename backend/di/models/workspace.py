"""Workspace state items and their seed (migration 0006)."""

from sqlalchemy import (
    BigInteger,
    Column,
    Identity,
    Index,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

# --- 0006 workspace state -------------------------------------------------------------------------------------------

state_item = Table(
    "state_item",
    metadata,
    Column("collection", Text, primary_key=True),
    Column("id", Text, primary_key=True),
    Column("seq", BigInteger, Identity(), nullable=False),  # insertion order
    Column("data", JSONB, nullable=False),
    ts("updated_at", now=True),
    Index("ix_state_item_order", "collection", "seq"),
)


state_seed = Table(
    "state_seed",
    metadata,
    Column("collection", Text, primary_key=True),
    ts("at", now=True),
)
