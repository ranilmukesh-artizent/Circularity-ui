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
    Column("pack", Text),  # the pack the model serves (0059, P9-13.8)
    ts("trained_at"),
    Column("data_window", JSONB),  # {from, to, n} of the rows it was fitted on
    Column("quality", JSONB),  # {mae, mae_active, n}
    Column("drift", JSONB),  # the last check: {psi, ratio, status, rule, n_new, checked_at, explanation}
    Column("drift_status", Text),  # ok, watch, alert
    Column("cadence", Text),
    ts("next_due"),
    CheckConstraint("status IN ('candidate','active','retired')", name="model_version_status"),
    CheckConstraint("drift_status IS NULL OR drift_status IN ('ok','watch','alert')", name="model_version_drift_status"),
    CheckConstraint("kind IN ('calibration','rated_life','price','repair_cost','demand','take_up')", name="model_version_kind"),
    Index("model_version_template_kind_status", "template", "kind", "status"),
)
