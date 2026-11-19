"""Build a mock system from a Spec (docs/BACKEND_STEPS.md, B5).

Storage: one table per system, `<schema>.docs (resource, id, doc jsonb, updated_at)`, plus a counter for new ids.
HTTP, below spec.base_path:
    GET    {path}                 list: equality filters (?field=value), ?updated_since=, paging as the spec says
    GET    {path}/{id}            one document
    POST   {path}                 create (when resource.create): assigns the id if missing, records an event
    PATCH  {path}/{id}            merge fields (when resource.update), records an event
    POST   {auth.token_path}      OAuth 2.0 client credentials (when auth.kind == "oauth_cc")
"""

import base64
import secrets
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, and_, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from sim import events
from sim.db import engine
from sim.generic.spec import Auth, Paging, Resource, Spec, credentials
from sim.mock import Mock
from sim.seed import Seed

__all__ = ["Auth", "Paging", "Resource", "Spec", "build", "credentials"]


def _tables(spec: Spec) -> tuple[MetaData, Table, Table]:
    md = MetaData(schema=spec.schema)
    docs = Table(
        "docs",
        md,
        Column("resource", String(60), primary_key=True),
        Column("id", String(80), primary_key=True),
        Column("doc", JSONB, nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    counters = Table("counters", md, Column("resource", String(60), primary_key=True), Column("n", Integer, nullable=False))
    return md, docs, counters


def build(spec: Spec) -> Mock:
    md, docs, counters = _tables(spec)
    creds = credentials(spec)
    tokens: dict[str, float] = {}
    by_name = {r.name: r for r in spec.resources}

    # ------------------------------------------------------------ storage
    def create_tables(conn: Connection) -> None:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{spec.schema}"'))
        md.create_all(conn)

    def load(conn: Connection, seed: Seed) -> dict[str, int]:
        data = spec.seed(seed)
        at = seed.world.as_of
        counts = {}
        for name, items in data.items():
            res = by_name[name]
            if items:
                conn.execute(
                    insert(docs), [{"resource": name, "id": str(d[res.id_field]), "doc": d, "updated_at": at} for d in items]
                )
            conn.execute(insert(counters).values(resource=name, n=len(items)))
            counts[name] = len(items)
        return counts

    def ensure(conn: Connection, seed: Seed) -> None:
        create_tables(conn)
        if conn.execute(select(func.count()).select_from(docs)).scalar_one() == 0:
            load(conn, seed)

    def reset(conn: Connection, seed: Seed) -> dict[str, int]:
        md.drop_all(conn)
        create_tables(conn)
        return load(conn, seed)

    # ------------------------------------------------------------ http helpers
    def err(status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
        return JSONResponse(spec.error(status, code, message), status_code=status, headers=headers)

    def authenticate(request: Request) -> bool:
        a = spec.auth
        h = request.headers.get(a.header if a.kind == "api_key" else "authorization", "")
        if a.kind == "api_key":
            return h.removeprefix("Bearer ").removeprefix("ApiKey ").strip() == creds["api_key"]
        if a.kind == "basic":
            try:
                return (
                    h.lower().startswith("basic ") and base64.b64decode(h[6:]).decode() == f"{creds['user']}:{creds['password']}"
                )
            except ValueError:
                return False
        if not h.lower().startswith("bearer "):
            return False
        tok = h[7:].strip()
        return tok == creds["api_key"] if a.kind == "bearer" else tokens.get(tok, 0) > time.time()

    def denied() -> JSONResponse:
        return err(
            401, "unauthorized", "Authentication failed", {"WWW-Authenticate": "Bearer" if spec.auth.kind != "basic" else "Basic"}
        )

    router = APIRouter(prefix=spec.base_path)

    if spec.auth.kind == "oauth_cc":

        @router.post(spec.auth.token_path)
        async def token(request: Request):
            form = dict(await request.form())
            h = request.headers.get("authorization", "")
            cid, csec = form.get("client_id", ""), form.get("client_secret", "")
            if h.lower().startswith("basic "):
                try:
                    cid, _, csec = base64.b64decode(h[6:]).decode().partition(":")
                except ValueError:
                    pass
            if form.get("grant_type") != "client_credentials" or (cid, csec) != (creds["client_id"], creds["client_secret"]):
                return JSONResponse({"error": "invalid_client"}, status_code=401)
            tok = secrets.token_urlsafe(32)
            tokens[tok] = time.time() + 3600
            return {"access_token": tok, "token_type": "Bearer", "expires_in": 3600}

    def page_args(request: Request) -> tuple[int, int] | JSONResponse:
        p, q = spec.paging, request.query_params
        try:
            if p.style == "page":
                size = int(q.get(p.size_param, p.default_size))
                page = int(q.get(p.page_param, 1))
                if page < 1:
                    raise ValueError
                offset = (page - 1) * size
            else:
                size = int(q.get(p.limit_param, p.default_size))
                raw = q.get(p.cursor_param if p.style == "cursor" else p.offset_param)
                offset = int(base64.urlsafe_b64decode(raw.encode()).decode()) if (raw and p.style == "cursor") else int(raw or 0)
            if size < 1 or offset < 0:
                raise ValueError
        except ValueError:
            return err(400, "invalid_request", "Invalid paging parameters")
        return min(size, p.max_size), offset

    def next_value(offset: int, size: int, total: int) -> Any:
        if offset + size >= total:
            return None
        p = spec.paging
        if p.style == "page":
            return offset // size + 2
        if p.style == "cursor":
            return base64.urlsafe_b64encode(str(offset + size).encode()).decode()
        return offset + size

    def now() -> datetime:
        return datetime.now(UTC)

    def counter(conn: Connection, name: str) -> int:
        n = conn.execute(
            update(counters).where(counters.c.resource == name).values(n=counters.c.n + 1).returning(counters.c.n)
        ).scalar()
        if n is None:
            conn.execute(insert(counters).values(resource=name, n=1))
            n = 1
        return n

    # ------------------------------------------------------------ routes per resource
    def add_routes(res: Resource) -> None:
        @router.get(res.path, name=f"{spec.source_id}:{res.name}:list")
        def list_(request: Request):
            if not authenticate(request):
                return denied()
            pa = page_args(request)
            if isinstance(pa, JSONResponse):
                return pa
            size, offset = pa
            q = request.query_params
            cond = [docs.c.resource == res.name]
            for f in res.filters:
                if f in q:
                    cond.append(docs.c.doc[f].astext == q[f])
            if spec.updated_since_param in q:
                try:
                    since = datetime.fromisoformat(q[spec.updated_since_param].replace("Z", "+00:00"))
                except ValueError:
                    return err(400, "invalid_request", f"Invalid {spec.updated_since_param}")
                cond.append(docs.c.updated_at > since)
            unknown = [
                k for k in q if k not in res.filters and k not in _paging_params(spec.paging) and k != spec.updated_since_param
            ]
            if unknown:
                return err(400, "invalid_request", f"Unknown query parameter '{unknown[0]}'")
            with engine.connect() as conn:
                total = conn.execute(select(func.count()).select_from(docs).where(and_(*cond))).scalar_one()
                rows = (
                    conn.execute(select(docs.c.doc).where(and_(*cond)).order_by(docs.c.id).offset(offset).limit(size))
                    .scalars()
                    .all()
                )
            p = spec.paging
            body: dict[str, Any] = {p.items_key: rows}
            if p.next_key:
                body[p.next_key] = next_value(offset, size, total)
            if p.total_key:
                body[p.total_key] = total
            return body

        @router.get(res.path + "/{item_id}", name=f"{spec.source_id}:{res.name}:get")
        def get(item_id: str, request: Request):
            if not authenticate(request):
                return denied()
            with engine.connect() as conn:
                doc = conn.execute(select(docs.c.doc).where(docs.c.resource == res.name, docs.c.id == item_id)).scalar()
            return doc if doc is not None else err(404, "not_found", f"{res.name} {item_id} not found")

        if res.create:

            @router.post(res.path, status_code=201, name=f"{spec.source_id}:{res.name}:create")
            async def create(request: Request):
                if not authenticate(request):
                    return denied()
                try:
                    body = await request.json()
                except ValueError:
                    return err(400, "invalid_request", "Body must be JSON")
                if not isinstance(body, dict):
                    return err(400, "invalid_request", "Body must be a JSON object")
                with engine.begin() as conn:
                    item_id = str(body.get(res.id_field) or res.id_format.format(n=counter(conn, res.name)))
                    exists = conn.execute(
                        select(func.count()).select_from(docs).where(docs.c.resource == res.name, docs.c.id == item_id)
                    )
                    if exists.scalar_one():
                        return err(409, "conflict", f"{res.name} {item_id} already exists")
                    at = now()
                    doc = body | {res.id_field: item_id, "createdAt": body.get("createdAt") or at.isoformat()}
                    conn.execute(insert(docs).values(resource=res.name, id=item_id, doc=doc, updated_at=at))
                    if res.event:
                        events.emit(conn, spec.source_id, f"{res.event}.created", item_id, doc, at)
                return JSONResponse(doc, status_code=201)

        if res.update:

            @router.patch(res.path + "/{item_id}", name=f"{spec.source_id}:{res.name}:update")
            async def patch(item_id: str, request: Request):
                if not authenticate(request):
                    return denied()
                try:
                    body = await request.json()
                except ValueError:
                    return err(400, "invalid_request", "Body must be JSON")
                with engine.begin() as conn:
                    doc = conn.execute(
                        select(docs.c.doc).where(docs.c.resource == res.name, docs.c.id == item_id).with_for_update()
                    ).scalar()
                    if doc is None:
                        return err(404, "not_found", f"{res.name} {item_id} not found")
                    at = now()
                    doc = doc | {k: v for k, v in body.items() if k != res.id_field}
                    conn.execute(
                        update(docs).where(docs.c.resource == res.name, docs.c.id == item_id).values(doc=doc, updated_at=at)
                    )
                    if res.event:
                        events.emit(conn, spec.source_id, f"{res.event}.updated", item_id, doc, at)
                return doc

    for r in spec.resources:
        add_routes(r)

    def expire_tokens() -> int:
        n = len(tokens)
        tokens.clear()
        return n

    router.expire_tokens = expire_tokens  # fault injection (B6)
    return Mock(spec.source_id, router, ensure, reset, spec.title)


def _paging_params(p: Paging) -> set[str]:
    return {p.limit_param, p.offset_param, p.page_param, p.size_param, p.cursor_param}
