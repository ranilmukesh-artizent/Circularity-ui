"""SAP S/4HANA tables in Postgres schema `s4` (docs/backend-steps.md, B3).

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

BKPF = Table(
    "BKPF",
    metadata,  # accounting document header (journal entries posted through sim/vendors/s4/journal.py, B13)
    Column("BUKRS", String(4), primary_key=True),
    Column("BELNR", String(10), primary_key=True),
    Column("GJAHR", String(4), primary_key=True),
    Column("BLART", String(2)),  # document type, SA = G/L account document
    Column("BLDAT", Date),
    Column("BUDAT", Date),
    Column("MONAT", String(2)),
    Column("XBLNR", String(16), index=True),  # reference document number: the caller's external reference
    Column("BKTXT", String(25)),
    Column("USNAM", String(12)),
    Column("AWTYP", String(5)),
    Column("AWKEY", String(20)),
    Column("MSG_ID", String(35)),  # the SOAP sub-message id that created it (not an SAP column; for tracing)
    Column("CPUTM", DateTime(timezone=True)),  # entry time (CPUDT + CPUTM)
    _changed(),
)

ACDOCA = Table(
    "ACDOCA",
    metadata,  # universal journal: one row per ledger line of a posted journal entry (actual costs; B13)
    Column("RLDNR", String(2), primary_key=True),  # ledger, 0L
    Column("RBUKRS", String(4), primary_key=True),
    Column("GJAHR", String(4), primary_key=True),
    Column("BELNR", String(10), primary_key=True),
    Column("DOCLN", String(6), primary_key=True),
    Column("BUZEI", String(3)),  # accounting document item
    Column("POPER", String(3)),  # posting period
    Column("BLART", String(2)),
    Column("BUDAT", Date),
    Column("BLDAT", Date),
    Column("RACCT", String(10)),  # G/L account
    Column("DRCRK", String(1)),  # S debit, H credit
    Column("WSL", AMT),  # amount in transaction currency (credit negative)
    Column("RWCUR", String(5)),
    Column("HSL", AMT),  # amount in company code currency
    Column("RHCUR", String(5)),
    Column("RCNTR", String(10)),  # cost centre
    Column("PS_POSID", String(24)),  # WBS element (external id)
    Column("MATNR", String(40)),
    Column("WERKS", String(4)),
    Column("SGTXT", String(50)),
    Column("ZUONR", String(18)),  # assignment
    Column("AWTYP", String(5)),  # reference procedure, BKPFF
    Column("AWREF", String(10)),  # reference document
    Column("USNAM", String(12)),
    _changed(),
)

# A_JournalEntryItemBasic reads ACDOCA with the header's reference (BKPF-XBLNR), as the CDS view I_JournalEntryItem does.
JE_ITEM_VIEW_DDL = """
CREATE OR REPLACE VIEW s4."V_JE_ITEM" AS
  SELECT a.*, h."XBLNR", h."BKTXT"
  FROM s4."ACDOCA" a JOIN s4."BKPF" h ON h."BUKRS" = a."RBUKRS" AND h."BELNR" = a."BELNR" AND h."GJAHR" = a."GJAHR"
"""

V_JE_ITEM = Table(
    "V_JE_ITEM",
    MetaData(schema="s4"),  # not created by metadata.create_all: it is the view above
    *[Column(c.name, c.type, primary_key=c.primary_key) for c in ACDOCA.columns],
    Column("XBLNR", String(16)),
    Column("BKTXT", String(25)),
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
    "CREATE SEQUENCE IF NOT EXISTS s4.belnr_seq START 100000000",  # number range 01 for document type SA
    "CREATE SEQUENCE IF NOT EXISTS s4.anek_seq START 100000",  # asset documents (P9-13.1)
]
SEQUENCES = ("rsnum_seq", "mblnr_seq", "belnr_seq", "anek_seq")

# Fixed assets (plan 9, P9-13.1): the asset master (ANLA-like) and the retirement and transfer documents (ANEK-like). The
# book value is the ERP's: a retirement's gain or loss is computed here, never by di.
ANLA = Table(
    "ANLA",
    metadata,
    Column("ANLN1", String(12), primary_key=True),  # asset number
    Column("ASSET_KEY", String(40), nullable=False, unique=True),  # the VIN, serial or tag of the unit
    Column("TXT50", String(50)),
    Column("AK_VALUE", AMT),  # acquisition value
    Column("BOOK_VALUE", AMT),
    Column("WAERS", String(3)),
    Column("LOCATION", String(20)),  # plant, site or cost centre
    Column("STATUS", String(10), nullable=False, server_default="active"),  # active | retired
    _changed(),
)

ANEK = Table(
    "ANEK",
    metadata,
    Column("BELNR", String(12), primary_key=True),  # asset document number
    Column("TYPE", String(10), nullable=False),  # retire | transfer
    Column("XBLNR", String(40), nullable=False, unique=True),  # external reference: one document per reference
    Column("ANLN1", String(12), nullable=False),
    Column("PROCEEDS", AMT),
    Column("BOOK_VALUE", AMT),
    Column("GAIN_LOSS", AMT),
    Column("WAERS", String(3)),
    Column("TO_LOCATION", String(20)),
    Column("BUDAT", Date),
    _changed(),
)
