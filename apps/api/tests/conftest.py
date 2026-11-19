"""Tests run against a real Postgres (DI_DATABASE_URL), migrated to head.

In Docker:  docker compose run --rm api pytest
"""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from di.db import SessionLocal, engine


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
def session():
    with SessionLocal() as s:
        yield s


@pytest.fixture(autouse=True)
def clean_jobs():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE job RESTART IDENTITY"))
    yield
