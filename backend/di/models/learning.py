"""The calibration models fitted on confirmed outcomes (migration 0026; plan 8 MVP-12.2)."""

from sqlalchemy import CheckConstraint, Column, Index, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

model_version = Table(
    "model_version",
    metadata,
    Column("id", Text, primary_key=True),
    Column("template", Text, nullable=False),
    Column("factors", JSONB, nullable=False),  # [{route, cls, factor}]
    Column("status", Text, nullable=False),  # candidate, active, retired
    Column("created_by", Text, nullable=False),
    Column("approved_by", Text),
    Column("metrics", JSONB, nullable=False),
    ts("created_at", now=True),
    Column("kind", Text, nullable=False, server_default=text("'calibration'")),  # what it predicts (0042, P9-3.10)
    CheckConstraint("status IN ('candidate','active','retired')", name="model_version_status"),
    CheckConstraint("kind IN ('calibration','rated_life','price','repair_cost','demand','take_up')", name="model_version_kind"),
    Index("model_version_template_kind_status", "template", "kind", "status"),
)
