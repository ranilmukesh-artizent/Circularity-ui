"""Machinio: the Dealer API v1 (see __init__.py for the documentation status and assumptions).

    GET   /machinio/v1/account                         the seller account the API key belongs to
    GET   /machinio/v1/listings                        own listings; status, stock_number, category, updated_since
    GET   /machinio/v1/listings/{id}
    PATCH /machinio/v1/listings/{id}                   {"status"?, "price": {"amount"}?}; status follows LISTING_FLOW
    GET   /machinio/v1/listings/{id}/similar           other dealers' listings matched to it; status, condition
    GET   /machinio/v1/offers                          offers on own listings; status, listing_id, stock_number,
                                                       offer_kind, updated_since
    GET   /machinio/v1/offers/{id}
    POST  /machinio/v1/offers/{id}/accept              open/countered -> accepted; the listing -> pending_sale
    POST  /machinio/v1/offers/{id}/decline             {"reason"?} open/countered -> declined
    POST  /machinio/v1/offers/{id}/counter             {"amount", "message"?} open -> countered; amount above the offer;
                                                       the buyer gets a new 7-day window

Lists use cursor paging: ?limit= (1..100, default 25) &cursor=; the body is {"data": [...], "meta": {"total",
"has_more", "next_cursor"}}. Errors: {"error": {"type", "code", "message", "param"?}}.
Offer validity: an open or countered offer whose expires_at has passed on the simulated clock becomes `expired`
(stamped with clock.now(), event machinio.offer.expired) the next time the API is called; it can no longer be accepted.
listing_age_days is computed on the simulated clock. Writes stamp clock.now() and emit machinio.* events.
"""

import base64
import binascii
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Table, and_, func, select, true, update
from sqlalchemy.engine import Connection

from sim.core import clock, events
from sim.core.db import engine
from sim.vendors.machinio.seed import ACCOUNT, CONDITION, LISTINGS, OFFERS, SIMILAR, _z

router = APIRouter(prefix="/machinio/v1")
SOURCE = "dlr"
API_KEYS = {"mch_demo_circularity_4f7b2e91": ACCOUNT["id"]}
DEFAULT_LIMIT, MAX_LIMIT = 25, 100
LISTING_FLOW = {
    "draft": {"active", "withdrawn"},
    "active": {"withdrawn", "sold", "pending_sale"},
    "pending_sale": {"active", "sold"},
    "withdrawn": {"active"},
    "sold": set(),
}
OFFER_OPEN = ("open", "countered")
COUNTER_DAYS = 7


class ApiError(Exception):
    def __init__(self, status: int, type_: str, code: str, message: str, param: str | None = None):
        super().__init__(message)
        self.status, self.type, self.code, self.message, self.param = status, type_, code, message, param


def _bad(code: str, message: str, param: str | None = None) -> ApiError:
    return ApiError(400, "invalid_request_error", code, message, param)


def error_response(e: ApiError) -> JSONResponse:
    body = {"error": {"type": e.type, "code": e.code, "message": e.message}}
    if e.param:
        body["error"]["param"] = e.param
    return JSONResponse(body, status_code=e.status, headers={"WWW-Authenticate": "ApiKey"} if e.status == 401 else None)


def _auth(request: Request) -> str:
    key = request.headers.get("x-api-key")
    if not key:
        raise ApiError(401, "authentication_error", "api_key_missing", "No API key provided (X-Api-Key header)")
    acct = API_KEYS.get(key)
    if acct is None:
        raise ApiError(401, "authentication_error", "api_key_invalid", "Invalid API key provided")
    return acct


def expire_offers(conn: Connection) -> int:
    """The validity rule: open or countered offers past expires_at become expired (event per offer)."""
    now = clock.now(conn)
    rows = conn.execute(
        select(OFFERS.c.offer_id, OFFERS.c.doc).where(OFFERS.c.status.in_(OFFER_OPEN), OFFERS.c.expires_at <= now)
    ).all()
    for oid, doc in rows:
        doc = doc | {"status": "expired", "updated_at": _z(now)}
        conn.execute(update(OFFERS).where(OFFERS.c.offer_id == oid).values(status="expired", updated_at=now, doc=doc))
        events.emit(conn, SOURCE, "machinio.offer.expired", oid, doc, now)
    return len(rows)


def _run(request: Request, fn, *, write: bool = False):  # noqa: ARG001 - callers mark writes; the transaction is the same either way
    try:
        _auth(request)
        with engine.begin() as conn:
            expire_offers(conn)
            return fn(conn)
    except ApiError as e:
        return error_response(e)


def _check(request: Request, allowed: set[str]) -> None:
    for k in request.query_params:
        if k not in allowed | {"limit", "cursor"}:
            raise _bad("parameter_unknown", f"Received unknown parameter: {k}", k)


def _since(request: Request) -> datetime | None:
    v = request.query_params.get("updated_since")
    if v is None:
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise _bad("parameter_invalid", "updated_since must be an ISO 8601 timestamp", "updated_since") from None
    if d.tzinfo is None:
        raise _bad("parameter_invalid", "updated_since must include a time zone", "updated_since")
    return d


def _cursor(request: Request) -> tuple[int, int]:
    q = request.query_params
    try:
        limit = int(q.get("limit", DEFAULT_LIMIT))
    except ValueError:
        raise _bad("parameter_invalid", "limit must be an integer", "limit") from None
    if not 1 <= limit <= MAX_LIMIT:
        raise _bad("parameter_invalid", f"limit must be between 1 and {MAX_LIMIT}", "limit")
    offset = 0
    if q.get("cursor"):
        try:
            raw = base64.urlsafe_b64decode(q["cursor"].encode()).decode()
            if not raw.startswith("o:"):
                raise ValueError
            offset = int(raw[2:])
        except (ValueError, binascii.Error, UnicodeDecodeError):
            raise _bad("parameter_invalid", "cursor is not valid", "cursor") from None
    return offset, limit


def _page(request: Request, conn: Connection, table: Table, cond, order, shape) -> dict:
    offset, limit = _cursor(request)
    total = conn.execute(select(func.count()).select_from(table).where(cond)).scalar_one()
    docs = conn.execute(select(table.c.doc).where(cond).order_by(*order).offset(offset).limit(limit)).scalars().all()
    more = offset + limit < total
    nxt = base64.urlsafe_b64encode(f"o:{offset + limit}".encode()).decode() if more else None
    now = clock.now(conn)
    return {"data": [shape(d, now) for d in docs], "meta": {"total": total, "has_more": more, "next_cursor": nxt}}


def listing_out(doc: dict, now: datetime) -> dict:
    listed = doc.get("listed_at")
    age = (now - datetime.fromisoformat(listed.replace("Z", "+00:00"))).days if listed and doc["status"] != "draft" else None
    return doc | {"listing_age_days": age}


def offer_out(doc: dict, now: datetime) -> dict:  # noqa: ARG001 - same signature as the other output mappers
    return doc


# ------------------------------------------------------------------ account
@router.get("/account")
def account(request: Request):
    return _run(request, lambda conn: ACCOUNT)  # noqa: ARG005 - _run passes the connection


# ------------------------------------------------------------------ listings
@router.get("/listings")
def listings(request: Request):
    def go(conn):
        _check(request, {"status", "stock_number", "category", "updated_since"})
        q, c = request.query_params, LISTINGS.c
        cond = [true()]
        if "status" in q:
            if q["status"] not in LISTING_FLOW:
                raise _bad("parameter_invalid", f"status must be one of {', '.join(LISTING_FLOW)}", "status")
            cond.append(c.status == q["status"])
        if "stock_number" in q:
            cond.append(c.stock_number == q["stock_number"])
        if "category" in q:
            cond.append(c.doc["category"].astext == q["category"])
        if (since := _since(request)) is not None:
            cond.append(c.updated_at > since)
        return _page(request, conn, LISTINGS, and_(*cond), (c.listing_id,), listing_out)

    return _run(request, go)


def _listing(conn: Connection, lid: str) -> dict:
    doc = conn.execute(select(LISTINGS.c.doc).where(LISTINGS.c.listing_id == lid)).scalar()
    if doc is None:
        raise ApiError(404, "invalid_request_error", "resource_missing", f"No such listing: '{lid}'", "id")
    return doc


@router.get("/listings/{lid}")
def listing(lid: str, request: Request):
    return _run(request, lambda conn: listing_out(_listing(conn, lid), clock.now(conn)))


@router.get("/listings/{lid}/similar")
def similar(lid: str, request: Request):
    def go(conn):
        _check(request, {"status", "condition"})
        _listing(conn, lid)
        q, c = request.query_params, SIMILAR.c
        cond = [c.similar_to == lid, c.status == q.get("status", "active")]
        if "condition" in q:
            if q["condition"] not in CONDITION.values():
                raise _bad("parameter_invalid", f"condition must be one of {', '.join(CONDITION.values())}", "condition")
            cond.append(c.condition == q["condition"])
        return _page(request, conn, SIMILAR, and_(*cond), (c.listing_id,), listing_out)

    return _run(request, go)


async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise _bad("body_invalid", "The request body must be JSON") from None
    if not isinstance(body, dict):
        raise _bad("body_invalid", "The request body must be a JSON object")
    return body


@router.patch("/listings/{lid}")
async def patch_listing(lid: str, request: Request):
    try:
        body = await _body(request)
    except ApiError as e:
        return error_response(e)

    def go(conn):
        unknown = [k for k in body if k not in ("status", "price")]
        if unknown:
            raise _bad("parameter_unknown", f"Received unknown parameter: {unknown[0]}", unknown[0])
        doc = _listing(conn, lid)
        now = clock.now(conn)
        new = dict(doc)
        if "price" in body:
            amt = (body["price"] or {}).get("amount") if isinstance(body["price"], dict) else None
            if not isinstance(amt, int | float) or isinstance(amt, bool) or amt <= 0:
                raise _bad("parameter_invalid", "price.amount must be a positive number", "price.amount")
            new["price"] = doc["price"] | {"amount": float(amt)}
        if "status" in body:
            to = body["status"]
            if to not in LISTING_FLOW:
                raise _bad("parameter_invalid", f"status must be one of {', '.join(LISTING_FLOW)}", "status")
            if to != doc["status"] and to not in LISTING_FLOW[doc["status"]]:
                raise ApiError(
                    409,
                    "invalid_request_error",
                    "listing_status_transition",
                    f"A {doc['status']} listing cannot become {to}",
                    "status",
                )
            new["status"] = to
            if to == "active" and not doc.get("listed_at"):
                new["listed_at"] = _z(now)
        new["updated_at"] = _z(now)
        conn.execute(
            update(LISTINGS)
            .where(LISTINGS.c.listing_id == lid)
            .values(status=new["status"], listed_at=_ts(new.get("listed_at")), updated_at=now, doc=new)
        )
        kind = "sold" if new["status"] == "sold" and doc["status"] != "sold" else "updated"
        events.emit(conn, SOURCE, f"machinio.listing.{kind}", lid, new, now)
        return listing_out(new, now)

    return _run(request, go, write=True)


def _ts(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


# ------------------------------------------------------------------ offers
@router.get("/offers")
def offers(request: Request):
    def go(conn):
        _check(request, {"status", "listing_id", "stock_number", "offer_kind", "updated_since"})
        q, c = request.query_params, OFFERS.c
        cond = [true()]
        if "status" in q:
            allowed = ("open", "countered", "accepted", "declined", "expired")
            if q["status"] not in allowed:
                raise _bad("parameter_invalid", f"status must be one of {', '.join(allowed)}", "status")
            cond.append(c.status == q["status"])
        if "listing_id" in q:
            cond.append(c.listing_id == q["listing_id"])
        for k in ("stock_number", "offer_kind"):
            if k in q:
                cond.append(c.doc[k].astext == q[k])
        if (since := _since(request)) is not None:
            cond.append(c.updated_at > since)
        return _page(request, conn, OFFERS, and_(*cond), (c.offer_id,), offer_out)

    return _run(request, go)


def _offer(conn: Connection, oid: str) -> dict:
    doc = conn.execute(select(OFFERS.c.doc).where(OFFERS.c.offer_id == oid)).scalar()
    if doc is None:
        raise ApiError(404, "invalid_request_error", "resource_missing", f"No such offer: '{oid}'", "id")
    return doc


@router.get("/offers/{oid}")
def offer(oid: str, request: Request):
    return _run(request, lambda conn: _offer(conn, oid))


def _respond(conn: Connection, oid: str, action: str, body: dict) -> dict:
    doc = _offer(conn, oid)
    now = clock.now(conn)
    if doc["status"] == "expired":
        raise ApiError(409, "invalid_request_error", "offer_expired", f"Offer {oid} expired at {doc['expires_at']}")
    allowed = OFFER_OPEN if action != "counter" else ("open",)
    if doc["status"] not in allowed:
        raise ApiError(409, "invalid_request_error", "offer_not_open", f"Offer {oid} is {doc['status']} and cannot be {action}ed")
    new = dict(doc) | {"responded_at": _z(now), "updated_at": _z(now)}
    if action == "accept":
        new["status"] = "accepted"
    elif action == "decline":
        reason = body.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise _bad("parameter_invalid", "reason must be a string", "reason")
        new |= {"status": "declined", "decline_reason": reason}
    else:
        amt = body.get("amount")
        if not isinstance(amt, int | float) or isinstance(amt, bool):
            raise _bad("parameter_missing" if amt is None else "parameter_invalid", "amount must be a number", "amount")
        if amt <= doc["offer_amount"]:
            raise _bad("parameter_invalid", f"A counter must be above the offer ({doc['offer_amount']:.2f} USD)", "amount")
        cur = body.get("currency", doc["offer_currency"])
        if cur != doc["offer_currency"]:
            raise _bad("parameter_invalid", f"currency must be {doc['offer_currency']}", "currency")
        new |= {
            "status": "countered",
            "counter_amount": float(amt),
            "counter_message": body.get("message"),
            "expires_at": _z(now + timedelta(days=COUNTER_DAYS)),
        }
    conn.execute(
        update(OFFERS)
        .where(OFFERS.c.offer_id == oid)
        .values(status=new["status"], expires_at=_ts(new["expires_at"]), updated_at=now, doc=new)
    )
    events.emit(conn, SOURCE, f"machinio.offer.{new['status']}", oid, new, now)
    if action == "accept":
        ldoc = _listing(conn, doc["listing_id"])
        if ldoc["status"] == "active":
            ldoc = ldoc | {"status": "pending_sale", "updated_at": _z(now)}
            conn.execute(
                update(LISTINGS)
                .where(LISTINGS.c.listing_id == ldoc["id"])
                .values(status="pending_sale", updated_at=now, doc=ldoc)
            )
            events.emit(conn, SOURCE, "machinio.listing.updated", ldoc["id"], ldoc, now)
    return new


def _action(name: str):
    async def handler(oid: str, request: Request):
        try:
            body = await _body(request) if (await request.body()) else {}
        except ApiError as e:
            return error_response(e)
        return _run(request, lambda conn: _respond(conn, oid, name, body), write=True)

    return handler


for _name in ("accept", "decline", "counter"):
    router.add_api_route(f"/offers/{{oid}}/{_name}", _action(_name), methods=["POST"], name=f"dlr:offer:{_name}")
