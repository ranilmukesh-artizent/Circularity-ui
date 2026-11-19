"""B13b contract tests: post actual cost journal entries to the S/4HANA mock the way an SAP SOAP client does
("Journal Entry - Post", JournalEntryCreateRequestConfirmation_In), then read them back through
API_JOURNALENTRYITEMBASIC_SRV (docs/BACKEND_STEPS.md)."""

from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.db import engine
from sim.main import app

AUTH = ("DI_CONNECTOR", "Circularity-demo-1")
POST = "/sap/bc/srt/scs_ext/sap/journalentrycreaterequestconfi"
READ = "/sap/opu/odata/sap/API_JOURNALENTRYITEMBASIC_SRV/A_JournalEntryItemBasic"
EVENT = "sap.s4.beh.journalentry.v1.JournalEntry.Created.v1"
XML = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": "http://sap.com/xi/SAPSCORE/SFIN/JournalEntryCreateRequestConfirmation_In/JournalEntryCreateRequestConfirmation_InRequest",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "erp"}).raise_for_status()
        yield c
        c.post("/_sim/reset", params={"system": "erp"}).raise_for_status()


def item(n, account, amount, currency="INR", **extra) -> str:
    assign = ""
    if extra.get("cost_center") or extra.get("wbs"):
        cc = f"<CostCenter>{extra['cost_center']}</CostCenter>" if extra.get("cost_center") else ""
        wbs = f"<WBSElement>{extra['wbs']}</WBSElement>" if extra.get("wbs") else ""
        assign = f"<AccountAssignment>{cc}{wbs}</AccountAssignment>"
    tags = "".join(f"<{k}>{v}</{k}>" for k, v in extra.items() if k[0].isupper())
    return (
        f"<Item><ReferenceDocumentItem>{n}</ReferenceDocumentItem><GLAccount>{account}</GLAccount>"
        f'<AmountInTransactionCurrency currencyCode="{currency}">{amount}</AmountInTransactionCurrency>'
        f"{tags}{assign}</Item>"
    )


def envelope(ref: str | None, items: list[str], company="1000", posting="2026-10-20", msg="JE-1") -> str:
    xblnr = f"<DocumentReferenceID>{ref}</DocumentReferenceID>" if ref else ""
    return (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:sfin="http://sap.com/xi/SAPSCORE/SFIN"><soapenv:Header/><soapenv:Body>'
        "<sfin:JournalEntryBulkCreateRequest>"
        f"<MessageHeader><ID>BULK-{msg}</ID><CreationDateTime>2026-10-20T10:00:00Z</CreationDateTime></MessageHeader>"
        "<JournalEntryCreateRequest>"
        f"<MessageHeader><ID>{msg}</ID><CreationDateTime>2026-10-20T10:00:00Z</CreationDateTime></MessageHeader>"
        "<JournalEntry><OriginalReferenceDocumentType>BKPFF</OriginalReferenceDocumentType>"
        "<BusinessTransactionType>RFBU</BusinessTransactionType><AccountingDocumentType>SA</AccountingDocumentType>"
        f"{xblnr}<DocumentHeaderText>Actual costs RT-1048</DocumentHeaderText>"
        f"<CompanyCode>{company}</CompanyCode><DocumentDate>{posting}</DocumentDate><PostingDate>{posting}</PostingDate>"
        + "".join(items)
        + "</JournalEntry></JournalEntryCreateRequest></sfin:JournalEntryBulkCreateRequest>"
        "</soapenv:Body></soapenv:Envelope>"
    )


def confirmations(r) -> list[dict]:
    """The JournalEntryCreateConfirmation entries of a reply: document, company code, year, severity, log notes."""
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/xml")
    root = ET.fromstring(r.content)
    out = []
    for conf in root.iter("JournalEntryCreateConfirmation"):
        inner = conf.find("JournalEntryCreateConfirmation")
        if inner is None:
            continue
        log = conf.find("Log")
        out.append(
            {
                "doc": inner.findtext("AccountingDocument"),
                "bukrs": inner.findtext("CompanyCode"),
                "year": inner.findtext("FiscalYear"),
                "severity": log.findtext("MaximumLogItemSeverityCode"),
                "log": [(i.findtext("TypeID"), i.findtext("Note")) for i in log.findall("Item")],
            }
        )
    return out


def events(ref: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT data FROM sim.outbox WHERE source = 'erp' AND type = :t AND data->>'DocumentReferenceID' = :r"),
            {"t": EVENT, "r": ref},
        )
        return [r.data for r in rows]


RT_1048_LINES = [
    item(
        1, "51000000", "41750.00", Material="MTR-2041", Plant="2030", DocumentItemText="Repair labour RT-1048", cost_center="RC01"
    ),
    item(2, "51100000", "8350.00", Material="MTR-2041", Plant="2030", DocumentItemText="Transport RT-1048", wbs="RT-1048.EX"),
    item(3, "21100000", "-50100.00", DocumentItemText="Accrual RT-1048", AssignmentReference="APR-2026-10-0161"),
]


# ---------------- security
def test_requires_authentication(client):
    body = envelope("APR-AUTH", RT_1048_LINES)
    r = client.post(POST, content=body, headers=XML)
    assert r.status_code == 401 and "SAP NetWeaver" in r.headers["www-authenticate"]
    assert client.post(POST, content=body, headers=XML, auth=("DI_CONNECTOR", "wrong")).status_code == 401


def test_not_a_soap_request_is_a_fault(client):
    r = client.post(POST, content="not xml", headers=XML, auth=AUTH)
    assert r.status_code == 500 and "<faultstring" in r.text
    r = client.post(POST, content=envelope("X", []).replace("JournalEntryBulkCreateRequest", "Nope"), headers=XML, auth=AUTH)
    assert r.status_code == 500 and "Nope" in r.text


# ---------------- post, duplicate, read back, event
def test_post_rt_1048_actuals_then_duplicate_then_read_back(client):
    before = datetime.fromisoformat(client.get("/_sim/clock").json()["now"])
    # Basic auth, no CSRF token: the SOAP runtime does not use one
    r = client.post(POST, content=envelope("APR-2026-10-0161", RT_1048_LINES), headers=XML, auth=AUTH)
    (c,) = confirmations(r)
    assert c["severity"] == "1" and c["bukrs"] == "1000" and c["year"] == "2026"
    belnr = c["doc"]
    assert len(belnr) == 10 and belnr.startswith("01")
    assert c["log"][0][0] == "605(RW)" and f"BKPFF {belnr}10002026" in c["log"][0][1]

    # the same reference again (a retry): the first document is confirmed, nothing new is posted
    again = confirmations(
        client.post(POST, content=envelope("APR-2026-10-0161", RT_1048_LINES, msg="JE-2"), headers=XML, auth=AUTH)
    )
    assert again[0]["doc"] == belnr and again[0]["severity"] == "2" and again[0]["log"][0][0] == "117(F5)"
    assert belnr in again[0]["log"][0][1]

    # read back as a delta, filtered by our reference
    stamp = (before - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S")
    page = client.get(
        READ,
        auth=AUTH,
        params={
            "$filter": f"DocumentReferenceID eq 'APR-2026-10-0161' and LastChangeDateTime gt datetimeoffset'{stamp}Z'",
            "$select": "AccountingDocument,LedgerGLLineItem,GLAccount,AmountInCompanyCodeCurrency,CompanyCodeCurrency,"
            "DebitCreditCode,Material,Plant,CostCenter,WBSElement,DocumentItemText,ReferenceDocument,PostingDate,FiscalPeriod",
            "$orderby": "LedgerGLLineItem",
            "$inlinecount": "allpages",
        },
    ).json()["d"]
    assert page["__count"] == "3"
    lines = page["results"]
    assert [x["LedgerGLLineItem"] for x in lines] == ["000001", "000002", "000003"]
    assert [x["GLAccount"] for x in lines] == ["0051000000", "0051100000", "0021100000"]
    assert [x["AmountInCompanyCodeCurrency"] for x in lines] == ["41750.00", "8350.00", "-50100.00"]
    assert [x["DebitCreditCode"] for x in lines] == ["S", "S", "H"]
    first = lines[0]
    assert (first["Material"], first["Plant"], first["CostCenter"], first["CompanyCodeCurrency"]) == (
        "MTR-2041",
        "2030",
        "RC01",
        "INR",
    )
    assert lines[1]["WBSElement"] == "RT-1048.EX" and first["DocumentItemText"] == "Repair labour RT-1048"
    assert first["ReferenceDocument"] == belnr and first["FiscalPeriod"] == "010" and first["PostingDate"].startswith("/Date(")
    assert {x["AccountingDocument"] for x in lines} == {belnr}

    # paging, by key, $count, and a delta after the posting that is empty
    two = client.get(READ, auth=AUTH, params={"$filter": f"AccountingDocument eq '{belnr}'", "$top": "2", "$skip": "1"}).json()
    assert [x["LedgerGLLineItem"] for x in two["d"]["results"]] == ["000002", "000003"]
    key = f"(SourceLedger='0L',CompanyCode='1000',FiscalYear='2026',AccountingDocument='{belnr}',LedgerGLLineItem='000003')"
    one = client.get(READ + key, auth=AUTH).json()["d"]
    assert one["AssignmentReference"] == "APR-2026-10-0161" and one["AccountingDocumentHeaderText"] == "Actual costs RT-1048"
    assert client.get(READ + "/$count", auth=AUTH, params={"$filter": "Material eq 'MTR-2041'"}).text == "2"
    later = client.get(READ, auth=AUTH, params={"$filter": "LastChangeDateTime gt datetimeoffset'2100-01-01T00:00:00Z'"})
    assert later.json()["d"]["results"] == []

    # exactly one business event, carrying the document number and our reference
    (ev,) = events("APR-2026-10-0161")
    assert ev["AccountingDocument"] == belnr and ev["CompanyCode"] == "1000" and ev["FiscalYear"] == "2026"
    assert ev["MessageHeaderID"] == "JE-1" and ev["PostingDate"] == "2026-10-20"


def test_oauth_and_usd_conversion(client):
    tok = client.post(
        "/sap/bc/sec/oauth2/token", data={"grant_type": "client_credentials"}, auth=("di-connector", "circularity-demo-secret")
    ).json()["access_token"]
    lines = [
        item(1, "51000000", "500.00", "USD", Material="PMP-0320", Plant="2010"),
        item(2, "21100000", "500.00", "USD", DebitCreditCode="H"),
    ]
    r = client.post(POST, content=envelope("APR-USD-1", lines), headers=XML | {"Authorization": "Bearer " + tok})
    (c,) = confirmations(r)
    assert c["severity"] == "1"
    rows = client.get(
        READ, auth=AUTH, params={"$filter": "DocumentReferenceID eq 'APR-USD-1'", "$orderby": "LedgerGLLineItem"}
    ).json()
    got = [
        (x["AmountInTransactionCurrency"], x["TransactionCurrency"], x["AmountInCompanyCodeCurrency"])
        for x in rows["d"]["results"]
    ]
    assert got == [("500.00", "USD", "41750.00"), ("-500.00", "USD", "-41750.00")]


def test_refused_entries_post_nothing(client):
    def refused(body) -> list[str]:
        (c,) = confirmations(client.post(POST, content=body, headers=XML, auth=AUTH))
        assert c["severity"] == "3" and c["doc"] == "0000000000" and c["log"][0][0] == "609(RW)"
        return [t for t, _ in c["log"][1:]]

    assert "702(F5)" in refused(envelope("APR-BAD-1", [item(1, "51000000", "100.00"), item(2, "21100000", "-90.00")]))
    assert "165(F5)" in refused(envelope("APR-BAD-2", RT_1048_LINES, company="9999"))
    assert "305(M3)" in refused(
        envelope("APR-BAD-3", [item(1, "51000000", "1.00", Material="NOPE"), item(2, "21100000", "-1.00")])
    )
    assert "105(SG)" in refused(envelope("APR-BAD-4", [item(1, "51000000", "1.00", "EUR"), item(2, "21100000", "-1.00", "EUR")]))
    assert "014(FINS_JE)" in refused(envelope("APR-2026-10-0161-TOO-LONG", RT_1048_LINES))
    for ref in ("APR-BAD-1", "APR-BAD-2", "APR-BAD-3", "APR-BAD-4"):
        assert events(ref) == []
        assert client.get(READ, auth=AUTH, params={"$filter": f"DocumentReferenceID eq '{ref}'"}).json()["d"]["results"] == []
    # a refused entry does not block a correct one with the same reference
    ok = confirmations(
        client.post(
            POST,
            content=envelope("APR-BAD-1", [item(1, "51000000", "1.00"), item(2, "21100000", "-1.00")]),
            headers=XML,
            auth=AUTH,
        )
    )
    assert ok[0]["severity"] == "1"


def test_metadata_lists_the_entity(client):
    r = client.get("/sap/opu/odata/sap/API_JOURNALENTRYITEMBASIC_SRV/$metadata", auth=AUTH)
    assert (
        '<EntitySet Name="A_JournalEntryItemBasic"' in r.text
        and 'Name="AmountInCompanyCodeCurrency" Type="Edm.Decimal"' in r.text
    )


def test_reset_clears_the_postings(client):
    client.post("/_sim/reset", params={"system": "erp"}).raise_for_status()
    assert client.get(READ + "/$count", auth=AUTH).text == "0"
    # numbering starts again from the first number of the range
    (c,) = confirmations(client.post(POST, content=envelope("APR-AFTER-RESET", RT_1048_LINES), headers=XML, auth=AUTH))
    assert c["doc"] == "0100000000"
