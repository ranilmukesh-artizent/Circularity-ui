"""IBM Maximo Manage 8.11 mock: the REST/OSLC JSON API (docs/backend-steps.md, B5).

    GET   /maximo/api/whoami                                        the authenticated user
    GET   /maximo/api/os/{mxasset|mxwo|mxfailurereport}             query an object structure
          ?oslc.where=status="APPR" and siteid="RC01"   &oslc.select=wonum,status,assetmeter{*}   &oslc.orderBy=-reportdate,+wonum
          &oslc.pageSize=20&pageno=2   &lean=1   &collectioncount=1
    GET   /maximo/api/os/{os}/{restid}                              one record (restid = the href token, or the numeric
                                                                    workorderid / assetuid / failurereportid)
    POST  /maximo/api/os/mxwo                                       create a work order: 201 + Location
                                                                    (header `properties: *` or a list returns the record)
    POST  /maximo/api/os/{mxwo|mxasset}/{restid}                    update with `x-method-override: PATCH`
    PATCH /maximo/api/os/{mxwo|mxasset}/{restid}                    (also accepted), optional `patchtype: MERGE`
    POST  /maximo/api/os/{mxwo|mxasset}/{restid}?action=wsmethod:changeStatus   {"status":"APPR","memo":"..."}

Without lean=1 the response uses OSLC prefixes (spi: attributes, rdf:about, rdfs:member, oslc:responseInfo).
A collection read without oslc.select returns only each member's href, as Maximo does. Null attributes are omitted.
Times are returned in the server's zone (+05:30). Writes record events in the shared outbox (source "eam").
"""

import base64
import binascii
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import Table, func, insert, select, tuple_, update
from sqlalchemy.engine import Connection

from sim import events
from sim.db import engine
from sim.vendors.maximo import tables as t
from sim.vendors.maximo.auth import user_of
from sim.vendors.maximo.seed import IST, ORG, rest_id
from sim.vendors.maximo.where import WhereError, coerce, parse_where

router = APIRouter(prefix="/maximo/api")
SOURCE = "eam"

WO_STATUS = {
    "WAPPR": "Waiting on Approval",
    "APPR": "Approved",
    "WSCH": "Waiting to be Scheduled",
    "WMATL": "Waiting on Material",
    "INPRG": "In Progress",
    "COMP": "Completed",
    "CLOSE": "Closed",
    "CAN": "Canceled",
}
ASSET_STATUS = {
    "OPERATING": "Operating",
    "NOT READY": "Not Ready",
    "LIMITEDUSE": "Limited Use",
    "BROKEN": "Broken",
    "DECOMMISSIONED": "Decommissioned",
    "ACTIVE": "Active",
}
WORKTYPES = {"CM", "PM", "EM", "INSP", "REFURB", "TDOWN", "CAL"}
SITES = {"WH01", "WH02", "RC01"} | {f"ST{i:02d}" for i in range(1, 9)}


@dataclass(frozen=True)
class ObjectStructure:
    name: str
    table: Table
    key: tuple[str, ...]  # the attributes behind the rest id
    pk: str
    children: dict[str, tuple[Table, tuple[str, ...]]] = field(default_factory=dict)
    statuses: dict[str, str] | None = None
    readonly: frozenset[str] = frozenset()


OS = {
    "mxasset": ObjectStructure(
        "mxasset",
        t.ASSET,
        ("assetnum", "siteid"),
        "assetuid",
        {"assetmeter": (t.ASSETMETER, ("assetnum", "siteid")), "assetspec": (t.ASSETSPEC, ("assetnum", "siteid"))},
        ASSET_STATUS,
        frozenset({"assetuid", "assetnum", "siteid", "orgid", "totalcost", "changedate", "changeby", "statusdate"}),
    ),
    "mxwo": ObjectStructure(
        "mxwo",
        t.WORKORDER,
        ("wonum", "siteid"),
        "workorderid",
        {"wostatus": (t.WOSTATUS, ("wonum", "siteid")), "failurereport": (t.FAILUREREPORT, ("wonum", "siteid"))},
        WO_STATUS,
        frozenset({"workorderid", "wonum", "siteid", "orgid", "woclass", "changedate", "changeby", "statusdate"}),
    ),
    "mxfailurereport": ObjectStructure("mxfailurereport", t.FAILUREREPORT, ("failurereportid",), "failurereportid"),
}
HIDDEN_CHILD_COLS = {"assetmeterid", "assetspecid", "wostatusid"}


# ------------------------------------------------------------------ errors
def maxerr(request: Request, status: int, code: str, message: str, attr: str = "") -> JSONResponse:
    return JSONResponse(
        {
            "Error": {
                "errorattrname": attr,
                "extendedError": {"moreInfo": {"href": str(request.base_url) + f"maximo/api/error/messages/{code}"}},
                "reasonCode": code,
                "message": f"{code} - {message}",
                "statusCode": str(status),
                "errorobjpath": "",
            }
        },
        status_code=status,
    )


def _unauthorized(request: Request) -> JSONResponse:
    return maxerr(request, 401, "BMXAA7901E", "You cannot log in at this time. Contact the system administrator.")


def _no_os(request: Request, name: str) -> JSONResponse:
    return maxerr(request, 404, "BMXAA9301E", f"The object structure {name.upper()} was not found.")


# ------------------------------------------------------------------ serialisation
def _value(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.astimezone(IST).isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _href(request: Request, os_: ObjectStructure, row) -> str:
    return f"{request.base_url}maximo/api/os/{os_.name}/{rest_id(*(str(row._mapping[k]) for k in os_.key))}"


def _parse_select(text: str | None) -> dict[str, Any] | None:
    """`a,b,child{x,y},child2{*}` -> {"a": None, "b": None, "child": {"x": None, ...}}; `*` -> {"*": None}."""
    if text is None:
        return None
    out: dict[str, Any] = {}
    depth, start, parts = 0, 0, []
    for i, ch in enumerate(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    for p in (p.strip() for p in parts):
        if not p:
            continue
        m = re.fullmatch(r"([\w:.*]+)\{(.*)\}", p)
        if m:
            out[m.group(1).split(":")[-1].lower()] = _parse_select(m.group(2)) or {"*": None}
        else:
            out[p.split(":")[-1].lower()] = None
    return out


def _record(attrs: dict, sel: dict[str, Any] | None, statuses: dict[str, str] | None, lean: bool) -> dict:
    """Attributes picked by an oslc.select (None = all), nulls omitted, OSLC-prefixed when not lean."""
    out = {}
    for k, v in attrs.items():
        if v is None or (sel is not None and "*" not in sel and k not in sel):
            continue
        out[k] = _value(v)
        if k == "status" and statuses and v in statuses:
            out["status_description"] = statuses[v]
    return out if lean else {f"spi:{k}": v for k, v in out.items()}


def _members(conn: Connection, request: Request, os_: ObjectStructure, rows, sel: dict | None, lean: bool) -> list[dict]:
    href_key = "href" if lean else "rdf:about"
    if sel is None:
        return [{href_key: _href(request, os_, r)} for r in rows]
    wanted = {c: sub for c, sub in sel.items() if c in os_.children}
    if "*" in sel:
        wanted = {c: {"*": None} for c in os_.children} | wanted
    kids: dict[str, dict[tuple, list[dict]]] = {}
    for child, sub in wanted.items():
        table, cols = os_.children[child]
        keys = {tuple(r._mapping[c] for c in cols) for r in rows}
        grouped: dict[tuple, list[dict]] = {}
        if keys:
            stmt = select(table).where(tuple_(*(table.c[c] for c in cols)).in_(list(keys))).order_by(*table.primary_key)
            for cr in conn.execute(stmt):
                m = {k: v for k, v in cr._mapping.items() if k not in HIDDEN_CHILD_COLS}
                stat = WO_STATUS if child == "wostatus" else None
                grouped.setdefault(tuple(cr._mapping[c] for c in cols), []).append(_record(m, sub, stat, lean))
        kids[child] = grouped
    out = []
    for r in rows:
        rec = {href_key: _href(request, os_, r)} | _record(dict(r._mapping), sel, os_.statuses, lean)
        for child, grouped in kids.items():
            items = grouped.get(tuple(r._mapping[c] for c in os_.children[child][1]), [])
            if items:
                rec[child if lean else f"spi:{child}"] = items
        out.append(rec)
    return out


def _lean(request: Request) -> bool:
    return request.query_params.get("lean", "0") in ("1", "true")


def _column(os_: ObjectStructure, name: str):
    if name not in os_.table.c:
        raise WhereError(f"The attribute {name.upper()} does not exist in object structure {os_.name.upper()}.")
    return os_.table.c[name]


# ------------------------------------------------------------------ whoami
@router.get("/whoami")
def whoami(request: Request):
    user = user_of(request)
    if not user:
        return _unauthorized(request)
    return {
        "userName": user,
        "personid": user,
        "displayName": "Maximo integration user",
        "defaultSite": "WH01",
        "defaultOrg": ORG,
        "langcode": "EN",
        "timezone": "Asia/Kolkata",
        "baseCurrency": "USD",
        "maxVersion": "Manage 8.11",
    }


# ------------------------------------------------------------------ query
@router.get("/os/{os_name}")
def query(os_name: str, request: Request):
    if not user_of(request):
        return _unauthorized(request)
    os_ = OS.get(os_name.lower())
    if os_ is None:
        return _no_os(request, os_name)
    q, lean, table = request.query_params, _lean(request), os_.table
    stmt = select(table)
    try:
        if where := q.get("oslc.where"):
            stmt = stmt.where(parse_where(where, lambda n: _column(os_, n)))
        order = []
        for part in filter(None, (p for p in (q.get("oslc.orderBy") or "").split(","))):
            desc = part.startswith("-")
            name = part.lstrip("+- ").split(":")[-1].lower()
            col = _column(os_, name)
            order.append(col.desc() if desc else col.asc())
        size = int(q["oslc.pageSize"]) if q.get("oslc.pageSize") else None
        page = int(q.get("pageno") or 1)
        if (size is not None and size < 1) or page < 1:
            raise ValueError
    except WhereError as e:
        return maxerr(request, 400, "BMXAA9302E", str(e))
    except ValueError:
        return maxerr(request, 400, "BMXAA9303E", "oslc.pageSize and pageno must be positive integers.")
    stmt = stmt.order_by(*order, table.c[os_.pk])
    sel = _parse_select(q.get("oslc.select"))
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
        rows = conn.execute(stmt.offset((page - 1) * size).limit(size) if size else stmt).all()
        members = _members(conn, request, os_, rows, sel, lean)
    info: dict[str, Any] = {"href": str(request.url)}
    pages = max(1, -(-total // size)) if size else 1
    if size:
        info["pagenum"] = page
        if page < pages:
            info["nextPage"] = {"href": str(request.url.include_query_params(pageno=page + 1))}
        if page > 1:
            info["previousPage"] = {"href": str(request.url.include_query_params(pageno=page - 1))}
    if q.get("collectioncount") in ("1", "true"):
        info["totalCount"] = total
        info["totalPages"] = pages
    collection = f"{request.base_url}maximo/api/os/{os_.name}"
    if lean:
        return {"member": members, "href": collection, "responseInfo": info}
    oslc_info = {"rdf:about": info.pop("href")} | {
        f"oslc:{k}": ({"rdf:resource": v["href"]} if isinstance(v, dict) else v) for k, v in info.items()
    }
    return {"rdfs:member": members, "rdf:about": collection, "oslc:responseInfo": oslc_info}


# ------------------------------------------------------------------ one record
def _find(conn: Connection, os_: ObjectStructure, rid: str):
    table = os_.table
    if rid.isdigit():
        return conn.execute(select(table).where(table.c[os_.pk] == int(rid))).first()
    if not rid.startswith("_"):
        return None
    try:
        parts = base64.b64decode(rid[1:].replace("-", "="), validate=True).decode().split("/")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if len(parts) != len(os_.key):
        return None
    try:
        cond = [table.c[k] == coerce(table.c[k], v) for k, v in zip(os_.key, parts, strict=True)]
    except WhereError:
        return None
    return conn.execute(select(table).where(*cond)).first()


def _not_found(request: Request, os_: ObjectStructure, rid: str) -> JSONResponse:
    return maxerr(request, 404, "BMXAA8727E", f"The OSLC resource {os_.name.upper()} with the ID {rid} was not found.")


@router.get("/os/{os_name}/{rid}")
def get_one(os_name: str, rid: str, request: Request):
    if not user_of(request):
        return _unauthorized(request)
    os_ = OS.get(os_name.lower())
    if os_ is None:
        return _no_os(request, os_name)
    sel = _parse_select(request.query_params.get("oslc.select")) or {"*": None}
    with engine.connect() as conn:
        row = _find(conn, os_, rid)
        if row is None:
            return _not_found(request, os_, rid)
        return _members(conn, request, os_, [row], sel, _lean(request))[0]


# ------------------------------------------------------------------ writes
async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise WhereError("The request body must be a JSON object.")
    return {k.split(":")[-1].lower(): v for k, v in body.items() if not isinstance(v, list | dict)}


def _properties(request: Request) -> dict | None:
    p = request.headers.get("properties")
    return _parse_select(p) if p else None


def _reply(conn, request: Request, os_: ObjectStructure, row, status: int, location: bool = False) -> Response:
    headers = {"Location": _href(request, os_, row)} if location else {}
    props = _properties(request)
    if props is None:
        return Response(status_code=204 if status == 200 else status, headers=headers)
    body = _members(conn, request, os_, [row], props, _lean(request))[0]
    return JSONResponse(body, status_code=status, headers=headers)


def _event_data(os_: ObjectStructure, row, changed: dict | None = None) -> dict:  # noqa: ARG001 - same signature as the other event builders
    data = {k: _value(v) for k, v in row._mapping.items() if v is not None}
    if changed is not None:
        data["changed"] = sorted(changed)
    return data


def _assign(os_: ObjectStructure, current, data: dict) -> dict:
    """Validated column values from a JSON body; unknown attributes are ignored, as Maximo does."""
    values = {}
    for k, v in data.items():
        if k not in os_.table.c or k.endswith("_description"):
            continue
        if k in os_.readonly:
            if current is not None and str(current._mapping[k]) != str(v):
                raise WhereError(f"The {k.upper()} attribute is read-only and cannot be changed.")
            continue
        values[k] = coerce(os_.table.c[k], v)
    if "status" in values and os_.statuses is not None:
        values["status"] = str(values["status"]).upper()
        if values["status"] not in os_.statuses:
            raise WhereError(f"{values['status']} is not a valid status.")
    if "worktype" in values and values["worktype"] is not None:
        values["worktype"] = str(values["worktype"]).upper()
        if values["worktype"] not in WORKTYPES:
            raise WhereError(f"The value {values['worktype']} for the Work Type field is invalid.")
    return values


@router.post("/os/{os_name}")
async def create(os_name: str, request: Request):
    if not (user := user_of(request)):
        return _unauthorized(request)
    os_ = OS.get(os_name.lower())
    if os_ is None:
        return _no_os(request, os_name)
    if os_.name != "mxwo":
        return maxerr(request, 400, "BMXAA9549E", f"The object structure {os_.name.upper()} does not allow inserts.")
    try:
        data = await _body(request)
        values = _assign(os_, None, data)
    except WhereError as e:
        return maxerr(request, 400, "BMXAA4195E", str(e))
    wo, a = t.WORKORDER, t.ASSET
    now = datetime.now(UTC)
    with engine.begin() as conn:
        site = (data.get("siteid") or "").upper() or None
        if values.get("assetnum"):
            stmt = select(a).where(a.c.assetnum == values["assetnum"])
            asset = conn.execute(stmt.where(a.c.siteid == site) if site else stmt.order_by(a.c.assetuid)).first()
            if asset is None:
                asset = conn.execute(stmt).first() if site else None
            if asset is None:
                return maxerr(
                    request, 400, "BMXAA4049E", f"The value {values['assetnum']} for the Asset field is invalid.", "assetnum"
                )
            site = site or asset.siteid
            if site == asset.siteid:
                values.setdefault("location", asset.location)
        if not site:
            return maxerr(request, 400, "BMXAA4195E", "A value is required for the Site field on the WORKORDER object.", "siteid")
        if site not in SITES:
            return maxerr(request, 400, "BMXAA4049E", f"The value {site} for the Site field is invalid.", "siteid")
        wonum = str(data.get("wonum") or "").upper()
        if wonum and conn.execute(select(wo.c.workorderid).where(wo.c.wonum == wonum, wo.c.siteid == site)).first():
            return maxerr(request, 400, "BMXAA4129E", f"Record already exists for Site={site}, Work Order={wonum}.")
        conn.execute(select(func.pg_advisory_xact_lock(48_201)))  # serialise numbering
        woid = conn.execute(select(func.coalesce(func.max(wo.c.workorderid), 10000))).scalar_one() + 1
        if not wonum:
            top = conn.execute(select(func.max(wo.c.wonum)).where(wo.c.wonum.regexp_match(r"^2\d{6}$"))).scalar_one()
            wonum = str(int(top) + 1 if top else 2_000_001)
        values.setdefault("status", "WAPPR")
        values.setdefault("reportdate", now)
        row = {
            "workorderid": woid,
            "wonum": wonum,
            "siteid": site,
            "orgid": ORG,
            "woclass": "WORKORDER",
            "reportedby": user,
            "statusdate": now,
            "changedate": now,
            "changeby": user,
        } | values
        if row["status"] == "INPRG" and not row.get("actstart"):
            row["actstart"] = now
        conn.execute(insert(wo).values(**row))
        conn.execute(
            insert(t.WOSTATUS).values(
                wonum=wonum, siteid=site, status=row["status"], changedate=now, changeby=user, memo=data.get("memo")
            )
        )
        created = conn.execute(select(wo).where(wo.c.workorderid == woid)).one()
        events.emit(conn, SOURCE, "maximo.workorder.created", wonum, _event_data(os_, created), now)
        return _reply(conn, request, os_, created, 201, location=True)


async def _update(os_name: str, rid: str, request: Request, status_only: bool = False):
    if not (user := user_of(request)):
        return _unauthorized(request)
    os_ = OS.get(os_name.lower())
    if os_ is None:
        return _no_os(request, os_name)
    if os_.name == "mxfailurereport":
        return maxerr(request, 400, "BMXAA9549E", "The object structure MXFAILUREREPORT does not allow updates.")
    try:
        data = await _body(request)
    except WhereError as e:
        return maxerr(request, 400, "BMXAA4195E", str(e))
    if status_only:
        data = {k: v for k, v in data.items() if k in ("status", "memo")}
        if "status" not in data:
            return maxerr(request, 400, "BMXAA4195E", "A value is required for the Status field.", "status")
    table, now = os_.table, datetime.now(UTC)
    with engine.begin() as conn:
        cur = _find(conn, os_, rid)
        if cur is None:
            return _not_found(request, os_, rid)
        if os_.name == "mxwo" and cur.status in ("CLOSE", "CAN"):
            word = "closed" if cur.status == "CLOSE" else "canceled"
            return maxerr(request, 400, "BMXAA4552E", f"Work order {cur.wonum} is {word} and cannot be modified.")
        try:
            values = _assign(os_, cur, data)
        except WhereError as e:
            return maxerr(request, 400, "BMXAA4195E", str(e))
        new_status = values.get("status")
        if new_status is not None and new_status != cur.status:
            if os_.name == "mxwo" and cur.status == "COMP" and new_status not in ("CLOSE",):
                return maxerr(request, 400, "BMXAA4590E", f"Work order {cur.wonum} is complete; it can only be closed.")
            values["statusdate"] = now
            if os_.name == "mxwo":
                if new_status == "INPRG" and not cur.actstart and "actstart" not in values:
                    values["actstart"] = now
                if new_status in ("COMP", "CLOSE") and not cur.actfinish and "actfinish" not in values:
                    values["actfinish"] = now
                conn.execute(
                    insert(t.WOSTATUS).values(
                        wonum=cur.wonum,
                        siteid=cur.siteid,
                        status=new_status,
                        changedate=now,
                        changeby=user,
                        memo=data.get("memo"),
                    )
                )
        elif new_status is not None:
            values.pop("status")
        changed = {k for k, v in values.items() if k != "statusdate" and cur._mapping[k] != v}
        values |= {"changedate": now, "changeby": user}
        pk = table.c[os_.pk]
        conn.execute(update(table).where(pk == cur._mapping[os_.pk]).values(**values))
        row = conn.execute(select(table).where(pk == cur._mapping[os_.pk])).one()
        if os_.name == "mxwo":
            events.emit(conn, SOURCE, "maximo.workorder.updated", row.wonum, _event_data(os_, row, changed), now)
        else:
            events.emit(conn, SOURCE, "maximo.asset.updated", row.assetnum, _event_data(os_, row, changed), now)
        return _reply(conn, request, os_, row, 200)


@router.post("/os/{os_name}/{rid}")
async def post_to_resource(os_name: str, rid: str, request: Request):
    action = request.query_params.get("action", "")
    if action.lower() == "wsmethod:changestatus":
        return await _update(os_name, rid, request, status_only=True)
    if request.headers.get("x-method-override", "").upper() == "PATCH":
        return await _update(os_name, rid, request)
    if not user_of(request):
        return _unauthorized(request)
    return maxerr(request, 400, "BMXAA9551E", "A POST to a resource needs x-method-override: PATCH or an action.")


@router.patch("/os/{os_name}/{rid}")
async def patch(os_name: str, rid: str, request: Request):
    return await _update(os_name, rid, request)
