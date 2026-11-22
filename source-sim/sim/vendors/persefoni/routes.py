"""Persefoni API v1 mock (docs/backend-steps.md, B5b). See the package docstring for documentation and assumptions.

    POST /persefoni/oauth/token                       client credentials (form or JSON) -> bearer token
    GET  /persefoni/v1/emission-factors               ?category= &asset_class= &route= &scope= &version=
    GET  /persefoni/v1/emission-factors/{id}
    GET  /persefoni/v1/activities                     ?activity_type= &asset_id= &external_reference= &route=
    GET  /persefoni/v1/activities/{id}
    POST /persefoni/v1/activities                     record activity data; its footprint is calculated (201)
    GET  /persefoni/v1/footprints                     ?activity_id= &asset_id= &external_reference= &activity_type= &route=
                                                      &calculation_method= &methodology=
    GET  /persefoni/v1/footprints/{id}
Every list: ?page= (1-based) &per_page= (default 100, max 500) &updated_since= (ISO 8601, strictly after); body
{"data": [...], "meta": {"page", "per_page", "total_count", "total_pages"}, "links": {"self", "next", "prev"}}.
Errors: {"errors": [{"status": "422", "code": "...", "title": "...", "detail": "...", "source": {"pointer": "/quantity"}}]}.
"""

import base64
import binascii
import math
import secrets
import time
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Table, func, select
from sqlalchemy.engine import Connection

from sim.core import clock, events
from sim.core.db import engine
from sim.vendors.persefoni import models as t
from sim.vendors.persefoni.seed import KG_PER, calculate, iso

router = APIRouter(prefix="/persefoni")
SOURCE = "esg"

CLIENTS = {"circularity-di-connector": "circularity-demo-persefoni-secret"}  # demo credentials
AUDIENCE = "https://api.persefoni.com"
TOKEN_TTL = 86400
_tokens: dict[str, float] = {}
DEFAULT_PER_PAGE, MAX_PER_PAGE = 100, 500
TITLES = {400: "Bad Request", 401: "Unauthorized", 404: "Not Found", 422: "Unprocessable Entity"}


def error(status: int, code: str, detail: str, pointer: str | None = None) -> JSONResponse:
    e: dict[str, Any] = {"status": str(status), "code": code, "title": TITLES.get(status, "Error"), "detail": detail}
    if pointer:
        e["source"] = {"pointer": pointer}
    headers = {"WWW-Authenticate": f'Bearer realm="{AUDIENCE}", error="invalid_token"'} if status == 401 else None
    return JSONResponse({"errors": [e]}, status_code=status, headers=headers)


def authenticated(request: Request) -> bool:
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer "):
        return False
    exp = _tokens.get(h[7:].strip())
    return bool(exp and exp > time.time())


def unauthorized() -> JSONResponse:
    return error(401, "unauthorized", "Missing or invalid access token")


@router.post("/oauth/token")
async def token(request: Request):
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
        except ValueError:
            body = {}
    else:
        body = dict(await request.form())
    body = body if isinstance(body, dict) else {}
    client, secret = body.get("client_id", ""), body.get("client_secret", "")
    h = request.headers.get("authorization", "")
    if not client and h.lower().startswith("basic "):
        try:
            client, _, secret = base64.b64decode(h[6:]).decode().partition(":")
        except (binascii.Error, UnicodeDecodeError):
            client = ""
    if body.get("grant_type") != "client_credentials":
        return JSONResponse({"error": "unsupported_grant_type", "error_description": "Unsupported grant type"}, 403)
    if not client or CLIENTS.get(client) != secret:
        return JSONResponse({"error": "access_denied", "error_description": "Unauthorized"}, 401)
    if body.get("audience") not in (None, "", AUDIENCE):
        return JSONResponse({"error": "access_denied", "error_description": "Service not found: " + body["audience"]}, 403)
    tok = secrets.token_urlsafe(40)
    _tokens[tok] = time.time() + TOKEN_TTL
    return {
        "access_token": tok,
        "token_type": "Bearer",
        "expires_in": TOKEN_TTL,
        "scope": "read:emission_factors read:activities write:activities read:footprints",
    }


def _since(v: str) -> datetime:
    d = datetime.fromisoformat(v.strip().replace(" ", "+").replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def listing(request: Request, table: Table, filters: tuple[str, ...]) -> JSONResponse:
    q = request.query_params
    try:
        page = int(q.get("page", 1))
        per_page = int(q.get("per_page", DEFAULT_PER_PAGE))
    except ValueError:
        return error(400, "invalid_parameter", "page and per_page must be integers")
    if page < 1:
        return error(400, "invalid_parameter", "page must be >= 1", "page")
    if not 1 <= per_page <= MAX_PER_PAGE:
        return error(400, "invalid_parameter", f"per_page must be between 1 and {MAX_PER_PAGE}", "per_page")
    where = []
    for f in filters:
        if q.get(f) is not None:
            where.append(table.c.doc[f].astext == q[f])
    if q.get("updated_since"):
        try:
            where.append(table.c.updated_at > _since(q["updated_since"]))
        except ValueError:
            return error(400, "invalid_parameter", "updated_since must be an ISO 8601 date-time", "updated_since")
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(table).where(*where)).scalar_one()
        docs = (
            conn.execute(select(table.c.doc).where(*where).order_by(table.c.id).offset((page - 1) * per_page).limit(per_page))
            .scalars()
            .all()
        )
    pages = max(1, math.ceil(total / per_page))

    def link(p: int) -> str:
        return str(request.url.include_query_params(page=p, per_page=per_page))

    return JSONResponse(
        {
            "data": docs,
            "meta": {"page": page, "per_page": per_page, "total_count": total, "total_pages": pages},
            "links": {
                "self": link(page),
                "next": link(page + 1) if page < pages else None,
                "prev": link(page - 1) if page > 1 else None,
            },
        }
    )


def one(table: Table, id_: str, kind: str):
    with engine.connect() as conn:
        doc = conn.execute(select(table.c.doc).where(table.c.id == id_)).scalar()
    return {"data": doc} if doc else error(404, "not_found", f"{kind} {id_} not found")


FACTOR_FILTERS = ("category", "asset_class", "route", "scope", "version")
ACTIVITY_FILTERS = ("activity_type", "asset_id", "external_reference", "route", "calculation_method")
FOOTPRINT_FILTERS = (
    "activity_id",
    "asset_id",
    "external_reference",
    "activity_type",
    "route",
    "calculation_method",
    "methodology",
)


@router.get("/v1/emission-factors")
def list_factors(request: Request):
    return listing(request, t.EMISSION_FACTOR, FACTOR_FILTERS) if authenticated(request) else unauthorized()


@router.get("/v1/emission-factors/{factor_id}")
def get_factor(factor_id: str, request: Request):
    return one(t.EMISSION_FACTOR, factor_id, "Emission factor") if authenticated(request) else unauthorized()


@router.get("/v1/activities")
def list_activities(request: Request):
    return listing(request, t.ACTIVITY, ACTIVITY_FILTERS) if authenticated(request) else unauthorized()


@router.get("/v1/activities/{activity_id}")
def get_activity(activity_id: str, request: Request):
    return one(t.ACTIVITY, activity_id, "Activity") if authenticated(request) else unauthorized()


@router.get("/v1/footprints")
def list_footprints(request: Request):
    return listing(request, t.FOOTPRINT, FOOTPRINT_FILTERS) if authenticated(request) else unauthorized()


@router.get("/v1/footprints/{footprint_id}")
def get_footprint(footprint_id: str, request: Request):
    return one(t.FOOTPRINT, footprint_id, "Footprint") if authenticated(request) else unauthorized()


def _factors(conn: Connection) -> dict[str, dict]:
    return {d["id"]: d for d in conn.execute(select(t.EMISSION_FACTOR.c.doc)).scalars()}


def _number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


@router.post("/v1/activities")
async def create_activity(request: Request):
    if not authenticated(request):
        return unauthorized()
    try:
        body = await request.json()
    except ValueError:
        return error(400, "invalid_json", "The request body is not valid JSON")
    a = body.get("data", body) if isinstance(body, dict) else None
    if not isinstance(a, dict):
        return error(400, "invalid_json", "The request body must be a JSON object")
    method = a.get("calculation_method", "factor_based")
    if method not in ("factor_based", "reported"):
        return error(422, "invalid_value", "calculation_method must be factor_based or reported", "/calculation_method")
    for f in ("activity_type", "asset_id"):
        if not isinstance(a.get(f), str) or not a[f]:
            return error(422, "missing_field", f"{f} is required", f"/{f}")
    with engine.begin() as conn:
        now = clock.now(conn)
        stamp = now.replace(microsecond=now.microsecond // 1000 * 1000)
        period = a.get("period") or stamp.strftime("%Y-%m")
        try:
            period_start = date.fromisoformat(period + "-01")
        except (TypeError, ValueError):
            return error(422, "invalid_value", "period must be YYYY-MM", "/period")
        factors = _factors(conn)
        ef = factors.get(a.get("emission_factor_id") or "")
        av_id = a.get("avoidance_factor_id") or (f"ef_route_{a['route']}" if a.get("route") else None)
        av = factors.get(av_id or "")
        if av_id and (av is None or av["category"] != "avoided_emissions"):
            return error(422, "unknown_emission_factor", f"Avoidance factor {av_id} not found", "/avoidance_factor_id")
        if method == "factor_based":
            if ef is None or ef["category"] != "embodied_carbon":
                return error(
                    422, "unknown_emission_factor", "emission_factor_id must name an emission factor", "/emission_factor_id"
                )
            if not _number(a.get("quantity")) or a["quantity"] <= 0:
                return error(422, "invalid_value", "quantity must be a positive number", "/quantity")
            if a.get("quantity_unit") != ef["activity_unit"]:
                return error(
                    422,
                    "unit_mismatch",
                    f"quantity_unit {a.get('quantity_unit')!r} does not match the factor's activity unit {ef['activity_unit']!r}",
                    "/quantity_unit",
                )
            for f in (ef, av):
                if f and (
                    period_start < date.fromisoformat(f["valid_from"])
                    or (f["valid_to"] and period_start > date.fromisoformat(f["valid_to"]))
                ):
                    return error(422, "factor_not_valid", f"{f['id']} is not valid for period {period}", "/period")
        else:
            if not _number(a.get("reported_co2e")) or a["reported_co2e"] < 0:
                return error(422, "invalid_value", "reported_co2e must be a number >= 0", "/reported_co2e")
            if a.get("reported_co2e_unit") not in KG_PER:
                return error(422, "invalid_value", f"reported_co2e_unit must be one of {sorted(KG_PER)}", "/reported_co2e_unit")
            if a.get("measured_co2e") is not None and (not _number(a["measured_co2e"]) or a["measured_co2e"] < 0):
                return error(422, "invalid_value", "measured_co2e must be a number >= 0", "/measured_co2e")
        n = conn.execute(select(func.count()).select_from(t.ACTIVITY)).scalar_one() + 1
        act = {
            "id": f"act_{secrets.token_hex(4)}{n:05d}",
            "activity_type": a["activity_type"],
            "calculation_method": method,
            "external_reference": a.get("external_reference"),
            "asset_id": a["asset_id"],
            "asset_class": a.get("asset_class") or (ef or {}).get("asset_class"),
            "route": a.get("route") or (av or {}).get("route"),
            "quantity": a.get("quantity"),
            "quantity_unit": a.get("quantity_unit"),
            "tenant": a.get("tenant"),
            "site": a.get("site"),
            "period": period,
            "emission_factor_id": ef["id"] if ef else None,
            "avoidance_factor_id": av["id"] if av else None,
            "reported_co2e": a.get("reported_co2e"),
            "measured_co2e": a.get("measured_co2e"),
            "reported_co2e_unit": a.get("reported_co2e_unit"),
            "status": a.get("status") or "estimate",
            "created_at": iso(stamp),
            "updated_at": iso(stamp),
        }
        fp = calculate(act, factors, stamp)
        conn.execute(t.ACTIVITY.insert().values(id=act["id"], doc=act, updated_at=stamp))
        conn.execute(t.FOOTPRINT.insert().values(id=fp["id"], activity_id=act["id"], doc=fp, updated_at=stamp))
        events.emit(conn, SOURCE, "persefoni.activity.created", act["id"], act)
        events.emit(conn, SOURCE, "persefoni.footprint.calculated", fp["id"], fp)
    return JSONResponse(
        {"data": act, "included": [fp]}, status_code=201, headers={"Location": f"/persefoni/v1/activities/{act['id']}"}
    )
