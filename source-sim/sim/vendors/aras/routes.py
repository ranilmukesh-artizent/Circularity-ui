"""Aras Innovator's RESTful API (OData v4) and its OAuth server, under /aras/InnovatorServer.

    GET   /Server/OAuthServerDiscovery.aspx                  {"locations": [{"uri": ".../oauthserver/"}]}
    GET   /oauthserver/.well-known/openid-configuration      OpenID discovery (token_endpoint, ...)
    POST  /oauthserver/connect/token                         password grant (see auth.py)
    GET   /server/odata/$metadata                            CSDL
    GET   /server/odata/{ItemType}                           ?$filter=&$select=&$expand=&$orderby=&$top=&$skip=&$count=true
                                                             paging only when asked: Prefer: odata.maxpagesize=N ->
                                                             @odata.nextLink with $skiptoken
    GET   /server/odata/{ItemType}/$count                    the number, as text
    GET   /server/odata/{ItemType}('{id}')                   one item
    GET   /server/odata/{ItemType}('{id}')/{Relationship}    e.g. Part('..')/Part BOM?$expand=related_id
    GET   /server/odata/{ItemType}('{id}')/{item property}   the referenced item, e.g. Part BOM('..')/related_id
    GET   /server/odata/{ItemType}('{id}')/{property}[/$value]
    POST  /server/odata/{ItemType}                           create (201 + representation, or 204 with Prefer: return=minimal)
    POST  /server/odata/{ItemType}('{id}')/{Relationship}    add a relationship (related_id@odata.bind or a deep insert)
    PATCH /server/odata/{ItemType}('{id}')                   update (200 + representation, or 204 with return=minimal)

ItemType names contain spaces ("Part BOM", "Manufacturer Part"); in $filter they are written in brackets
([Part BOM]/quantity eq 2). Relationships (capitalised names) appear only when expanded; item properties appear only
when selected (as @aras.id / @aras.type / @aras.keyed_name annotations) or expanded (as the full item).
Errors use Innovator's OData error body {"code", "message", "target", "details": {"code", "message", "target"}}.
"""

import re
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, update

from sim.core import clock, events
from sim.core.db import engine
from sim.vendors.aras import auth
from sim.vendors.aras.odata4 import QueryError, order, parse_expand, parse_filter, parse_select, path_value, split_top, window
from sim.vendors.aras.seed import ADMIN_ID, CONNECTOR_ID, ITEM, ITEMTYPES, RELATIONSHIPS, aras_id, itemtype_id, stamp

router = APIRouter(prefix="/aras/InnovatorServer")
SOURCE = "bom"
SYSTEM = {
    "id",
    "config_id",
    "itemtype",
    "created_on",
    "created_by_id",
    "modified_on",
    "modified_by_id",
    "generation",
    "is_current",
    "keyed_name",
    "state",
    "is_released",
    "release_date",
}
USER_IDS = {"di-connector": CONNECTOR_ID, "admin": ADMIN_ID}
REASONS = {400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 409: "Conflict"}


class Fault(Exception):
    def __init__(self, status: int, message: str, target: str = "OData", detail_code: str = "SOAP-ENV:Server"):
        super().__init__(message)
        self.status, self.message, self.target, self.detail_code = status, message, target, detail_code


def fault_response(f: Fault) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if f.status == 401 else None
    return JSONResponse(
        {
            "code": str(f.status),
            "message": REASONS.get(f.status, "Error"),
            "target": "AML" if f.target != "OData" else "OData",
            "details": {"code": f.detail_code, "message": f.message, "target": f.target},
        },
        status_code=f.status,
        headers=headers,
    )


def service_root(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/aras/InnovatorServer/server/odata/"


# ------------------------------------------------------------------ the item store for one request
class Store:
    def __init__(self, conn):
        self.rows: dict[str, dict] = {}
        self.types: dict[str, str] = {}
        for r in conn.execute(select(ITEM.c.id, ITEM.c.itemtype, ITEM.c.data)):
            self.rows[r.id] = dict(r.data)
            self.types[r.id] = r.itemtype
        self.by_source: dict[tuple[str, str], list[dict]] = {}
        for iid, t in self.types.items():
            src = self.rows[iid].get("source_id")
            if src:
                self.by_source.setdefault((t, src), []).append(self.rows[iid])

    def of_type(self, t: str) -> list[dict]:
        return [r for i, r in self.rows.items() if self.types[i] == t]

    def resolve(self, itemtype: str):
        """A $filter / $orderby path resolver for rows of an ItemType."""

        def get(row: dict, name: str) -> Any:
            t = self.types.get(row.get("id"), itemtype)
            props = ITEMTYPES[t]
            if name in RELATIONSHIPS.get(t, []):
                return self.by_source.get((name, row["id"]), [])
            if name not in props:
                raise QueryError(f"Property '{name}' is not defined for ItemType '{t}'")
            v = row.get(name)
            if props[name].startswith("item:") and v:
                return self.rows.get(v, {"id": v})
            return v

        def final(row: dict, path: str) -> Any:
            v = path_value(row, path, get)
            if isinstance(v, dict):
                return v.get("id")
            if isinstance(v, list):
                return [x.get("id") if isinstance(x, dict) else x for x in v]
            return v

        return get, final

    # ------------------------------------------------------------ rendering
    def render(self, row: dict, itemtype: str, opts: dict[str, str]) -> dict:
        props = ITEMTYPES[itemtype]
        sel = parse_select(opts.get("$select"))
        exp = parse_expand(opts.get("$expand"))
        for s in sel or []:
            if s not in props and s not in RELATIONSHIPS.get(itemtype, []):
                raise QueryError(f"Property '{s}' is not defined for ItemType '{itemtype}'")
        out: dict[str, Any] = {"@odata.id": f"{itemtype}('{row['id']}')"}
        for name, kind in props.items():
            if name in exp:
                continue
            if sel is not None and name not in sel and name != "id":
                continue
            if kind.startswith("item:"):
                if sel is None:
                    continue  # item properties appear only when selected or expanded
                v = row.get(name)
                ref = self.rows.get(v) if v else None
                out[f"{name}@aras.id"] = v
                out[f"{name}@aras.type"] = kind[5:]
                out[f"{name}@aras.keyed_name"] = ref.get("keyed_name") if ref else None
                continue
            out[name] = row.get(name)
        for name, sub in exp.items():
            if name in RELATIONSHIPS.get(itemtype, []):
                rows = self.query(self.by_source.get((name, row["id"]), []), name, sub)
                out[name] = [self.render(r, name, sub) for r in rows]
            elif name in props and props[name].startswith("item:"):
                v = row.get(name)
                ref = self.rows.get(v) if v else None
                out[name] = self.render(ref, self.types[v], sub) if ref else None
            else:
                raise QueryError(f"Cannot expand '{name}': it is not an item property or relationship of '{itemtype}'")
        return out

    def query(self, rows: list[dict], itemtype: str, opts) -> list[dict]:
        get, final = self.resolve(itemtype)
        flt = parse_filter(opts.get("$filter"))
        if flt:
            rows = [r for r in rows if flt(r, final)]
        rows = order(rows, opts.get("$orderby"), final)
        if opts.get("$orderby") is None:
            rows = sorted(rows, key=lambda r: (r.get("sort_order") or 0, r.get("keyed_name") or "", r["id"]))
        if not hasattr(opts, "multi_items"):  # nested $expand options: $top / $skip applied here
            skip, top = int(opts.get("$skip") or 0), opts.get("$top")
            rows = rows[skip:]
            if top is not None:
                rows = rows[: int(top)]
        return rows


_SEG = re.compile(r"^(?P<name>[^(]+?)(?:\('(?P<key>[^']*)'\))?$")


def _locate(store: Store, path: str):
    """Resolve a resource path. Returns (kind, itemtype, payload, context)."""
    segs = [s for s in path.split("/") if s]
    if not segs:
        raise Fault(404, "No resource path")
    m = _SEG.match(segs[0])
    t = m.group("name") if m else ""
    if t not in ITEMTYPES:
        raise Fault(404, f"ItemType '{t}' does not exist or is not accessible", "AML")
    if m.group("key") is None:
        if len(segs) == 2 and segs[1] == "$count":
            return "count", t, store.of_type(t), t
        if len(segs) > 1:
            raise Fault(400, f"Unsupported resource path segment '{segs[1]}'")
        return "collection", t, store.of_type(t), t
    row = store.rows.get(m.group("key"))
    if row is None or store.types[row["id"]] != t:
        raise Fault(404, f"No items of type {t} found.", "AML")
    context = f"{t}/$entity"
    i = 1
    while i < len(segs):
        seg = segs[i]
        if seg in RELATIONSHIPS.get(t, []):
            rows = store.by_source.get((seg, row["id"]), [])
            if i + 1 < len(segs) and segs[i + 1] == "$count":
                return "count", seg, rows, seg
            if i + 1 < len(segs):
                raise Fault(400, f"Unsupported resource path segment '{segs[i + 1]}'")
            return "collection", seg, rows, seg
        props = ITEMTYPES[t]
        if seg not in props:
            raise Fault(400, f"Property '{seg}' is not defined for ItemType '{t}'", "AML")
        if props[seg].startswith("item:"):
            ref = store.rows.get(row.get(seg) or "")
            if ref is None:
                return "none", t, None, f"{t}/$entity/{seg}"
            t, row = store.types[ref["id"]], ref
            context = f"{t}/$entity"
            i += 1
            continue
        raw = len(segs) > i + 1 and segs[i + 1] == "$value"
        return ("raw" if raw else "value"), t, row.get(seg), f"{t}/$entity/{seg}"
    return "entity", t, row, context


# ------------------------------------------------------------------ OAuth server
@router.get("/Server/OAuthServerDiscovery.aspx")
def oauth_discovery(request: Request):
    return {"locations": [{"uri": str(request.base_url).rstrip("/") + "/aras/InnovatorServer/oauthserver/"}]}


@router.get("/oauthserver/.well-known/openid-configuration")
def openid_configuration(request: Request):
    base = str(request.base_url).rstrip("/") + "/aras/InnovatorServer/oauthserver"
    return {
        "issuer": "OAuthServer",
        "jwks_uri": f"{base}/.well-known/openid-configuration/jwks",
        "authorization_endpoint": f"{base}/connect/authorize",
        "token_endpoint": f"{base}/connect/token",
        "userinfo_endpoint": f"{base}/connect/userinfo",
        "end_session_endpoint": f"{base}/connect/endsession",
        "scopes_supported": ["openid", "Innovator", "offline_access"],
        "grant_types_supported": ["authorization_code", "password", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
    }


@router.post("/oauthserver/connect/token")
async def token(request: Request):
    form = {k: str(v) for k, v in (await request.form()).items()}
    body, err, desc = auth.issue(form)
    if err:
        return JSONResponse({"error": err} | ({"error_description": desc} if desc else {}), status_code=400)
    return JSONResponse(body, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


# ------------------------------------------------------------------ OData reads
@router.get("/server/odata/$metadata")
def metadata(request: Request):
    if auth.user_of(request) is None:
        return fault_response(Fault(401, "Authentication failed: a valid bearer token is required"))
    edm = {
        "string": "Edm.String",
        "text": "Edm.String",
        "decimal": "Edm.Decimal",
        "integer": "Edm.Int32",
        "boolean": "Edm.String",
        "date": "Edm.DateTimeOffset",
    }
    types = []
    for t, props in ITEMTYPES.items():
        name = t.replace(" ", "_")
        ps = "".join(
            f'<NavigationProperty Name="{p}" Type="Aras.{k[5:].replace(" ", "_")}"/>'
            if k.startswith("item:")
            else f'<Property Name="{p}" Type="{edm[k]}"/>'
            for p, k in props.items()
        )
        rels = "".join(
            f'<NavigationProperty Name="{r}" Type="Collection(Aras.{r.replace(" ", "_")})"/>' for r in RELATIONSHIPS.get(t, [])
        )
        types.append(f'<EntityType Name="{name}"><Key><PropertyRef Name="id"/></Key>{ps}{rels}</EntityType>')
    sets = "".join(f'<EntitySet Name="{t}" EntityType="Aras.{t.replace(" ", "_")}"/>' for t in ITEMTYPES)
    xml = (
        '<?xml version="1.0" encoding="utf-8"?><edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">'
        '<edmx:DataServices><Schema Namespace="Aras" xmlns="http://docs.oasis-open.org/odata/ns/edm">'
        f'{"".join(types)}<EntityContainer Name="Innovator">{sets}</EntityContainer></Schema></edmx:DataServices></edmx:Edmx>'
    )
    return Response(xml, media_type="application/xml")


@router.get("/server/odata/{path:path}")
def read(path: str, request: Request):
    if auth.user_of(request) is None:
        return fault_response(Fault(401, "Authentication failed: a valid bearer token is required"))
    root = service_root(request)
    params = request.query_params
    try:
        with engine.connect() as conn:
            store = Store(conn)
        kind, t, payload, context = _locate(store, path)
        if kind == "count":
            rows = store.query(payload, t, {"$filter": params.get("$filter")})
            return Response(str(len(rows)), media_type="text/plain")
        if kind == "raw":
            return Response("" if payload is None else str(payload), media_type="text/plain")
        if kind == "value":
            return {"@odata.context": f"{root}$metadata#{context}", "value": payload}
        if kind == "none":
            return Response(status_code=204)
        sel = params.get("$select")
        ctx_sel = f"({sel})" if sel else ""
        if kind == "entity":
            body = store.render(payload, t, dict(params))
            return {"@odata.context": f"{root}$metadata#{t}{ctx_sel}/$entity"} | body
        rows = store.query(payload, t, params)
        total = len(rows)
        page, nxt, size = window(rows, params, request.headers.get("prefer"), root + path)
        body: dict[str, Any] = {"@odata.context": f"{root}$metadata#{t}{ctx_sel}"}
        if (params.get("$count") or "").lower() == "true":
            body["@odata.count"] = total
        if nxt:
            body["@odata.nextLink"] = nxt
        body["value"] = [store.render(r, t, dict(params)) for r in page]
        headers = {"Preference-Applied": f"odata.maxpagesize={size}"} if size else {}
        return JSONResponse(body, headers=headers)
    except QueryError as e:
        return fault_response(Fault(400, str(e)))
    except Fault as f:
        return fault_response(f)


# ------------------------------------------------------------------ OData writes
def _bind(store: Store, value: Any, kind: str) -> str:
    want = kind[5:]
    m = re.fullmatch(r"(?:.*/)?([^/(]+)\('([^']+)'\)", str(value or ""))
    if not m or m.group(1) != want or store.types.get(m.group(2)) != want:
        raise Fault(400, f"The @odata.bind value '{value}' does not reference an existing {want}")
    return m.group(2)


def _locked(store: Store, itemtype: str, row: dict) -> bool:
    """A Released Part (and the BOM lines under it) cannot be edited: its lifecycle state grants no update."""
    if itemtype == "Part":
        return row.get("state") == "Released"
    if itemtype == "Part BOM":
        parent = store.rows.get(row.get("source_id") or "")
        return bool(parent and parent.get("state") == "Released")
    return False


def _apply(store: Store, itemtype: str, row: dict, body: dict) -> dict:
    props = ITEMTYPES[itemtype]
    out = dict(row)
    for k, v in body.items():
        if k.startswith("@"):
            if k == "@aras.action" and v not in ("edit", "update", "merge", "add", "create"):
                raise Fault(400, f"Action '{v}' is not supported here")
            continue
        if k.endswith("@odata.bind"):
            name = k[: -len("@odata.bind")]
            if name not in props or not props[name].startswith("item:") or name in SYSTEM:
                raise Fault(400, f"Property '{name}' is not defined for ItemType '{itemtype}'", "AML")
            out[name] = _bind(store, v, props[name])
            continue
        if k not in props:
            raise Fault(400, f"Property '{k}' is not defined for ItemType '{itemtype}'", "AML")
        if k in SYSTEM:
            raise Fault(400, f"Property '{k}' is set by the server and cannot be changed", "AML")
        kind = props[k]
        if kind.startswith("item:"):
            raise Fault(400, f"Set the item property '{k}' with {k}@odata.bind")
        if kind in ("decimal", "integer") and v is not None and (isinstance(v, bool) or not isinstance(v, int | float)):
            raise Fault(400, f"The value of '{k}' must be a number", "AML")
        if kind == "boolean" and v not in ("0", "1", 0, 1, True, False, None):
            raise Fault(400, f"The value of '{k}' must be 0 or 1", "AML")
        out[k] = ("1" if v in ("1", 1, True) else "0") if kind == "boolean" and v is not None else v
    return out


def _check_unique(store: Store, itemtype: str, row: dict) -> None:
    if itemtype in ("Part", "Manufacturer Part") and row.get("item_number"):
        for other in store.of_type(itemtype):
            if (
                other["id"] != row["id"]
                and other.get("item_number") == row["item_number"]
                and (itemtype == "Part" or other.get("manufacturer") == row.get("manufacturer"))
            ):
                raise Fault(
                    400, f"The {itemtype} '{row['item_number']}' already exists", "Aras.Server.Core.UniqueConstraintException"
                )


def _save(conn, store: Store, itemtype: str, row: dict, new: bool, user: str) -> dict:
    now = clock.now(conn)
    row = row | {"modified_on": stamp(now), "modified_by_id": USER_IDS.get(user, ADMIN_ID)}
    if new:
        row |= {"created_on": stamp(now), "created_by_id": USER_IDS.get(user, ADMIN_ID)}
    row["keyed_name"] = (
        row.get("item_number")
        or row.get("name")
        or (store.rows.get(row.get("related_id") or "", {}).get("keyed_name"))
        or row["id"]
    )
    _check_unique(store, itemtype, row)
    if new:
        conn.execute(insert(ITEM).values(id=row["id"], itemtype=itemtype, data=row, modified_on=now))
    else:
        conn.execute(update(ITEM).where(ITEM.c.id == row["id"]).values(data=row, modified_on=now))
    store.rows[row["id"]], store.types[row["id"]] = row, itemtype
    if row.get("source_id"):
        lst = store.by_source.setdefault((itemtype, row["source_id"]), [])
        lst[:] = [r for r in lst if r["id"] != row["id"]] + [row]
    events.emit(
        conn,
        SOURCE,
        f"com.aras.innovator.{itemtype.replace(' ', '')}.{'created' if new else 'updated'}",
        row["keyed_name"],
        {"id": row["id"], "itemtype": itemtype, "keyed_name": row["keyed_name"]},
        now,
    )
    return row


def _new(store: Store, itemtype: str, body: dict, source_id: str | None = None) -> dict:
    iid = aras_id(itemtype, "new", str(len(store.rows)), str(len(body)), str(sorted(body.items(), key=str)))
    row: dict[str, Any] = {"id": iid, "config_id": iid, "itemtype": itemtype_id(itemtype), "generation": 1, "is_current": "1"}
    if itemtype == "Part":
        row |= {"state": "Preliminary", "major_rev": "A", "is_released": "0", "unit": "EA", "make_buy": "Make"}
    if itemtype in ("Manufacturer Part", "Manufacturer"):
        row["state"] = "Preliminary"
    if itemtype == "Part AML":
        row["state"] = "Approved"
    if source_id:
        row["source_id"] = source_id
    return row


def _answer(request: Request, store: Store, itemtype: str, row: dict, status: int) -> Response:
    location = f"{service_root(request)}{itemtype}('{row['id']}')"
    if "return=minimal" in (request.headers.get("prefer") or ""):
        return Response(status_code=204, headers={"Location": location})
    body = {"@odata.context": f"{service_root(request)}$metadata#{itemtype}/$entity"} | store.render(row, itemtype, {})
    return JSONResponse(body, status_code=status, headers={"Location": location})


async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise Fault(400, "The request body must be a single JSON item")
    return body


@router.post("/server/odata/{path:path}")
async def create(path: str, request: Request):
    user = auth.user_of(request)
    if user is None:
        return fault_response(Fault(401, "Authentication failed: a valid bearer token is required"))
    try:
        body = await _body(request)
        with engine.begin() as conn:
            store = Store(conn)
            segs = [s for s in path.split("/") if s]
            m = _SEG.match(segs[0]) if segs else None
            t = m.group("name") if m else ""
            if t not in ITEMTYPES:
                raise Fault(404, f"ItemType '{t}' does not exist or is not accessible", "AML")
            source_id = None
            if m.group("key") is not None:  # POST to a relationship of an item
                parent = store.rows.get(m.group("key"))
                if parent is None or store.types[parent["id"]] != t:
                    raise Fault(404, f"No items of type {t} found.", "AML")
                if len(segs) != 2 or segs[1] not in RELATIONSHIPS.get(t, []):
                    raise Fault(400, f"'{'/'.join(segs[1:])}' is not a relationship of {t}")
                source_id, t = parent["id"], segs[1]
                if t == "Part BOM" and _locked(store, "Part", parent):
                    raise Fault(
                        400,
                        f"Insufficient permissions to change the BOM of Part '{parent['item_number']}': " "it is Released",
                        "Aras.Server.Core.InsufficientPermissionsException",
                    )
            elif len(segs) != 1:
                raise Fault(400, "Items are created by a POST to the ItemType's collection")
            if t == "User":
                raise Fault(
                    403, "Users cannot be created through this service", "Aras.Server.Core.InsufficientPermissionsException"
                )
            deep = body.get("related_id")
            if isinstance(deep, dict):  # deep insert of the related item
                rel_type = ITEMTYPES[t]["related_id"][5:]
                related = _save(conn, store, rel_type, _apply(store, rel_type, _new(store, rel_type, deep), deep), True, user)
                body = {k: v for k, v in body.items() if k != "related_id"} | {
                    "related_id@odata.bind": f"{rel_type}('{related['id']}')"
                }
            row = _apply(store, t, _new(store, t, body, source_id), body)
            required = {
                "Part": ["item_number"],
                "Manufacturer Part": ["item_number", "manufacturer"],
                "Manufacturer": ["name"],
                "Part BOM": ["source_id", "related_id"],
                "Part AML": ["source_id", "related_id"],
            }[t]
            missing = [p for p in required if not row.get(p)]
            if missing:
                raise Fault(400, f"Required property '{missing[0]}' is missing", "AML")
            row = _save(conn, store, t, row, True, user)
            return _answer(request, store, t, row, 201)
    except QueryError as e:
        return fault_response(Fault(400, str(e)))
    except Fault as f:
        return fault_response(f)


@router.patch("/server/odata/{path:path}")
async def patch(path: str, request: Request):
    user = auth.user_of(request)
    if user is None:
        return fault_response(Fault(401, "Authentication failed: a valid bearer token is required"))
    try:
        body = await _body(request)
        with engine.begin() as conn:
            store = Store(conn)
            kind, t, row, _ = _locate(store, path)
            if kind != "entity" or len(split_top(path, "/")) != 1:
                raise Fault(400, "PATCH needs a single item URL, e.g. Part('id')")
            if t == "User":
                raise Fault(
                    403, "Users cannot be changed through this service", "Aras.Server.Core.InsufficientPermissionsException"
                )
            if _locked(store, t, row):
                raise Fault(
                    400,
                    f"Insufficient permissions to edit {t} '{row.get('keyed_name')}': it is Released",
                    "Aras.Server.Core.InsufficientPermissionsException",
                )
            row = _save(conn, store, t, _apply(store, t, row, body), False, user)
            resp = _answer(request, store, t, row, 200)
            return resp
    except QueryError as e:
        return fault_response(Fault(400, str(e)))
    except Fault as f:
        return fault_response(f)
