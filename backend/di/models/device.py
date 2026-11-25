"""The device-recommerce tables (migration 0047; plan 9 P9-6.2): trade-ins and grading disputes landed from the device
lab, and the market tables (price feed, launches, listings, bids, sales, replacement demand) landed from the device market
(P9-6.3). Core tables, read and written with SQL. Synthetic data; an IMEI is a device identifier, no person is stored."""

from sqlalchemy import Boolean, Column, Date, Index, Integer, Numeric, PrimaryKeyConstraint, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

device_tradein = Table(
    "device_tradein",
    metadata,
    Column("trade_in_id", Text, primary_key=True),
    Column("org_unit_id", Text),
    Column("imei", Text, nullable=False),
    Column("sku", JSONB, nullable=False),
    Column("quote", JSONB, nullable=False),
    Column("partner", Text, nullable=False),
    Column("batch_id", Text),
    Column("bulk", Boolean, nullable=False),
    ts("received_at", nullable=False),
    Column("payout", JSONB),
    Column("case_id", Text),
    Column("source", Text, nullable=False),
    Index("ix_device_tradein_imei", "imei"),
    Index("ix_device_tradein_batch", "batch_id"),
)

device_price_point = Table(
    "device_price_point",
    metadata,
    Column("sku_key", Text, nullable=False),
    Column("grade", Text, nullable=False),
    Column("week", Date, nullable=False),
    Column("price", Numeric(12, 2), nullable=False),
    Column("currency", Text, nullable=False),
    Column("source", Text, nullable=False),
    PrimaryKeyConstraint("sku_key", "grade", "week"),
)

device_launch = Table(
    "device_launch",
    metadata,
    Column("model", Text, nullable=False),
    Column("successor", Text, nullable=False),
    Column("launched_on", Date, nullable=False),
    PrimaryKeyConstraint("model", "launched_on"),
)

device_listing = Table(
    "device_listing",
    metadata,
    Column("listing_id", Text, primary_key=True),
    Column("org_unit_id", Text),
    Column("imei", Text, nullable=False),
    Column("case_id", Text),
    Column("channel", Text, nullable=False),
    Column("price", Numeric(12, 2), nullable=False),
    ts("listed_at", nullable=False),
    Column("offers", Integer, nullable=False),
    Column("status", Text, nullable=False),
    ts("updated_at", nullable=False),
    Index("ix_device_listing_channel_status", "channel", "status"),
)

device_bid = Table(
    "device_bid",
    metadata,
    Column("bid_id", Text, primary_key=True),
    Column("lot_ref", Text, nullable=False),
    Column("buyer_code", Text, nullable=False),
    Column("amount", Numeric(12, 2), nullable=False),
    Column("fees", Numeric(12, 2), nullable=False),
    Column("logistics", Numeric(12, 2), nullable=False),
    ts("received_at", nullable=False),
    Index("ix_device_bid_lot", "lot_ref"),
)

device_sale = Table(
    "device_sale",
    metadata,
    Column("sale_id", Text, primary_key=True),
    Column("listing_id", Text),
    Column("lot_ref", Text),
    Column("imeis", JSONB, nullable=False),
    Column("price", Numeric(12, 2), nullable=False),
    Column("fees", Numeric(12, 2), nullable=False),
    Column("buyer_returns", Numeric(12, 2), nullable=False),
    ts("settled_at", nullable=False),
    Column("case_ids", JSONB, nullable=False),
)

device_dispute = Table(
    "device_dispute",
    metadata,
    Column("id", Text, primary_key=True),
    Column("imei", Text, nullable=False),
    Column("partner", Text, nullable=False),
    Column("reason", Text, nullable=False),
    ts("opened_at", nullable=False),
    Column("outcome", Text, nullable=False),
)

device_replacement_demand = Table(
    "device_replacement_demand",
    metadata,
    Column("id", Text, primary_key=True),
    Column("sku_key", Text, nullable=False),
    Column("grade_min", Text, nullable=False),
    Column("qty", Integer, nullable=False),
    Column("unit_cost", Numeric(12, 2), nullable=False),
    Column("needed_by", Date),
    Column("reserved", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
)

DEVICE_TABLES = (
    device_tradein, device_price_point, device_launch, device_listing, device_bid, device_sale, device_dispute,
    device_replacement_demand,
)  # fmt: skip
