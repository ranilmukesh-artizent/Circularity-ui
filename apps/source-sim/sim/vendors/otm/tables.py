"""OTM data in Postgres schema `otm`. Every business object (location, service provider, rate offering, lane, rate
record, order release, shipment) is one row of OBJECT holding its REST representation, child collections included
(refnums, stops, statuses, costs, ...); tracking events (IE_SHIPMENTSTATUS) have their own table, as in OTM."""

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="otm")

OBJECT = Table(
    "object",
    metadata,
    Column("resource", String(40), primary_key=True),  # locations, serviceProviders, rateOfferings, xLanes, rateGeos, ...
    Column("gid", String(120), primary_key=True),  # NORTHFIELD.LD-21048
    Column("xid", String(100), nullable=False),
    Column("doc", JSONB, nullable=False),  # the REST representation without insertDate / updateDate / links
    Column("insert_date", DateTime(timezone=True), nullable=False),
    Column("update_date", DateTime(timezone=True), nullable=False),
)

TRACKING_EVENT = Table(
    "tracking_event",
    metadata,
    Column("i_transaction_no", BigInteger, primary_key=True, autoincrement=True),
    Column("shipment_gid", String(120), nullable=False, index=True),
    Column("doc", JSONB, nullable=False),
    Column("insert_date", DateTime(timezone=True), nullable=False),
    Column("update_date", DateTime(timezone=True), nullable=False),
)
