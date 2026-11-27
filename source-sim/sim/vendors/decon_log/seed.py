"""The decontamination log mock's seed, synthetic and fixed (no randomness), and the scheduled cycles of the batch.

The pinned facts are in the package docstring. Cycles are placed against the rental system's returns (their check-in
times), read from sim.vendors.medical_rental_system.seed (pure functions: no database access across mocks).
"""

from datetime import datetime, timedelta

from sqlalchemy import insert, text, update
from sqlalchemy.engine import Connection

from sim.core import clock, events, scheduler
from sim.seed import Seed
from sim.vendors.decon_log.models import CYCLE, metadata
from sim.vendors.medical_rental_system import seed as rental

SOURCE = "mr_decon"
HANDLER = "decon_log.complete"
CYCLE_LENGTH = timedelta(hours=3)
BATCH_DELAY = timedelta(hours=6)  # the scheduled batch's records arrive this long after the seed is loaded
BEFORE_CHECK_IN = 5  # SYN-MR-IP-0005 (MR-S4): the record ended before the check-in
BATCH = range(20, 26)  # six returns without a record
ARRIVING = range(20, 24)  # four of them get one later; 0024 and 0025 never
ENHANCED = {10, 11}  # the isolation-ward returns


def _doc(cycle_id: str, tag: str, enhanced: bool, start: datetime, end: datetime) -> dict:
    return {
        "cycleId": cycle_id, "tag": tag, "method": "enhanced" if enhanced else "standard", "enhanced": enhanced,
        "cycleStartedAt": start.isoformat(), "cycleEndedAt": end.isoformat(),
        "operatorRef": f"OP-{int(tag[-4:]) % 4 + 1:02d}", "result": "pass",
    }  # fmt: skip


def pending_doc(cycle_id: str, tag: str, enhanced: bool, start: datetime, end: datetime) -> dict:
    """The document of a cycle that has not ended yet (listed only once it has)."""
    return _doc(cycle_id, tag, enhanced, start, end)


def finished() -> list[dict]:
    """The cycles that are finished from the start: one per return, but the batch (and none for no one else). The pumps'
    cycles are `DC-<n>`; another device's (the patient monitor SYN-MR-PM-0007) `DC-<900 + n>`, one standard cycle: a plain
    number, as the POST route's next id counts on, below the route's own DC-1001 on."""
    out = []
    for r in rental.returns():
        n = int(r["tag"][-4:])
        if not r["tag"].startswith("SYN-MR-IP-"):
            start = datetime.fromisoformat(r["checkedInAt"]) + timedelta(minutes=30)
            out.append(_doc(f"DC-{900 + n:04d}", r["tag"], False, start, start + CYCLE_LENGTH))
            continue
        if n in BATCH:
            continue
        check_in = datetime.fromisoformat(r["checkedInAt"])
        if n == BEFORE_CHECK_IN:
            end = check_in - timedelta(hours=6)  # cleaned before it came back
            start = end - CYCLE_LENGTH
        else:
            start = check_in + timedelta(minutes=30)
            end = start + CYCLE_LENGTH
        out.append(_doc(f"DC-{n:04d}", r["tag"], n in ENHANCED, start, end))
    return out


def _row(doc: dict, status: str, updated_at: datetime) -> dict:
    return {
        "cycle_id": doc["cycleId"], "tag": doc["tag"], "status": status,
        "ended_at": datetime.fromisoformat(doc["cycleEndedAt"]), "updated_at": updated_at, "doc": doc,
    }  # fmt: skip


def _schedule(conn: Connection, doc: dict) -> None:
    scheduler.schedule(conn, datetime.fromisoformat(doc["cycleEndedAt"]), HANDLER, {"cycleId": doc["cycleId"]}, SOURCE)


@scheduler.handler(HANDLER)
def complete(conn: Connection, payload: dict) -> None:
    """The cycle ends: list it, stamp the change, tell subscribers."""
    now = clock.now(conn)
    doc = conn.execute(
        text("SELECT doc FROM decon_log.cycle WHERE cycle_id = :c AND status = 'scheduled' FOR UPDATE"), {"c": payload["cycleId"]}
    ).scalar()
    if doc is None:  # already completed (a reset replays nothing twice)
        return
    conn.execute(update(CYCLE).where(CYCLE.c.cycle_id == doc["cycleId"]).values(status="done", updated_at=now))
    data = {"cycleId": doc["cycleId"], "tag": doc["tag"], "enhanced": doc["enhanced"], "result": doc["result"]}
    events.emit(conn, SOURCE, "decon.cycle.completed", doc["cycleId"], data, now)


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    done = finished()
    conn.execute(insert(CYCLE), [_row(d, "done", clock.AS_OF) for d in done])  # as old as the simulated clock
    now = clock.now(conn)
    end = now + BATCH_DELAY
    batch = [_doc(f"DC-{n:04d}", rental.tag(n), False, end - CYCLE_LENGTH, end) for n in ARRIVING]
    conn.execute(insert(CYCLE), [_row(d, "scheduled", now) for d in batch])
    for d in batch:
        _schedule(conn, d)
    return {"cycle": len(done), "scheduled": len(batch)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS decon_log"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM decon_log.cycle")).scalar_one() == 0:
        load(conn, s)
        return
    pending = conn.execute(
        text("SELECT count(*) FROM sim.scheduled WHERE handler = :h AND NOT done"), {"h": HANDLER}
    ).scalar_one()
    open_docs = conn.execute(text("SELECT doc FROM decon_log.cycle WHERE status = 'scheduled'")).scalars().all()
    if open_docs and not pending:  # scheduled work was cleared by a full reset of another kind
        for d in open_docs:
            _schedule(conn, d)
