"""SAP S/4HANA mock: fixed assets, retirement and transfer postings (plan 9, P9-13.1, story X-13).

Choice of API
    SAP documents fixed-asset retirement and transfer postings as services on its API Business Hub. These endpoints are
    MODELLED, NOT VERIFIED against those pages (they could not be read here); the names follow the plan's fallback, and the
    bodies are JSON rather than SAP's exact structures:

    POST /sap/bc/srt/scs_ext/sap/fixedassetretirement
         {assetKey, retirementDate, proceeds, currency, externalReference}
         -> {assetDocument, assetNumber, postingDate, proceeds, bookValue, gainLoss, currency}
    POST /sap/bc/srt/scs_ext/sap/fixedassettransfer
         {assetKey, transferDate, toLocation, externalReference}
         -> {assetDocument, assetNumber, postingDate, toLocation}

The asset master (`ANLA`, seeded in `seed.assets`) holds the book value; the gain or loss of a retirement is the proceeds less
the book value, computed here as the ERP's answer (di stores it, never computes it). One document per `externalReference`: a
repeat answers the first document with HTTP 200 and changes nothing. Refused: unknown asset (404 asset_not_found), an asset
already retired (409 asset_retired), a missing field (422). Auth is Basic or an OAuth bearer token, as for the other S/4 calls.
Accounting references are for orientation only: Finance and Kinective's Legal team confirm them.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, text, update
from sqlalchemy.engine import Connection

from sim.core import clock
from sim.core.db import engine
from sim.vendors.s4 import models as t
from sim.vendors.s4 import security

router = APIRouter()
RETIRE = "/sap/bc/srt/scs_ext/sap/fixedassetretirement"
TRANSFER = "/sap/bc/srt/scs_ext/sap/fixedassettransfer"


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _num(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number") from None


def _answer(doc: Any, asset: Any) -> dict[str, Any]:
    out = {"assetDocument": doc.BELNR, "assetNumber": doc.ANLN1, "postingDate": doc.BUDAT.isoformat()}
    if doc.TYPE == "retire":
        return out | {"proceeds": float(doc.PROCEEDS), "bookValue": float(doc.BOOK_VALUE), "gainLoss": float(doc.GAIN_LOSS),
                      "currency": doc.WAERS}  # fmt: skip
    return out | {"toLocation": doc.TO_LOCATION}


def _post(conn: Connection, kind: str, body: dict[str, Any]) -> JSONResponse:
    for f in ("assetKey", "externalReference") + (("proceeds",) if kind == "retire" else ("toLocation",)):
        if body.get(f) in (None, ""):
            return _err(422, "missing_field", f"{f} is required")
    ref = str(body["externalReference"])
    first = conn.execute(select(t.ANEK).where(t.ANEK.c.XBLNR == ref)).first()
    if first is not None:  # a retry: the first document, nothing written
        asset = conn.execute(select(t.ANLA).where(t.ANLA.c.ANLN1 == first.ANLN1)).first()
        return JSONResponse(_answer(first, asset))
    asset = conn.execute(select(t.ANLA).where(t.ANLA.c.ASSET_KEY == str(body["assetKey"])).with_for_update()).first()
    if asset is None:
        return _err(404, "asset_not_found", f"No fixed asset for {body['assetKey']}")
    if asset.STATUS == "retired":
        return _err(409, "asset_retired", f"Asset {asset.ANLN1} is already retired")
    now = clock.now()
    when = body.get("retirementDate") if kind == "retire" else body.get("transferDate")
    try:
        posted = date.fromisoformat(str(when)) if when else now.date()
        proceeds = _num(body["proceeds"], "proceeds") if kind == "retire" else None
    except ValueError as e:
        return _err(422, "bad_value", str(e))
    belnr = f"{conn.execute(text('SELECT nextval(\'s4.anek_seq\')')).scalar_one()}"
    row = {"BELNR": belnr, "TYPE": kind, "XBLNR": ref, "ANLN1": asset.ANLN1, "WAERS": asset.WAERS, "BUDAT": posted,
           "LAST_CHANGE": now}  # fmt: skip
    if kind == "retire":
        row |= {"PROCEEDS": proceeds, "BOOK_VALUE": asset.BOOK_VALUE, "GAIN_LOSS": proceeds - asset.BOOK_VALUE}
        conn.execute(update(t.ANLA).where(t.ANLA.c.ANLN1 == asset.ANLN1).values(STATUS="retired", LAST_CHANGE=now))
    else:
        row |= {"TO_LOCATION": str(body["toLocation"])}
        conn.execute(update(t.ANLA).where(t.ANLA.c.ANLN1 == asset.ANLN1).values(LOCATION=str(body["toLocation"]), LAST_CHANGE=now))
    conn.execute(insert(t.ANEK).values(**row))
    doc = conn.execute(select(t.ANEK).where(t.ANEK.c.BELNR == belnr)).one()
    return JSONResponse(_answer(doc, asset))


async def _handle(request: Request, kind: str) -> JSONResponse:
    if security.authenticate(request) is None:
        return security.unauthorized()  # type: ignore[return-value]
    try:
        body = await request.json()
    except ValueError:
        return _err(400, "bad_json", "The request body is not JSON")
    if not isinstance(body, dict):
        return _err(400, "bad_json", "The request body is not an object")
    with engine.begin() as conn:
        return _post(conn, kind, body)


@router.post(RETIRE)
async def retire(request: Request):
    return await _handle(request, "retire")


@router.post(TRANSFER)
async def transfer(request: Request):
    return await _handle(request, "transfer")
