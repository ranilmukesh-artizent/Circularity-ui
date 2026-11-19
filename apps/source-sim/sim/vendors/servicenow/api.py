"""ServiceNow Table API (Xanadu), as a REST client meets it on https://<instance>.service-now.com/api/now.

    POST   /servicenow/oauth_token.do                          OAuth 2.0 token (see auth.py)
    GET    /servicenow/api/now/table/{table}                   → {"result":[...]}, X-Total-Count, Link (first/prev/next/last)
           sysparm_query, sysparm_fields, sysparm_limit (default 10000), sysparm_offset,
           sysparm_display_value=false|true|all, sysparm_exclude_reference_link, sysparm_no_count,
           sysparm_suppress_pagination_header
    GET    /servicenow/api/now/table/{table}/{sys_id}          → {"result":{...}}
    POST   /servicenow/api/now/table/{table}                   → 201 {"result":{...}}, Location
    PUT    /servicenow/api/now/table/{table}/{sys_id}          → 200 {"result":{...}}
    PATCH  /servicenow/api/now/table/{table}/{sys_id}
    DELETE /servicenow/api/now/table/{table}/{sys_id}          → 204
Writes are allowed on wm_order, wm_task and sm_part_requirement (the integration role's ACLs); other tables
answer 403. Every write records an outbox event: servicenow.<table>.created|updated|deleted.
FSM business rules that a client sees: a new order or task gets its number and state Draft; assigning a task that
is Pending Dispatch makes it Assigned; closing a task stamps closed_at and actual_work_end; when the last task of an
order closes, the order closes too (Closed Complete, or Closed Incomplete if any task did not complete).
"""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Connection

from sim import events
from sim.db import engine
from sim.vendors.servicenow import auth
from sim.vendors.servicenow.query import QueryError, parse_query
from sim.vendors.servicenow.schema import CLOSED_STATES, SPECS, TABLES, Field
from sim.vendors.servicenow.values import SYS_ID, BadValue, to_db, to_display, to_value

router = APIRouter(prefix="/servicenow")
API = "/api/now"
SOURCE = "fsm"
DEFAULT_LIMIT = 10000
TABLE_DEFAULTS: dict[str, dict[str, Any]] = {
    "wm_order": {"state": 1, "priority": 4},
    "wm_task": {"state": 1, "priority": 4, "u_labour_rate": Decimal("1100.00")},
    "sm_part_requirement": {"state": "requested", "consumed_quantity": 0},
}
# Besides the display value, a reference given on a write may name the record by these fields
ALTERNATE_KEYS = {"sys_user": ("user_name",), "alm_asset": ("asset_tag",), "wm_order": (), "cmn_location": ("u_site_code",)}


def _error(status: int, message: str, detail: str | None = None) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "detail": detail}, "status": "failure"}, status_code=status)


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _instance(request: Request) -> str:
    return str(request.base_url).rstrip("/") + router.prefix + API


# ------------------------------------------------------------------ OAuth
@router.post("/oauth_token.do")
async def oauth_token(request: Request):
    form = {k: str(v) for k, v in (await request.form()).items()}
    body = auth.token(form, request.headers.get("authorization", ""))
    return body if body else auth.token_refused()


# ------------------------------------------------------------------ rendering
class _Renderer:
    """Turns stored rows into ServiceNow JSON, resolving references for display values and dot-walked fields."""

    def __init__(self, conn: Connection, request: Request, display: str, exclude_link: bool):
        self.conn, self.base = conn, _instance(request)
        self.display, self.exclude_link = display, exclude_link
        self.cache: dict[str, dict[str, Any]] = {}

    def prefetch(self, table: str, ids: set[str]) -> None:
        have = self.cache.setdefault(table, {})
        missing = [i for i in ids if i and i not in have]
        for i in range(0, len(missing), 1000):
            t = TABLES[table]
            for r in self.conn.execute(select(t).where(t.c.sys_id.in_(missing[i : i + 1000]))).mappings():
                have[r["sys_id"]] = dict(r)
        for i in missing:
            have.setdefault(i, None)

    def row(self, table: str, sid: str | None) -> dict | None:
        if not sid:
            return None
        if sid not in self.cache.get(table, {}):
            self.prefetch(table, {sid})
        return self.cache[table][sid]

    def display_of(self, f: Field, v: Any) -> str:
        if f.type == "reference":
            target = self.row(f.ref, v)
            return "" if target is None else to_value(SPECS[f.ref].by_name[SPECS[f.ref].display], target[SPECS[f.ref].display])
        return to_display(f, v)

    def field(self, f: Field, v: Any) -> Any:
        value = to_value(f, v)
        if f.type == "reference" and v:
            link = f"{self.base}/table/{f.ref}/{v}"
            if self.display == "all":
                out = {"display_value": self.display_of(f, v), "link": link, "value": value}
                return {k: x for k, x in out.items() if k != "link" or not self.exclude_link}
            if self.display == "true":
                d = self.display_of(f, v)
                return d if self.exclude_link else {"display_value": d, "link": link}
            return value if self.exclude_link else {"link": link, "value": value}
        if self.display == "all":
            return {"display_value": self.display_of(f, v), "value": value}
        if self.display == "true":
            return self.display_of(f, v)
        return value

    def walk(self, table: str, row: dict, path: str) -> tuple[Field, Any] | None:
        head, _, rest = path.partition(".")
        f = SPECS[table].by_name.get(head)
        if f is None:
            return None
        if not rest:
            return f, row.get(head)
        if f.type != "reference":
            return None
        target = self.row(f.ref, row.get(head))
        if target is None:
            leaf = self._leaf(f.ref, rest)
            return (leaf, None) if leaf else None
        return self.walk(f.ref, target, rest)

    def _leaf(self, table: str, path: str) -> Field | None:
        head, _, rest = path.partition(".")
        f = SPECS[table].by_name.get(head)
        if f is None or not rest:
            return f
        return self._leaf(f.ref, rest) if f.type == "reference" else None

    def render(self, table: str, rows: list[dict], fields: list[str] | None) -> list[dict]:
        spec = SPECS[table]
        names = fields or list(spec.by_name)
        if self.display != "false":
            for name in names:
                f = spec.by_name.get(name.split(".")[0])
                if f is not None and f.type == "reference":
                    self.prefetch(f.ref, {r[f.name] for r in rows if r[f.name]})
        out = []
        for r in rows:
            rec = {}
            for name in names:
                hit = self.walk(table, r, name)
                if hit is not None:
                    rec[name] = self.field(*hit)
            out.append(rec)
        return out


def _params(request: Request) -> tuple[str, bool, list[str] | None]:
    q = request.query_params
    display = (q.get("sysparm_display_value") or "false").lower()
    display = display if display in ("true", "false", "all") else "false"
    exclude = (q.get("sysparm_exclude_reference_link") or "").lower() == "true"
    fields = [x.strip() for x in (q.get("sysparm_fields") or "").split(",") if x.strip()] or None
    return display, exclude, fields


def _guard(request: Request, table: str) -> tuple[str | None, JSONResponse | None]:
    user = auth.authenticate(request)
    if user is None:
        return None, auth.unauthorized()
    if table not in SPECS:
        return None, _error(400, f"Invalid table {table}")
    return user, None


# ------------------------------------------------------------------ reads
@router.get(API + "/table/{table}")
def list_records(table: str, request: Request):
    _, denied = _guard(request, table)
    if denied:
        return denied
    q = request.query_params
    try:
        limit = int(q.get("sysparm_limit") or DEFAULT_LIMIT)
        offset = int(q.get("sysparm_offset") or 0)
        if limit < 1 or offset < 0:
            raise ValueError
    except ValueError:
        return _error(400, "Invalid sysparm_limit or sysparm_offset", "Both must be non-negative integers")
    try:
        parsed = parse_query(table, q.get("sysparm_query"))
    except (QueryError, BadValue) as e:
        return _error(400, "Invalid query", str(e))
    display, exclude, fields = _params(request)
    t = TABLES[table]
    no_count = (q.get("sysparm_no_count") or "").lower() == "true"
    with engine.connect() as conn:
        total = None if no_count else conn.execute(select(func.count()).select_from(t).where(parsed.where)).scalar_one()
        stmt = select(t).where(parsed.where).order_by(*parsed.order_by, t.c.sys_id).offset(offset).limit(limit)
        rows = [dict(r) for r in conn.execute(stmt).mappings()]
        result = _Renderer(conn, request, display, exclude).render(table, rows, fields)
    headers = {}
    if total is not None:
        headers["X-Total-Count"] = str(total)
        if (q.get("sysparm_suppress_pagination_header") or "").lower() != "true":
            headers["Link"] = _links(request, table, limit, offset, total)
    return JSONResponse({"result": result}, headers=headers)


def _links(request: Request, table: str, limit: int, offset: int, total: int) -> str:
    base = f"{_instance(request)}/table/{table}"
    params = {k: v for k, v in request.query_params.items() if k not in ("sysparm_offset", "sysparm_limit")}

    def url(off: int) -> str:
        return f"{base}?{urlencode(params | {'sysparm_limit': limit, 'sysparm_offset': off})}"

    last = max(0, (total - 1) // limit * limit)
    links = [f'<{url(0)}>;rel="first"']
    if offset > 0:
        links.append(f'<{url(max(0, offset - limit))}>;rel="prev"')
    if offset + limit < total:
        links.append(f'<{url(offset + limit)}>;rel="next"')
    links.append(f'<{url(last)}>;rel="last"')
    return ",".join(links)


def _not_found() -> JSONResponse:
    return _error(404, "No Record found", "Record doesn't exist or ACL restricts the record retrieval")


@router.get(API + "/table/{table}/{sys_id}")
def get_record(table: str, sys_id: str, request: Request):
    _, denied = _guard(request, table)
    if denied:
        return denied
    display, exclude, fields = _params(request)
    t = TABLES[table]
    with engine.connect() as conn:
        r = conn.execute(select(t).where(t.c.sys_id == sys_id)).mappings().first()
        if r is None:
            return _not_found()
        return {"result": _Renderer(conn, request, display, exclude).render(table, [dict(r)], fields)[0]}


# ------------------------------------------------------------------ writes
def _resolve_ref(conn: Connection, f: Field, raw: Any) -> str | None:
    """A reference given as a sys_id or as the referenced record's display value."""
    v = raw.get("value") if isinstance(raw, dict) else raw
    if v in (None, ""):
        return None
    v = str(v).strip()
    target, spec = TABLES[f.ref], SPECS[f.ref]
    if SYS_ID.match(v) and conn.execute(select(target.c.sys_id).where(target.c.sys_id == v)).first():
        return v
    hit = None
    for key in (spec.display, *ALTERNATE_KEYS.get(f.ref, ())):
        hit = conn.execute(select(target.c.sys_id).where(target.c[key] == v).order_by(target.c.sys_id)).first()
        if hit is not None:
            break
    if hit is None:
        raise BadValue(f"Invalid reference for {f.name}: {v} is not a {spec.label}")
    return hit[0]


def _values(conn: Connection, table: str, body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise BadValue("The request body must be a JSON object")
    spec, out = SPECS[table], {}
    for k, raw in body.items():
        f = spec.by_name.get(k)
        if f is None or k.startswith("sys_"):
            continue  # unknown and system fields are ignored, as on an instance
        out[k] = _resolve_ref(conn, f, raw) if f.type == "reference" else to_db(f, raw)
    return out


def _next_number(conn: Connection, table: str) -> str:
    prefix = SPECS[table].prefix
    t = TABLES[table]
    top = conn.execute(select(func.max(t.c.number)).where(t.c.number.like(f"{prefix}%"))).scalar_one()
    n = int(top[len(prefix) :]) + 1 if top and top[len(prefix) :].isdigit() else 10001
    return f"{prefix}{n:07d}"


async def _body(request: Request) -> Any:
    try:
        return json.loads(await request.body() or b"{}")
    except ValueError as e:
        raise BadValue(f"Exception while reading request: {e}") from e


def _event_data(conn: Connection, request: Request, table: str, row: dict) -> dict:
    return _Renderer(conn, request, "false", True).render(table, [row], None)[0]


def _write_guard(request: Request, table: str, verb: str) -> tuple[str | None, JSONResponse | None]:
    user, denied = _guard(request, table)
    if denied:
        return None, denied
    if not SPECS[table].writable:
        return None, _error(403, "Operation Failed", f"ACL Exception {verb} Failed due to security constraints")
    return user, None


@router.post(API + "/table/{table}")
async def create_record(table: str, request: Request):
    user, denied = _write_guard(request, table, "Insert")
    if denied:
        return denied
    display, exclude, fields = _params(request)
    t, spec = TABLES[table], SPECS[table]
    now = _now()
    with engine.begin() as conn:
        try:
            body = await _body(request)
            values = _values(conn, table, body)
        except BadValue as e:
            return _error(400, "Invalid value", str(e))
        sid = str(body.get("sys_id") or "")
        if not SYS_ID.match(sid) or conn.execute(select(t.c.sys_id).where(t.c.sys_id == sid)).first():
            sid = uuid.uuid4().hex
        row = {f: None for f in spec.by_name} | TABLE_DEFAULTS.get(table, {}) | values
        row |= {
            "sys_id": sid,
            "sys_created_on": now,
            "sys_updated_on": now,
            "sys_created_by": user,
            "sys_updated_by": user,
            "sys_mod_count": 0,
        }
        if spec.prefix and not row.get("number"):
            row["number"] = _next_number(conn, table)
        _inherit(conn, table, row, now)
        conn.execute(insert(t).values(**row))
        events.emit(conn, SOURCE, f"servicenow.{table}.created", sid, _event_data(conn, request, table, row), now)
        result = _Renderer(conn, request, display, exclude).render(table, [row], fields)[0]
    location = f"{_instance(request)}/table/{table}/{sid}"
    return JSONResponse({"result": result}, status_code=201, headers={"Location": location})


def _inherit(conn: Connection, table: str, row: dict, now: datetime) -> None:
    """Defaults FSM fills on insert."""
    if table == "wm_order":
        row["opened_at"] = row.get("opened_at") or now
        if not row.get("company") and row.get("location"):
            loc = TABLES["cmn_location"]
            row["company"] = conn.execute(select(loc.c.company).where(loc.c.sys_id == row["location"])).scalar()
    if table == "wm_task" and row.get("parent"):
        o = TABLES["wm_order"]
        parent = conn.execute(select(o).where(o.c.sys_id == row["parent"])).mappings().first()
        for k in ("company", "location", "asset", "priority"):
            if row.get(k) is None and parent is not None:
                row[k] = parent[k]


@router.put(API + "/table/{table}/{sys_id}")
@router.patch(API + "/table/{table}/{sys_id}")
async def update_record(table: str, sys_id: str, request: Request):
    user, denied = _write_guard(request, table, "Update")
    if denied:
        return denied
    display, exclude, fields = _params(request)
    t = TABLES[table]
    now = _now()
    with engine.begin() as conn:
        old = conn.execute(select(t).where(t.c.sys_id == sys_id).with_for_update()).mappings().first()
        if old is None:
            return _not_found()
        try:
            values = _values(conn, table, await _body(request))
        except BadValue as e:
            return _error(400, "Invalid value", str(e))
        if table == "wm_task":
            _task_rules(dict(old), values, now)
        values |= {"sys_updated_on": now, "sys_updated_by": user, "sys_mod_count": (old["sys_mod_count"] or 0) + 1}
        conn.execute(update(t).where(t.c.sys_id == sys_id).values(**values))
        row = dict(old) | values
        events.emit(conn, SOURCE, f"servicenow.{table}.updated", sys_id, _event_data(conn, request, table, row), now)
        if table == "wm_task" and row.get("parent") and "state" in values:
            _roll_up(conn, request, row["parent"], user, now)
        result = _Renderer(conn, request, display, exclude).render(table, [row], fields)[0]
    return {"result": result}


def _task_rules(old: dict, values: dict, now: datetime) -> None:
    state = values.get("state", old["state"])
    if values.get("assigned_to") and "state" not in values and old["state"] in (1, 10):
        values["state"] = state = 16  # dispatching a task assigns it
    if state == 2 and old["state"] != 2 and not old.get("actual_work_start"):
        values.setdefault("actual_work_start", now)
    if state in CLOSED_STATES and old["state"] not in CLOSED_STATES:
        values.setdefault("closed_at", now)
        if state in (3, 4):
            values.setdefault("actual_work_end", now)


def _roll_up(conn: Connection, request: Request, order_id: str, user: str, now: datetime) -> None:
    """The order follows its tasks: in progress when one starts, closed when all are closed."""
    o, tk = TABLES["wm_order"], TABLES["wm_task"]
    order = conn.execute(select(o).where(o.c.sys_id == order_id)).mappings().first()
    if order is None or order["state"] in CLOSED_STATES:
        return
    states = list(conn.execute(select(tk.c.state).where(tk.c.parent == order_id)).scalars())
    new: dict[str, Any] = {}
    if states and all(s in CLOSED_STATES for s in states):
        complete = all(s in (3, 7) for s in states) and 3 in states
        new = {"state": 3 if complete else 4, "closed_at": now}
    elif any(s == 2 for s in states) and order["state"] != 2:
        new = {"state": 2}
    elif any(s in (16, 18) for s in states) and order["state"] in (1, 10):
        new = {"state": 16}
    if not new:
        return
    new |= {"sys_updated_on": now, "sys_updated_by": user, "sys_mod_count": (order["sys_mod_count"] or 0) + 1}
    conn.execute(update(o).where(o.c.sys_id == order_id).values(**new))
    row = dict(order) | new
    events.emit(conn, SOURCE, "servicenow.wm_order.updated", order_id, _event_data(conn, request, "wm_order", row), now)


@router.delete(API + "/table/{table}/{sys_id}")
def delete_record(table: str, sys_id: str, request: Request):
    _, denied = _write_guard(request, table, "Delete")
    if denied:
        return denied
    t = TABLES[table]
    with engine.begin() as conn:
        old = conn.execute(select(t).where(t.c.sys_id == sys_id)).mappings().first()
        if old is None:
            return _not_found()
        data = _event_data(conn, request, table, dict(old))
        conn.execute(sql_delete(t).where(t.c.sys_id == sys_id))
        events.emit(conn, SOURCE, f"servicenow.{table}.deleted", sys_id, data, _now())
    return Response(status_code=204)
