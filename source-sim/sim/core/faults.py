"""Fault injection (docs/backend-steps.md, B6). One middleware, so every mock gets it without code of its own.

POST /_sim/faults {"system": "mkt", "kind": "token_expired"}     kinds:
    latency        delay every call by `value` ms
    error          answer `value` (HTTP status, default 500) to every `every`-th call (default every call)
    unavailable    answer 503 to every call (system down)
    token_expired  refuse every call with 401 unless it uses Basic auth: bearer tokens and API keys have expired
    amount         a mock that posts an amount (the S/4 credit memo) posts `value` cents instead of the one asked (P9-13.4)
Optional "minutes": the fault ends after that many simulated minutes; otherwise it lasts until removed.
DELETE /_sim/faults[?system=…] removes faults.
A mock can register its vendor's error shape for these in SHAPES (AWS IoT: ThrottlingException for a 429, etc.).

The demo starts with one fault (SOURCES.mkt: "Feed token expired 6 Oct"): Ritchie Bros. Market Data has an expired
token. It is applied by POST /_sim/faults/demo, and at start-up when SIM_DEMO_FAULTS is true.
"""

import asyncio
from collections.abc import Callable
from datetime import timedelta

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, delete, insert, select, text, update
from sqlalchemy.engine import Connection
from starlette.middleware.base import BaseHTTPMiddleware

from sim.core import clock
from sim.core.db import engine
from sim.core.registry import SYSTEMS

KINDS = {"latency", "error", "unavailable", "token_expired", "amount"}
DEMO_FAULTS = [{"system": "mkt", "kind": "token_expired", "note": "Feed token expired 6 Oct (demo SOURCES.mkt)"}]

metadata = MetaData(schema="sim")
FAULTS = Table(
    "faults",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("system", String(40), nullable=False),
    Column("kind", String(20), nullable=False),
    Column("value", Integer),
    Column("every", Integer, nullable=False, server_default="1"),
    Column("calls", Integer, nullable=False, server_default="0"),
    Column("until", DateTime(timezone=True)),
    Column("note", String(200)),
)

# first path segment -> system id: /sap -> erp, /ariba -> proc, /maximo -> eam …
PREFIX = {"sap": "erp", "ariba": "proc"} | {s.base_path.strip("/").split("/")[0]: s.source_id for s in SYSTEMS if s.base_path}

# A mock may answer faults in its vendor's own error shape: system -> fn(kind, status, message) -> Response.
# kind is "unavailable", "error" or "token_expired"; without one, the generic shapes below are used.
SHAPES: dict[str, Callable[[str, int, str], Response]] = {}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS sim"))
    metadata.create_all(conn)


def add(
    conn: Connection,
    system: str,
    kind: str,
    value: int | None = None,
    every: int = 1,
    minutes: float | None = None,
    note: str | None = None,
) -> int:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    if system not in {s.source_id for s in SYSTEMS}:
        raise ValueError(f"unknown system {system!r}")
    until = clock.now(conn) + timedelta(minutes=minutes) if minutes else None
    return conn.execute(
        insert(FAULTS)
        .values(system=system, kind=kind, value=value, every=max(1, every), until=until, note=note)
        .returning(FAULTS.c.id)
    ).scalar_one()


def remove(conn: Connection, system: str | None = None) -> int:
    stmt = delete(FAULTS) if system is None else delete(FAULTS).where(FAULTS.c.system == system)
    return conn.execute(stmt).rowcount


def active(conn: Connection, system: str | None = None) -> list[dict]:
    now = clock.now(conn)
    q = select(FAULTS).where((FAULTS.c.until.is_(None)) | (FAULTS.c.until > now))
    if system:
        q = q.where(FAULTS.c.system == system)
    return [dict(r._mapping) for r in conn.execute(q.order_by(FAULTS.c.id))]


def apply_demo(conn: Connection, systems: list[str] | None = None) -> list[int]:
    """Replace the faults with the demo's. With `systems` (a per-system reset), only those systems' faults are replaced
    by their demo faults; other systems keep theirs (refactor R3)."""
    if systems is None:
        remove(conn)
    else:
        conn.execute(delete(FAULTS).where(FAULTS.c.system.in_(systems)))
    demo = [f for f in DEMO_FAULTS if systems is None or f["system"] in systems]
    return [add(conn, f["system"], f["kind"], note=f["note"]) for f in demo]


class FaultMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        seg = request.url.path.strip("/").split("/")[0]
        system = PREFIX.get(seg)
        if system is None:  # /_sim, /health, /docs …
            return await call_next(request)
        faults = await asyncio.to_thread(self._hit, system)
        for f in faults:
            if f["kind"] == "latency" and f["value"]:
                await asyncio.sleep(f["value"] / 1000)
        shape = SHAPES.get(system)
        for f in faults:
            if f["kind"] == "unavailable":
                if shape:
                    return shape("unavailable", 503, f"{system} is unavailable (simulated)")
                return JSONResponse({"error": {"code": "unavailable", "message": f"{system} is unavailable (simulated)"}}, 503)
            if f["kind"] == "error" and f["calls"] % f["every"] == 0:
                status = f["value"] or 500
                if shape:
                    return shape("error", status, f"Simulated HTTP {status}")
                return JSONResponse({"error": {"code": "simulated_error", "message": f"Simulated HTTP {status}"}}, status)
            if f["kind"] == "token_expired" and not request.headers.get("authorization", "").lower().startswith("basic "):
                if shape:
                    return shape("token_expired", 401, "The access token expired")
                return JSONResponse(
                    {"error": {"code": "invalid_token", "message": "The access token expired"}},
                    401,
                    headers={"WWW-Authenticate": 'Bearer error="invalid_token", error_description="The access token expired"'},
                )
        return await call_next(request)

    @staticmethod
    def _hit(system: str) -> list[dict]:
        with engine.begin() as conn:
            faults = active(conn, system)
            if faults:
                conn.execute(update(FAULTS).where(FAULTS.c.id.in_([f["id"] for f in faults])).values(calls=FAULTS.c.calls + 1))
                for f in faults:
                    f["calls"] += 1
        return faults
