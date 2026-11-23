"""The Modeler's process flows (migration 0021; plan 8 MVP-3.1): one flow per template and org unit, and the graphs
each publish replaced."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

# --- 0021 decision flows (seeded: one published default flow per template on `workspace`) ---------------------------

decision_flow = Table(
    "decision_flow",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("template_key", Text, nullable=False),
    Column("org_unit_id", Text, ForeignKey("org_unit.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("status", Text, nullable=False),  # draft, review, shadow, pub
    Column("ver", Integer, nullable=False),
    Column("dver", Integer),
    Column("maker", Text),
    Column("checker", Text),
    Column("draft", JSONB),
    Column("published", JSONB, nullable=False),
    ts("updated_at", now=True),
    CheckConstraint("status IN ('draft','review','shadow','pub')", name="decision_flow_status"),
    UniqueConstraint("template_key", "org_unit_id", name="uq_decision_flow_template_org"),
)

decision_flow_version = Table(
    "decision_flow_version",
    metadata,
    Column("flow_id", BigInteger, ForeignKey("decision_flow.id"), primary_key=True),
    Column("ver", Integer, primary_key=True),
    Column("graph", JSONB, nullable=False),
    Column("published_by", Text),
    ts("published_at"),
    Column("note", Text),
)
