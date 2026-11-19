from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from sim import events
from sim.db import engine, ensure_schemas
from sim.mock import discover
from sim.registry import SYSTEMS
from sim.seed import seed

MOCKS = discover()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schemas()
    with engine.begin() as conn:
        events.create(conn)
        for m in MOCKS.values():
            m.ensure(conn, seed())
    yield


app = FastAPI(title="Circularity source-sim", version="0.3.0", lifespan=lifespan)
for _m in MOCKS.values():
    if _m.router is not None:
        app.include_router(_m.router, tags=[_m.title or _m.source_id])


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        schemas = set(conn.execute(text("SELECT schema_name FROM information_schema.schemata")).scalars())
    missing = [s.schema for s in SYSTEMS if s.schema not in schemas]
    return {"status": "ok" if not missing else "degraded", "systems": len(SYSTEMS), "missing_schemas": missing}


@app.get("/_sim/systems")
def systems() -> list[dict]:
    return [asdict(s) | {"implemented": s.source_id in MOCKS} for s in SYSTEMS]


@app.post("/_sim/reset")
def reset(system: str | None = None) -> dict:
    """Rebuild one system (?system=erp) or every implemented system from the seed."""
    targets = [system] if system else list(MOCKS)
    unknown = [t for t in targets if t not in MOCKS]
    if unknown:
        raise HTTPException(404, f"No mock to reset for {unknown[0]!r}")
    out = {}
    with engine.begin() as conn:
        for t in targets:
            out[t] = MOCKS[t].reset(conn, seed())
        conn.execute(text("DELETE FROM sim.outbox WHERE source = ANY(:s)"), {"s": targets})
    return {"reset": out}
