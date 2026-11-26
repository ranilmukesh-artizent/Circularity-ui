"""The disposal partner mock's seed: nothing. Collections and sanitisations arrive through the POST routes."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.disposal_partner.models import metadata


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS disposal_partner"))
    metadata.create_all(conn)


def reset(conn: Connection, _s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return {"collection": 0, "sanitisation": 0}


def ensure(conn: Connection, _s: Seed) -> None:
    create(conn)
