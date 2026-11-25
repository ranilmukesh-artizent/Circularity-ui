"""Oracle Depot Repair data in Postgres schema `depot_repair`, after the EBS tables it stands for: CSD_REPAIRS (repair
orders), the repair order's tasks / WIP operations, and the quality results of its bench tests (QA_RESULTS). Each row
keeps its record as the query service returns it (upper-case EBS column names) in `doc`."""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="depot_repair")

CSD_REPAIRS = Table(
    "csd_repairs",
    metadata,
    Column("repair_line_id", BigInteger, primary_key=True),
    Column("repair_number", String(30), nullable=False, unique=True),  # RO-61048
    Column("serial_number", String(40), nullable=False, index=True),  # MTR-2041
    Column("doc", JSONB, nullable=False),
    Column("creation_date", DateTime(timezone=True), nullable=False),
    Column("last_update_date", DateTime(timezone=True), nullable=False),
)

CSD_TASKS = Table(
    "csd_tasks",
    metadata,
    Column("task_id", BigInteger, primary_key=True, autoincrement=True),
    Column("repair_line_id", BigInteger, nullable=False, index=True),
    Column("operation_seq_num", Integer, nullable=False),
    Column("doc", JSONB, nullable=False),
    Column("last_update_date", DateTime(timezone=True), nullable=False),
)

QA_RESULTS = Table(
    "qa_results",
    metadata,
    Column("collection_id", BigInteger, primary_key=True, autoincrement=True),
    Column("repair_line_id", BigInteger, nullable=False, index=True),
    Column("doc", JSONB, nullable=False),
    Column("last_update_date", DateTime(timezone=True), nullable=False),
)

# Closed repairs of the last three years and refurbished units released to service (plan 9, P9-4.1), as
# history.generate() makes them; the query service's get_repair_history reads this table.
REPAIR_HISTORY = Table(
    "repair_history",
    metadata,
    Column("seq", BigInteger, primary_key=True, autoincrement=True),
    Column("repair_number", String(30), nullable=False, unique=True),  # RH-1
    Column("model_class", String(8), nullable=False),
    Column("fault_code", String(8)),
    Column("repair_type", String(30), nullable=False),
    Column("date_closed", DateTime(timezone=True), nullable=False),
    Column("doc", JSONB, nullable=False),
    Column("last_update_date", DateTime(timezone=True), nullable=False),
    Index("ix_repair_history_key", "model_class", "fault_code", "date_closed"),
)
