"""AWS IoT Core data in Postgres schema `aws_iot` (docs/BACKEND_STEPS.md, B5c).

Control-plane objects (things, thing groups, topic rules, jobs) are stored as the JSON the API returns (`doc`), with the
columns the API filters and sorts on. Shadows keep their state and metadata documents; retained messages their payload
bytes. Times are UTC.
"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, LargeBinary, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="aws_iot")

THING = Table(
    "thing",
    metadata,
    Column("thing_name", String(128), primary_key=True),  # cm-mtr-2041
    Column("thing_type", String(128), nullable=False),
    Column("asset_tag", String(40), nullable=False, index=True),  # attributes.assetTag, e.g. MTR-2041
    Column("fleet", String(40), nullable=False),  # the topic's fleet segment: motors | pumps
    Column("online", Boolean, nullable=False),  # publishes telemetry on the simulated clock
    Column("doc", JSONB, nullable=False),  # DescribeThing
    # the simulated machine behind the device (baseline vibration, temperature, duty, wear trend); never served
    Column("profile", JSONB, nullable=False),
)

THING_GROUP = Table(
    "thing_group",
    metadata,
    Column("group_name", String(128), primary_key=True),
    Column("parent", String(128)),
    Column("doc", JSONB, nullable=False),  # DescribeThingGroup
)

GROUP_MEMBER = Table(
    "group_member",
    metadata,
    Column("group_name", String(128), primary_key=True),
    Column("thing_name", String(128), primary_key=True),
)

SHADOW = Table(
    "shadow",
    metadata,
    Column("thing_name", String(128), primary_key=True),
    Column("shadow_name", String(64), primary_key=True),  # "" is the classic (unnamed) shadow
    Column("state", JSONB, nullable=False),  # {"desired": {...}, "reported": {...}}
    Column("metadata", JSONB, nullable=False),  # the same shape, each leaf {"timestamp": epoch seconds}
    Column("version", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

RETAINED = Table(
    "retained",
    metadata,
    Column("topic", String(256), primary_key=True),
    Column("payload", LargeBinary, nullable=False),
    Column("qos", Integer, nullable=False),
    Column("last_modified", BigInteger, nullable=False),  # epoch milliseconds (lastModifiedTime)
)

RULE = Table(
    "topic_rule",
    metadata,
    Column("rule_name", String(128), primary_key=True),
    Column("topic_filter", String(256), nullable=False),  # the FROM clause of the rule's SQL
    Column("disabled", Boolean, nullable=False),
    Column("doc", JSONB, nullable=False),  # GetTopicRule
)

JOB = Table(
    "job",
    metadata,
    Column("job_id", String(64), primary_key=True),
    Column("status", String(20), nullable=False),
    Column("doc", JSONB, nullable=False),  # DescribeJob .job
)
