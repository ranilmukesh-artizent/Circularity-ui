"""SAP S/4HANA mock: HTTP surface (docs/backend-steps.md, B3).

POST /sap/bc/sec/oauth2/token                                   OAuth 2.0 client credentials
GET  /sap/opu/odata/sap/<SERVICE>/[<EntitySet>[(<key>)][/<nav>]][/$count]   reads, with OData v2 query options
GET  /sap/opu/odata/sap/<SERVICE>/$metadata
POST /sap/opu/odata/sap/API_RESERVATION_DOCUMENT_SRV/A_ReservationDocumentHeader   (deep insert of items)
POST /sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader         (deep insert; moves stock)
POST /sap/bc/srt/scs_ext/sap/journalentrycreaterequestconfi   SOAP "Journal Entry - Post" (sim/vendors/s4/journal.py, B13)
GET  /sap/opu/odata/sap/API_JOURNALENTRYITEMBASIC_SRV/A_JournalEntryItemBasic     the posted lines (ACDOCA)
"""

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.engine import Connection

from sim.core import clock, events
from sim.core.db import engine
from sim.vendors.s4 import journal, security
from sim.vendors.s4 import models as t
from sim.vendors.s4.odata.service import ODataError, error_response
from sim.vendors.s4.services import SERVICES

router = APIRouter()
router.include_router(journal.router)
BASE = "/sap/opu/odata/sap"
SOURCE = "erp"


def sim_now() -> datetime:
    """Simulated time (sim/core/clock.py, B6)."""
    return clock.now()


# ------------------------------------------------------------------ auth
@router.post("/sap/bc/sec/oauth2/token")
async def token(request: Request):
    form = dict(await request.form())
    out = security.issue_token(form, request.headers.get("authorization", ""))
    if out is None:
        return JSONResponse({"error": "invalid_client", "error_description": "Bad client credentials"}, status_code=401)
    return out


def _guard(request: Request, changing: bool) -> Response | None:
    if security.authenticate(request) is None:
        return security.unauthorized()
    if changing and not security.csrf_ok(request):
        return security.csrf_required()
    return None


# ------------------------------------------------------------------ reads
@router.get(BASE + "/{service}")
@router.get(BASE + "/{service}/{path:path}")
def read(service: str, request: Request, path: str = ""):
    if (denied := _guard(request, changing=False)) is not None:
        return denied
    svc = SERVICES.get(service)
    try:
        if svc is None:
            raise ODataError(404, "/IWFND/MED/170", f"No service found for namespace '', name '{service}', version '0001'")
        with engine.connect() as conn:
            resp = svc.handle_get(request, path, conn)
    except ODataError as e:
        resp = error_response(e.status, e.code, e.message)
    if request.headers.get("x-csrf-token", "").lower() == "fetch":
        security.fetch_csrf(request, resp)
    return resp


# ------------------------------------------------------------------ writes
WRITERS = {}


def writer(service: str, entity_set: str):
    def register(fn):
        WRITERS[(service, entity_set)] = fn
        return fn

    return register


@router.post(BASE + "/{service}/{entity_set}")
async def create(service: str, entity_set: str, request: Request):
    if (denied := _guard(request, changing=True)) is not None:
        return denied
    fn = WRITERS.get((service, entity_set))
    if fn is None:
        return error_response(405, "/IWBEP/CM_MGW_RT/043", f"Method 'CREATE_ENTITY' not implemented for '{entity_set}'")
    try:
        body = await request.json()
    except ValueError:
        return error_response(400, "/IWBEP/CM_MGW_RT/004", "Malformed JSON in the request body")
    try:
        with engine.begin() as conn:
            key = fn(body.get("d", body), conn)
        # read the created entity back, with its items, as SAP Gateway returns it
        with engine.connect() as conn:
            svc = SERVICES[service]
            nav = next(iter(svc.sets[entity_set].navs))
            created = svc.handle_get(_with_query(request, f"$expand={nav}"), f"{entity_set}({key})", conn)
        created.status_code = 201
        created.headers["location"] = f"{str(request.base_url).rstrip('/')}{BASE}/{service}/{entity_set}({key})"
        return created
    except ODataError as e:
        return error_response(e.status, e.code, e.message)


def _with_query(request: Request, query: str) -> Request:
    scope = dict(request.scope)
    scope["query_string"] = query.encode()
    return Request(scope)


# ------------------------------------------------------------------ helpers for request bodies
_DATE_RE = re.compile(r"^/Date\((-?\d+)(?:[+-]\d{4})?\)/$")


def _date(value: Any, field: str) -> date:
    if value in (None, ""):
        return sim_now().date()
    if isinstance(value, str) and (m := _DATE_RE.match(value)):
        return datetime.fromtimestamp(int(m[1]) / 1000, UTC).date()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError as e:
        raise ODataError(400, "/IWBEP/CM_MGW_RT/004", f"Invalid date '{value}' for property '{field}'") from e


def _qty(value: Any, field: str) -> Decimal:
    try:
        q = Decimal(str(value))
    except (InvalidOperation, TypeError) as e:
        raise ODataError(400, "/IWBEP/CM_MGW_RT/004", f"Invalid value '{value}' for property '{field}'") from e
    if q <= 0:
        raise ODataError(400, "M7/022", f"Enter a positive quantity in '{field}'")
    return q


def _items(body: dict, nav: str) -> list[dict]:
    raw = body.get(nav) or {}
    items = raw.get("results", raw) if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise ODataError(400, "M7/096", f"Enter at least one item in '{nav}'")
    return items


def _require(item: dict, *fields: str) -> None:
    for f in fields:
        if not item.get(f):
            raise ODataError(400, "/IWBEP/CM_MGW_RT/004", f"Property '{f}' is required")


def _stock(conn: Connection, matnr: str, werks: str, lgort: str, lock: bool = True):
    q = select(t.MARD).where(t.MARD.c.MATNR == matnr, t.MARD.c.WERKS == werks, t.MARD.c.LGORT == lgort)
    return conn.execute(q.with_for_update() if lock else q).first()


def _material(conn: Connection, matnr: str):
    row = conn.execute(select(t.MARA).where(t.MARA.c.MATNR == matnr)).first()
    if row is None:
        raise ODataError(400, "M3/305", f"Material {matnr} does not exist")
    return row


# ------------------------------------------------------------------ reservation
@writer("API_RESERVATION_DOCUMENT_SRV", "A_ReservationDocumentHeader")
def create_reservation(body: dict, conn: Connection) -> str:
    items = _items(body, "to_ReservationDocumentItem")
    bwart = str(body.get("GoodsMovementType") or "311")
    now = sim_now()
    rsnum = f"{conn.execute(text("SELECT nextval('s4.rsnum_seq')")).scalar_one():010d}"
    rows = []
    for i, it in enumerate(items, start=1):
        _require(it, "Product", "Plant", "ResvnItmRequiredQtyInBaseUnit")
        matnr, werks, lgort = it["Product"], it["Plant"], it.get("StorageLocation") or "RT01"
        qty = _qty(it["ResvnItmRequiredQtyInBaseUnit"], "ResvnItmRequiredQtyInBaseUnit")
        mat = _material(conn, matnr)
        stock = _stock(conn, matnr, werks, lgort)
        reserved = conn.execute(
            select(func.coalesce(func.sum(t.RESB.c.BDMNG), 0)).where(
                t.RESB.c.MATNR == matnr, t.RESB.c.WERKS == werks, t.RESB.c.LGORT == lgort, t.RESB.c.XLOEK.is_(False)
            )
        ).scalar_one()
        available = (stock.LABST if stock else Decimal(0)) - reserved
        if qty > available:
            raise ODataError(
                400,
                "M7/021",
                f"Deficit of SL Unrestricted-use {qty - available:f} {mat.MEINS} : {matnr} {werks} {lgort} "
                f"(available {available:f}, already reserved {reserved:f})",
            )
        rows.append(
            {
                "RSNUM": rsnum,
                "RSPOS": f"{i:04d}",
                "MATNR": matnr,
                "WERKS": werks,
                "LGORT": lgort,
                "BDMNG": qty,
                "MEINS": mat.MEINS,
                "BDTER": _date(it.get("MatlCompRequirementDate"), "MatlCompRequirementDate"),
                "XLOEK": False,
                "LAST_CHANGE": now,
            }
        )
    conn.execute(
        insert(t.RKPF).values(
            RSNUM=rsnum,
            RSDAT=_date(body.get("ReservationDate"), "ReservationDate"),
            BWART=bwart,
            UMWRK=body.get("IssuingOrReceivingPlant"),
            WEMPF=(body.get("GoodsRecipientName") or "")[:12],
            EXT_REF=body.get("YY1_CircularityRef_RSV"),
            LAST_CHANGE=now,
        )
    )
    conn.execute(insert(t.RESB), rows)
    events.emit(
        conn,
        SOURCE,
        "sap.s4.beh.reservation.v1.Reservation.Created.v1",
        rsnum,
        {"Reservation": rsnum, "YY1_CircularityRef_RSV": body.get("YY1_CircularityRef_RSV")},
        now,
    )
    return f"'{rsnum}'"


# ------------------------------------------------------------------ goods movement
RECEIPTS = {"101", "501", "561"}
ISSUES = {"201", "261", "551", "601"}
TRANSFERS = {"301", "311"}
GMCODE = {"01": "GR for purchase order", "03": "Goods issue", "04": "Transfer posting", "05": "Other goods receipt"}


def _add_stock(conn: Connection, matnr: str, werks: str, lgort: str, delta: Decimal, now: datetime, unit: str) -> None:
    row = _stock(conn, matnr, werks, lgort)
    if row is None:
        if delta < 0:
            raise ODataError(400, "M7/021", f"Deficit of SL Unrestricted-use {-delta:f} {unit} : {matnr} {werks} {lgort}")
        conn.execute(
            text(
                'INSERT INTO s4."MARC" ("MATNR","WERKS","EKGRP","LAST_CHANGE") VALUES (:m,:w,\'RT1\',:n) ON CONFLICT DO NOTHING'
            ),
            {"m": matnr, "w": werks, "n": now},
        )
        conn.execute(insert(t.MARD).values(MATNR=matnr, WERKS=werks, LGORT=lgort, LABST=delta, INSME=0, SPEME=0, LAST_CHANGE=now))
        return
    if row.LABST + delta < 0:
        raise ODataError(
            400, "M7/021", f"Deficit of SL Unrestricted-use {-(row.LABST + delta):f} {unit} : {matnr} {werks} {lgort}"
        )
    conn.execute(
        update(t.MARD)
        .where(t.MARD.c.MATNR == matnr, t.MARD.c.WERKS == werks, t.MARD.c.LGORT == lgort)
        .values(LABST=row.LABST + delta, LAST_CHANGE=now)
    )


@writer("API_MATERIAL_DOCUMENT_SRV", "A_MaterialDocumentHeader")
def create_material_document(body: dict, conn: Connection) -> str:
    items = _items(body, "to_MaterialDocumentItem")
    gmcode = str(body.get("GoodsMovementCode") or "")
    if gmcode not in GMCODE:
        raise ODataError(400, "M7/895", f"Goods movement code '{gmcode}' is not valid (01, 03, 04 or 05)")
    now = sim_now()
    posting = _date(body.get("PostingDate"), "PostingDate")
    mblnr = str(conn.execute(text("SELECT nextval('s4.mblnr_seq')")).scalar_one())
    mjahr = str(posting.year)
    rows = []
    for i, it in enumerate(items, start=1):
        _require(it, "Material", "Plant", "GoodsMovementType", "QuantityInEntryUnit")
        bwart, matnr, werks = str(it["GoodsMovementType"]), it["Material"], it["Plant"]
        lgort = it.get("StorageLocation") or "RT01"
        qty = _qty(it["QuantityInEntryUnit"], "QuantityInEntryUnit")
        unit = _material(conn, matnr).MEINS
        umwrk = it.get("IssuingOrReceivingPlant") or (werks if bwart == "311" else None)
        umlgo = it.get("IssuingOrReceivingStorageLoc") or (lgort if bwart == "301" else None)
        if bwart in RECEIPTS:
            _add_stock(conn, matnr, werks, lgort, qty, now, unit)
            shkzg = "S"
        elif bwart in ISSUES:
            _add_stock(conn, matnr, werks, lgort, -qty, now, unit)
            shkzg = "H"
        elif bwart in TRANSFERS:
            if not umwrk or not umlgo:
                raise ODataError(400, "M7/018", "Enter the receiving plant and storage location for a transfer posting")
            _add_stock(conn, matnr, werks, lgort, -qty, now, unit)
            _add_stock(conn, matnr, umwrk, umlgo, qty, now, unit)
            shkzg = "H"
        else:
            raise ODataError(400, "M7/162", f"Movement type {bwart} is not supported")
        rsnum, rspos = it.get("Reservation") or None, it.get("ReservationItem") or None
        if rsnum:
            found = conn.execute(select(t.RESB).where(t.RESB.c.RSNUM == rsnum, t.RESB.c.RSPOS == (rspos or "0001"))).first()
            if found is None:
                raise ODataError(400, "M7/047", f"Reservation {rsnum} item {rspos or '0001'} does not exist")
        rows.append(
            {
                "MBLNR": mblnr,
                "MJAHR": mjahr,
                "ZEILE": f"{i:04d}",
                "BWART": bwart,
                "MATNR": matnr,
                "WERKS": werks,
                "LGORT": lgort,
                "UMWRK": umwrk,
                "UMLGO": umlgo,
                "MENGE": qty,
                "MEINS": unit,
                "SHKZG": shkzg,
                "RSNUM": rsnum,
                "RSPOS": rspos,
                "LAST_CHANGE": now,
            }
        )
    conn.execute(
        insert(t.MKPF).values(
            MBLNR=mblnr,
            MJAHR=mjahr,
            BLDAT=_date(body.get("DocumentDate"), "DocumentDate"),
            BUDAT=posting,
            GMCODE=gmcode,
            BKTXT=(body.get("MaterialDocumentHeaderText") or "")[:25],
            LAST_CHANGE=now,
        )
    )
    conn.execute(insert(t.MSEG), rows)
    events.emit(
        conn,
        SOURCE,
        "sap.s4.beh.materialdocument.v1.MaterialDocument.Created.v1",
        f"{mblnr}/{mjahr}",
        {"MaterialDocument": mblnr, "MaterialDocumentYear": mjahr, "GoodsMovementCode": gmcode},
        now,
    )
    return f"MaterialDocumentYear='{mjahr}',MaterialDocument='{mblnr}'"
