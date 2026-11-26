"""The decontamination log mock's table (schema `decon_log`): one row per cycle, the document as the API serves it.

`status` is `done` (listed by GET) or `scheduled` (ends later on the simulated clock; the handler flips it).
"""

from sqlalchemy import Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="decon_log")

CYCLE = Table(
    "cycle",
    metadata,
    Column("cycle_id", String(20), primary_key=True),
    Column("tag", String(40), nullable=False, index=True),
    Column("status", String(10), nullable=False),  # done | scheduled
    Column("ended_at", DateTime(timezone=True), nullable=False),  # the order the API lists them in
    Column("updated_at", DateTime(timezone=True), nullable=False),  # what updatedSince compares
    Column("doc", JSONB, nullable=False),
)
