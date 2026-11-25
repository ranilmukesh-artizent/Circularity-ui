"""The dealer mock's tables (schema `dealer_dms`).

`record`: every read document (trade-ins, lots, lot sales, stock, bids) as JSON with the columns the filters use.
`written`: the documents the POST routes created; (kind, idem_key) is unique, so one key makes one document.
"""

from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, String, Table, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="dealer_dms")

RECORD = Table(
    "record",
    metadata,
    Column("kind", String(20), primary_key=True),  # trade-ins | lots | lot-sales | partner-bids | stock
    Column("rec_id", String(40), primary_key=True),
    Column("ord", Integer, nullable=False),  # the order the API lists them in
    Column("vin", String(17), index=True),
    Column("lot_id", String(10)),
    Column("segment", String(20)),
    Column("mileage_band", String(10)),
    Column("doc", JSONB, nullable=False),
)

WRITTEN = Table(
    "written",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("kind", String(20), nullable=False),  # recon-orders | transfers | listings | dealer-trades
    Column("seq", Integer, nullable=False),  # 1, 2 ... within the kind (the number in the document's id)
    Column("idem_key", String(200)),
    Column("doc", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("kind", "idem_key", name="written_kind_idem_key"),
)
