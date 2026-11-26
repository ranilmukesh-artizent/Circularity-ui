"""The core returns mock's seed: five cores and the dealers' return history (pinned, no randomness)."""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.core_returns.models import CORE, DEALER_EVENT, metadata

ALL = {"housing_intact": True, "no_cracks": True, "complete": True, "family_match": True}


def _core(core_id: str, dealer: str, at: str, observed: str = "ALT-1450", **checks: bool) -> dict:
    return {
        "coreId": core_id, "dealerId": dealer, "declaredPartNumber": "ALT-1450", "observedPartNumber": observed,
        "deposit": 85, "checks": ALL | checks, "receivedAt": at,
    }  # fmt: skip


def cores() -> list[dict]:
    return [
        _core("C-0001", "D-02", "2026-11-03T09:00:00+00:00"),
        _core("C-0002", "D-02", "2026-11-04T09:00:00+00:00", complete=False),  # the bracket is missing
        _core("C-0003", "D-03", "2026-11-05T09:00:00+00:00", no_cracks=False),  # cracked
        _core("C-0004", "D-05", "2026-11-06T09:00:00+00:00", observed="STR-2210", family_match=False),  # a starter arrived
        _core("C-0005", "D-17", "2026-11-20T09:00:00+00:00"),  # clean, from a dealer with a history of rejects
    ]


def _event(core_id: str, dealer: str, outcome: str, at: str) -> dict:
    return {"dealerId": dealer, "coreId": core_id, "outcome": outcome, "at": at}


def dealer_history() -> list[dict]:
    """D-17: four rejects, one of them older than 90 days before C-0005's receipt, and one accepted return."""
    return [
        _event("C-0080", "D-17", "rejected", "2026-05-01T10:00:00+00:00"),
        _event("C-0090", "D-17", "rejected", "2026-09-10T10:00:00+00:00"),
        _event("C-0091", "D-17", "rejected", "2026-10-05T10:00:00+00:00"),
        _event("C-0092", "D-17", "rejected", "2026-11-02T10:00:00+00:00"),
        _event("C-0093", "D-17", "accepted", "2026-10-20T10:00:00+00:00"),
        _event("C-0070", "D-02", "rejected", "2026-08-01T10:00:00+00:00"),
        _event("C-0071", "D-02", "accepted", "2026-10-15T10:00:00+00:00"),
    ]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    cs, ev = cores(), dealer_history()
    conn.execute(insert(CORE), [{"core_id": c["coreId"], "doc": c} for c in cs])
    conn.execute(insert(DEALER_EVENT), [{"core_id": e["coreId"], "dealer_id": e["dealerId"], "doc": e} for e in ev])
    return {"core": len(cs), "dealer_event": len(ev)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS core_returns"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM core_returns.core")).scalar_one() == 0:
        load(conn, s)
