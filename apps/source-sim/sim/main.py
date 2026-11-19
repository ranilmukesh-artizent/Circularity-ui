from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from sim import events
from sim.ariba import api as ariba_api
from sim.ariba import seed as ariba_seed
from sim.db import engine, ensure_schemas
from sim.registry import SYSTEMS
from sim.s4 import api as s4_api
from sim.s4 import seed as s4_seed
from sim.seed import seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schemas()
    with engine.begin() as conn:
        events.create(conn)
        s4_seed.ensure(conn, seed())
        ariba_seed.ensure(conn, seed())
    yield


app = FastAPI(title="Circularity source-sim", version="0.2.0", lifespan=lifespan)
app.include_router(s4_api.router, tags=["SAP S/4HANA"])
app.include_router(ariba_api.router, tags=["SAP Ariba"])

RESETTERS = {"erp": s4_seed.reset, "proc": ariba_seed.reset}


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        schemas = set(conn.execute(text("SELECT schema_name FROM information_schema.schemata")).scalars())
    missing = [s.schema for s in SYSTEMS if s.schema not in schemas]
    return {"status": "ok" if not missing else "degraded", "systems": len(SYSTEMS), "missing_schemas": missing}


@app.get("/_sim/systems")
def systems() -> list[dict]:
    return [asdict(s) | {"implemented": s.source_id in RESETTERS} for s in SYSTEMS]


@app.post("/_sim/reset")
def reset(system: str | None = None) -> dict:
    """Rebuild one system (?system=erp) or every implemented system from the seed."""
    targets = [system] if system else list(RESETTERS)
    unknown = [t for t in targets if t not in RESETTERS]
    if unknown:
        raise HTTPException(404, f"No mock to reset for {unknown[0]!r}")
    out = {}
    with engine.begin() as conn:
        for t in targets:
            out[t] = RESETTERS[t](conn, seed())
        conn.execute(text("DELETE FROM sim.outbox WHERE source = ANY(:s)"), {"s": targets})
    return {"reset": out}
