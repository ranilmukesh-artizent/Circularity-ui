"""The spares planning mock's tables (schema `spares_planning`).

`record`: every read document (catalogue, targets, forecast6m, stock) as JSON, in the order the API lists them.
`requisition`: the purchase requisitions; a reduce rewrites the document.
`written`: the answers of the reduce route; (req_id, idem_key) is unique, so one key makes one cut.
"""

from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, String, Table, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="spares_planning")

RECORD = Table(
    "record",
    metadata,
    Column("kind", String(20), primary_key=True),  # catalogue | targets | forecast6m | stock
    Column("rec_id", String(40), primary_key=True),
    Column("ord", Integer, nullable=False),
    Column("doc", JSONB, nullable=False),
)

REQUISITION = Table(
    "requisition",
    metadata,
    Column("req_id", String(20), primary_key=True),
    Column("doc", JSONB, nullable=False),
)

WRITTEN = Table(
    "written",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("req_id", String(20), nullable=False),
    Column("idem_key", String(200), nullable=False),
    Column("doc", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("req_id", "idem_key", name="written_req_idem_key"),
)
