import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from sim.core import clock, events, faults, scheduler, webhooks
from sim.core.config import get_settings
from sim.core.db import engine, ensure_schemas
from sim.core.mock import discover
from sim.core.registry import EXTRA_SYSTEMS, SYSTEMS
from sim.routes import admin, mcp_demo
from sim.seed import seed

log = logging.getLogger("sim")
MOCKS = discover()
STARTUP_ERRORS: dict[str, str] = {}  # system -> why its seed failed to load


async def _loop(name: str, fn, every: float) -> None:
    """Run fn every `every` seconds in a thread, forever; errors are logged, not fatal."""
    while True:
        try:
            await asyncio.to_thread(fn)
        except Exception:
            log.exception("%s failed", name)
        await asyncio.sleep(every)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schemas()
    with engine.begin() as conn:
        for mod in (events, clock, scheduler, webhooks, faults):
            mod.create(conn)
    # each mock loads in its own transaction: one that fails is reported in /health and skipped, not fatal
    STARTUP_ERRORS.clear()
    for sid, m in MOCKS.items():
        try:
            with engine.begin() as conn:
                m.ensure(conn, seed())
        except Exception as e:
            log.exception("mock %s failed to load", sid)
            STARTUP_ERRORS[sid] = f"{type(e).__name__}: {e}"[:500]
    with engine.begin() as conn:
        if get_settings().demo_faults and not faults.active(conn):
            faults.apply_demo(conn)
    tasks = []
    if get_settings().background:
        tasks = [
            asyncio.create_task(_loop("scheduler", scheduler.tick, 1.0)),
            asyncio.create_task(_loop("webhooks", webhooks.deliver, 1.0)),
        ]
    started = []  # mocks with their own servers (e.g. the Sims SFTP server)
    for sid, m in MOCKS.items():
        if m.startup is not None:
            try:
                started.append(await m.startup())
            except Exception as e:  # reported in /health, not fatal
                log.exception("mock %s failed to start", sid)
                STARTUP_ERRORS[sid] = f"startup: {type(e).__name__}: {e}"[:500]
    yield
    for s in started:
        with contextlib.suppress(Exception):
            s.close()
    for t in tasks:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t


app = FastAPI(title="Circularity source-sim", version="0.4.0", lifespan=lifespan)
app.add_middleware(faults.FaultMiddleware)
app.include_router(admin.router)
app.include_router(mcp_demo.router)  # POST /mcp-demo: a tiny MCP server for di's MCP client source (plan 8 MVP-11.7)
for _m in MOCKS.values():
    if _m.router is not None:
        app.include_router(_m.router, tags=[_m.title or _m.source_id])


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        schemas = set(conn.execute(text("SELECT schema_name FROM information_schema.schemata")).scalars())
        now = clock.now(conn)
    missing = [s.schema for s in (*SYSTEMS, *EXTRA_SYSTEMS) if s.schema not in schemas]
    from sim.core.mock import DISCOVERY_ERRORS

    return {
        "status": "ok" if not (missing or STARTUP_ERRORS or DISCOVERY_ERRORS) else "degraded",
        "failed_mocks": STARTUP_ERRORS | DISCOVERY_ERRORS,
        "systems": len(SYSTEMS),
        "missing_schemas": missing,
        "mocks": len(MOCKS),
        "sim_time": now.isoformat(),
    }


@app.get("/_sim/systems")
def systems() -> list[dict]:
    return [asdict(s) | {"implemented": s.source_id in MOCKS} for s in (*SYSTEMS, *EXTRA_SYSTEMS)]


@app.post("/_sim/reset")
def reset(system: str | None = None) -> dict:
    """Rebuild one system (?system=erp) or every implemented system from the seed. A full reset also resets the
    clock, clears scheduled work and re-applies the demo faults when SIM_DEMO_FAULTS is on; a per-system reset then
    re-applies only that system's demo faults and keeps the other systems' faults."""
    targets = [system] if system else list(MOCKS)
    unknown = [t for t in targets if t not in MOCKS]
    if unknown:
        raise HTTPException(404, f"No mock to reset for {unknown[0]!r}")
    out = {}
    with engine.begin() as conn:
        # scheduled work is cleared first, so a mock can schedule work as part of its reset (AWS IoT's telemetry)
        scheduler.clear(conn, targets)
        for t in targets:
            out[t] = MOCKS[t].reset(conn, seed())
        conn.execute(
            text("DELETE FROM sim.deliveries WHERE outbox_id IN (SELECT id FROM sim.outbox WHERE source = ANY(:s))"),
            {"s": targets},
        )
        conn.execute(text("DELETE FROM sim.outbox WHERE source = ANY(:s)"), {"s": targets})
        if system is None:
            clock.reset(conn)
        # tell subscribers: a reset rewinds the data (and, for a full reset, the clock), so their delta cursors are void
        for t in targets:
            events.emit(conn, t, "sim.reset", t, {"system": t, "clock_reset": system is None})
        if get_settings().demo_faults:  # a per-system reset leaves the other systems' faults alone (refactor R3)
            faults.apply_demo(conn, None if system is None else targets)
    return {"reset": out}
