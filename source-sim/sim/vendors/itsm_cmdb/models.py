"""The CMDB mock's table (schema `itsm_cmdb`): the configuration items as JSON."""

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="itsm_cmdb")

CI = Table(
    "ci",
    metadata,
    Column("serial", String(20), primary_key=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)
