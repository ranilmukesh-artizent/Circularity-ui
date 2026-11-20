"""MasterControl Quality Excellence data in Postgres schema `mastercontrol` (docs/backend-steps.md, B5b).

One table per object the API serves. Standard InfoCard / record metadata are columns; the site-configured form data
fields (CERT_EXPIRY, REUSE_CLASS, TEST_RESULT ...) are kept in `data_fields` under their configured names, exactly as
the API returns them. Times are UTC, truncated to milliseconds (the API's precision).
"""

from sqlalchemy import Column, Date, DateTime, Integer, MetaData, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="mastercontrol")

DOCUMENT = Table(  # controlled documents: one row per InfoCard revision
    "document",
    metadata,
    Column("infocard_id", String(16), primary_key=True),  # IC-00001
    Column("document_number", String(40), nullable=False),  # POL-REUSE-MTR
    Column("revision", String(10), nullable=False),  # 3.2
    Column("title", String(200), nullable=False),
    Column("infocard_type", String(20), nullable=False),  # Policy | SOP
    Column("lifecycle", String(20), nullable=False),  # Draft | In Approval | Released | Obsolete
    Column("effective_date", Date),  # Released revisions only
    Column("owner", String(80)),
    Column("data_fields", JSONB, nullable=False),  # ASSET_CLASS, REUSE_CLASS, STANDARD_REF
    Column("created_date", DateTime(timezone=True), nullable=False),
    Column("last_modified_date", DateTime(timezone=True), nullable=False),
)

CERTIFICATE = Table(
    "certificate",
    metadata,
    Column("record_id", String(40), primary_key=True),  # CERT-MTR-2041
    Column("certificate_number", String(40), nullable=False),  # QMS-2906
    Column("certificate_type", String(30), nullable=False),  # LIFE_CERTIFICATION | REQUALIFICATION | DATA_ERASURE
    Column("issued_date", Date, nullable=False),
    Column("revoked_date", DateTime(timezone=True)),
    Column("revoke_reason", Text),
    Column("data_fields", JSONB, nullable=False),  # ASSET_ID, CERT_EXPIRY, TEST_RESULT, REUSE_CLASS, ...
    Column("created_by", String(40), nullable=False),
    Column("created_date", DateTime(timezone=True), nullable=False),
    Column("last_modified_date", DateTime(timezone=True), nullable=False),
)

TEST_CRITERION = Table(
    "test_criterion",
    metadata,
    Column("test_id", String(20), primary_key=True),  # TC-MTR-01
    Column("test_name", String(120), nullable=False),
    Column("asset_class", String(20), nullable=False),
    Column("method", Text),
    Column("acceptance_criteria", Text),
    Column("standard_ref", String(40)),
    Column("mandatory_for_routes", JSONB, nullable=False),
    Column("document_number", String(40), nullable=False),
    Column("last_modified_date", DateTime(timezone=True), nullable=False),
)

DEVIATION = Table(
    "deviation",
    metadata,
    Column("deviation_id", String(20), primary_key=True),  # DEV-118
    Column("title", String(200), nullable=False),
    Column("asset_id", String(25)),
    Column("severity", String(10), nullable=False),  # Minor | Major | Critical
    Column("status", String(20), nullable=False),  # Open | Under Review | Closed
    Column("disposition", String(60)),
    Column("approver_name", String(80)),
    Column("opened_date", Date, nullable=False),
    Column("closed_date", Date),
    Column("last_modified_date", DateTime(timezone=True), nullable=False),
)

COUNTER = Table("counter", metadata, Column("name", String(20), primary_key=True), Column("value", Integer, nullable=False))
