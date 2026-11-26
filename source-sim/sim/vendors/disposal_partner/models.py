"""The disposal partner mock's tables (schema `disposal_partner`).

`collection`: one row per booked collection, the document as JSON and the simulated time it was booked (its certificates
follow from the tags and that time). `sanitisation`: one row per tag, `tag` unique, with the simulated time it was requested.
"""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="disposal_partner")

COLLECTION = Table(
    "collection",
    metadata,
    Column("seq", Integer, primary_key=True),  # 1, 2 ... (the number in the document's id)
    Column("doc", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),  # simulated time
)

SANITISATION = Table(
    "sanitisation",
    metadata,
    Column("seq", Integer, primary_key=True),
    Column("tag", String(40), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),  # simulated time
)
