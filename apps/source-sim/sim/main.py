from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI
from sqlalchemy import text

from sim.db import engine, ensure_schemas
from sim.registry import SYSTEMS


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schemas()
    yield


app = FastAPI(title="Circularity source-sim", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        schemas = set(
            conn.execute(text("SELECT schema_name FROM information_schema.schemata")).scalars()
        )
    missing = [s.schema for s in SYSTEMS if s.schema not in schemas]
    return {"status": "ok" if not missing else "degraded", "systems": len(SYSTEMS), "missing_schemas": missing}


@app.get("/_sim/systems")
def systems() -> list[dict]:
    return [asdict(s) for s in SYSTEMS]
