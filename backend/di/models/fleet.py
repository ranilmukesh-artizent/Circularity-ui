"""unit_reservation (migration 0046; plan 9 P9-5.3): a refurbished unit held for one contract refresh swap, once."""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Table, Text, text

from di.models.base import metadata, ts

unit_reservation = Table(
    "unit_reservation",
    metadata,
    Column("unit_id", Text, nullable=False),
    Column("org_unit_id", Text, ForeignKey("org_unit.id"), nullable=False),
    Column("case_id", Text, nullable=False),
    Column("need_id", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_by", Text, nullable=False),
    ts("created_at", now=True),
    CheckConstraint("status IN ('held','released','consumed')", name="unit_reservation_status"),
    Index("ux_unit_reservation_held", "unit_id", unique=True, postgresql_where=text("status = 'held'")),
    Index("ix_unit_reservation_case", "case_id"),
)  # fmt: skip
