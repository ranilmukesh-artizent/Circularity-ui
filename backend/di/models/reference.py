"""Dated currency rates (migration 0017; di/workflow/steps/transform.py x_fx)."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    Numeric,
    Table,
    Text,
)

from di.models.base import metadata

# --- 0017 dated currency rates (plan 6 C4; di/workflow/steps/transform.py x_fx) --------------------------------------

fx_rate = Table(
    "fx_rate",
    metadata,
    Column("date", Date, primary_key=True),
    Column("currency", Text, primary_key=True),
    Column("usd_rate", Numeric(18, 6), nullable=False),  # units of the currency per USD
    CheckConstraint("usd_rate > 0", name="fx_rate_positive"),
)
