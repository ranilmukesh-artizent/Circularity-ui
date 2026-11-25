"""The customer overlay of a pack (migration 0031; plan 9 P9-1.3): one row per pack and org unit, the operations in force
(`published`), the operations being worked on (`draft`) and what a rebase onto a newer pack version found."""

from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Integer, Table, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

customer_overlay = Table(
    "customer_overlay",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("pack_key", Text, nullable=False),
    Column("org_unit_id", Text, ForeignKey("org_unit.id"), nullable=False),
    Column("base_version", Text, nullable=False),  # the pack version `published` was made against
    Column("draft", JSONB),
    Column("draft_base_version", Text),
    Column("published", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("status", Text, nullable=False),  # draft, review, pub
    Column("ver", Integer, nullable=False, server_default="0"),
    Column("maker", Text),
    Column("checker", Text),
    Column("conflicts", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("notes", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    ts("updated_at", now=True),
    CheckConstraint("status IN ('draft','review','pub')", name="customer_overlay_status"),
    UniqueConstraint("pack_key", "org_unit_id", name="uq_customer_overlay_pack_org"),
)
