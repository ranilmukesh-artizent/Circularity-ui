"""SAP Ariba data in Postgres schema `ariba` (docs/backend-steps.md, B4)."""

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, MetaData, Numeric, String, Table

metadata = MetaData(schema="ariba")

SUPPLIERS = Table(
    "suppliers",
    metadata,
    Column("sm_vendor_id", String(20), primary_key=True),  # SUP-88120
    Column("erp_vendor_id", String(10)),  # the S/4 supplier (LFA1-LIFNR)
    Column("name", String(80), nullable=False),
    Column("country", String(2)),
    Column("registration_status", String(20)),  # Registered
    Column("qualification_status", String(20)),  # Qualified
    Column("category", String(60)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

EVENTS = Table(
    "events",
    metadata,
    Column("event_id", String(20), primary_key=True),  # Doc1048
    Column("title", String(120), nullable=False),
    Column("event_type", String(20)),  # RFQ
    Column("status", String(20)),  # Open, Completed
    Column("commodity", String(60)),
    Column("currency", String(3)),
    Column("quantity", Numeric(13, 3)),
    Column("plant", String(4)),
    Column("external_ref", String(40)),  # the S/4 purchase plan it prices (EKKO-EBELN)
    Column("owner", String(60)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("close_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

BIDS = Table(
    "bids",
    metadata,
    Column("bid_id", String(30), primary_key=True),
    Column("event_id", String(20), ForeignKey("ariba.events.event_id"), nullable=False),
    Column("sm_vendor_id", String(20), ForeignKey("ariba.suppliers.sm_vendor_id"), nullable=False),
    Column("unit_price", Numeric(15, 2), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("lead_time_days", Integer, nullable=False),
    Column("valid_until", Date),
    Column("status", String(20)),  # Submitted, Accepted, Rejected
    Column("submitted_at", DateTime(timezone=True), nullable=False),
)

PURCHASE_ORDERS = Table(
    "purchase_orders",
    metadata,
    Column("po_id", String(30), primary_key=True),  # EP49048
    Column("erp_po", String(10)),  # EKKO-EBELN
    Column("event_id", String(20)),
    Column("sm_vendor_id", String(20)),
    Column("status", String(20)),  # Composing, Ordered, Received, Canceled
    Column("amount", Numeric(15, 2)),
    Column("currency", String(3)),
    Column("plant", String(4)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
