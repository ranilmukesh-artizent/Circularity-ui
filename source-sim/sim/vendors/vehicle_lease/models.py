"""The vehicle lease mock's tables (schema `vehicle_lease`).

`lease_return`: one row per lease return, the document as JSON.
`written`: the charges the POST route created (P9-9.20); (kind, idem_key) is unique, so one key makes one charge.
"""

from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, String, Table, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="vehicle_lease")

LEASE_RETURN = Table(
    "lease_return",
    metadata,
    Column("lease_id", String(20), primary_key=True),
    Column("vin", String(17), nullable=False, unique=True),
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
    Column("updated_at", DateTime(timezone=True), nullable=False, index=True),
)

WRITTEN = Table(
    "written",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("kind", String(20), nullable=False),  # charges
    Column("seq", Integer, nullable=False),  # 1, 2 ... within the kind (the number in the document's id)
    Column("idem_key", String(200)),
    Column("doc", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("kind", "idem_key", name="written_kind_idem_key"),
)
