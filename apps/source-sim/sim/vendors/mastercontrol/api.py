"""MasterControl Quality Excellence REST API mock (docs/BACKEND_STEPS.md, B5b). See the package docstring for the
documentation followed and the assumptions.

    POST /mastercontrol/mc/api/oauth2/token                          client credentials -> bearer token
    GET  /mastercontrol/mc/api/v2/controlled-documents               ?documentNumber= &documentType= &status= &assetClass=
    GET  /mastercontrol/mc/api/v2/controlled-documents/{infoCardId}
    GET  /mastercontrol/mc/api/v2/certificates                       ?assetId= &certificateNumber= &certificateType= &status=
    GET  /mastercontrol/mc/api/v2/certificates/{recordId}
    POST /mastercontrol/mc/api/v2/certificates                       record a certificate (201 + Location)
    POST /mastercontrol/mc/api/v2/certificates/{recordId}/revoke     {"reason": "..."}
    GET  /mastercontrol/mc/api/v2/test-criteria                      ?assetClass= &documentNumber=
    GET  /mastercontrol/mc/api/v2/deviations                         ?assetId= &status=
Every list: ?limit= (default 100, max 1000) &cursor= (opaque) &modifiedSince= (ISO 8601, strictly after);
body {"data": [...], "paging": {"limit": n, "nextCursor": "..."|null}, "totalCount": n}.

Business rules (on the simulated clock, UTC dates):
- document status: Draft / In Approval as stored; a Released revision is "Pending Effective" before its effective date,
  "Superseded" once a later released revision is effective, otherwise "Effective". Only Effective revisions are policy:
  a certificate can only be recorded against a document number with an Effective revision.
- certificate status: "Revoked" once revoked; "Expired" from the day after CERT_EXPIRY; otherwise "Active".
- a status that changes with the clock moves `lastModifiedDate` to the moment it changed, so ?modifiedSince= sees it.
Writes stamp clock.now() and emit outbox events (source "qms").
"""

import base64
import binascii
import json
import secrets
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from sim import clock, events
from sim.db import engine
from sim.vendors.mastercontrol import tables as t

router = APIRouter(prefix="/mastercontrol/mc/api")
SOURCE = "qms"

# Demo credentials (nothing real is protected here)
CLIENTS = {"circularity-di": "circularity-demo-mastercontrol-secret"}  # OAuth client id -> secret
API_KEYS = {"circularity-demo-mastercontrol-apikey": "circularity-di"}  # tenant API key -> integration user
TOKEN_TTL = 3600
_tokens: dict[str, float] = {}

DEFAULT_LIMIT, MAX_LIMIT = 100, 1000
CERT_TYPES = {"LIFE_CERTIFICATION", "REQUALIFICATION", "DATA_ERASURE"}
RESULTS = {"PASS", "FAIL"}


# ------------------------------------------------------------------ errors and auth
def error(request: Request, status: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    body: dict[str, Any] = {
        "status": status,
        "errorCode": code,
        "message": message,
        "timestamp": iso(datetime.now(UTC)),
        "path": request.url.path,
    }
    if details:
        body["errors"] = details
    headers = {"WWW-Authenticate": 'Bearer realm="MasterControl"'} if status == 401 else None
    return JSONResponse(body, status_code=status, headers=headers)


def authenticated(request: Request) -> bool:
    key = request.headers.get("x-api-key")
    if key:
        return key in API_KEYS
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        exp = _tokens.get(h[7:].strip())
        return bool(exp and exp > time.time())
    return False


def unauthorized(request: Request) -> JSONResponse:
    return error(request, 401, "UNAUTHORIZED", "Full authentication is required to access this resource")


@router.post("/oauth2/token")
async def token(request: Request):
    form = dict(await request.form())
    client, secret = form.get("client_id", ""), form.get("client_secret", "")
    h = request.headers.get("authorization", "")
    if not client and h.lower().startswith("basic "):
        try:
            client, _, secret = base64.b64decode(h[6:]).decode().partition(":")
        except (binascii.Error, UnicodeDecodeError):
            client = ""
    if form.get("grant_type") != "client_credentials":
        return JSONResponse({"error": "unsupported_grant_type", "error_description": "Only client_credentials"}, 400)
    if not client or CLIENTS.get(client) != secret:
        return JSONResponse({"error": "invalid_client", "error_description": "Bad client credentials"}, 401)
    tok = secrets.token_urlsafe(32)
    _tokens[tok] = time.time() + TOKEN_TTL
    return {"access_token": tok, "token_type": "bearer", "expires_in": TOKEN_TTL, "scope": "qx.read qx.write"}


# ------------------------------------------------------------------ helpers
def iso(d: datetime | None) -> str | None:
    if d is None:
        return None
    return d.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ms(d: datetime) -> datetime:
    return d.replace(microsecond=d.microsecond // 1000 * 1000)


def midnight(d: date) -> datetime:
    return datetime.combine(d, dtime(0), tzinfo=UTC)


def _parse_since(v: str | None) -> datetime | None:
    if not v:
        return None
    d = datetime.fromisoformat(v.strip().replace(" ", "+").replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def listing(request: Request, items: list[dict]) -> JSONResponse:
    """Filter by ?modifiedSince=, then page with ?limit= / ?cursor=."""
    q = request.query_params
    try:
        since = _parse_since(q.get("modifiedSince"))
    except ValueError:
        return error(request, 400, "INVALID_PARAMETER", "modifiedSince must be an ISO 8601 date-time")
    try:
        limit = int(q.get("limit", DEFAULT_LIMIT))
        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError
    except ValueError:
        return error(request, 400, "INVALID_PARAMETER", f"limit must be between 1 and {MAX_LIMIT}")
    offset = 0
    if q.get("cursor"):
        try:
            offset = int(json.loads(base64.urlsafe_b64decode(q["cursor"].encode()))["o"])
        except (ValueError, KeyError, TypeError, binascii.Error):
            return error(request, 400, "INVALID_CURSOR", "The cursor is not valid")
    if since:
        items = [i for i in items if _parse_since(i["lastModifiedDate"]) > since]
    page = items[offset : offset + limit]
    nxt = None
    if offset + limit < len(items):
        nxt = base64.urlsafe_b64encode(json.dumps({"o": offset + limit}).encode()).decode()
    return JSONResponse({"data": page, "paging": {"limit": limit, "nextCursor": nxt}, "totalCount": len(items)})


def _match(request: Request, item: dict, params: dict[str, Any]) -> bool:
    for param, getter in params.items():
        v = request.query_params.get(param)
        if v is not None and str(getter(item) or "").lower() != v.lower():
            return False
    return True


# ------------------------------------------------------------------ controlled documents
def documents(conn: Connection) -> list[dict]:
    now = clock.now(conn)
    today = now.astimezone(UTC).date()
    rows = [r._mapping for r in conn.execute(select(t.DOCUMENT).order_by(t.DOCUMENT.c.infocard_id))]
    out = []
    for r in rows:
        status, changed, superseded = r["lifecycle"], r["last_modified_date"], None
        if r["lifecycle"] == "Released":
            eff = r["effective_date"]
            if eff > today:
                status = "Pending Effective"
            else:
                changed = max(changed, midnight(eff))
                later = [
                    o["effective_date"]
                    for o in rows
                    if o["document_number"] == r["document_number"]
                    and o["lifecycle"] == "Released"
                    and o["effective_date"] <= today
                    and o["effective_date"] > eff
                ]
                if later:
                    status, superseded = "Superseded", min(later)
                    changed = max(changed, midnight(superseded))
                else:
                    status = "Effective"
        out.append(
            {
                "infoCardId": r["infocard_id"],
                "documentNumber": r["document_number"],
                "revision": r["revision"],
                "title": r["title"],
                "infoCardType": r["infocard_type"],
                "lifecycleState": r["lifecycle"],
                "status": status,
                "effectiveDate": r["effective_date"].isoformat() if r["effective_date"] else None,
                "supersededDate": superseded.isoformat() if superseded else None,
                "owner": r["owner"],
                "dataFields": r["data_fields"],
                "createdDate": iso(r["created_date"]),
                "lastModifiedDate": iso(changed),
            }
        )
    return out


DOC_FILTERS = {
    "documentNumber": lambda d: d["documentNumber"],
    "documentType": lambda d: d["infoCardType"],
    "status": lambda d: d["status"],
    "assetClass": lambda d: d["dataFields"].get("ASSET_CLASS"),
}


@router.get("/v2/controlled-documents")
def list_documents(request: Request):
    if not authenticated(request):
        return unauthorized(request)
    with engine.connect() as conn:
        docs = documents(conn)
    return listing(request, [d for d in docs if _match(request, d, DOC_FILTERS)])


@router.get("/v2/controlled-documents/{infocard_id}")
def get_document(infocard_id: str, request: Request):
    if not authenticated(request):
        return unauthorized(request)
    with engine.connect() as conn:
        doc = next((d for d in documents(conn) if d["infoCardId"] == infocard_id), None)
    return doc or error(request, 404, "NOT_FOUND", f"InfoCard {infocard_id} not found")


def effective_document(conn: Connection, number: str) -> dict | None:
    return next((d for d in documents(conn) if d["documentNumber"] == number and d["status"] == "Effective"), None)


# ------------------------------------------------------------------ certificates
def _cert(r, now: datetime) -> dict:
    fields = r["data_fields"]
    changed, status, expired_on = r["last_modified_date"], "Active", None
    exp = fields.get("CERT_EXPIRY")
    if r["revoked_date"] is not None:
        status = "Revoked"
    elif exp:
        expired_on = midnight(date.fromisoformat(exp) + timedelta(days=1))
        if now >= expired_on:
            status = "Expired"
            changed = max(changed, expired_on)
    return {
        "recordId": r["record_id"],
        "certificateNumber": r["certificate_number"],
        "certificateType": r["certificate_type"],
        "status": status,
        "issuedDate": r["issued_date"].isoformat(),
        "revokedDate": iso(r["revoked_date"]),
        "revokeReason": r["revoke_reason"],
        "dataFields": fields,
        "createdBy": r["created_by"],
        "createdDate": iso(r["created_date"]),
        "lastModifiedDate": iso(changed),
    }


def certificates(conn: Connection) -> list[dict]:
    now = clock.now(conn)
    return [_cert(r._mapping, now) for r in conn.execute(select(t.CERTIFICATE).order_by(t.CERTIFICATE.c.record_id))]


CERT_FILTERS = {
    "assetId": lambda c: c["dataFields"].get("ASSET_ID"),
    "certificateNumber": lambda c: c["certificateNumber"],
    "certificateType": lambda c: c["certificateType"],
    "status": lambda c: c["status"],
}


@router.get("/v2/certificates")
def list_certificates(request: Request):
    if not authenticated(request):
        return unauthorized(request)
    with engine.connect() as conn:
        certs = certificates(conn)
    return listing(request, [c for c in certs if _match(request, c, CERT_FILTERS)])


@router.get("/v2/certificates/{record_id}")
def get_certificate(record_id: str, request: Request):
    if not authenticated(request):
        return unauthorized(request)
    with engine.connect() as conn:
        r = conn.execute(select(t.CERTIFICATE).where(t.CERTIFICATE.c.record_id == record_id)).first()
        return _cert(r._mapping, clock.now(conn)) if r else error(request, 404, "NOT_FOUND", f"Record {record_id} not found")


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(v) if isinstance(v, str) else None
    except ValueError:
        return None


@router.post("/v2/certificates")
async def create_certificate(request: Request):
    if not authenticated(request):
        return unauthorized(request)
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return error(request, 400, "MALFORMED_REQUEST", "The request body must be a JSON object")
    fields = body.get("dataFields") if isinstance(body.get("dataFields"), dict) else {}
    problems = []
    number, type_ = body.get("certificateNumber"), body.get("certificateType")
    issued, expiry = _date(body.get("issuedDate")), fields.get("CERT_EXPIRY")
    if not number or not isinstance(number, str):
        problems.append({"field": "certificateNumber", "message": "must not be blank"})
    if type_ not in CERT_TYPES:
        problems.append({"field": "certificateType", "message": f"must be one of {sorted(CERT_TYPES)}"})
    if issued is None:
        problems.append({"field": "issuedDate", "message": "must be a date (yyyy-MM-dd)"})
    if not fields.get("ASSET_ID"):
        problems.append({"field": "dataFields.ASSET_ID", "message": "must not be blank"})
    if fields.get("TEST_RESULT") not in RESULTS:
        problems.append({"field": "dataFields.TEST_RESULT", "message": "must be PASS or FAIL"})
    if not fields.get("DOCUMENT_NUMBER"):
        problems.append({"field": "dataFields.DOCUMENT_NUMBER", "message": "must not be blank"})
    if type_ != "DATA_ERASURE" or expiry is not None:
        if _date(expiry) is None:
            problems.append({"field": "dataFields.CERT_EXPIRY", "message": "must be a date (yyyy-MM-dd)"})
        elif issued and _date(expiry) <= issued:
            problems.append({"field": "dataFields.CERT_EXPIRY", "message": "must be after issuedDate"})
    months = fields.get("CERTIFIED_LIFE_MONTHS")
    if months is not None and (not isinstance(months, int) or isinstance(months, bool) or months <= 0):
        problems.append({"field": "dataFields.CERTIFIED_LIFE_MONTHS", "message": "must be a positive integer"})
    with engine.begin() as conn:
        now = clock.now(conn)
        if issued and issued > now.astimezone(UTC).date():
            problems.append({"field": "issuedDate", "message": "must not be in the future"})
        if problems:
            return error(request, 400, "VALIDATION_ERROR", "Validation failed", problems)
        if conn.execute(
            select(t.CERTIFICATE.c.record_id).where(
                t.CERTIFICATE.c.certificate_number == number, t.CERTIFICATE.c.revoked_date.is_(None)
            )
        ).first():
            return error(request, 409, "DUPLICATE_CERTIFICATE_NUMBER", f"Certificate {number} already exists")
        doc = effective_document(conn, fields["DOCUMENT_NUMBER"])
        if doc is None:
            return error(
                request,
                422,
                "DOCUMENT_NOT_EFFECTIVE",
                f"Document {fields['DOCUMENT_NUMBER']} has no effective revision",
            )
        n = conn.execute(
            update(t.COUNTER)
            .where(t.COUNTER.c.name == "certificate")
            .values(value=t.COUNTER.c.value + 1)
            .returning(t.COUNTER.c.value)
        ).scalar_one()
        stamp = ms(now)
        record = {
            "record_id": f"MC-CERT-{n:06d}",
            "certificate_number": number,
            "certificate_type": type_,
            "issued_date": issued,
            "revoked_date": None,
            "revoke_reason": None,
            "data_fields": {
                "ASSET_ID": fields["ASSET_ID"],
                "ASSET_CLASS": fields.get("ASSET_CLASS") or doc["dataFields"].get("ASSET_CLASS"),
                "CERTIFIED_LIFE_MONTHS": months,
                "CERT_EXPIRY": expiry,
                "TEST_RESULT": fields["TEST_RESULT"],
                "REUSE_CLASS": doc["dataFields"].get("REUSE_CLASS"),  # from the effective policy revision
                "DOCUMENT_NUMBER": fields["DOCUMENT_NUMBER"],
                "BASIS": fields.get("BASIS"),
            },
            "created_by": "circularity-di",
            "created_date": stamp,
            "last_modified_date": stamp,
        }
        conn.execute(t.CERTIFICATE.insert().values(**record))
        out = _cert(record, now)
        events.emit(conn, SOURCE, "mastercontrol.certificate.created", record["record_id"], out)
    return JSONResponse(out, status_code=201, headers={"Location": f"{router.prefix}/v2/certificates/{record['record_id']}"})


@router.post("/v2/certificates/{record_id}/revoke")
async def revoke_certificate(record_id: str, request: Request):
    if not authenticated(request):
        return unauthorized(request)
    try:
        body = await request.json()
    except ValueError:
        body = None
    reason = body.get("reason") if isinstance(body, dict) else None
    if not reason or not isinstance(reason, str):
        return error(request, 400, "VALIDATION_ERROR", "Validation failed", [{"field": "reason", "message": "must not be blank"}])
    with engine.begin() as conn:
        r = conn.execute(select(t.CERTIFICATE).where(t.CERTIFICATE.c.record_id == record_id)).first()
        if r is None:
            return error(request, 404, "NOT_FOUND", f"Record {record_id} not found")
        if r.revoked_date is not None:
            return error(request, 409, "ALREADY_REVOKED", f"Record {record_id} is already revoked")
        now = clock.now(conn)
        stamp = ms(now)
        conn.execute(
            update(t.CERTIFICATE)
            .where(t.CERTIFICATE.c.record_id == record_id)
            .values(revoked_date=stamp, revoke_reason=reason, last_modified_date=stamp)
        )
        r = conn.execute(select(t.CERTIFICATE).where(t.CERTIFICATE.c.record_id == record_id)).first()
        out = _cert(r._mapping, now)
        events.emit(conn, SOURCE, "mastercontrol.certificate.revoked", record_id, out)
    return out


# ------------------------------------------------------------------ test criteria and deviations
@router.get("/v2/test-criteria")
def list_test_criteria(request: Request):
    if not authenticated(request):
        return unauthorized(request)
    with engine.connect() as conn:
        rows = [r._mapping for r in conn.execute(select(t.TEST_CRITERION).order_by(t.TEST_CRITERION.c.test_id))]
    items = [
        {
            "testId": r["test_id"],
            "testName": r["test_name"],
            "assetClass": r["asset_class"],
            "method": r["method"],
            "acceptanceCriteria": r["acceptance_criteria"],
            "standardRef": r["standard_ref"],
            "mandatoryForRoutes": r["mandatory_for_routes"],
            "documentNumber": r["document_number"],
            "lastModifiedDate": iso(r["last_modified_date"]),
        }
        for r in rows
    ]
    filters = {"assetClass": lambda x: x["assetClass"], "documentNumber": lambda x: x["documentNumber"]}
    return listing(request, [i for i in items if _match(request, i, filters)])


@router.get("/v2/deviations")
def list_deviations(request: Request):
    if not authenticated(request):
        return unauthorized(request)
    with engine.connect() as conn:
        rows = [r._mapping for r in conn.execute(select(t.DEVIATION).order_by(t.DEVIATION.c.deviation_id))]
    items = [
        {
            "deviationId": r["deviation_id"],
            "title": r["title"],
            "assetId": r["asset_id"],
            "severity": r["severity"],
            "status": r["status"],
            "disposition": r["disposition"],
            "approverName": r["approver_name"],
            "openedDate": r["opened_date"].isoformat(),
            "closedDate": r["closed_date"].isoformat() if r["closed_date"] else None,
            "lastModifiedDate": iso(r["last_modified_date"]),
        }
        for r in rows
    ]
    filters = {"assetId": lambda x: x["assetId"], "status": lambda x: x["status"]}
    return listing(request, [i for i in items if _match(request, i, filters)])
