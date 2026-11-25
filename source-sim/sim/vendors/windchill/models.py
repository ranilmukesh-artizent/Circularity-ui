"""The Windchill mock's tables (schema `windchill`): parts (WTPart, latest iteration) and their usage links.

A usage link (WTPartUsageLink) runs from a parent part version to the child's master, i.e. its number, as Windchill
holds it: the structure resolves the child to its current version when it is read.
"""

from sqlalchemy import Boolean, Column, Float, Integer, MetaData, String, Table

metadata = MetaData(schema="windchill")

WTPART = Table(
    "wtpart",
    metadata,
    Column("id", String(40), primary_key=True),  # OR:wt.part.WTPart:<n>
    Column("number", String(40), nullable=False, unique=True),
    Column("name", String(120), nullable=False),
    Column("version", String(8), nullable=False),  # A, B, C ...
    Column("iteration", String(8), nullable=False),  # 1, 2 ...
    Column("state", String(20), nullable=False),  # INWORK, RELEASED, OBSOLETE
    Column("unit_cost", Float, nullable=False),
    # soft attributes of the tool classes (P9-3.3), null on the industrial parts
    Column("rated_life_hours", Float),
    Column("criticality_weight", Float),
    Column("critical", Boolean),
    Column("end_of_parts_date", String(10)),  # ISO date
    Column("successor_number", String(40)),
    Column("tool_class", String(8)),
)

USAGE = Table(
    "wtpartusagelink",
    metadata,
    Column("id", String(48), primary_key=True),  # OR:wt.part.WTPartUsageLink:<n>
    Column("parent_id", String(40), nullable=False, index=True),
    Column("child_number", String(40), nullable=False),
    Column("quantity", Float, nullable=False),
    Column("line_number", Integer, nullable=False),
)
