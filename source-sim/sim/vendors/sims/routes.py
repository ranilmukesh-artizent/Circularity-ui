"""The drop's admin view over HTTP (not part of the partner's interface: Sims offers SFTP only), plus ensure/reset."""

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.engine import Connection

from sim.core import clock
from sim.seed import Seed, seed
from sim.vendors.sims import drop, sftp

router = APIRouter(prefix="/sims/admin")


def ensure(conn: Connection, s: Seed) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS sims"))  # nothing is kept in it: the drop is the files
    if not drop.exists():
        drop.publish(s)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS sims"))
    return {"files": drop.publish(s)}


@router.get("/outbound")
def list_files() -> dict:
    return {
        "partner": "Sims Lifecycle Services",
        "sftp": {
            "port": sftp.port(),
            "user": sftp.USER,
            "directory": "/" + drop.OUTBOUND,
            "hostKey": " ".join(sftp.HOST_KEY),
        },
        "files": drop.listing(),
    }


@router.get("/outbound/{name}")
def get_file(name: str) -> Response:
    data = drop.read(name)
    if data is None:
        raise HTTPException(404, f"No file {name!r} in /outbound")
    media = "text/csv" if name.endswith(".csv") else "application/json" if name.endswith(".json") else "text/plain"
    return Response(data, media_type=media)


@router.put("/outbound/{name}")
async def put_file(name: str, request: Request) -> dict:
    """Replace a file as is, without signing it again: a tampered or corrupted file (tests, demos)."""
    try:
        drop.put(name, await request.body(), clock.now())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"fileName": name, "signed": False}


@router.post("/publish")
def publish() -> dict:
    """The partner publishes the drop again (same data, signed again), stamped with the simulated time."""
    at = clock.now()
    return {"files": drop.publish(seed(), at), "publishedAt": at.isoformat()}


@router.post("/regenerate")
def regenerate() -> dict:
    """Rebuild the seed drop (as /_sim/reset?system=rcy, without the reset event)."""
    return {"files": drop.publish(seed())}
