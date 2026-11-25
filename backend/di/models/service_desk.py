"""The service desk's data (migration 0043; plan 9 P9-4.1): closed repairs, upgrade offers, refurbished stock and service
tickets, landed by the extra sources `rephist` and `sdesk`. Plain tables: they are not canonical facts."""

from sqlalchemy import BigInteger, Boolean, Column, Date, Index, Integer, Numeric, Table, Text
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

repair_history = Table(
    "repair_history",
    metadata,
    Column("id", Text, primary_key=True),  # the repair number, RH-<n>
    Column("org_unit_id", Text),  # None: shared
    Column("serial", Text),
    Column("model_class", Text),
    Column("age_months", Integer),
    Column("fault_code", Text),
    Column("market", Text),
    Column("parts", JSONB, nullable=False, server_default="[]"),  # [{PART_NUMBER, QUANTITY}]
    Column("labour_hours", Numeric(8, 2)),
    Column("test_fee", Boolean),
    Column("turnaround_days", Integer),
    Column("actual_cost", Numeric(12, 2)),
    Column("currency", Text),
    Column("closed_on", Date, nullable=False),
    Column("source", Text),
    Index("ix_repair_history_key", "model_class", "fault_code", "closed_on"),
)

upgrade_offer = Table(
    "upgrade_offer",
    metadata,
    Column("id", Text, primary_key=True),
    Column("org_unit_id", Text),
    Column("account", Text),
    Column("market", Text),
    Column("model_class", Text),
    Column("offered_on", Date, nullable=False),
    Column("credit_pct", Numeric(5, 4)),
    Column("credit_amount", Numeric(12, 2)),
    Column("currency", Text),
    Column("accepted", Boolean),
    Column("source", Text),
    Index("ix_upgrade_offer_account", "account", "offered_on"),
)

refurb_unit = Table(
    "refurb_unit",
    metadata,
    Column("serial", Text, primary_key=True),
    Column("org_unit_id", Text),
    Column("model_class", Text),
    Column("grade", Text),
    Column("market", Text),
    Column("released_on", Date),
    Column("reserved_case", Text),  # the case holding the unit, None while free
)

service_ticket = Table(
    "service_ticket",
    metadata,
    Column("number", Text, primary_key=True),
    Column("org_unit_id", Text),
    Column("account", Text),
    Column("market", Text),
    Column("site", Text),
    Column("batch_id", Text),
    Column("lines", JSONB, nullable=False, server_default="[]"),
    Column("requester_role", Text),
    Column("loaner_promised", Boolean, nullable=False, server_default="false"),
    ts("opened_at", nullable=False),
    Column("case_id", Text),  # None until a case is opened from the ticket
    Column("source", Text),
)

repair_accuracy = Table(
    "repair_accuracy",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("org_unit_id", Text),  # None: the shared rows only
    Column("as_of", Date, nullable=False),
    Column("model_class", Text, nullable=False),
    Column("n", Integer, nullable=False),
    Column("mae", Numeric(12, 2), nullable=False),
    Column("mae_share", Numeric(6, 4), nullable=False),
    Column("coverage", Numeric(6, 4), nullable=False),
    Column("auto_share", Numeric(6, 4), nullable=False),
    Column("instant", Boolean, nullable=False),
    ts("computed_at", nullable=False, now=True),
    Index("ix_repair_accuracy_class", "model_class", "as_of"),
)
