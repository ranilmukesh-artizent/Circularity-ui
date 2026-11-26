"""The test bench mock's tables (schema `test_bench`): the results as JSON, the wipe jobs, the refurbishment orders and
the teardowns."""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="test_bench")

RESULT = Table(
    "result",
    metadata,
    Column("serial", String(20), primary_key=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)

WIPE_JOB = Table(
    "wipe_job",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("serial", String(20), nullable=False),
    Column("status", String(10), nullable=False),  # running | completed
    Column("doc", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

REFURB_ORDER = Table(
    "refurb_order",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("serial", String(20), nullable=False, unique=True),
    Column("doc", JSONB, nullable=False),
)

TEARDOWN = Table(
    "teardown",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("serial", String(20), nullable=False),
    Column("boards_key", String(200), nullable=False),  # the sorted board ids joined: the idempotency key with the serial
    Column("doc", JSONB, nullable=False),
    UniqueConstraint("serial", "boards_key"),
)
