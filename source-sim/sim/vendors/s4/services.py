"""The S/4HANA OData services (API names and property names as in SAP's API Business Hub)."""

from sim.vendors.s4 import models as t
from sim.vendors.s4.odata.service import Nav, ODataService

S, D, DT, DTO, B = "Edm.String", "Edm.Decimal", "Edm.DateTime", "Edm.DateTimeOffset", "Edm.Boolean"


def _build() -> dict[str, ODataService]:
    svc: dict[str, ODataService] = {}

    p = ODataService("API_PRODUCT_SRV")
    p.entity_set(
        "A_Product",
        t.MARA,
        {
            "Product": (t.MARA.c.MATNR, S),
            "ProductType": (t.MARA.c.MTART, S),
            "ProductGroup": (t.MARA.c.MATKL, S),
            "BaseUnit": (t.MARA.c.MEINS, S),
            "ManufacturerNumber": (t.MARA.c.MFRNR, S),
            "CreationDate": (t.MARA.c.ERSDA, DT),
            "LastChangeDateTime": (t.MARA.c.LAST_CHANGE, DTO),
        },
        keys=["Product"],
        navs={
            "to_Description": Nav("A_ProductDescription", [("Product", "Product")]),
            "to_Plant": Nav("A_ProductPlant", [("Product", "Product")]),
            "to_Valuation": Nav("A_ProductValuation", [("Product", "Product")]),
        },
    )
    p.entity_set(
        "A_ProductDescription",
        t.MAKT,
        {
            "Product": (t.MAKT.c.MATNR, S),
            "Language": (t.MAKT.c.SPRAS, S),
            "ProductDescription": (t.MAKT.c.MAKTX, S),
        },
        keys=["Product", "Language"],
    )
    p.entity_set(
        "A_ProductPlant",
        t.MARC,
        {
            "Product": (t.MARC.c.MATNR, S),
            "Plant": (t.MARC.c.WERKS, S),
            "PurchasingGroup": (t.MARC.c.EKGRP, S),
        },
        keys=["Product", "Plant"],
    )
    p.entity_set(
        "A_ProductValuation",
        t.MBEW,
        {
            "Product": (t.MBEW.c.MATNR, S),
            "ValuationArea": (t.MBEW.c.BWKEY, S),
            "ValuationClass": (t.MBEW.c.BKLAS, S),
            "InventoryValuationProcedure": (t.MBEW.c.VPRSV, S),
            "StandardPrice": (t.MBEW.c.STPRS, D),
            "PriceUnitQty": (t.MBEW.c.PEINH, D),
            "Currency": (t.MBEW.c.WAERS, S),
        },
        keys=["Product", "ValuationArea"],
    )
    svc[p.name] = p

    st = ODataService("API_MATERIAL_STOCK_SRV")
    v = t.V_MATL_STK
    st.entity_set(
        "A_MatlStkInAcctMod",
        v,
        {
            "Material": (v.c.MATNR, S),
            "Plant": (v.c.WERKS, S),
            "StorageLocation": (v.c.LGORT, S),
            "InventoryStockType": (v.c.STOCK_TYPE, S),
            "MaterialBaseUnit": (v.c.MEINS, S),
            "MatlWrhsStkQtyInMatlBaseUnit": (v.c.QTY, D),
            "LastChangeDateTime": (v.c.LAST_CHANGE, DTO),
        },
        keys=["Material", "Plant", "StorageLocation", "InventoryStockType"],
    )
    svc[st.name] = st

    po = ODataService("API_PURCHASEORDER_PROCESS_SRV")
    po.entity_set(
        "A_PurchaseOrder",
        t.EKKO,
        {
            "PurchaseOrder": (t.EKKO.c.EBELN, S),
            "PurchaseOrderType": (t.EKKO.c.BSART, S),
            "PurchasingDocumentCategory": (t.EKKO.c.BSTYP, S),
            "Supplier": (t.EKKO.c.LIFNR, S),
            "CompanyCode": (t.EKKO.c.BUKRS, S),
            "DocumentCurrency": (t.EKKO.c.WAERS, S),
            "CreationDate": (t.EKKO.c.AEDAT, DT),
            "LastChangeDateTime": (t.EKKO.c.LAST_CHANGE, DTO),
        },
        keys=["PurchaseOrder"],
        navs={"to_PurchaseOrderItem": Nav("A_PurchaseOrderItem", [("PurchaseOrder", "PurchaseOrder")])},
    )
    po.entity_set(
        "A_PurchaseOrderItem",
        t.EKPO,
        {
            "PurchaseOrder": (t.EKPO.c.EBELN, S),
            "PurchaseOrderItem": (t.EKPO.c.EBELP, S),
            "Material": (t.EKPO.c.MATNR, S),
            "PurchaseOrderItemText": (t.EKPO.c.TXZ01, S),
            "Plant": (t.EKPO.c.WERKS, S),
            "OrderQuantity": (t.EKPO.c.MENGE, D),
            "PurchaseOrderQuantityUnit": (t.EKPO.c.MEINS, S),
            "NetPriceAmount": (t.EKPO.c.NETPR, D),
            "NetPriceQuantity": (t.EKPO.c.PEINH, D),
            "DocumentCurrency": (t.EKPO.c.WAERS, S),
            "PurchasingDocumentDeletionCode": (t.EKPO.c.LOEKZ, S),
            "LastChangeDateTime": (t.EKPO.c.LAST_CHANGE, DTO),
        },
        keys=["PurchaseOrder", "PurchaseOrderItem"],
    )
    svc[po.name] = po

    rs = ODataService("API_RESERVATION_DOCUMENT_SRV")
    rs.entity_set(
        "A_ReservationDocumentHeader",
        t.RKPF,
        {
            "Reservation": (t.RKPF.c.RSNUM, S),
            "GoodsMovementType": (t.RKPF.c.BWART, S),
            "ReservationDate": (t.RKPF.c.RSDAT, DT),
            "IssuingOrReceivingPlant": (t.RKPF.c.UMWRK, S),
            "GoodsRecipientName": (t.RKPF.c.WEMPF, S),
            "YY1_CircularityRef_RSV": (t.RKPF.c.EXT_REF, S),  # key-user extension field: the instruction reference from di
            "LastChangeDateTime": (t.RKPF.c.LAST_CHANGE, DTO),
        },
        keys=["Reservation"],
        navs={"to_ReservationDocumentItem": Nav("A_ReservationDocumentItem", [("Reservation", "Reservation")])},
    )
    rs.entity_set(
        "A_ReservationDocumentItem",
        t.RESB,
        {
            "Reservation": (t.RESB.c.RSNUM, S),
            "ReservationItem": (t.RESB.c.RSPOS, S),
            "Product": (t.RESB.c.MATNR, S),
            "Plant": (t.RESB.c.WERKS, S),
            "StorageLocation": (t.RESB.c.LGORT, S),
            "ResvnItmRequiredQtyInBaseUnit": (t.RESB.c.BDMNG, D),
            "BaseUnit": (t.RESB.c.MEINS, S),
            "MatlCompRequirementDate": (t.RESB.c.BDTER, DT),
            "ReservationItemIsMarkedForDeletion": (t.RESB.c.XLOEK, B),
        },
        keys=["Reservation", "ReservationItem"],
    )
    svc[rs.name] = rs

    md = ODataService("API_MATERIAL_DOCUMENT_SRV")
    md.entity_set(
        "A_MaterialDocumentHeader",
        t.MKPF,
        {
            "MaterialDocument": (t.MKPF.c.MBLNR, S),
            "MaterialDocumentYear": (t.MKPF.c.MJAHR, S),
            "DocumentDate": (t.MKPF.c.BLDAT, DT),
            "PostingDate": (t.MKPF.c.BUDAT, DT),
            "GoodsMovementCode": (t.MKPF.c.GMCODE, S),
            "MaterialDocumentHeaderText": (t.MKPF.c.BKTXT, S),
            "LastChangeDateTime": (t.MKPF.c.LAST_CHANGE, DTO),
        },
        keys=["MaterialDocumentYear", "MaterialDocument"],
        navs={
            "to_MaterialDocumentItem": Nav(
                "A_MaterialDocumentItem",
                [("MaterialDocument", "MaterialDocument"), ("MaterialDocumentYear", "MaterialDocumentYear")],
            ),
        },
    )
    md.entity_set(
        "A_MaterialDocumentItem",
        t.MSEG,
        {
            "MaterialDocument": (t.MSEG.c.MBLNR, S),
            "MaterialDocumentYear": (t.MSEG.c.MJAHR, S),
            "MaterialDocumentItem": (t.MSEG.c.ZEILE, S),
            "GoodsMovementType": (t.MSEG.c.BWART, S),
            "Material": (t.MSEG.c.MATNR, S),
            "Plant": (t.MSEG.c.WERKS, S),
            "StorageLocation": (t.MSEG.c.LGORT, S),
            "IssuingOrReceivingPlant": (t.MSEG.c.UMWRK, S),
            "IssuingOrReceivingStorageLoc": (t.MSEG.c.UMLGO, S),
            "QuantityInEntryUnit": (t.MSEG.c.MENGE, D),
            "EntryUnit": (t.MSEG.c.MEINS, S),
            "DebitCreditCode": (t.MSEG.c.SHKZG, S),
            "Reservation": (t.MSEG.c.RSNUM, S),
            "ReservationItem": (t.MSEG.c.RSPOS, S),
        },
        keys=["MaterialDocumentYear", "MaterialDocument", "MaterialDocumentItem"],
    )
    svc[md.name] = md

    # Journal Entry Item - Read (ACDOCA). Read-only: journal entries are posted through the SOAP service in journal.py.
    je = ODataService("API_JOURNALENTRYITEMBASIC_SRV")
    j = t.V_JE_ITEM
    je.entity_set(
        "A_JournalEntryItemBasic",
        j,
        {
            "SourceLedger": (j.c.RLDNR, S),
            "CompanyCode": (j.c.RBUKRS, S),
            "FiscalYear": (j.c.GJAHR, S),
            "AccountingDocument": (j.c.BELNR, S),
            "LedgerGLLineItem": (j.c.DOCLN, S),
            "Ledger": (j.c.RLDNR, S),
            "AccountingDocumentItem": (j.c.BUZEI, S),
            "FiscalPeriod": (j.c.POPER, S),
            "AccountingDocumentType": (j.c.BLART, S),
            "PostingDate": (j.c.BUDAT, DT),
            "DocumentDate": (j.c.BLDAT, DT),
            "GLAccount": (j.c.RACCT, S),
            "DebitCreditCode": (j.c.DRCRK, S),
            "AmountInTransactionCurrency": (j.c.WSL, D),
            "TransactionCurrency": (j.c.RWCUR, S),
            "AmountInCompanyCodeCurrency": (j.c.HSL, D),
            "CompanyCodeCurrency": (j.c.RHCUR, S),
            "CostCenter": (j.c.RCNTR, S),
            "WBSElement": (j.c.PS_POSID, S),
            "Material": (j.c.MATNR, S),
            "Plant": (j.c.WERKS, S),
            "DocumentItemText": (j.c.SGTXT, S),
            "AssignmentReference": (j.c.ZUONR, S),
            "ReferenceDocumentType": (j.c.AWTYP, S),
            "ReferenceDocument": (j.c.AWREF, S),
            "DocumentReferenceID": (j.c.XBLNR, S),  # the header's reference: our decision / approval reference
            "AccountingDocumentHeaderText": (j.c.BKTXT, S),
            "AccountingDocCreatedByUser": (j.c.USNAM, S),
            "LastChangeDateTime": (j.c.LAST_CHANGE, DTO),
        },
        keys=["SourceLedger", "CompanyCode", "FiscalYear", "AccountingDocument", "LedgerGLLineItem"],
    )
    svc[je.name] = je
    return svc


SERVICES = _build()
