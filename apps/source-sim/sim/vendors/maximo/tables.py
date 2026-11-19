"""IBM Maximo Manage data in Postgres schema `maximo` (docs/BACKEND_STEPS.md, B5).

Table and column names are Maximo's (ASSET, ASSETMETER, ASSETSPEC, WORKORDER, WOSTATUS, FAILUREREPORT), lower case,
so an OSLC attribute name is the column name. Money is in the base currency (USD); times are stored in UTC and
returned in the server's time zone (Asia/Kolkata, +05:30) as Maximo does.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

metadata = MetaData(schema="maximo")

ASSET = Table(
    "asset",
    metadata,
    Column("assetuid", BigInteger, primary_key=True),
    Column("assetnum", String(25), nullable=False),  # MTR-2041: the demo's asset id
    Column("siteid", String(8), nullable=False),  # WH01, WH02, RC01, ST01..ST08
    Column("orgid", String(8), nullable=False),
    Column("location", String(12)),  # WH01-RTN, ST03-PROD
    Column("description", String(100)),
    Column("assettype", String(16)),  # MOTOR, PUMP, ...
    Column("status", String(20), nullable=False),  # OPERATING, NOT READY, LIMITEDUSE, BROKEN, DECOMMISSIONED
    Column("statusdate", DateTime(timezone=True)),
    Column("priority", Integer),  # 1 (highest) .. 5
    Column("criticality", Integer),  # 1 .. 10, higher is more critical
    Column("manufacturer", String(40)),
    Column("serialnum", String(30)),
    Column("installdate", DateTime(timezone=True)),
    Column("purchaseprice", Numeric(12, 2)),
    Column("totalcost", Numeric(12, 2)),
    Column("conditioncode", String(4)),  # B+ (grade table v3 maps B+ -> B)
    Column("lastservicedate", DateTime(timezone=True)),
    Column("isrunning", Boolean, nullable=False, default=False),
    Column("pluscustomer", String(40)),  # the owner tenant (Maximo for Service Providers customer)
    Column("changedate", DateTime(timezone=True), nullable=False),
    Column("changeby", String(30)),
    UniqueConstraint("assetnum", "siteid"),
)

ASSETMETER = Table(
    "assetmeter",
    metadata,
    Column("assetmeterid", BigInteger, primary_key=True),
    Column("assetnum", String(25), nullable=False),
    Column("siteid", String(8), nullable=False),
    Column("metername", String(10), nullable=False),  # RUNHOURS
    Column("measureunitid", String(16)),  # HOURS
    Column("lastreading", Numeric(14, 2)),
    Column("lastreadingdate", DateTime(timezone=True)),
)

ASSETSPEC = Table(
    "assetspec",
    metadata,
    Column("assetspecid", BigInteger, primary_key=True),
    Column("assetnum", String(25), nullable=False),
    Column("siteid", String(8), nullable=False),
    Column("assetattrid", String(30), nullable=False),  # RATED_PWR
    Column("numvalue", Numeric(16, 4)),
    Column("alnvalue", String(60)),
    Column("measureunitid", String(16)),  # W, V, RPM
)

WORKORDER = Table(
    "workorder",
    metadata,
    Column("workorderid", BigInteger, primary_key=True),
    Column("wonum", String(10), nullable=False),  # 1048001
    Column("siteid", String(8), nullable=False),
    Column("orgid", String(8), nullable=False),
    Column("description", String(100)),
    Column("status", String(10), nullable=False),  # WAPPR, APPR, WSCH, WMATL, INPRG, COMP, CLOSE, CAN
    Column("statusdate", DateTime(timezone=True)),
    Column("worktype", String(6)),  # CM, PM, INSP, REFURB, TDOWN
    Column("woclass", String(16), nullable=False, default="WORKORDER"),
    Column("wopriority", Integer),
    Column("assetnum", String(25)),
    Column("location", String(12)),
    Column("reportdate", DateTime(timezone=True)),
    Column("reportedby", String(30)),
    Column("targstartdate", DateTime(timezone=True)),
    Column("targcompdate", DateTime(timezone=True)),
    Column("actstart", DateTime(timezone=True)),
    Column("actfinish", DateTime(timezone=True)),
    Column("failurecode", String(8)),  # failure class: MOTOR
    Column("problemcode", String(12)),  # BRG-WEAR
    Column("estlabhrs", Numeric(9, 2)),
    Column("estlabcost", Numeric(12, 2)),
    Column("estmatcost", Numeric(12, 2)),
    Column("actlabhrs", Numeric(9, 2)),
    Column("actlabcost", Numeric(12, 2)),
    Column("actmatcost", Numeric(12, 2)),
    Column("supervisor", String(30)),
    Column("externalrefid", String(20)),  # the case (RT-1048) or the depot-repair document (WO-47034)
    Column("changedate", DateTime(timezone=True), nullable=False),
    Column("changeby", String(30)),
    UniqueConstraint("wonum", "siteid"),
)

WOSTATUS = Table(
    "wostatus",
    metadata,
    Column("wostatusid", BigInteger, primary_key=True, autoincrement=True),
    Column("wonum", String(10), nullable=False),
    Column("siteid", String(8), nullable=False),
    Column("status", String(10), nullable=False),
    Column("changedate", DateTime(timezone=True), nullable=False),
    Column("changeby", String(30)),
    Column("memo", String(100)),
)

FAILUREREPORT = Table(
    "failurereport",
    metadata,
    Column("failurereportid", BigInteger, primary_key=True),
    Column("wonum", String(10), nullable=False),
    Column("siteid", String(8), nullable=False),
    Column("assetnum", String(25)),
    Column("failurecode", String(12), nullable=False),  # BRG-WEAR
    Column("description", String(100)),  # the failure code's description (FAILURECODE.DESCRIPTION)
    Column("type", String(10), nullable=False),  # PROBLEM, CAUSE, REMEDY
    Column("linenum", Integer, nullable=False),
    Column("reportdate", DateTime(timezone=True)),
)
