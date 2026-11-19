"""Ritchie Bros. Market Data: the Comparables API v2 (see __init__.py for the documentation status and assumptions).

    GET  /ritchie/v2/comparables                 realised sales; filters make, model, class, condition (comma list),
                                                 region (IN-West, or a country IN), lotSize, soldFrom, soldTo
                                                 (YYYY-MM-DD), modifiedSince; sort; offset/limit paging
    GET  /ritchie/v2/comparables/{COMP_ID}
    GET  /ritchie/v2/subjects                    the customer's registered subject assets; modifiedSince
    GET  /ritchie/v2/subjects/{ref}
    GET  /ritchie/v2/subjects/{ref}/comparables  the match rule for one subject: same make, model, region and lot-size
                                                 band, condition of the scenario (?scenario=AS_IS|REFURBISHED, or
                                                 ?condition=); also takes soldFrom/soldTo/sort and paging
    GET  /ritchie/v2/market-summary              count, median sale price, median days listed, average bidders for the
                                                 same filters as /comparables
    GET  /ritchie/v2/price-index                 class, period, from, to (YYYY-MM); modifiedSince; paging
    GET  /ritchie/v2/feed/status                 last refresh, feed-token expiry, age and state on the simulated clock
    POST /ritchie/v2/feed/token                  renew the feed token {"validityDays": 1..365}: the feed refreshes now and
                                                 the sales held back since the expiry are served

Freshness rule: a record is served only when the feed published it at or before the feed's last refresh. With the
token expired (the seed: 6 Oct 14:00 UTC), nothing newer arrives. Every list answers `dataAsOf` (the last refresh)
and the X-Data-As-Of header.
"""

import statistics
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Select, and_, func, select, true, update
from sqlalchemy.engine import Connection

from sim import clock, events
from sim.db import engine
from sim.vendors.ritchie.seed import COMPARABLES, CONDITIONS, FEED, PRICE_INDEX, SUBJECTS, lakh, lot_band

router = APIRouter(prefix="/ritchie/v2")
SOURCE = "mkt"
API_KEYS = {"mkt-demo-key": "CIRCULARITY-REMARKETING"}  # demo key -> account
DEFAULT_LIMIT, MAX_LIMIT = 100, 500
COMMON = {"offset", "limit"}
SORTS = {
    "COMP_ID": COMPARABLES.c.comp_id,
    "SOLD_DATE": COMPARABLES.c.sold_date,
    "SOLD_PRC_AMT": COMPARABLES.c.amount,
}
RATE_HEADERS = {"X-RateLimit-Limit": "30", "X-RateLimit-Remaining": "29"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, target: str | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.target = status, code, message, target


def error(status: int, code: str, message: str, target: str | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "requestId": str(uuid.uuid4())}}
    if target:
        body["error"]["target"] = target
    headers = {"WWW-Authenticate": 'ApiKey realm="marketdata"'} if status == 401 else None
    return JSONResponse(body, status_code=status, headers=headers)


def _auth(request: Request) -> None:
    key = request.headers.get("x-api-key")
    if not key:
        raise ApiError(401, "missing_api_key", "Provide your API key in the X-Api-Key header")
    if key not in API_KEYS:
        raise ApiError(401, "invalid_api_key", "The API key is not valid")


def _check(request: Request, allowed: set[str]) -> None:
    for k in request.query_params:
        if k not in allowed | COMMON:
            raise ApiError(400, "invalid_parameter", f"Unknown query parameter '{k}'", k)


def _paging(request: Request) -> tuple[int, int]:
    q = request.query_params
    try:
        offset, limit = int(q.get("offset", 0)), int(q.get("limit", DEFAULT_LIMIT))
    except ValueError:
        raise ApiError(400, "invalid_parameter", "offset and limit must be integers") from None
    if offset < 0 or not 1 <= limit <= MAX_LIMIT:
        raise ApiError(400, "invalid_parameter", f"offset must be >= 0 and limit between 1 and {MAX_LIMIT}")
    return offset, limit


def _date(v: str, name: str) -> date:
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise ApiError(400, "invalid_parameter", f"{name} must be a date (YYYY-MM-DD)", name) from None


def _since(v: str) -> datetime:
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, "invalid_parameter", "modifiedSince must be an ISO 8601 timestamp", "modifiedSince") from None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _z(d: datetime) -> str:
    return d.astimezone(UTC).isoformat().replace("+00:00", "Z")


def feed_row(conn: Connection):
    return conn.execute(select(FEED).where(FEED.c.id == 1)).one()


def _page(request: Request, conn: Connection, q: Select, total_q: Select, as_of: datetime) -> JSONResponse:
    offset, limit = _paging(request)
    total = conn.execute(total_q).scalar_one()
    docs = conn.execute(q.offset(offset).limit(limit)).scalars().all()
    nxt = None
    if offset + limit < total:
        u = request.url.include_query_params(offset=offset + limit, limit=limit)
        nxt = f"{u.path}?{u.query}"
    body = {"totalCount": total, "offset": offset, "limit": limit, "dataAsOf": _z(as_of), "results": docs, "links": {"next": nxt}}
    return JSONResponse(body, headers=RATE_HEADERS | {"X-Data-As-Of": _z(as_of)})


def _comp_filters(request: Request, as_of: datetime) -> list:
    q = request.query_params
    c = COMPARABLES.c
    cond = [c.last_updated <= as_of]  # the freshness rule: nothing published after the last refresh
    if "make" in q:
        cond.append(func.lower(c.make) == q["make"].lower())
    if "model" in q:
        cond.append(func.lower(c.model) == q["model"].lower())
    if "class" in q:
        cond.append(c.asset_class == q["class"].upper())
    if "condition" in q:
        codes = [x.strip().upper() for x in q["condition"].split(",") if x.strip()]
        bad = [x for x in codes if x not in CONDITIONS]
        if bad or not codes:
            raise ApiError(400, "invalid_parameter", f"condition must be one of {', '.join(CONDITIONS)}", "condition")
        cond.append(c.condition.in_(codes))
    if "region" in q:
        r = q["region"]
        cond.append(c.region.like(r + "-%") if "-" not in r else c.region == r)
    if "lotSize" in q:
        try:
            n = int(q["lotSize"])
            if n < 1:
                raise ValueError
        except ValueError:
            raise ApiError(400, "invalid_parameter", "lotSize must be a positive integer", "lotSize") from None
        band = lot_band(n)
        lo, hi = {"1": (1, 1), "2-10": (2, 10), "11-20": (11, 20), "21+": (21, 10**9)}[band]
        cond.append(c.qty.between(lo, hi))
    if "soldFrom" in q:
        cond.append(c.sold_date >= _date(q["soldFrom"], "soldFrom"))
    if "soldTo" in q:
        cond.append(c.sold_date <= _date(q["soldTo"], "soldTo"))
    if "modifiedSince" in q:
        cond.append(c.last_updated > _since(q["modifiedSince"]))
    return cond


def _order(request: Request):
    s = request.query_params.get("sort", "COMP_ID")
    col = SORTS.get(s.lstrip("-"))
    if col is None:
        raise ApiError(400, "invalid_parameter", f"sort must be one of {', '.join(SORTS)} (prefix - for descending)", "sort")
    return (col.desc() if s.startswith("-") else col.asc(), COMPARABLES.c.comp_id)


COMP_PARAMS = {"make", "model", "class", "condition", "region", "lotSize", "soldFrom", "soldTo", "modifiedSince", "sort"}


def _run(request: Request, fn):
    try:
        _auth(request)
        with engine.begin() as conn:
            return fn(conn)
    except ApiError as e:
        return error(e.status, e.code, e.message, e.target)


@router.get("/comparables")
def comparables(request: Request):
    def go(conn):
        _check(request, COMP_PARAMS)
        as_of = feed_row(conn).last_refresh_at
        cond = and_(*_comp_filters(request, as_of))
        q = select(COMPARABLES.c.doc).where(cond).order_by(*_order(request))
        return _page(request, conn, q, select(func.count()).select_from(COMPARABLES).where(cond), as_of)

    return _run(request, go)


@router.get("/comparables/{comp_id}")
def comparable(comp_id: str, request: Request):
    def go(conn):
        as_of = feed_row(conn).last_refresh_at
        doc = conn.execute(
            select(COMPARABLES.c.doc).where(COMPARABLES.c.comp_id == comp_id, COMPARABLES.c.last_updated <= as_of)
        ).scalar()
        if doc is None:
            raise ApiError(404, "not_found", f"Comparable {comp_id} was not found")
        return doc

    return _run(request, go)


@router.get("/subjects")
def subjects(request: Request):
    def go(conn):
        _check(request, {"modifiedSince", "class"})
        q = request.query_params
        cond = []
        if "modifiedSince" in q:
            cond.append(SUBJECTS.c.last_updated > _since(q["modifiedSince"]))
        if "class" in q:
            cond.append(SUBJECTS.c.doc["ASSET_CLASS"].astext == q["class"].upper())
        w = and_(true(), *cond)
        sel = select(SUBJECTS.c.doc).where(w).order_by(SUBJECTS.c.subject_ref)
        return _page(request, conn, sel, select(func.count()).select_from(SUBJECTS).where(w), feed_row(conn).last_refresh_at)

    return _run(request, go)


def _subject(conn: Connection, ref: str) -> dict:
    doc = conn.execute(select(SUBJECTS.c.doc).where(SUBJECTS.c.subject_ref == ref)).scalar()
    if doc is None:
        raise ApiError(404, "not_found", f"Subject {ref} was not found")
    return doc


@router.get("/subjects/{ref}")
def subject(ref: str, request: Request):
    return _run(request, lambda conn: _subject(conn, ref))


@router.get("/subjects/{ref}/comparables")
def subject_comparables(ref: str, request: Request):
    """The vendor's match rule: make, model, region and lot-size band of the subject; condition of the scenario."""

    def go(conn):
        _check(request, {"scenario", "condition", "soldFrom", "soldTo", "sort"})
        s = _subject(conn, ref)
        q = request.query_params
        if "condition" in q:
            condition = q["condition"].upper()
            if condition not in CONDITIONS:
                raise ApiError(400, "invalid_parameter", f"condition must be one of {', '.join(CONDITIONS)}", "condition")
        else:
            name = q.get("scenario", "AS_IS").upper()
            sc = next((x for x in s["SCENARIOS"] if x["SCENARIO"] == name), None)
            if sc is None:
                raise ApiError(404, "not_found", f"Subject {ref} has no {name} scenario", "scenario")
            condition = sc["CONDITION"]
        as_of = feed_row(conn).last_refresh_at
        c = COMPARABLES.c
        lo, hi = {"1": (1, 1), "2-10": (2, 10), "11-20": (11, 20), "21+": (21, 10**9)}[s["LOT_SIZE_BAND"]]
        cond = [
            c.last_updated <= as_of,
            c.make == s["MAKE"],
            c.model == s["MODEL"],
            c.region == s["REGION"],
            c.condition == condition,
            c.qty.between(lo, hi),
        ]
        if "soldFrom" in q:
            cond.append(c.sold_date >= _date(q["soldFrom"], "soldFrom"))
        if "soldTo" in q:
            cond.append(c.sold_date <= _date(q["soldTo"], "soldTo"))
        w = and_(*cond)
        sel = select(c.doc).where(w).order_by(*_order(request))
        return _page(request, conn, sel, select(func.count()).select_from(COMPARABLES).where(w), as_of)

    return _run(request, go)


@router.get("/market-summary")
def market_summary(request: Request):
    def go(conn):
        _check(request, COMP_PARAMS - {"sort", "modifiedSince"})
        as_of = feed_row(conn).last_refresh_at
        docs = conn.execute(select(COMPARABLES.c.doc).where(and_(*_comp_filters(request, as_of)))).scalars().all()
        if not docs:
            return {"count": 0, "dataAsOf": _z(as_of)}
        med = round(statistics.median(d["SOLD_PRC_AMT"] for d in docs))
        return {
            "count": len(docs),
            "medianSoldPrice": {"amount": med, "currency": "INR", "display": lakh(med)},
            "medianDaysListed": round(statistics.median(d["DAYS_LISTED"] for d in docs)),
            "avgBidders": round(statistics.mean(d["BIDDERS"] for d in docs), 1),
            "latestSaleDate": max(datetime.strptime(d["SOLD_DATE"], "%d/%m/%Y").date() for d in docs).strftime("%d/%m/%Y"),
            "dataAsOf": _z(as_of),
        }

    return _run(request, go)


@router.get("/price-index")
def price_index(request: Request):
    def go(conn):
        _check(request, {"class", "period", "from", "to", "modifiedSince"})
        q = request.query_params
        p = PRICE_INDEX.c
        as_of = feed_row(conn).last_refresh_at
        cond = [p.last_updated <= as_of]
        if "class" in q:
            cond.append(p.asset_class == q["class"].upper())
        for k, op in (("period", "__eq__"), ("from", "__ge__"), ("to", "__le__")):
            if k in q:
                v = q[k]
                if len(v) != 7 or v[4] != "-":
                    raise ApiError(400, "invalid_parameter", f"{k} must be a month (YYYY-MM)", k)
                cond.append(getattr(p.period, op)(v))
        if "modifiedSince" in q:
            cond.append(p.last_updated > _since(q["modifiedSince"]))
        w = and_(*cond)
        sel = select(p.doc).where(w).order_by(p.asset_class, p.period)
        return _page(request, conn, sel, select(func.count()).select_from(PRICE_INDEX).where(w), as_of)

    return _run(request, go)


def _status(conn: Connection) -> dict:
    f = feed_row(conn)
    now = clock.now(conn)
    age = int((now - f.last_refresh_at).total_seconds() // 60)
    held = conn.execute(
        select(func.count()).select_from(COMPARABLES).where(COMPARABLES.c.last_updated > f.last_refresh_at)
    ).scalar_one()
    expired = now >= f.token_expires_at
    return {
        "feedId": f.feed_id,
        "state": "stale" if expired or age > 2 * f.refresh_interval_min else "current",
        "lastRefreshAt": _z(f.last_refresh_at),
        "refreshIntervalMinutes": f.refresh_interval_min,
        "ageMinutes": age,
        "tokenExpiresAt": _z(f.token_expires_at),
        "tokenExpired": expired,
        "pendingRecords": held,
        "asOf": _z(now),
    }


@router.get("/feed/status")
def feed_status(request: Request):
    return _run(request, _status)


@router.post("/feed/token")
async def renew_token(request: Request):
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        body = {"__invalid__": True}

    def go(conn):
        if "__invalid__" in body:
            raise ApiError(400, "invalid_body", "The request body must be a JSON object")
        days = body.get("validityDays", 90)
        if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365:
            raise ApiError(400, "invalid_parameter", "validityDays must be an integer from 1 to 365", "validityDays")
        now = clock.now(conn)
        conn.execute(update(FEED).where(FEED.c.id == 1).values(last_refresh_at=now, token_expires_at=now + timedelta(days=days)))
        out = _status(conn)
        events.emit(conn, SOURCE, "com.rbglobal.marketdata.feed.refreshed", out["feedId"], out, now)
        return out

    return _run(request, go)
