"""Salesforce REST API surface (docs/BACKEND_STEPS.md, B5). Paths as a client sees them, under the mock's /salesforce:

    POST  /services/oauth2/token                          JWT bearer (assertion) or client credentials
    GET   /services/data                                  API versions (no auth)
    GET   /services/data/v59.0                            resources
    GET   /services/data/v59.0/sobjects                   describeGlobal
    GET   /services/data/v59.0/sobjects/{Object}          basic info and recent items
    GET   /services/data/v59.0/sobjects/{Object}/describe
    GET   /services/data/v59.0/sobjects/{Object}/{Id}[?fields=A,B]
    POST  /services/data/v59.0/sobjects/{Object}          Task, Opportunity → 201 {id, success, errors}
    PATCH /services/data/v59.0/sobjects/{Object}/{Id}     Task, Opportunity → 204
    GET   /services/data/v59.0/query?q=<SOQL>             → {totalSize, done, records, nextRecordsUrl}
    GET   /services/data/v59.0/query/{locator}-{offset}   next page

Every API call needs `Authorization: Bearer <access_token>`. Errors are Salesforce's JSON arrays
`[{"message": ..., "errorCode": ..., "fields": [...]}]`. Pages hold PAGE_SIZE (2000) records; a client may ask for
smaller ones with `Sforce-Query-Options: batchSize=n` (Salesforce's minimum of 200 is not enforced, for tests).
URLs in responses are relative to instance_url, which the token endpoint returns as <host>/salesforce.
"""

import functools
import inspect
import re
import secrets
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select, update

from sim import events
from sim.db import engine
from sim.vendors.salesforce import auth
from sim.vendors.salesforce.schema import (
    API_VERSION,
    BASE,
    BY_LOWER,
    BY_PREFIX,
    OBJECTS,
    RECORD_SEQ,
    STAGE_RULES,
    TABLES,
    Field,
    SObject,
    make_id,
    normalise_id,
)
from sim.vendors.salesforce.soql import SoqlError, compile_query, parse

SOURCE = "crm"
PAGE_SIZE = 2000
router = APIRouter(prefix="/salesforce")
_locators: dict[str, tuple[str, int]] = {}  # query locator -> (SOQL, batch size)


class SFError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields


def _error_response(e: SFError) -> JSONResponse:
    body: dict[str, Any] = {"message": e.message, "errorCode": e.code}
    if e.fields is not None:
        body["fields"] = e.fields
    return JSONResponse([body], status_code=e.status)


def _sf(fn):
    """Turn SFError and SoqlError into Salesforce error arrays."""

    def handle(e: Exception) -> JSONResponse:
        if isinstance(e, SoqlError):
            return _error_response(SFError(400, e.code, e.message))
        return _error_response(e)

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except (SFError, SoqlError) as e:
                return handle(e)

    else:

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except (SFError, SoqlError) as e:
                return handle(e)

    return wrapper


def _user(request: Request) -> str:
    uid = auth.session_user(request)
    if not uid:
        raise SFError(401, "INVALID_SESSION_ID", "Session expired or invalid")
    return uid


def _object(name: str) -> SObject:
    obj = BY_LOWER.get(name.lower())
    if not obj:
        raise SFError(404, "NOT_FOUND", "The requested resource does not exist")
    return obj


def _not_found() -> SFError:
    return SFError(404, "NOT_FOUND", "The requested resource does not exist")


# ------------------------------------------------------------------ values out
def ts(v: datetime) -> str:
    v = v.astimezone(UTC)
    return v.strftime("%Y-%m-%dT%H:%M:%S.") + f"{v.microsecond // 1000:03d}+0000"


def out(f: Field, v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return int(v) if f.type == "int" else float(v)
    if isinstance(v, datetime):
        return ts(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def _url(obj: str, rid: str) -> str:
    return f"{BASE}/sobjects/{obj}/{rid}"


def record(obj: SObject, row: Any, fields: list[Field] | None = None) -> dict:
    rec: dict[str, Any] = {"attributes": {"type": obj.name, "url": _url(obj.name, row["Id"])}}
    for f in fields or obj.fields:
        rec[f.name] = out(f, row[f.name])
    return rec


# ------------------------------------------------------------------ auth
@router.post("/services/oauth2/token")
async def token(request: Request):
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    try:
        return auth.issue(form, request.headers.get("authorization", ""), str(request.base_url).rstrip("/") + "/salesforce")
    except auth.OAuthError as e:
        return JSONResponse({"error": e.error, "error_description": e.description}, status_code=e.status)


# ------------------------------------------------------------------ discovery
@router.get("/services/data")
def versions():
    return [{"label": "Winter '24", "url": BASE, "version": API_VERSION}]


@router.get(BASE)
@_sf
def resources(request: Request):
    _user(request)
    return {name: f"{BASE}/{name}" for name in ("sobjects", "query")}


def _basic(obj: SObject) -> dict:
    return {
        "name": obj.name,
        "label": obj.label,
        "labelPlural": obj.plural,
        "keyPrefix": obj.prefix,
        "custom": False,
        "createable": obj.writable,
        "updateable": obj.writable,
        "deletable": False,
        "queryable": True,
        "retrieveable": True,
        "searchable": True,
        "urls": {
            "sobject": f"{BASE}/sobjects/{obj.name}",
            "describe": f"{BASE}/sobjects/{obj.name}/describe",
            "rowTemplate": f"{BASE}/sobjects/{obj.name}/{{ID}}",
        },
    }


@router.get(BASE + "/sobjects")
@_sf
def describe_global(request: Request):
    _user(request)
    return {"encoding": "UTF-8", "maxBatchSize": 200, "sobjects": [_basic(o) for o in OBJECTS.values()]}


_SOAP = {
    "id": "tns:ID",
    "reference": "tns:ID",
    "boolean": "xsd:boolean",
    "date": "xsd:date",
    "datetime": "xsd:dateTime",
    "int": "xsd:int",
    "currency": "xsd:double",
    "double": "xsd:double",
    "percent": "xsd:double",
}


def _describe_field(f: Field) -> dict:
    numeric = f.type in ("currency", "double", "percent")
    return {
        "name": f.name,
        "label": f.label,
        "type": f.type,
        "soapType": _SOAP.get(f.type, "xsd:string"),
        "length": f.length if f.type not in _SOAP else 0,
        "precision": 18 if numeric else 0,
        "scale": 2 if numeric else 0,
        "custom": f.custom,
        "nillable": f.nillable,
        "createable": f.create,
        "updateable": f.update,
        "filterable": True,
        "sortable": f.type != "textarea",
        "idLookup": f.name == "Id",
        "referenceTo": list(f.ref),
        "relationshipName": f.rel,
        "defaultedOnCreate": f.default is not None or not f.create,
        "picklistValues": [{"active": True, "defaultValue": v == f.default, "label": v, "value": v} for v in f.picklist],
    }


@router.get(BASE + "/sobjects/{name}/describe")
@_sf
def describe(name: str, request: Request):
    _user(request)
    obj = _object(name)
    children = [
        {"childSObject": o.name, "field": f.name, "relationshipName": None, "cascadeDelete": False}
        for o in OBJECTS.values()
        for f in o.fields
        if obj.name in f.ref and f.name not in ("CreatedById", "LastModifiedById", "OwnerId")
    ]
    return _basic(obj) | {"fields": [_describe_field(f) for f in obj.fields], "childRelationships": children}


@router.get(BASE + "/sobjects/{name}")
@_sf
def sobject_info(name: str, request: Request):
    _user(request)
    obj = _object(name)
    t = TABLES[obj.name]
    label = obj.get("Name") or obj.get("Subject")
    with engine.connect() as conn:
        rows = conn.execute(select(t.c.Id, t.c[label.name]).order_by(t.c.LastModifiedDate.desc(), t.c.Id).limit(5)).all()
    return {
        "objectDescribe": _basic(obj),
        "recentItems": [
            {"attributes": {"type": obj.name, "url": _url(obj.name, r[0])}, "Id": r[0], label.name: r[1]} for r in rows
        ],
    }


@router.get(BASE + "/sobjects/{name}/{rid}")
@_sf
def retrieve(name: str, rid: str, request: Request):
    _user(request)
    obj = _object(name)
    nid = normalise_id(rid)
    if not nid or not nid.startswith(obj.prefix):
        raise SFError(404, "NOT_FOUND", f"Provided external ID field does not exist or is not accessible: {rid}")
    fields = None
    if request.query_params.get("fields"):
        fields = []
        for n in request.query_params["fields"].split(","):
            f = obj.get(n.strip())
            if not f:
                raise SFError(400, "INVALID_FIELD", f"No such column '{n.strip()}' on entity '{obj.name}'.")
            fields.append(f)
    t = TABLES[obj.name]
    with engine.connect() as conn:
        row = conn.execute(select(t).where(t.c.Id == nid)).mappings().first()
    if not row:
        raise _not_found()
    return record(obj, row, fields)


# ------------------------------------------------------------------ query
def _batch_size(request: Request) -> int:
    opts = request.headers.get("sforce-query-options", "")
    m = re.search(r"batchSize\s*=\s*(\d+)", opts)
    return max(1, min(PAGE_SIZE, int(m.group(1)))) if m else PAGE_SIZE


def _run(soql: str, batch: int, page: int, locator: str | None) -> dict:
    plan = compile_query(parse(soql))
    with engine.connect() as conn:
        n = conn.execute(plan.count).scalar_one()
        total = max(0, n - plan.offset)
        if plan.limit is not None:
            total = min(total, plan.limit)
        if plan.count_only:
            return {"totalSize": total, "done": True, "records": []}
        if page and page >= total:
            raise SFError(400, "INVALID_QUERY_LOCATOR", "invalid query locator")
        size = min(batch, total - page)
        rows = conn.execute(plan.rows.offset(plan.offset + page).limit(size)).mappings().all() if size > 0 else []
    records = []
    for row in rows:
        rec: dict[str, Any] = {"attributes": {"type": plan.obj.name, "url": _url(plan.obj.name, row["__id"])}}
        for s in plan.selected:
            if not s.rel:
                rec[s.field.name] = out(s.field, row[s.label])
                continue
            lab, parent = plan.rel_ids[s.rel.rel]
            if row[lab] is None:
                rec[s.rel.rel] = None
                continue
            rec.setdefault(s.rel.rel, {"attributes": {"type": parent.name, "url": _url(parent.name, row[lab])}})
            rec[s.rel.rel][s.field.name] = out(s.field, row[s.label])
        records.append(rec)
    done = page + len(records) >= total
    body: dict[str, Any] = {"totalSize": total, "done": done, "records": records}
    if not done:
        if locator is None:
            locator = make_id("01g", secrets.randbelow(62**6))
            _locators[locator] = (soql, batch)
        body["nextRecordsUrl"] = f"{BASE}/query/{locator}-{page + len(records)}"
    return body


@router.get(BASE + "/query")
@_sf
def query(request: Request):
    _user(request)
    q = request.query_params.get("q")
    if q is None:
        raise SFError(400, "MALFORMED_QUERY", "A query string has to be specified")
    return _run(q, _batch_size(request), 0, None)


@router.get(BASE + "/query/{cursor}")
@_sf
def query_more(cursor: str, request: Request):
    _user(request)
    locator, _, offset = cursor.rpartition("-")
    if locator not in _locators or not offset.isdigit():
        raise SFError(400, "INVALID_QUERY_LOCATOR", "invalid query locator")
    soql, batch = _locators[locator]
    return _run(soql, batch, int(offset), locator)


# ------------------------------------------------------------------ writes
async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise SFError(400, "JSON_PARSER_ERROR", "Unexpected character: the request body is not valid JSON") from None
    if not isinstance(body, dict):
        raise SFError(400, "JSON_PARSER_ERROR", "Cannot deserialize instance of SObject from a non-object value")
    body.pop("attributes", None)
    return body


def _coerce(f: Field, v: Any) -> Any:
    if v is None:
        if not f.nillable:
            raise SFError(400, "REQUIRED_FIELD_MISSING", f"Required fields are missing: [{f.name}]", [f.name])
        return None
    bad = SFError(400, "JSON_PARSER_ERROR", f"Cannot deserialize instance of {f.type} from value {v!r} for field {f.name}")
    if f.type in ("id", "reference"):
        nid = normalise_id(v) if isinstance(v, str) else None
        if not nid:
            raise SFError(400, "MALFORMED_ID", f"{f.label}: id value of incorrect type: {v}", [f.name])
        return nid
    if f.textual or f.type == "textarea":
        if isinstance(v, bool) or not isinstance(v, str | int | float):
            raise bad
        v = str(v)
        if f.length and len(v) > f.length:
            raise SFError(400, "STRING_TOO_LONG", f"{f.label}: data value too large: {v[:40]} (max length={f.length})", [f.name])
        if f.picklist and v not in f.picklist:
            raise SFError(
                400,
                "INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST",
                f"{f.label}: bad value for restricted picklist field: {v}",
                [f.name],
            )
        return v
    if f.type in ("int", "currency", "double", "percent"):
        if isinstance(v, bool):
            raise bad
        try:
            d = Decimal(str(v))
        except InvalidOperation:
            raise bad from None
        if f.type == "int" and d != d.to_integral_value():
            raise bad
        return d
    if f.type == "boolean":
        if not isinstance(v, bool):
            raise bad
        return v
    if f.type == "date":
        try:
            return date.fromisoformat(v)
        except (TypeError, ValueError):
            raise bad from None
    raise bad


def _values(obj: SObject, body: dict, creating: bool) -> dict:
    values = {}
    for key, v in body.items():
        f = obj.get(key)
        if not f:
            raise SFError(400, "INVALID_FIELD", f"No such column '{key}' on sobject of type {obj.name}", [key])
        if not (f.create if creating else f.update):
            raise SFError(
                400,
                "INVALID_FIELD_FOR_INSERT_UPDATE",
                f"Unable to create/update fields: {f.name}. Please check the security settings of this field and verify "
                "that it is read/write for your profile or permission set.",
                [f.name],
            )
        values[f.name] = _coerce(f, v)
    return values


def _check_references(conn, obj: SObject, values: dict) -> dict[str, Any]:
    """Every lookup points at an existing record of an allowed type. Returns the referenced rows by field name."""
    found = {}
    for name, v in values.items():
        f = obj.get(name)
        if f.type != "reference" or v is None:
            continue
        target = BY_PREFIX.get(v[:3])
        if not target or target.name not in f.ref:
            raise SFError(400, "FIELD_INTEGRITY_EXCEPTION", f"{f.label}: id value of incorrect type: {v}", [f.name])
        t = TABLES[target.name]
        row = conn.execute(select(t).where(t.c.Id == v)).mappings().first()
        if not row:
            raise SFError(400, "INVALID_CROSS_REFERENCE_KEY", f"invalid cross reference id: {v}", [f.name])
        found[name] = (target, row)
    return found


def _derive(obj: SObject, values: dict, refs: dict, explicit: set[str]) -> None:
    """Fields Salesforce computes: an opportunity's stage-driven fields, a task's IsClosed and AccountId."""
    if obj.name == "Opportunity" and "StageName" in values:
        prob, cat, closed, won = STAGE_RULES[values["StageName"]]
        values |= {"ForecastCategoryName": cat, "IsClosed": closed, "IsWon": won}
        if "Probability" not in explicit:
            values["Probability"] = prob
    if obj.name == "Task":
        if "Status" in values:
            values["IsClosed"] = values["Status"] == "Completed"
        if "WhatId" in refs:
            target, row = refs["WhatId"]
            values["AccountId"] = row["Id"] if target.name == "Account" else row.get("AccountId")
        elif "WhoId" in refs and "WhatId" not in explicit:
            values["AccountId"] = refs["WhoId"][1].get("AccountId")


def _writable(name: str) -> SObject:
    obj = _object(name)
    if not obj.writable:
        raise SFError(
            403, "INSUFFICIENT_ACCESS_OR_READONLY", f"insufficient access rights: the integration user cannot change {obj.name}"
        )
    return obj


@router.post(BASE + "/sobjects/{name}")
@_sf
async def create(name: str, request: Request):
    uid = _user(request)
    obj = _writable(name)
    body = await _body(request)
    values = _values(obj, body, creating=True)
    explicit = set(values)
    for f in obj.fields:
        if f.create and f.name not in values and f.default is not None:
            values[f.name] = f.default
    missing = [f.name for f in obj.fields if f.create and not f.nillable and values.get(f.name) is None]
    if missing:
        raise SFError(400, "REQUIRED_FIELD_MISSING", f"Required fields are missing: [{', '.join(missing)}]", missing)
    now = datetime.now(UTC)
    t = TABLES[obj.name]
    with engine.begin() as conn:
        refs = _check_references(conn, obj, values)
        _derive(obj, values, refs, explicit)
        rid = make_id(obj.prefix, conn.execute(select(RECORD_SEQ.next_value())).scalar_one())
        values = {f.name: None for f in obj.fields} | values
        values |= {"Id": rid, "IsDeleted": False, "CreatedDate": now, "CreatedById": uid}
        values |= {"LastModifiedDate": now, "LastModifiedById": uid, "SystemModstamp": now}
        values["OwnerId"] = values.get("OwnerId") or uid
        conn.execute(t.insert().values(**values))
        events.emit(conn, SOURCE, f"salesforce.{obj.name}.created", rid, record(obj, values), now)
    return JSONResponse({"id": rid, "success": True, "errors": []}, status_code=201)


@router.patch(BASE + "/sobjects/{name}/{rid}")
@_sf
async def patch(name: str, rid: str, request: Request):
    uid = _user(request)
    obj = _writable(name)
    nid = normalise_id(rid)
    if not nid or not nid.startswith(obj.prefix):
        raise SFError(404, "NOT_FOUND", f"Provided external ID field does not exist or is not accessible: {rid}")
    body = await _body(request)
    values = _values(obj, body, creating=False)
    explicit = set(values)
    now = datetime.now(UTC)
    t = TABLES[obj.name]
    with engine.begin() as conn:
        if not conn.execute(select(t.c.Id).where(t.c.Id == nid)).first():
            raise _not_found()
        refs = _check_references(conn, obj, values)
        _derive(obj, values, refs, explicit)
        values |= {"LastModifiedDate": now, "LastModifiedById": uid, "SystemModstamp": now}
        conn.execute(update(t).where(t.c.Id == nid).values(**values))
        row = conn.execute(select(t).where(t.c.Id == nid)).mappings().one()
        data = record(obj, row) | {"changedFields": sorted(explicit)}
        events.emit(conn, SOURCE, f"salesforce.{obj.name}.updated", nid, data, now)
    return Response(status_code=204)
