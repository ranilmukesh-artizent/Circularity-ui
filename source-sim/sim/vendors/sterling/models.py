"""IBM Sterling OMS data in Postgres schema `sterling`: the YFS_ORDER_HEADER / YFS_ORDER_LINE pair, cut down to what
the demo reads and writes. Sales orders (DocumentType 0001) and return orders (0003) share both tables, as in Sterling."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

metadata = MetaData(schema="sterling")

ORDER_HEADER = Table(
    "yfs_order_header",
    metadata,
    Column("order_header_key", String(24), primary_key=True),
    Column("order_no", String(40), nullable=False),  # SO-48102, RMA-56509
    Column("enterprise_code", String(24), nullable=False),  # NORTHFIELD
    Column("document_type", String(4), nullable=False),  # 0001 sales, 0003 return
    Column("order_type", String(40)),  # CONTRACT_REPLACEMENT, CUSTOMER_RETURN
    Column("buyer_organization_code", String(24), nullable=False),  # CUSTOMER_A
    Column("order_date", DateTime(timezone=True), nullable=False),
    Column("req_delivery_date", Date),
    Column("ship_to_key", String(24)),  # LOC-CHN-03
    Column("ship_to", JSON),  # PersonInfoShipTo
    Column("receiving_node", String(10)),  # returns: WH01, WH02, RC01
    Column("currency", String(3), nullable=False),
    Column("extn", JSON),
    Column("createts", DateTime(timezone=True), nullable=False),
    Column("modifyts", DateTime(timezone=True), nullable=False),
    UniqueConstraint("enterprise_code", "document_type", "order_no"),
)

ORDER_LINE = Table(
    "yfs_order_line",
    metadata,
    Column("order_line_key", String(28), primary_key=True),
    Column("order_header_key", String(24), ForeignKey("sterling.yfs_order_header.order_header_key"), nullable=False),
    Column("prime_line_no", Integer, nullable=False),
    Column("sub_line_no", Integer, nullable=False),
    Column("line_type", String(24)),  # REPLACEMENT, NEW_EQUIPMENT, RETURN
    Column("item_id", String(40), nullable=False),  # MTR-55KW
    Column("item_desc", String(120)),
    Column("product_class", String(10)),  # NEW, REFURB, RETURN
    Column("uom", String(10), nullable=False),
    Column("ordered_qty", Numeric(14, 2), nullable=False),
    Column("unit_price", Numeric(14, 2)),
    Column("ship_node", String(10)),
    Column("ship_to_key", String(24)),
    Column("req_delivery_date", Date),
    Column("status", String(12), nullable=False),  # see api.STATUS
    Column("accepts_refurbished", Boolean, nullable=False, server_default="false"),
    Column("serial_no", String(40)),  # returns: the returned unit (asset id)
    Column("return_reason", String(24)),
    Column("allocated_serial", String(40), unique=True),  # sales: the returned unit allocated to this line
    Column("reservation", JSON),  # OrderLineReservation
    Column("shipment", JSON),
    Column("pod", JSON),  # proof of delivery
    Column("idempotency_key", String(80)),
    Column("history", JSON, nullable=False),  # OrderStatus records, oldest first
    Column("extn", JSON),
    Column("createts", DateTime(timezone=True), nullable=False),
    Column("modifyts", DateTime(timezone=True), nullable=False),
    UniqueConstraint("order_header_key", "prime_line_no", "sub_line_no"),
)
