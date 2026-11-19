import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from sim import admin, clock, events, faults, scheduler, webhooks
from sim.config import get_settings
from sim.db import engine, ensure_schemas
from sim.mock import discover
from sim.registry import SYSTEMS
from sim.seed import seed

log = logging.getLogger("sim")
MOCKS = discover()


async def _loop(name: str, fn, every: float) -> None:
    """Run fn every `every` seconds in a thread, forever; errors are logged, not fatal."""
    while True:
        try:
            await asyncio.to_thread(fn)
        except Exception:  # noqa: BLE001
            log.exception("%s failed", name)
        await asyncio.sleep(every)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schemas()
    with engine.begin() as conn:
        for mod in (events, clock, scheduler, webhooks, faults):
            mod.create(conn)
        for m in MOCKS.values():
            m.ensure(conn, seed())
        if get_settings().demo_faults and not faults.active(conn):
            faults.apply_demo(conn)
    tasks = []
    if get_settings().background:
        tasks = [
            asyncio.create_task(_loop("scheduler", scheduler.tick, 1.0)),
            asyncio.create_task(_loop("webhooks", webhooks.deliver, 1.0)),
        ]
    yield
    for t in tasks:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t


app = FastAPI(title="Circularity source-sim", version="0.4.0", lifespan=lifespan)
app.add_middleware(faults.FaultMiddleware)
app.include_router(admin.router)
for _m in MOCKS.values():
    if _m.router is not None:
        app.include_router(_m.router, tags=[_m.title or _m.source_id])


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        schemas = set(conn.execute(text("SELECT schema_name FROM information_schema.schemata")).scalars())
        now = clock.now(conn)
    missing = [s.schema for s in SYSTEMS if s.schema not in schemas]
    return {
        "status": "ok" if not missing else "degraded",
        "systems": len(SYSTEMS),
        "missing_schemas": missing,
        "mocks": len(MOCKS),
        "sim_time": now.isoformat(),
    }


@app.get("/_sim/systems")
def systems() -> list[dict]:
    return [asdict(s) | {"implemented": s.source_id in MOCKS} for s in SYSTEMS]


@app.post("/_sim/reset")
def reset(system: str | None = None) -> dict:
    """Rebuild one system (?system=erp) or every implemented system from the seed. A full reset also resets the
    clock, clears scheduled work and re-applies the demo faults when SIM_DEMO_FAULTS is on."""
    targets = [system] if system else list(MOCKS)
    unknown = [t for t in targets if t not in MOCKS]
    if unknown:
        raise HTTPException(404, f"No mock to reset for {unknown[0]!r}")
    out = {}
    with engine.begin() as conn:
        for t in targets:
            out[t] = MOCKS[t].reset(conn, seed())
        conn.execute(
            text("DELETE FROM sim.deliveries WHERE outbox_id IN (SELECT id FROM sim.outbox WHERE source = ANY(:s))"),
            {"s": targets},
        )
        conn.execute(text("DELETE FROM sim.outbox WHERE source = ANY(:s)"), {"s": targets})
        scheduler.clear(conn, targets)
        if system is None:
            clock.reset(conn)
            if get_settings().demo_faults:
                faults.apply_demo(conn)
    return {"reset": out}
