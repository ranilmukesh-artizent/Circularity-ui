"""AssetWise engineering data warehouse over OData v4, plus Bentley IMS tokens.

    POST  /assetwise/ims/connect/token                                    IMS token (client credentials)
    GET   /assetwise/eB/Service/OData/{warehouse}/                        service document
    GET   /assetwise/eB/Service/OData/{warehouse}/$metadata               CSDL
    GET   /assetwise/eB/Service/OData/{warehouse}/{EntitySet}             ?$filter=&$select=&$orderby=&$top=&$skip=&$count=true
                                                                          server-driven paging (100 per page, or
                                                                          Prefer: odata.maxpagesize=N) -> @odata.nextLink
    GET   /assetwise/eB/Service/OData/{warehouse}/{EntitySet}('{key}')    one entity
    GET   /assetwise/eB/Service/OData/{warehouse}/{EntitySet}/$count      the number, as text
    PATCH /assetwise/eB/Service/OData/{warehouse}/LifeAssessments('{key}')                    edit a draft
    POST  /assetwise/eB/Service/OData/{warehouse}/LifeAssessments('{key}')/AssetWise.Submit   draft -> submitted
    POST  /assetwise/eB/Service/OData/{warehouse}/LifeAssessments('{key}')/AssetWise.Approve  submitted -> approved
    POST  /assetwise/eB/Service/OData/{warehouse}/LifeAssessments('{key}')/AssetWise.Reject   submitted -> rejected

Warehouse: Engineering. Entity sets: LifeAssessments (key ASSESSMENT_ID), Standards (STANDARD_ID), EngineeringLimits
(LIMIT_ID). Every row has MODIFIED_ON (UTC); LifeAssessments also return VALIDITY, worked out at read time against the
simulated clock. Errors use the OData v4 JSON error format {"error": {"code", "message"}}.
"""

import base64
import binascii
import re
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select, update

from sim.core import clock, events
from sim.core.db import engine
from sim.vendors.aras.odata4 import QueryError, order, parse_filter, parse_select, path_value, window
from sim.vendors.assetwise import auth
from sim.vendors.assetwise.seed import ENTITY, KEYS, MIN_RUL_MONTHS, STANDARDS, add_months, z

router = APIRouter(prefix="/assetwise")
SOURCE = "eng"
WAREHOUSE = "Engineering"
PAGE = 100
TYPES = {"LifeAssessments": "LifeAssessment", "Standards": "Standard", "EngineeringLimits": "EngineeringLimit"}
PROPS = {
    "LifeAssessments": [
        ("ASSESSMENT_ID", "Edm.String"),
        ("ASSET_ID", "Edm.String"),
        ("ASSET_CLASS", "Edm.String"),
        ("MANUFACTURER", "Edm.String"),
        ("METHOD", "Edm.String"),
        ("LIFE_TEXT", "Edm.String"),
        ("RUL_MONTHS", "Edm.Int32"),
        ("RUL_LOW_MONTHS", "Edm.Int32"),
        ("RUL_HIGH_MONTHS", "Edm.Int32"),
        ("MIN_RUL_MONTHS", "Edm.Int32"),
        ("CONFIDENCE", "Edm.String"),
        ("STANDARD_REF", "Edm.String"),
        ("ASSESSMENT_STATUS", "Edm.String"),
        ("REQUAL_STATUS", "Edm.String"),
        ("APPROVAL_STATUS", "Edm.String"),
        ("SUBMITTED_BY", "Edm.String"),
        ("APPROVED_BY", "Edm.String"),
        ("APPROVED_AT", "Edm.DateTimeOffset"),
        ("VALID_FROM", "Edm.DateTimeOffset"),
        ("VALID_UNTIL", "Edm.DateTimeOffset"),
        ("VALIDITY", "Edm.String"),
        ("CONDITION_GRADE", "Edm.String"),
        ("AGE_YEARS", "Edm.Double"),
        ("QUANTITY", "Edm.Int32"),
        ("NEXT_INSPECTION_DATE", "Edm.Date"),
        ("ASSESSED_BY", "Edm.String"),
        ("ASSESSED_AT", "Edm.DateTimeOffset"),
        ("MODIFIED_ON", "Edm.DateTimeOffset"),
    ],
    "Standards": [
        ("STANDARD_ID", "Edm.String"),
        ("STANDARD_REF", "Edm.String"),
        ("TITLE", "Edm.String"),
        ("ASSET_CLASS", "Edm.String"),
        ("REQUAL_INTERVAL_MONTHS", "Edm.Int32"),
        ("MIN_RUL_MONTHS", "Edm.Int32"),
        ("STATUS", "Edm.String"),
        ("MODIFIED_ON", "Edm.DateTimeOffset"),
    ],
    "EngineeringLimits": [
        ("LIMIT_ID", "Edm.String"),
        ("ASSET_CLASS", "Edm.String"),
        ("PARAMETER", "Edm.String"),
        ("LIMIT_TYPE", "Edm.String"),
        ("LIMIT_VALUE", "Edm.Double"),
        ("UNIT", "Edm.String"),
        ("STANDARD_REF", "Edm.String"),
        ("APPLIES_TO_ROUTES", "Collection(Edm.String)"),
        ("MODIFIED_ON", "Edm.DateTimeOffset"),
    ],
}
EDITABLE = {"RUL_MONTHS", "RUL_LOW_MONTHS", "RUL_HIGH_MONTHS", "CONFIDENCE", "LIFE_TEXT", "NEXT_INSPECTION_DATE"}
CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}


def error(status: int, message: str, code: str = "") -> JSONResponse:
    headers = {"WWW-Authenticate": 'Bearer realm="AssetWise", Basic realm="AssetWise"'} if status == 401 else None
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status,
        headers=headers,
        media_type="application/json; odata.metadata=minimal",
    )


def root(request: Request, warehouse: str) -> str:
    return str(request.base_url).rstrip("/") + f"/assetwise/eB/Service/OData/{warehouse}/"


def validity(row: dict, now) -> str:
    if row.get("APPROVAL_STATUS") != "Approved" or not row.get("VALID_UNTIL"):
        return "NOT_APPROVED"
    now_z = z(now)
    if row.get("VALID_FROM") and now_z < row["VALID_FROM"]:
        return "NOT_YET_VALID"
    return "EXPIRED" if now_z >= row["VALID_UNTIL"] else "VALID"


def _rows(conn, entity_set: str, key: str | None = None) -> list[dict]:
    q = select(ENTITY.c.data).where(ENTITY.c.entity_set == entity_set)
    if key is not None:
        q = q.where(ENTITY.c.key == key)
    rows = [dict(r.data) for r in conn.execute(q.order_by(ENTITY.c.key))]
    if entity_set == "LifeAssessments":
        now = clock.now(conn)
        names = [n for n, _ in PROPS[entity_set]]
        rows = [{n: r.get(n) for n in names if n != "VALIDITY"} | {"VALIDITY": validity(r, now)} for r in rows]
    return rows


def _resolver(entity_set: str):
    names = {n for n, _ in PROPS[entity_set]}

    def get(row: dict, name: str) -> Any:
        if name not in names:
            raise QueryError(f"Could not find a property named '{name}' on type 'AssetWise.{TYPES[entity_set]}'.")
        return row.get(name)

    return get


def _check_warehouse(warehouse: str) -> JSONResponse | None:
    if warehouse != WAREHOUSE:
        return error(404, f"The data warehouse '{warehouse}' does not exist or is not published.")
    return None


# ------------------------------------------------------------------ IMS
@router.post("/ims/connect/token")
async def token(request: Request):
    form = await request.form()
    if form.get("grant_type") != "client_credentials":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    cid, secret = str(form.get("client_id") or ""), str(form.get("client_secret") or "")
    h = request.headers.get("authorization", "")
    if not cid and h.lower().startswith("basic "):  # client_secret_basic is accepted too
        try:
            cid, _, secret = base64.b64decode(h[6:], validate=True).decode().partition(":")
        except (binascii.Error, UnicodeDecodeError):
            return JSONResponse({"error": "invalid_client"}, status_code=400)
    body, err = auth.issue(cid, secret, str(form.get("scope") or ""))
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return JSONResponse(body, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


# ------------------------------------------------------------------ OData
@router.get("/eB/Service/OData/{warehouse}/")
@router.get("/eB/Service/OData/{warehouse}")
def service_document(warehouse: str, request: Request):
    if auth.user_of(request) is None:
        return error(401, "Authorization has been denied for this request.")
    if (e := _check_warehouse(warehouse)) is not None:
        return e
    return {
        "@odata.context": root(request, warehouse) + "$metadata",
        "value": [{"name": n, "kind": "EntitySet", "url": n} for n in PROPS],
    }


@router.get("/eB/Service/OData/{warehouse}/$metadata")
def metadata(warehouse: str, request: Request):
    if auth.user_of(request) is None:
        return error(401, "Authorization has been denied for this request.")
    if (e := _check_warehouse(warehouse)) is not None:
        return e
    not_null = ' Nullable="false"'
    types = "".join(
        f'<EntityType Name="{TYPES[s]}"><Key><PropertyRef Name="{KEYS[s]}"/></Key>'
        + "".join(f'<Property Name="{n}" Type="{t}"{not_null if n == KEYS[s] else ""}/>' for n, t in props)
        + "</EntityType>"
        for s, props in PROPS.items()
    )
    sets = "".join(f'<EntitySet Name="{s}" EntityType="AssetWise.{TYPES[s]}"/>' for s in PROPS)
    actions = "".join(
        f'<Action Name="{a}" IsBound="true"><Parameter Name="bindingParameter" Type="AssetWise.LifeAssessment"/>'
        '<Parameter Name="Comment" Type="Edm.String"/></Action>'
        for a in ("Submit", "Approve", "Reject")
    )
    xml = (
        '<?xml version="1.0" encoding="utf-8"?><edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">'
        '<edmx:DataServices><Schema Namespace="AssetWise" xmlns="http://docs.oasis-open.org/odata/ns/edm">'
        f'{types}{actions}<EntityContainer Name="{warehouse}">{sets}</EntityContainer></Schema></edmx:DataServices></edmx:Edmx>'
    )
    return Response(xml, media_type="application/xml")


_ENTITY = re.compile(r"^(\w+)(?:\('([^']*)'\))?(?:/(\$count|AssetWise\.\w+))?$")


@router.get("/eB/Service/OData/{warehouse}/{resource:path}")
def read(warehouse: str, resource: str, request: Request):
    if auth.user_of(request) is None:
        return error(401, "Authorization has been denied for this request.")
    if (e := _check_warehouse(warehouse)) is not None:
        return e
    m = _ENTITY.match(resource)
    if not m or m.group(1) not in PROPS or (m.group(3) and m.group(3) != "$count"):
        return error(404, f"No HTTP resource was found that matches the request URI '{request.url}'.")
    entity_set, key, count_only = m.group(1), m.group(2), m.group(3) == "$count"
    params = request.query_params
    base = root(request, warehouse)
    try:
        select_ = parse_select(params.get("$select"))
        get = _resolver(entity_set)
        for s in select_ or []:
            get({}, s)
        with engine.connect() as conn:
            rows = _rows(conn, entity_set, key)
        if key is not None:
            if not rows:
                return error(404, f"The {TYPES[entity_set]} with key '{key}' was not found.")
            row = rows[0]
            body = {
                "@odata.context": f"{base}$metadata#{entity_set}" + (f"({','.join(select_)})" if select_ else "") + "/$entity"
            }
            return body | ({k: row[k] for k in select_} if select_ else row)
        flt = parse_filter(params.get("$filter"))
        if flt:
            rows = [r for r in rows if flt(r, lambda row, p: path_value(row, p, get))]
        if count_only:
            return Response(str(len(rows)), media_type="text/plain")
        rows = order(rows, params.get("$orderby"), get)
        total = len(rows)
        prefer = request.headers.get("prefer")
        if not re.search(r"odata\.maxpagesize", prefer or ""):
            prefer = f"odata.maxpagesize={PAGE}"
        page, nxt, size = window(rows, params, prefer, f"{base}{entity_set}")
    except QueryError as e:
        return error(400, str(e))
    body: dict = {"@odata.context": f"{base}$metadata#{entity_set}" + (f"({','.join(select_)})" if select_ else "")}
    if (params.get("$count") or "").lower() == "true":
        body["@odata.count"] = total
    body["value"] = [{k: r[k] for k in select_} if select_ else r for r in page]
    if nxt:
        body["@odata.nextLink"] = nxt
    headers = {"Preference-Applied": f"odata.maxpagesize={size}"} if size and request.headers.get("prefer") else {}
    return JSONResponse(body, headers=headers, media_type="application/json; odata.metadata=minimal")


# ------------------------------------------------------------------ writes (the approval workflow)
def _write(conn, key: str, row: dict, action: str, user: str, now) -> None:
    row = {k: v for k, v in row.items() if k != "VALIDITY"} | {"MODIFIED_ON": z(now)}
    conn.execute(
        update(ENTITY).where(ENTITY.c.entity_set == "LifeAssessments", ENTITY.c.key == key).values(data=row, modified_on=now)
    )
    events.emit(
        conn,
        SOURCE,
        f"com.bentley.assetwise.LifeAssessment.{action}",
        key,
        {
            "ASSESSMENT_ID": key,
            "ASSET_ID": row["ASSET_ID"],
            "APPROVAL_STATUS": row["APPROVAL_STATUS"],
            "REQUAL_STATUS": row["REQUAL_STATUS"],
            "by": user,
        },
        now,
    )


def _load_assessment(conn, key: str) -> dict | None:
    r = conn.execute(select(ENTITY.c.data).where(ENTITY.c.entity_set == "LifeAssessments", ENTITY.c.key == key)).first()
    return dict(r.data) if r else None


@router.patch("/eB/Service/OData/{warehouse}/LifeAssessments('{key}')")
async def patch(warehouse: str, key: str, request: Request):
    user = auth.user_of(request)
    if user is None:
        return error(401, "Authorization has been denied for this request.")
    if (e := _check_warehouse(warehouse)) is not None:
        return e
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return error(400, "The request body must be a JSON object.")
    unknown = [k for k in body if k not in {n for n, _ in PROPS["LifeAssessments"]}]
    if unknown:
        return error(400, f"The property '{unknown[0]}' does not exist on type 'AssetWise.LifeAssessment'.")
    locked = [k for k in body if k not in EDITABLE]
    if locked:
        return error(400, f"The property '{locked[0]}' cannot be changed.")
    with engine.begin() as conn:
        row = _load_assessment(conn, key)
        if row is None:
            return error(404, f"The LifeAssessment with key '{key}' was not found.")
        if row["APPROVAL_STATUS"] not in ("Draft", "Rejected"):
            return error(409, f"The assessment {key} is {row['APPROVAL_STATUS'].lower()} and cannot be edited.")
        new = row | body
        if new.get("CONFIDENCE") is not None and new["CONFIDENCE"] not in CONFIDENCE:
            return error(400, "CONFIDENCE must be LOW, MEDIUM or HIGH.")
        for k in ("RUL_MONTHS", "RUL_LOW_MONTHS", "RUL_HIGH_MONTHS"):
            if new.get(k) is not None and (not isinstance(new[k], int) or new[k] < 0):
                return error(400, f"{k} must be a whole number of months.")
        lo, est, hi = new.get("RUL_LOW_MONTHS"), new.get("RUL_MONTHS"), new.get("RUL_HIGH_MONTHS")
        if est is not None and ((lo is not None and lo > est) or (hi is not None and hi < est)):
            return error(400, "The remaining life must lie between RUL_LOW_MONTHS and RUL_HIGH_MONTHS.")
        if "RUL_MONTHS" in body and "LIFE_TEXT" not in body and est is not None:
            new["LIFE_TEXT"] = f"{est} months"
        new |= {"APPROVAL_STATUS": "Draft", "ASSESSMENT_STATUS": "SCHEDULED", "REQUAL_STATUS": "PENDING"}
        _write(conn, key, new, "Updated", user, clock.now(conn))
    return Response(status_code=204)


@router.post("/eB/Service/OData/{warehouse}/LifeAssessments('{key}')/AssetWise.{action}")
async def workflow(warehouse: str, key: str, action: str, request: Request):
    user = auth.user_of(request)
    if user is None:
        return error(401, "Authorization has been denied for this request.")
    if (e := _check_warehouse(warehouse)) is not None:
        return e
    if action not in ("Submit", "Approve", "Reject"):
        return error(404, f"No HTTP resource was found that matches the request URI '{request.url}'.")
    try:
        params = await request.json() if await request.body() else {}
    except ValueError:
        params = None
    if not isinstance(params, dict):
        return error(400, "The action parameters must be a JSON object.")
    with engine.begin() as conn:
        row = _load_assessment(conn, key)
        if row is None:
            return error(404, f"The LifeAssessment with key '{key}' was not found.")
        now = clock.now(conn)
        state = row["APPROVAL_STATUS"]
        if action == "Submit":
            if state != "Draft":
                return error(409, f"Only a draft assessment can be submitted; {key} is {state.lower()}.")
            if row.get("RUL_MONTHS") is None:
                return error(400, "An assessment without a remaining useful life (RUL_MONTHS) cannot be submitted.")
            row |= {"APPROVAL_STATUS": "Submitted", "SUBMITTED_BY": user, "ASSESSMENT_STATUS": "SUBMITTED"}
            _write(conn, key, row, "Submitted", user, now)
            return Response(status_code=204)
        if state != "Submitted":
            return error(409, f"Only a submitted assessment can be {action.lower()}d; {key} is {state.lower()}.")
        if row.get("SUBMITTED_BY") == user:
            return error(403, "The approver of an assessment must not be the person who submitted it.")
        if action == "Reject":
            row |= {
                "APPROVAL_STATUS": "Rejected",
                "ASSESSMENT_STATUS": "REJECTED",
                "REQUAL_STATUS": "REJECTED",
                "APPROVED_BY": None,
                "APPROVED_AT": None,
                "VALID_FROM": None,
                "VALID_UNTIL": None,
            }
            _write(conn, key, row, "Rejected", user, now)
            return Response(status_code=204)
        if row["RUL_MONTHS"] < MIN_RUL_MONTHS:
            return error(
                400,
                f"The remaining useful life ({row['RUL_MONTHS']} months) is below the minimum of "
                f"{MIN_RUL_MONTHS} months; reject the assessment instead.",
            )
        months = STANDARDS[row["ASSET_CLASS"]][3]
        row |= {
            "APPROVAL_STATUS": "Approved",
            "ASSESSMENT_STATUS": "APPROVED",
            "REQUAL_STATUS": "APPROVED",
            "APPROVED_BY": user,
            "APPROVED_AT": z(now),
            "VALID_FROM": z(now),
            "VALID_UNTIL": z(add_months(now, months)),
        }
        _write(conn, key, row, "Approved", user, now)
    return Response(status_code=204)
