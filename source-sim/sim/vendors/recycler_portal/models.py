"""The recycler portal mock's tables (schema `recycler_portal`): the recyclers, the pickups, the disposal certificates."""

from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table, text
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="recycler_portal")

VENDOR = Table(
    "vendor",
    metadata,
    Column("vendor_id", String(20), primary_key=True),
    Column("lapsed", Boolean, nullable=False, server_default=text("false")),  # the certificate has lapsed (not served)
    Column("doc", JSONB, nullable=False),  # the document exactly as the API serves it
)

PICKUP = Table(
    "pickup",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("idem", String(500), nullable=False, unique=True),  # the vendor and the sorted serials: the idempotency key
    Column("doc", JSONB, nullable=False),
)

CERTIFICATE = Table(
    "certificate",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("serial", String(30), nullable=False, index=True),
    Column("pickup_id", String(20), nullable=False, index=True),
    Column("doc", JSONB, nullable=False),
)
