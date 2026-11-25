"""The pack versions (migration 0032; plan 9 P9-1.6): one row per pack key, version and org unit (no org unit: a pack for
every org), with the pack document, its status (draft, review, pub, retired), its maker and checker, and the impact of
publishing it."""

from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

pack_version = Table(
    "pack_version",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("key", Text, nullable=False),
    Column("version", Text, nullable=False),
    Column("org_unit_id", Text, ForeignKey("org_unit.id")),
    Column("doc", JSONB, nullable=False),
    Column("status", Text, nullable=False),  # draft, review, pub, retired
    Column("maker", Text),
    Column("checker", Text),
    Column("note", Text),
    Column("impact", JSONB),  # {changed, total, dv}
    ts("created_at", now=True),
    ts("published_at"),
    CheckConstraint("status IN ('draft','review','pub','retired')", name="pack_version_status"),
    Index("ux_pack_version", "key", "version", text("coalesce(org_unit_id, '')"), unique=True),
)
