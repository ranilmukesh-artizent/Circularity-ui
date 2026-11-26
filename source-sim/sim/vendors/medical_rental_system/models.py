"""The rental system mock's tables (schema `medical_rental_system`).

`record`: every read document (hospitals, depots, requests, returns, forecast weeks, turnaround rows) as JSON, with the
columns the filters use. `dispatch`: the documents the POST route created; `req_id` is unique, so one request has one
dispatch.
"""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="medical_rental_system")

RECORD = Table(
    "record",
    metadata,
    Column("kind", String(20), primary_key=True),  # hospitals | depots | requests | returns | forecast | turnaround
    Column("rec_id", String(40), primary_key=True),
    Column("ord", Integer, nullable=False),  # the order the API lists them in
    Column("depot", String(10)),  # returns and turnaround rows
    Column("region", String(10)),  # forecast weeks
    Column("checked_in_at", DateTime(timezone=True)),  # turnaround rows: the window filter
    Column("doc", JSONB, nullable=False),
)

DISPATCH = Table(
    "dispatch",
    metadata,
    Column("seq", Integer, primary_key=True),  # 1, 2 ... (the number in the document's id)
    Column("req_id", String(20), nullable=False, unique=True),
    Column("tag", String(40), nullable=False),
    Column("doc", JSONB, nullable=False),
)
