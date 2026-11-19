"""SAP S/4HANA tables in Postgres schema `s4` (docs/BACKEND_STEPS.md, B3).

Table and column names are SAP's (MARA-MATNR, EKPO-NETPR …), so the field mappings in di read like the real ones.
Every table carries LAST_CHANGE (timestamptz) for delta reads (`LastChangeDateTime gt datetimeoffset'…'`).
"""

from sqlalchemy import Boolean, Column, Date, DateTime, MetaData, Numeric, String, Table, text

metadata = MetaData(schema="s4")


def _changed():
    return Column("LAST_CHANGE", DateTime(timezone=True), nullable=False, server_default=text("now()"))


QTY = Numeric(13, 3)
AMT = Numeric(15, 2)

T001W = Table(
    "T001W",
    metadata,  # plants
    Column("WERKS", String(4), primary_key=True),
    Column("NAME1", String(30)),
    Column("ORT01", String(25)),
    _changed(),
)

LFA1 = Table(
    "LFA1",
    metadata,  # suppliers
    Column("LIFNR", String(10), primary_key=True),
    Column("NAME1", String(35)),
    _changed(),
)

MARA = Table(
    "MARA",
    metadata,  # material master
    Column("MATNR", String(40), primary_key=True),
    Column("MTART", String(4)),
    Column("MATKL", String(9)),
    Column("MEINS", String(3)),
    Column("MFRNR", String(35)),
    Column("ERSDA", Date),
    _changed(),
)

MAKT = Table(
    "MAKT",
    metadata,  # material descriptions
    Column("MATNR", String(40), primary_key=True),
    Column("SPRAS", String(2), primary_key=True),
    Column("MAKTX", String(40)),
    _changed(),
)

MARC = Table(
    "MARC",
    metadata,  # material per plant
    Column("MATNR", String(40), primary_key=True),
    Column("WERKS", String(4), primary_key=True),
    Column("EKGRP", String(3)),
    _changed(),
)

MARD = Table(
    "MARD",
    metadata,  # stock per storage location
    Column("MATNR", String(40), primary_key=True),
    Column("WERKS", String(4), primary_key=True),
    Column("LGORT", String(4), primary_key=True),
    Column("LABST", QTY, nullable=False, server_default="0"),  # unrestricted
    Column("INSME", QTY, nullable=False, server_default="0"),  # in quality inspection
    Column("SPEME", QTY, nullable=False, server_default="0"),  # blocked
    _changed(),
)

MBEW = Table(
    "MBEW",
    metadata,  # valuation
    Column("MATNR", String(40), primary_key=True),
    Column("BWKEY", String(4), primary_key=True),
    Column("BKLAS", String(4)),
    Column("VPRSV", String(1)),
    Column("STPRS", AMT),
    Column("PEINH", Numeric(5, 0)),
    Column("WAERS", String(5)),
    _changed(),
)

EKKO = Table(
    "EKKO",
    metadata,  # purchase order header
    Column("EBELN", String(10), primary_key=True),
    Column("BSTYP", String(1)),
    Column("BSART", String(4)),
    Column("LIFNR", String(10)),
    Column("BUKRS", String(4)),
    Column("WAERS", String(5)),
    Column("AEDAT", Date),
    _changed(),
)

EKPO = Table(
    "EKPO",
    metadata,  # purchase order item
    Column("EBELN", String(10), primary_key=True),
    Column("EBELP", String(5), primary_key=True),
    Column("MATNR", String(40)),
    Column("TXZ01", String(40)),
    Column("WERKS", String(4)),
    Column("MENGE", QTY),
    Column("MEINS", String(3)),
    Column("NETPR", AMT),
    Column("PEINH", Numeric(5, 0)),
    Column("WAERS", String(5)),
    Column("LOEKZ", String(1), server_default=""),
    _changed(),
)

RKPF = Table(
    "RKPF",
    metadata,  # reservation header
    Column("RSNUM", String(10), primary_key=True),
    Column("RSDAT", Date),
    Column("BWART", String(3)),
    Column("UMWRK", String(4)),
    Column("WEMPF", String(12)),
    Column("EXT_REF", String(40)),
    _changed(),
)

RESB = Table(
    "RESB",
    metadata,  # reservation item
    Column("RSNUM", String(10), primary_key=True),
    Column("RSPOS", String(4), primary_key=True),
    Column("MATNR", String(40)),
    Column("WERKS", String(4)),
    Column("LGORT", String(4)),
    Column("BDMNG", QTY),
    Column("MEINS", String(3)),
    Column("BDTER", Date),
    Column("XLOEK", Boolean, server_default=text("false")),
    _changed(),
)

MKPF = Table(
    "MKPF",
    metadata,  # material document header
    Column("MBLNR", String(10), primary_key=True),
    Column("MJAHR", String(4), primary_key=True),
    Column("BLDAT", Date),
    Column("BUDAT", Date),
    Column("GMCODE", String(2)),
    Column("BKTXT", String(25)),
    _changed(),
)

MSEG = Table(
    "MSEG",
    metadata,  # material document item
    Column("MBLNR", String(10), primary_key=True),
    Column("MJAHR", String(4), primary_key=True),
    Column("ZEILE", String(4), primary_key=True),
    Column("BWART", String(3)),
    Column("MATNR", String(40)),
    Column("WERKS", String(4)),
    Column("LGORT", String(4)),
    Column("UMWRK", String(4)),
    Column("UMLGO", String(4)),
    Column("MENGE", QTY),
    Column("MEINS", String(3)),
    Column("SHKZG", String(1)),
    Column("RSNUM", String(10)),
    Column("RSPOS", String(4)),
    _changed(),
)

ACDOCA = Table(
    "ACDOCA",
    metadata,  # universal journal (actual costs; written in B13)
    Column("RLDNR", String(2), primary_key=True),
    Column("RBUKRS", String(4), primary_key=True),
    Column("GJAHR", String(4), primary_key=True),
    Column("BELNR", String(10), primary_key=True),
    Column("DOCLN", String(6), primary_key=True),
    Column("RACCT", String(10)),
    Column("HSL", AMT),
    Column("RHCUR", String(5)),
    Column("MATNR", String(40)),
    Column("WERKS", String(4)),
    Column("BUDAT", Date),
    Column("SGTXT", String(50)),
    _changed(),
)

# Stock by type, as API_MATERIAL_STOCK_SRV reports it: unrestricted (01), quality inspection (02), blocked (07).
STOCK_VIEW_DDL = """
CREATE OR REPLACE VIEW s4."V_MATL_STK" AS
  SELECT d."MATNR", d."WERKS", d."LGORT", t.type AS "STOCK_TYPE", t.qty AS "QTY", m."MEINS", d."LAST_CHANGE"
  FROM s4."MARD" d JOIN s4."MARA" m ON m."MATNR" = d."MATNR"
  CROSS JOIN LATERAL (VALUES ('01', d."LABST"), ('02', d."INSME"), ('07', d."SPEME")) AS t(type, qty)
  WHERE t.qty <> 0 OR t.type = '01'
"""

V_MATL_STK = Table(
    "V_MATL_STK",
    MetaData(schema="s4"),  # not created by metadata.create_all: it is the view above
    Column("MATNR", String(40), primary_key=True),
    Column("WERKS", String(4), primary_key=True),
    Column("LGORT", String(4), primary_key=True),
    Column("STOCK_TYPE", String(2), primary_key=True),
    Column("QTY", QTY),
    Column("MEINS", String(3)),
    Column("LAST_CHANGE", DateTime(timezone=True)),
)

# Number ranges, as in a fresh S/4 client
SEQUENCES_DDL = [
    "CREATE SEQUENCE IF NOT EXISTS s4.rsnum_seq START 100000",
    "CREATE SEQUENCE IF NOT EXISTS s4.mblnr_seq START 4900000000",
]
