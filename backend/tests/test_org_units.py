"""Org units (plan 8, MVP-1.1): the table and its seed.

The seeded ids equal the demo's tenant strings (fixtures/golden/world.json `tenants`), under one root `workspace`, so
`case_record.owner` keeps holding an org unit id and every tenant check reads the same values as before.
"""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from di.core.config import get_settings
from di.core.db import engine

SCRATCH = "di_org_units_test"
SEEDED = [
    ("Customer A", "workspace", "customer", "Customer A"),
    ("Customer B", "workspace", "customer", "Customer B"),
    ("Customer C", "workspace", "customer", "Customer C"),
    ("workspace", None, "group", "Workspace"),
]
SEEDED_IDS = ("workspace", "Customer A", "Customer B", "Customer C")


def _seeded_rows(eng) -> list[tuple]:
    with eng.connect() as conn:
        rows = conn.execute(
            text("SELECT id, parent_id, kind, name FROM org_unit WHERE id = ANY(:ids) ORDER BY id"),
            {"ids": list(SEEDED_IDS)},
        )
        return [tuple(r) for r in rows]


def test_seeded_org_units():
    assert _seeded_rows(engine) == SEEDED


def test_kind_is_checked():
    with pytest.raises(Exception, match="org_unit_kind"), engine.begin() as conn:
        conn.execute(text("INSERT INTO org_unit (id, parent_id, kind, name) VALUES ('x-bad', 'workspace', 'planet', 'X')"))


@pytest.fixture
def scratch_url():
    url = make_url(get_settings().database_url)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {SCRATCH}"))
    try:
        yield url.set(database=SCRATCH).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)"))
        admin.dispose()


def test_migration_round_trip(scratch_url):
    assert make_url(scratch_url).database == SCRATCH  # never the live database
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", scratch_url.replace("%", "%%"))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0017")
    command.upgrade(cfg, "head")
    eng = create_engine(scratch_url)
    try:
        assert _seeded_rows(eng) == SEEDED
    finally:
        eng.dispose()
