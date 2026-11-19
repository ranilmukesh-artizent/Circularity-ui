from sqlalchemy import create_engine, text

from sim.config import get_settings
from sim.registry import SYSTEMS

engine = create_engine(get_settings().database_url, pool_pre_ping=True)


def ensure_schemas() -> None:
    """One Postgres schema per mocked system. Tables arrive in phase 1."""
    with engine.begin() as conn:
        for s in SYSTEMS:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{s.schema}"'))
