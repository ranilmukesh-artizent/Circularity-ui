"""SAP Ariba mock: HTTP surface (docs/backend-steps.md, B4). Read-only, as in the demo (SOURCES.proc: "Read").

    POST /ariba/v2/oauth/token                                                         OAuth 2.0 client credentials
    GET  /ariba/api/procurement-reporting-details/v2/prod/views/PurchaseOrders          Operational Reporting view
         ?realm=…&filters={"updatedDateFrom":"…","updatedDateTo":"…"}&pageToken=…    → {"Records":[…],"PageToken":…}
    GET  /ariba/api/sourcing-event/v2/prod/events[?status=Open]                        → {"payload":[…],"pageToken":…}
    GET  /ariba/api/sourcing-event/v2/prod/events/{eventId}[/bids]
    GET  /ariba/api/supplier-data/v4/prod/suppliers[/{smVendorId}]                      → {"payload":[…],"pageToken":…}

Every API call needs the application's `apiKey` header, a bearer token and the `realm` query parameter, as on
api.ariba.com. Page tokens are opaque; the reporting view returns 50 records a page, the others 25.
"""

import base64
import json
import secrets
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Select, func, select
from sqlalchemy.engine import Connection

from sim.core.config import get_settings
from sim.core.db import engine
from sim.vendors.ariba import models as t

router = APIRouter(prefix="/ariba")
API = "/api"
_tokens: dict[str, float] = {}


def _err(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse({"error": error, "message": message}, status_code=status)


# ------------------------------------------------------------------ auth
@router.post("/v2/oauth/token")
async def token(request: Request):
    form = dict(await request.form())
    s = get_settings()
    h = request.headers.get("authorization", "")
    try:
        client, _, secret = base64.b64decode(h[6:]).decode().partition(":") if h.lower().startswith("basic ") else ("", "", "")
    except ValueError:
        client, secret = "", ""
    if form.get("grant_type") != "client_credentials" or f"{client}:{secret}" != s.ariba_client:
        return _err(401, "invalid_client", "Bad credentials")
    tok = secrets.token_urlsafe(32)
    _tokens[tok] = time.time() + 1440
    return {
        "access_token": tok,
        "token_type": "bearer",
        "expires_in": 1440,
        "scope": "",
        "refresh_token": secrets.token_urlsafe(16),
    }


def expire_all_tokens() -> int:
    """Fault injection (B6)."""
    n = len(_tokens)
    _tokens.clear()
    return n


def _guard(request: Request) -> JSONResponse | None:
    s = get_settings()
    if request.headers.get("apikey") != s.ariba_api_key:
        return _err(401, "unauthorized", "Invalid or missing apiKey header")
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer ") or _tokens.get(h[7:].strip(), 0) < time.time():
        return _err(401, "invalid_token", "Access token is missing, invalid or expired")
    realm = request.query_params.get("realm")
    if not realm:
        return _err(400, "invalid_request", "The realm query parameter is required")
    if realm != s.ariba_realm:
        return _err(403, "forbidden", f"The application is not enabled for realm {realm}")
    return None


# ------------------------------------------------------------------ paging
def _page(conn: Connection, stmt: Select, request: Request, size: int) -> tuple[list, str | None]:
    token = request.query_params.get("pageToken")
    try:
        offset = int(base64.urlsafe_b64decode(token.encode()).decode()) if token else 0
    except ValueError:
        offset = -1
    if offset < 0:
        raise ValueError("Invalid pageToken")
    rows = conn.execute(stmt.offset(offset).limit(size + 1)).all()
    nxt = base64.urlsafe_b64encode(str(offset + size).encode()).decode() if len(rows) > size else None
    return rows[:size], nxt


def _ts(v: datetime | None) -> str | None:
    return v.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if v else None


def _money(amount, currency) -> dict:
    return {"amount": float(amount), "currency": currency}


# ------------------------------------------------------------------ operational reporting: purchase orders
@router.get(API + "/procurement-reporting-details/v2/prod/views/PurchaseOrders")
def purchase_orders(request: Request):
    if (denied := _guard(request)) is not None:
        return denied
    try:
        f = json.loads(request.query_params.get("filters") or "{}")
        start = datetime.fromisoformat(f["updatedDateFrom"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(f["updatedDateTo"].replace("Z", "+00:00"))
    except (ValueError, KeyError, TypeError, AttributeError):
        return _err(
            400,
            "invalid_request",
            'filters must be JSON with updatedDateFrom and updatedDateTo, e.g. {"updatedDateFrom":'
            '"2026-10-01T00:00:00Z","updatedDateTo":"2026-10-08T00:00:00Z"}',
        )
    if end <= start or (end - start).days > 366:
        return _err(400, "invalid_request", "The date range must be positive and at most one year")
    po, s = t.PURCHASE_ORDERS, t.SUPPLIERS
    stmt = (
        select(po, s.c.name.label("supplier_name"))
        .join(s, s.c.sm_vendor_id == po.c.sm_vendor_id, isouter=True)
        .where(po.c.updated_at >= start, po.c.updated_at < end)
        .order_by(po.c.updated_at, po.c.po_id)
    )
    with engine.connect() as conn:
        try:
            rows, nxt = _page(conn, stmt, request, 50)
        except ValueError as e:
            return _err(400, "invalid_request", str(e))
    records = [
        {
            "POId": r.po_id,
            "ERPPONumber": r.erp_po,
            "EventId": r.event_id,
            "SupplierId": r.sm_vendor_id,
            "SupplierName": r.supplier_name,
            "StatusString": r.status,
            "TotalCost": _money(r.amount, r.currency),
            "Plant": r.plant,
            "CreatedDate": _ts(r.created_at),
            "LastModified": _ts(r.updated_at),
        }
        for r in rows
    ]
    body = {"Records": records}
    if nxt:
        body["PageToken"] = nxt
    return body


# ------------------------------------------------------------------ event management
def _event(r) -> dict:
    return {
        "eventId": r.event_id,
        "title": r.title,
        "eventType": r.event_type,
        "status": r.status,
        "commodity": r.commodity,
        "currency": r.currency,
        "quantity": float(r.quantity),
        "plant": r.plant,
        "externalReference": r.external_ref,
        "owner": r.owner,
        "createDate": _ts(r.created_at),
        "closeDate": _ts(r.close_at),
        "lastModified": _ts(r.updated_at),
    }


@router.get(API + "/sourcing-event/v2/prod/events")
def events(request: Request):
    if (denied := _guard(request)) is not None:
        return denied
    stmt = select(t.EVENTS).order_by(t.EVENTS.c.event_id)
    if status := request.query_params.get("status"):
        stmt = stmt.where(t.EVENTS.c.status == status)
    with engine.connect() as conn:
        try:
            rows, nxt = _page(conn, stmt, request, 25)
        except ValueError as e:
            return _err(400, "invalid_request", str(e))
    return {"payload": [_event(r) for r in rows], "pageToken": nxt}


@router.get(API + "/sourcing-event/v2/prod/events/{event_id}")
def event(event_id: str, request: Request):
    if (denied := _guard(request)) is not None:
        return denied
    with engine.connect() as conn:
        r = conn.execute(select(t.EVENTS).where(t.EVENTS.c.event_id == event_id)).first()
    return _event(r) if r else _err(404, "not_found", f"Event {event_id} not found")


@router.get(API + "/sourcing-event/v2/prod/events/{event_id}/bids")
def bids(event_id: str, request: Request):
    if (denied := _guard(request)) is not None:
        return denied
    b, s = t.BIDS, t.SUPPLIERS
    with engine.connect() as conn:
        if conn.execute(select(func.count()).where(t.EVENTS.c.event_id == event_id)).scalar_one() == 0:
            return _err(404, "not_found", f"Event {event_id} not found")
        rows = conn.execute(
            select(b, s.c.name.label("supplier_name"))
            .join(s, s.c.sm_vendor_id == b.c.sm_vendor_id)
            .where(b.c.event_id == event_id)
            .order_by(b.c.unit_price)
        ).all()
    return {
        "payload": [
            {
                "bidId": r.bid_id,
                "eventId": r.event_id,
                "supplierId": r.sm_vendor_id,
                "supplierName": r.supplier_name,
                "unitPrice": _money(r.unit_price, r.currency),
                "leadTimeDays": r.lead_time_days,
                "validUntil": r.valid_until.isoformat() if r.valid_until else None,
                "status": r.status,
                "submitDate": _ts(r.submitted_at),
            }
            for r in rows
        ],
        "pageToken": None,
    }


# ------------------------------------------------------------------ supplier data
def _supplier(r) -> dict:
    return {
        "smVendorId": r.sm_vendor_id,
        "erpVendorId": r.erp_vendor_id,
        "name": r.name,
        "country": r.country,
        "registrationStatus": r.registration_status,
        "qualificationStatus": r.qualification_status,
        "category": r.category,
        "lastModified": _ts(r.updated_at),
    }


@router.get(API + "/supplier-data/v4/prod/suppliers")
def suppliers(request: Request):
    if (denied := _guard(request)) is not None:
        return denied
    with engine.connect() as conn:
        try:
            rows, nxt = _page(conn, select(t.SUPPLIERS).order_by(t.SUPPLIERS.c.sm_vendor_id), request, 25)
        except ValueError as e:
            return _err(400, "invalid_request", str(e))
    return {"payload": [_supplier(r) for r in rows], "pageToken": nxt}


@router.get(API + "/supplier-data/v4/prod/suppliers/{sm_vendor_id}")
def supplier(sm_vendor_id: str, request: Request):
    if (denied := _guard(request)) is not None:
        return denied
    with engine.connect() as conn:
        r = conn.execute(select(t.SUPPLIERS).where(t.SUPPLIERS.c.sm_vendor_id == sm_vendor_id)).first()
    return _supplier(r) if r else _err(404, "not_found", f"Supplier {sm_vendor_id} not found")
