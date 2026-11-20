"""A small OData v2 server over SQLAlchemy tables, shaped like SAP Gateway (docs/BACKEND_STEPS.md, B3).

    svc = ODataService("API_PRODUCT_SRV", namespace="API_PRODUCT_SRV")
    svc.entity_set("A_Product", table, {"Product": (table.c.product, "Edm.String"), ...}, keys=["Product"])

The router (sim/s4/api.py) hands every request below /sap/opu/odata/sap/<service>/ to `handle_get`.
Values are serialised as SAP Gateway does in JSON: decimals as strings, Edm.DateTime as "/Date(ms)/",
Edm.DateTimeOffset as "/Date(ms+0000)/", collections in {"d":{"results":[…]}} with "__metadata" on each entry.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import Column, Table, and_, func, select
from sqlalchemy.engine import Connection

from sim.odata.filter import FilterError, parse_filter


class ODataError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def error_response(status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    """The SAP Gateway error body."""
    body = {
        "error": {
            "code": code,
            "message": {"lang": "en", "value": message},
            "innererror": {"application": {"component_id": "", "service_namespace": "/SAP/"}},
        }
    }
    return JSONResponse(body, status_code=status, headers=headers)


@dataclass
class Prop:
    column: Column
    edm: str  # Edm.String, Edm.Decimal, Edm.DateTime, Edm.DateTimeOffset, Edm.Boolean, Edm.Int32, Edm.Guid, Edm.Time


@dataclass
class Nav:
    target: str  # entity set name in the same service
    on: list[tuple[str, str]]  # (property here, property there)
    many: bool = True


@dataclass
class EntitySet:
    name: str  # A_Product
    table: Table
    props: dict[str, Prop]
    keys: list[str]
    navs: dict[str, Nav] = field(default_factory=dict)
    type_name: str = ""  # A_ProductType

    def __post_init__(self):
        self.type_name = self.type_name or self.name + "Type"


def _odata_value(value: Any, edm: str) -> Any:
    if value is None:
        return None
    if edm == "Edm.Decimal":  # SAP sends decimals as strings with the column's scale, e.g. "1002000.00"
        return str(value) if isinstance(value, Decimal) else str(Decimal(str(value)))
    if edm in ("Edm.DateTime", "Edm.DateTimeOffset"):
        if isinstance(value, date) and not isinstance(value, datetime):
            value = datetime(value.year, value.month, value.day, tzinfo=UTC)
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        ms = int(value.timestamp() * 1000)
        return f"/Date({ms}+0000)/" if edm == "Edm.DateTimeOffset" else f"/Date({ms})/"
    if edm in ("Edm.Int32", "Edm.Int16", "Edm.Byte"):
        return int(value)
    if edm == "Edm.Int64":
        return str(int(value))
    return value


def _key_literal(value: Any, edm: str) -> str:
    return f"'{value}'" if edm in ("Edm.String", "Edm.Guid") else str(value)


_KEY_RE = re.compile(r"^(?P<set>[A-Za-z_][A-Za-z0-9_]*)(?:\((?P<key>[^)]*)\))?$")


class ODataService:
    def __init__(self, name: str, namespace: str | None = None):
        self.name = name
        self.namespace = namespace or name
        self.sets: dict[str, EntitySet] = {}

    def entity_set(self, name: str, table: Table, props: dict[str, tuple[Column, str]], keys: Sequence[str], **kw) -> EntitySet:
        es = EntitySet(name, table, {k: Prop(*v) for k, v in props.items()}, list(keys), **kw)
        self.sets[name] = es
        return es

    # ------------------------------------------------------------- serialisation
    def entry(self, es: EntitySet, row: Any, base: str, select_props: list[str] | None, expand: dict, conn: Connection) -> dict:
        m = row._mapping
        key = ",".join(f"{k}={_key_literal(m[es.props[k].column.key], es.props[k].edm)}" for k in es.keys)
        if len(es.keys) == 1:
            k = es.keys[0]
            key = _key_literal(m[es.props[k].column.key], es.props[k].edm)
        uri = f"{base}/{es.name}({key})"
        out: dict[str, Any] = {"__metadata": {"id": uri, "uri": uri, "type": f"{self.namespace}.{es.type_name}"}}
        for p, prop in es.props.items():
            if select_props is None or p in select_props:
                out[p] = _odata_value(m[prop.column.key], prop.edm)
        for nav_name, nav in es.navs.items():
            if nav_name in expand:
                target = self.sets[nav.target]
                cond = and_(*[target.props[there].column == m[es.props[here].column.key] for here, there in nav.on])
                rows = conn.execute(select(target.table).where(cond)).all()
                items = [self.entry(target, r, base, None, expand[nav_name], conn) for r in rows]
                out[nav_name] = {"results": items} if nav.many else (items[0] if items else None)
            elif select_props is None:
                out[nav_name] = {"__deferred": {"uri": f"{uri}/{nav_name}"}}
        return out

    # ------------------------------------------------------------- GET
    def handle_get(self, request: Request, path: str, conn: Connection) -> Response:
        base = str(request.base_url).rstrip("/") + f"/sap/opu/odata/sap/{self.name}"
        path = path.strip("/")
        if path in ("", "$metadata"):
            return self.service_document(base) if path == "" else Response(self.metadata(), media_type="application/xml")
        parts = path.split("/")
        count_only = parts[-1] == "$count"
        if count_only:
            parts = parts[:-1]
        m = _KEY_RE.match(parts[0])
        if not m or m["set"] not in self.sets:
            raise ODataError(
                404,
                "/IWFND/MED/170",
                f"No service found for namespace '', name '{self.name}', version '0001'"
                if not m
                else f"Resource not found for segment '{parts[0]}'",
            )
        es = self.sets[m["set"]]
        q = request.query_params
        where = []
        if m["key"]:
            where.append(self._key_condition(es, m["key"]))
        if len(parts) > 1:  # navigation: A_PurchaseOrder('49048')/to_PurchaseOrderItem
            if not m["key"] or parts[1] not in es.navs:
                raise ODataError(404, "/IWBEP/CM_MGW_RT/021", f"Resource not found for segment '{parts[1]}'")
            parent = conn.execute(select(es.table).where(*where)).first()
            if parent is None:
                raise ODataError(404, "/IWBEP/CM_MGW_RT/020", "Resource not found")
            nav = es.navs[parts[1]]
            es = self.sets[nav.target]
            where = [
                es.props[there].column == parent._mapping[self.sets[m["set"]].props[here].column.key] for here, there in nav.on
            ]
            single = not nav.many
        else:
            single = bool(m["key"])
        if "$filter" in q:
            try:
                where.append(parse_filter(q["$filter"], {p: v.column for p, v in es.props.items()}))
            except FilterError as e:
                raise ODataError(400, "/IWBEP/CM_MGW_RT/022", f"Invalid filter expression: {e}") from e
        stmt = select(es.table).where(*where)
        if count_only:
            n = conn.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            return Response(str(n), media_type="text/plain")
        total = (
            conn.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            if q.get("$inlinecount") == "allpages"
            else None
        )
        if "$orderby" in q:
            for part in q["$orderby"].split(","):
                name, _, direction = part.strip().partition(" ")
                if name not in es.props:
                    raise ODataError(400, "/IWBEP/CM_MGW_RT/022", f"Property '{name}' is invalid in $orderby")
                col = es.props[name].column
                stmt = stmt.order_by(col.desc() if direction.strip().lower() == "desc" else col.asc())
        else:
            stmt = stmt.order_by(*[es.props[k].column for k in es.keys])
        if "$skip" in q:
            stmt = stmt.offset(_int(q["$skip"], "$skip"))
        if "$top" in q:
            stmt = stmt.limit(_int(q["$top"], "$top"))
        select_props = self._select(es, q.get("$select"))
        expand = self._expand(es, q.get("$expand"))
        rows = conn.execute(stmt).all()
        entries = [self.entry(es, r, base, select_props, expand, conn) for r in rows]
        if single:
            if not entries:
                raise ODataError(404, "/IWBEP/CM_MGW_RT/020", "Resource not found")
            return JSONResponse({"d": entries[0]})
        body: dict[str, Any] = {"results": entries}
        if total is not None:
            body["__count"] = str(total)
        return JSONResponse({"d": body})

    def _key_condition(self, es: EntitySet, key: str):
        parts = [p.strip() for p in _split_keys(key)]
        if len(parts) == 1 and "=" not in parts[0]:
            if len(es.keys) != 1:
                raise ODataError(400, "/IWBEP/CM_MGW_RT/005", "Key predicate is not valid")
            parts = [f"{es.keys[0]}={parts[0]}"]
        cond = []
        for p in parts:
            name, _, lit = p.partition("=")
            if name not in es.props:
                raise ODataError(400, "/IWBEP/CM_MGW_RT/005", f"Key property '{name}' is invalid")
            value = lit[1:-1].replace("''", "'") if lit.startswith("'") else lit
            cond.append(es.props[name].column == value)
        return and_(*cond)

    def _select(self, es: EntitySet, text: str | None) -> list[str] | None:
        if not text:
            return None
        names = [s.strip() for s in text.split(",") if s.strip()]
        bad = [n for n in names if n not in es.props and n not in es.navs and n != "*"]
        if bad:
            raise ODataError(400, "/IWBEP/CM_MGW_RT/022", f"Property '{bad[0]}' is invalid in $select")
        return None if "*" in names else names

    def _expand(self, es: EntitySet, text: str | None) -> dict:
        tree: dict = {}
        for path in (text or "").split(","):
            node, current = tree, es
            for seg in [s for s in path.strip().split("/") if s]:
                if seg not in current.navs:
                    raise ODataError(400, "/IWBEP/CM_MGW_RT/022", f"Navigation property '{seg}' is invalid in $expand")
                node = node.setdefault(seg, {})
                current = self.sets[current.navs[seg].target]
        return tree

    # ------------------------------------------------------------- documents
    def service_document(self, base: str) -> JSONResponse:  # noqa: ARG002 - the service interface
        return JSONResponse({"d": {"EntitySets": list(self.sets)}})

    def metadata(self) -> str:
        types, sets, assocs = [], [], []
        for es in self.sets.values():
            keys = "".join(f'<PropertyRef Name="{k}"/>' for k in es.keys)
            props = "".join(
                f'<Property Name="{p}" Type="{v.edm}" Nullable="{"false" if p in es.keys else "true"}"/>'
                for p, v in es.props.items()
            )
            navs = "".join(
                f'<NavigationProperty Name="{n}" Relationship="{self.namespace}.assoc_{es.name}_{n}" '
                f'FromRole="FromRole_{es.name}" ToRole="ToRole_{nav.target}"/>'
                for n, nav in es.navs.items()
            )
            types.append(f'<EntityType Name="{es.type_name}"><Key>{keys}</Key>{props}{navs}</EntityType>')
            sets.append(f'<EntitySet Name="{es.name}" EntityType="{self.namespace}.{es.type_name}"/>')
            for n, nav in es.navs.items():
                target = self.sets[nav.target]
                assocs.append(
                    f'<Association Name="assoc_{es.name}_{n}"><End Type="{self.namespace}.{es.type_name}" Multiplicity="1" '
                    f'Role="FromRole_{es.name}"/><End Type="{self.namespace}.{target.type_name}" '
                    f'Multiplicity="{"*" if nav.many else "0..1"}" Role="ToRole_{nav.target}"/></Association>'
                )
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx" '
            'xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">'
            '<edmx:DataServices m:DataServiceVersion="2.0">'
            f'<Schema Namespace="{escape(self.namespace)}" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">'
            + "".join(types)
            + "".join(assocs)
            + f'<EntityContainer Name="{escape(self.namespace)}_Entities" m:IsDefaultEntityContainer="true">'
            + "".join(sets)
            + "</EntityContainer></Schema></edmx:DataServices></edmx:Edmx>"
        )


def _int(value: str, name: str) -> int:
    try:
        n = int(value)
    except ValueError as e:
        raise ODataError(400, "/IWBEP/CM_MGW_RT/022", f"Invalid value '{value}' for {name}") from e
    if n < 0:
        raise ODataError(400, "/IWBEP/CM_MGW_RT/022", f"Invalid value '{value}' for {name}")
    return n


def _split_keys(text: str) -> list[str]:
    """Split "A='x,y',B='z'" on commas outside quotes."""
    out, cur, quoted = [], "", False
    for ch in text:
        if ch == "'":
            quoted = not quoted
        if ch == "," and not quoted:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


Writer = Callable[[Request, dict, Connection], dict]
