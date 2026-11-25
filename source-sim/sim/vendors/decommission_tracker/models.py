"""The decommission tracker mock's tables (schema `decommission_tracker`): the removal jobs and the site demand, each
document as JSON."""

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="decommission_tracker")

REMOVAL_JOB = Table(
    "removal_job",
    metadata,
    Column("job_id", String(20), primary_key=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)

SITE_DEMAND = Table(
    "site_demand",
    metadata,
    Column("demand_id", String(20), primary_key=True),
    Column("doc", JSONB, nullable=False),
)
