"""Oracle Depot Repair data in Postgres schema `depot_repair`, after the EBS tables it stands for: CSD_REPAIRS (repair
orders), the repair order's tasks / WIP operations, and the quality results of its bench tests (QA_RESULTS). Each row
keeps its record as the query service returns it (upper-case EBS column names) in `doc`."""

from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, String, Table
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
