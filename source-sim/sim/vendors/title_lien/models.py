"""The title mock's tables (schema `title_lien`): one row per title (the document as JSON) and the release requests."""

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="title_lien")

TITLE = Table(
    "title",
    metadata,
    Column("vin", String(17), primary_key=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
    Column("updated_at", DateTime(timezone=True), nullable=False, index=True),
)

REQUEST = Table(
    "release_request",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("vin", String(17), nullable=False),
    Column("lien_id", String(20), nullable=False),
    Column("idem_key", String(200)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("idem_key", name="release_request_idem_key"),
)
