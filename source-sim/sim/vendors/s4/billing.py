"""SAP S/4HANA mock: customer credit memos (plan 9, P9-13.4, story X-16).

Choice of API
    SAP documents billing documents (credit memos) in its Billing Document API on the API Business Hub. This endpoint is
    MODELLED, NOT VERIFIED against that page (it could not be read here); the name follows the plan's fallback and the body is
    JSON rather than SAP's exact structure:

    POST /sap/bc/srt/scs_ext/sap/creditmemo  {customer, amount, currency, externalReference}
         -> {creditMemo, amount, currency, postingDate}   `amount` is what the ERP posted

One document per `externalReference`: a repeat answers the first memo with HTTP 200 and changes nothing. A fault of kind `amount`
on the system (`POST /_sim/faults {"system": "erp", "kind": "amount", "value": 15000}`) makes the ERP post `value` cents instead of
the amount asked, for tests and smokes of the mismatch. Refused: a missing field or a non-positive amount (422). Auth is Basic or
an OAuth bearer token, as for the other S/4 calls. Accounting references are for orientation only: Finance and Kinective's Legal
team confirm them.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, text
from sqlalchemy.engine import Connection

from sim.core import clock, faults
from sim.core.db import engine
from sim.vendors.s4 import models as t
from sim.vendors.s4 import security

router = APIRouter()
PATH = "/sap/bc/srt/scs_ext/sap/creditmemo"
CENT = Decimal("0.01")


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _answer(doc: Any) -> dict[str, Any]:
    return {"creditMemo": doc.VBELN, "amount": float(doc.NETWR), "currency": doc.WAERS, "postingDate": doc.BUDAT.isoformat()}


def _post(conn: Connection, body: dict[str, Any]) -> JSONResponse:
    for f in ("customer", "amount", "externalReference"):
        if body.get(f) in (None, ""):
            return _err(422, "missing_field", f"{f} is required")
    ref = str(body["externalReference"])
    first = conn.execute(select(t.VBRK).where(t.VBRK.c.XBLNR == ref)).first()
    if first is not None:  # a retry: the first memo, nothing written
        return JSONResponse(_answer(first))
    try:
        amount = Decimal(str(body["amount"])).quantize(CENT)
    except InvalidOperation:
        return _err(422, "bad_value", "amount must be a number")
    if amount <= 0:
        return _err(422, "bad_value", "amount must be positive")
    for f in faults.active(conn, "erp"):
        if f["kind"] == "amount" and f["value"] is not None:
            amount = Decimal(f["value"]) / 100  # the ERP posts another amount than the one asked
            break
    vbeln = str(conn.execute(text("SELECT nextval('s4.vbrk_seq')")).scalar_one())
    conn.execute(
        insert(t.VBRK).values(
            VBELN=vbeln, XBLNR=ref, CUSTOMER=str(body["customer"]), NETWR=amount, WAERS=str(body.get("currency") or "USD"),
            BUDAT=clock.now(conn).date(),
        )
    )  # fmt: skip
    return JSONResponse(_answer(conn.execute(select(t.VBRK).where(t.VBRK.c.VBELN == vbeln)).one()))


@router.post(PATH)
async def credit_memo(request: Request):
    if security.authenticate(request) is None:
        return security.unauthorized()  # type: ignore[return-value]
    try:
        body = await request.json()
    except ValueError:
        return _err(400, "bad_json", "The request body is not JSON")
    if not isinstance(body, dict):
        return _err(400, "bad_json", "The request body is not an object")
    with engine.begin() as conn:
        return _post(conn, body)
