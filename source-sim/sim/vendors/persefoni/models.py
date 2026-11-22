"""Persefoni data in Postgres schema `persefoni` (docs/backend-steps.md, B5b).

Each object is stored as the JSON document the API returns (`doc`), with the columns the API filters and sorts on.
Times are UTC, truncated to milliseconds.
"""

from sqlalchemy import Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="persefoni")

EMISSION_FACTOR = Table(
    "emission_factor",
    metadata,
    Column("id", String(60), primary_key=True),  # ef_embodied_motor, ef_route_redeploy
    Column("doc", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

ACTIVITY = Table(
    "activity",
    metadata,
    Column("id", String(60), primary_key=True),  # act_RT-1048_1, act_CS-2001
    Column("doc", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

FOOTPRINT = Table(  # one calculated footprint per activity
    "footprint",
    metadata,
    Column("id", String(60), primary_key=True),  # fp_RT-1048_1, fp_CS-2001
    Column("activity_id", String(60), nullable=False, unique=True),
    Column("doc", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
