"""Oracle Lease and Finance Management data in Postgres schema `oracle_lease`, after the EBS tables it stands for:
OKC_K_HEADERS_ALL_B / OKL_K_HEADERS (contracts), OKC_K_LINES_B / OKL_K_LINES (lease asset lines, KLE_ID), the re-lease
opportunities, and OKL_ASSET_RETURNS_B (asset returns). Each row keeps its record (upper-case columns) in `doc`."""

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="oracle_lease")

CONTRACTS = Table(
    "contracts",
    metadata,
    Column("contract_number", String(30), primary_key=True),  # LC-004417
    Column("doc", JSONB, nullable=False),
    Column("last_update_date", DateTime(timezone=True), nullable=False),
)

ASSETS = Table(
    "assets",
    metadata,
    Column("asset_number", String(40), primary_key=True),  # MTR-2041
    Column("doc", JSONB, nullable=False),
    Column("last_update_date", DateTime(timezone=True), nullable=False),
)

RENEWALS = Table(
    "renewals",
    metadata,
    Column("renewal_id", String(40), primary_key=True),
    Column("doc", JSONB, nullable=False),
    Column("last_update_date", DateTime(timezone=True), nullable=False),
)

ASSET_RETURNS = Table(
    "asset_returns",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("kle_id", BigInteger, nullable=False, unique=True),
    Column("doc", JSONB, nullable=False),
    Column("last_update_date", DateTime(timezone=True), nullable=False),
)
