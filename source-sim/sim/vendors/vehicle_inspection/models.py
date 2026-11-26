"""The vehicle inspection mock's tables (schema `vehicle_inspection`).

`inspection`: one row per VIN, the document as the API serves it. `battery_assessment`: the assessments posted since
the last reset; one `Idempotency-Key` makes one assessment.
"""

from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="vehicle_inspection")

INSPECTION = Table(
    "inspection",
    metadata,
    Column("inspection_id", String(20), primary_key=True),
    Column("vin", String(17), nullable=False, unique=True),
    Column("doc", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, index=True),
)

BATTERY_ASSESSMENT = Table(
    "battery_assessment",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("assessment_id", String(20), nullable=False, unique=True),
    Column("seq", Integer, nullable=False),
    Column("vin", String(17), nullable=False, index=True),
    Column("idem_key", String(200)),
    Column("doc", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, index=True),
    UniqueConstraint("idem_key", name="battery_assessment_idem_key"),
)
