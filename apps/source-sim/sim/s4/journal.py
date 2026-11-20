"""SAP S/4HANA mock: posting journal entries with actual cost lines (docs/backend-steps.md, B13b).

Choice of API
    SAP's documented way to post a journal entry from outside S/4HANA is the SOAP service "Journal Entry - Post"
    (synchronous inbound service JournalEntryCreateRequestConfirmation_In, namespace http://sap.com/xi/SAPSCORE/SFIN).
    There is no OData create for journal entries (API_JOURNALENTRYITEMBASIC_SRV is read-only), so an OData-style
    create would be an invented API. This mock therefore implements the SOAP service (XML), and the read side is the
    real OData service API_JOURNALENTRYITEMBASIC_SRV / A_JournalEntryItemBasic (sim/s4/services.py).

    POST /sap/bc/srt/scs_ext/sap/journalentrycreaterequestconfi
         Content-Type: text/xml (SOAP 1.1) or application/soap+xml (SOAP 1.2); the reply uses the same version.
         Auth: Basic (communication user) or an OAuth bearer token, as for the OData services (sim/s4/security.py).
         No CSRF token: SAP's CSRF protection belongs to OData/ICF REST handlers, not to the SOAP runtime.

Request (SAP's message structure; child elements unqualified):
    <sfin:JournalEntryBulkCreateRequest>
      <MessageHeader><ID/><CreationDateTime/></MessageHeader>
      <JournalEntryCreateRequest>                                  (one or more; each is posted on its own)
        <MessageHeader><ID/><CreationDateTime/></MessageHeader>
        <JournalEntry>
          <OriginalReferenceDocumentType>BKPFF</…>               (default BKPFF; anything else is refused)
          <BusinessTransactionType>RFBU</…>                      (default RFBU)
          <AccountingDocumentType>SA</…>                         (default SA)
          <DocumentReferenceID>APR-2026-10-0161</…>               BKPF-XBLNR, at most 16: our external reference
          <DocumentHeaderText/>                                   BKPF-BKTXT, at most 25
          <CreatedByUser/>                                        (default: the calling user)
          <CompanyCode>1000</…>  <DocumentDate>2026-10-20</…>  <PostingDate>2026-10-20</…>
          <Item>                                                  (two or more G/L account items)
            <ReferenceDocumentItem>1</…>
            <GLAccount>0051000000</…>                            (padded to 10 digits)
            <AmountInTransactionCurrency currencyCode="INR">41750.00</…>   credit lines negative, as in SAP's
            <AmountInCompanyCodeCurrency currencyCode="INR"/>     (optional)  examples, or positive with
            <DebitCreditCode>S|H</…>                              (optional)  DebitCreditCode H
            <DocumentItemText/>  <AssignmentReference/>
            <Material>MTR-2041</…>  <Plant>2030</…>
            <AccountAssignment><CostCenter/><WBSElement/></AccountAssignment>
          </Item>
        </JournalEntry>
      </JournalEntryCreateRequest>
    </sfin:JournalEntryBulkCreateRequest>

Response 200 (SAP's confirmation; one JournalEntryCreateConfirmation per request, in order):
    <sfin:JournalEntryBulkCreateConfirmation>
      <MessageHeader><ID/><ReferenceID>request id</ReferenceID><CreationDateTime/></MessageHeader>
      <JournalEntryCreateConfirmation>
        <MessageHeader>…</MessageHeader>
        <JournalEntryCreateConfirmation>
          <AccountingDocument>0100000000</…> <CompanyCode>1000</…> <FiscalYear>2026</…>
        </JournalEntryCreateConfirmation>
        <Log><MaximumLogItemSeverityCode>1|2|3</…><Item><TypeID>605(RW)</TypeID><SeverityCode/><Note/></Item></Log>
      </JournalEntryCreateConfirmation>
    </sfin:JournalEntryBulkCreateConfirmation>
    Posted: severity 1, "605(RW) Document posted successfully: BKPFF <belnr><bukrs><gjahr> <logical system>".
    Refused (as SAP does, still HTTP 200): AccountingDocument 0000000000, severity 3, "609(RW) Error in document"
    plus one log item per problem (e.g. "702(F5) Balance in transaction currency", unknown company code, material
    or plant, missing G/L account, mixed transaction currencies, no exchange rate).
    A request that is not a SOAP envelope of this operation: HTTP 500 with a SOAP Fault (as the SAP SOAP runtime).

Idempotency: a second post with the same DocumentReferenceID in the same company code does not create a second
    document. The reply confirms the first document (its number, company code and year) with severity 2 and the
    note "117(F5) Check whether document has already been entered under number <belnr> <bukrs> <gjahr>"; nothing is
    written and no event is emitted. A request without DocumentReferenceID is not checked.

Posting: BKPF (header, XBLNR = DocumentReferenceID) and one ACDOCA row per item in ledger 0L: RACCT, DRCRK, WSL /
    RWCUR, HSL / RHCUR (company code currency INR; USD converted at the demo's 83.5), RCNTR, PS_POSID, MATNR, WERKS,
    SGTXT, ZUONR, AWTYP BKPFF, AWREF = BELNR, BUDAT/BLDAT, POPER, LAST_CHANGE = simulated time. Document numbers
    come from number range 01 (0100000000 …). The business event
    sap.s4.beh.journalentry.v1.JournalEntry.Created.v1 (subject <bukrs>/<belnr>/<gjahr>) carries CompanyCode,
    FiscalYear, AccountingDocument, AccountingDocumentType, PostingDate, DocumentReferenceID and MessageHeaderID.

ASSUMPTION: the sync service's request root is JournalEntryBulkCreateRequest and its reply root
    JournalEntryBulkCreateConfirmation, as in SAP's published examples; WSDL (?wsdl) is not served.
ASSUMPTION: SAP's FI posting does not itself refuse a repeated XBLNR for G/L documents; the duplicate rule above is
    this deployment's (it follows the F5 117 duplicate-document check) so retries from di are safe.
ASSUMPTION: DocumentReferenceID is limited to 16 characters (BKPF-XBLNR); longer values are refused, not truncated.
ASSUMPTION: Item/Material and Item/Plant are accepted as plain item fields (the documented item carries account
    assignments; material and plant are needed for the cost trace); CostCenter and WBSElement are not validated
    (there is no CSKS/PRPS master here), G/L accounts are not checked against a chart of accounts.
ASSUMPTION: only company code 1000 (INR, fiscal year = calendar year, variant K4) exists; FX rate type M has only
    USD→INR at 83.5. Message numbers other than RW 605/609, F5 702 and F5 117 are illustrative.
ASSUMPTION: CreditorItem, DebtorItem and tax items are not supported (refused with an error log item).
ASSUMPTION: the event payload adds DocumentReferenceID and MessageHeaderID to SAP's key fields so di can match it.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy import insert, select, text
from sqlalchemy.engine import Connection

from sim import clock, events
from sim.db import engine
from sim.s4 import security
from sim.s4 import tables as t

router = APIRouter()
PATH = "/sap/bc/srt/scs_ext/sap/journalentrycreaterequestconfi"
SOURCE = "erp"
EVENT = "sap.s4.beh.journalentry.v1.JournalEntry.Created.v1"
NS = "http://sap.com/xi/SAPSCORE/SFIN"
SOAP11, SOAP12 = "http://schemas.xmlsoap.org/soap/envelope/", "http://www.w3.org/2003/05/soap-envelope"
LOGICAL_SYSTEM = "S4HCLNT100"
LEDGER = "0L"
COMPANY_CODES = {"1000": "INR"}
RATES = {("USD", "INR"): Decimal("83.5")}  # rate type M, the demo's dated rate
CENT = Decimal("0.01")
NEXT_BELNR = text("SELECT nextval('s4.belnr_seq')")


# ------------------------------------------------------------------ XML helpers
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element | None, name: str) -> ET.Element | None:
    if el is None:
        return None
    return next((c for c in el if _local(c.tag) == name), None)


def _children(el: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in el if _local(c.tag) == name]


def _text(el: ET.Element | None, *path: str) -> str:
    for name in path:
        el = _child(el, name)
    return (el.text or "").strip() if el is not None else ""


def _envelope(soap_ns: str, body: str) -> Response:
    xml = (
        f'<?xml version="1.0" encoding="utf-8"?><soap-env:Envelope xmlns:soap-env="{soap_ns}">'
        f"<soap-env:Header/><soap-env:Body>{body}</soap-env:Body></soap-env:Envelope>"
    )
    media = "application/soap+xml" if soap_ns == SOAP12 else "text/xml"
    return Response(xml, media_type=f"{media}; charset=utf-8")


def _fault(soap_ns: str, message: str) -> Response:
    if soap_ns == SOAP12:
        body = (
            "<soap-env:Fault><soap-env:Code><soap-env:Value>soap-env:Sender</soap-env:Value></soap-env:Code>"
            f'<soap-env:Reason><soap-env:Text xml:lang="en">{escape(message)}</soap-env:Text></soap-env:Reason>'
            "</soap-env:Fault>"
        )
    else:
        body = (
            "<soap-env:Fault><faultcode>soap-env:Client</faultcode>"
            f'<faultstring xml:lang="en">{escape(message)}</faultstring></soap-env:Fault>'
        )
    resp = _envelope(soap_ns, body)
    resp.status_code = 500
    return resp


def _header(msg_id: str, ref_id: str, now: datetime) -> str:
    ref = f"<ReferenceID>{escape(ref_id)}</ReferenceID>" if ref_id else ""
    stamp = now.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    return f"<MessageHeader><ID>{escape(msg_id)}</ID>{ref}<CreationDateTime>{stamp}</CreationDateTime></MessageHeader>"


# ------------------------------------------------------------------ one journal entry
class _Refused(Exception):
    def __init__(self, notes: list[tuple[str, str]]):
        super().__init__(notes)
        self.notes = notes


@dataclass
class _Result:
    belnr: str = "0000000000"
    bukrs: str = ""
    gjahr: str = "0000"
    severity: int = 1
    log: list[tuple[str, int, str]] = field(default_factory=list)  # (TypeID, SeverityCode, Note)


def _date(value: str, name: str, notes: list) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        notes.append(("004(FINS_JE)", f"{name} '{value}' is not a valid date (YYYY-MM-DD)"))
        return None


def _amount(el: ET.Element | None) -> tuple[Decimal, str] | None:
    if el is None or not (el.text or "").strip():
        return None
    try:
        value = Decimal(el.text.strip())
    except InvalidOperation:
        return None
    return value, (el.get("currencyCode") or "").strip().upper()


def _post(conn: Connection, je: ET.Element, msg_id: str, user: str) -> _Result:
    """Validate and post one JournalEntry. Raises _Refused with SAP-style log notes."""
    notes: list[tuple[str, str]] = []
    bukrs = _text(je, "CompanyCode")
    if bukrs not in COMPANY_CODES:
        raise _Refused([("165(F5)", f"Company code {bukrs or '(blank)'} does not exist")])
    local = COMPANY_CODES[bukrs]
    awtyp = _text(je, "OriginalReferenceDocumentType") or "BKPFF"
    if awtyp != "BKPFF":
        notes.append(("012(FINS_JE)", f"Original reference document type {awtyp} is not allowed; use BKPFF"))
    if (_text(je, "BusinessTransactionType") or "RFBU") != "RFBU":
        notes.append(("013(FINS_JE)", "Business transaction type must be RFBU"))
    blart = _text(je, "AccountingDocumentType") or "SA"
    xblnr = _text(je, "DocumentReferenceID")
    if len(xblnr) > 16:
        notes.append(("014(FINS_JE)", f"DocumentReferenceID '{xblnr}' is longer than 16 characters"))
    bktxt = _text(je, "DocumentHeaderText")[:25]
    usnam = (_text(je, "CreatedByUser") or user)[:12]
    budat = _date(_text(je, "PostingDate"), "PostingDate", notes) if _text(je, "PostingDate") else None
    bldat = _date(_text(je, "DocumentDate"), "DocumentDate", notes) if _text(je, "DocumentDate") else None
    if budat is None and not any(n[1].startswith("PostingDate") for n in notes):
        notes.append(("001(FINS_JE)", "Enter a posting date (PostingDate)"))
    bldat = bldat or budat
    for other in ("CreditorItem", "DebtorItem", "ProductTaxItem", "WithholdingTaxItem"):
        if _child(je, other) is not None:
            notes.append(("015(FINS_JE)", f"{other} is not supported by this system; post G/L account items (Item)"))
    items = _children(je, "Item")
    if len(items) < 2:
        notes.append(("096(F5)", "A journal entry needs at least two items"))

    # duplicate check before anything else is written (serialised per company code and reference)
    if xblnr and len(xblnr) <= 16:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"BKPF/{bukrs}/{xblnr}"})
        first = conn.execute(
            select(t.BKPF.c.BELNR, t.BKPF.c.GJAHR)
            .where(t.BKPF.c.BUKRS == bukrs, t.BKPF.c.XBLNR == xblnr)
            .order_by(t.BKPF.c.GJAHR, t.BKPF.c.BELNR)
        ).first()
        if first is not None:
            note = f"Check whether document has already been entered under number {first.BELNR} {bukrs} {first.GJAHR}"
            return _Result(first.BELNR, bukrs, first.GJAHR, 2, [("117(F5)", 2, note + f" (reference {xblnr}); not posted")])

    rows, currencies = [], set()
    for i, it in enumerate(items, start=1):
        where = f"Item {_text(it, 'ReferenceDocumentItem') or i}"
        racct = _text(it, "GLAccount")
        if not racct:
            notes.append(("044(F5)", f"{where}: enter a G/L account (GLAccount)"))
        elif not racct.isdigit() or len(racct) > 10:
            notes.append(("045(F5)", f"{where}: G/L account {racct} is not valid"))
        amt = _amount(_child(it, "AmountInTransactionCurrency"))
        if amt is None or not amt[1]:
            notes.append(("046(F5)", f"{where}: enter AmountInTransactionCurrency with its currencyCode"))
            continue
        wsl, waers = amt
        currencies.add(waers)
        drcrk = _text(it, "DebitCreditCode").upper()
        if drcrk and drcrk not in ("S", "H"):
            notes.append(("047(F5)", f"{where}: DebitCreditCode must be S (debit) or H (credit)"))
        if drcrk:
            wsl = abs(wsl) * (-1 if drcrk == "H" else 1)
        wsl = wsl.quantize(CENT, ROUND_HALF_UP)
        if wsl == 0:
            notes.append(("048(F5)", f"{where}: the amount is zero"))
        given = _amount(_child(it, "AmountInCompanyCodeCurrency"))
        if given is not None and given[1] and given[1] != local:
            notes.append(("049(F5)", f"{where}: AmountInCompanyCodeCurrency must be in {local}"))
        if given is not None:
            hsl = (abs(given[0]) * (1 if wsl > 0 else -1)).quantize(CENT, ROUND_HALF_UP)
        elif waers == local:
            hsl = wsl
        elif (waers, local) in RATES:
            hsl = (wsl * RATES[(waers, local)]).quantize(CENT, ROUND_HALF_UP)
        else:
            on = budat.isoformat() if budat else "the posting date"
            notes.append(("105(SG)", f"Enter rate {waers} / {local} rate type M for {on} in the system settings"))
            continue
        matnr, werks = _text(it, "Material") or None, _text(it, "Plant") or None
        if matnr and conn.execute(select(t.MARA.c.MATNR).where(t.MARA.c.MATNR == matnr)).first() is None:
            notes.append(("305(M3)", f"{where}: material {matnr} does not exist"))
        if werks and conn.execute(select(t.T001W.c.WERKS).where(t.T001W.c.WERKS == werks)).first() is None:
            notes.append(("024(M3)", f"{where}: plant {werks} does not exist"))
        rows.append(
            {
                "RACCT": racct.zfill(10) if racct.isdigit() else racct,
                "DRCRK": "S" if wsl > 0 else "H",
                "WSL": wsl,
                "RWCUR": waers,
                "HSL": hsl,
                "RHCUR": local,
                "RCNTR": _text(it, "AccountAssignment", "CostCenter") or None,
                "PS_POSID": _text(it, "AccountAssignment", "WBSElement") or None,
                "MATNR": matnr,
                "WERKS": werks,
                "SGTXT": _text(it, "DocumentItemText")[:50] or None,
                "ZUONR": _text(it, "AssignmentReference")[:18] or None,
            }
        )
    if len(currencies) > 1:
        notes.append(("017(FINS_JE)", f"All items must use one transaction currency (found {', '.join(sorted(currencies))})"))
    elif rows and len(rows) == len(items):
        balance = sum((r["WSL"] for r in rows), Decimal(0))
        if balance != 0:
            notes.append(("702(F5)", f"Balance in transaction currency {rows[0]['RWCUR']}: {balance:f}"))
    if notes:
        raise _Refused(notes)

    # rounding difference in the local currency goes to the largest line, as S/4 posts it
    diff = sum((r["HSL"] for r in rows), Decimal(0))
    if diff:
        max(rows, key=lambda r: abs(r["HSL"]))["HSL"] -= diff

    now = clock.now(conn)
    gjahr = str(budat.year)
    belnr = f"{conn.execute(NEXT_BELNR).scalar_one():010d}"
    conn.execute(
        insert(t.BKPF).values(
            BUKRS=bukrs,
            BELNR=belnr,
            GJAHR=gjahr,
            BLART=blart,
            BLDAT=bldat,
            BUDAT=budat,
            MONAT=f"{budat.month:02d}",
            XBLNR=xblnr or None,
            BKTXT=bktxt or None,
            USNAM=usnam,
            AWTYP="BKPFF",
            AWKEY=f"{belnr}{bukrs}{gjahr}",
            MSG_ID=msg_id[:35] or None,
            CPUTM=now,
            LAST_CHANGE=now,
        )
    )
    common = {
        "RLDNR": LEDGER,
        "RBUKRS": bukrs,
        "GJAHR": gjahr,
        "BELNR": belnr,
        "POPER": f"{budat.month:03d}",
        "BLART": blart,
        "BUDAT": budat,
        "BLDAT": bldat,
        "AWTYP": "BKPFF",
        "AWREF": belnr,
        "USNAM": usnam,
        "LAST_CHANGE": now,
    }
    conn.execute(insert(t.ACDOCA), [common | r | {"DOCLN": f"{i:06d}", "BUZEI": f"{i:03d}"} for i, r in enumerate(rows, start=1)])
    events.emit(
        conn,
        SOURCE,
        EVENT,
        f"{bukrs}/{belnr}/{gjahr}",
        {
            "CompanyCode": bukrs,
            "FiscalYear": gjahr,
            "AccountingDocument": belnr,
            "AccountingDocumentType": blart,
            "PostingDate": budat.isoformat(),
            "DocumentReferenceID": xblnr or None,
            "MessageHeaderID": msg_id or None,
        },
        now,
    )
    note = f"Document posted successfully: BKPFF {belnr}{bukrs}{gjahr} {LOGICAL_SYSTEM}"
    return _Result(belnr, bukrs, gjahr, 1, [("605(RW)", 1, note)])


def _confirmation(res: _Result, sub_id: str, now: datetime) -> str:
    log = "".join(
        f"<Item><TypeID>{escape(tid)}</TypeID><SeverityCode>{sev}</SeverityCode><Note>{escape(note)}</Note></Item>"
        for tid, sev, note in res.log
    )
    return (
        "<JournalEntryCreateConfirmation>" + _header(uuid.uuid4().hex.upper(), sub_id, now) + "<JournalEntryCreateConfirmation>"
        f"<AccountingDocument>{res.belnr}</AccountingDocument><CompanyCode>{escape(res.bukrs)}</CompanyCode>"
        f"<FiscalYear>{res.gjahr}</FiscalYear>"
        "</JournalEntryCreateConfirmation>"
        f"<Log><MaximumLogItemSeverityCode>{res.severity}</MaximumLogItemSeverityCode>{log}</Log>"
        "</JournalEntryCreateConfirmation>"
    )


# ------------------------------------------------------------------ the SOAP endpoint
@router.post(PATH)
async def journal_entry_post(request: Request):
    user = security.authenticate(request)
    if user is None:
        return security.unauthorized()
    soap_ns = SOAP12 if "soap+xml" in request.headers.get("content-type", "") else SOAP11
    try:
        root = ET.fromstring(await request.body())  # noqa: S314 - requests come from di, the integration under test
    except ET.ParseError as e:
        return _fault(soap_ns, f"The request is not well-formed XML: {e}")
    if _local(root.tag) != "Envelope":
        return _fault(soap_ns, "The request is not a SOAP envelope")
    soap_ns = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else soap_ns
    soap_body = _child(root, "Body")
    bulk = next(iter(soap_body), None) if soap_body is not None else None
    if bulk is None or _local(bulk.tag) != "JournalEntryBulkCreateRequest":
        name = _local(bulk.tag) if bulk is not None else "(empty body)"
        return _fault(soap_ns, f"Operation {name} is not offered by service JOURNALENTRYCREATEREQUESTCONFI")
    requests = _children(bulk, "JournalEntryCreateRequest")
    if not requests:
        return _fault(soap_ns, "JournalEntryBulkCreateRequest contains no JournalEntryCreateRequest")

    confirmations = []
    for req in requests:
        sub_id = _text(req, "MessageHeader", "ID")
        je = _child(req, "JournalEntry")
        try:
            if je is None:
                raise _Refused([("002(FINS_JE)", "JournalEntry is missing")])
            with engine.begin() as conn:
                res = _post(conn, je, sub_id, user)
        except _Refused as r:
            log = [("609(RW)", 3, f"Error in document: BKPFF $ {LOGICAL_SYSTEM}")] + [(tid, 3, n) for tid, n in r.notes]
            res = _Result(bukrs=_text(je, "CompanyCode"), severity=3, log=log)
        confirmations.append(_confirmation(res, sub_id, clock.now()))

    now = clock.now()
    body = (
        f"<n0:JournalEntryBulkCreateConfirmation xmlns:n0={quoteattr(NS)}>"
        + _header(uuid.uuid4().hex.upper(), _text(bulk, "MessageHeader", "ID"), now)
        + "".join(confirmations)
        + "</n0:JournalEntryBulkCreateConfirmation>"
    )
    return _envelope(soap_ns, body)
