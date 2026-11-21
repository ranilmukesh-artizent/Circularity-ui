"""Tests run against a real Postgres (DI_DATABASE_URL), migrated to head.

In Docker:  docker compose run --rm api pytest

The suite runs on the demo's pinned clock and does not send instructions to the systems, whatever the container's
environment says (the running services set DI_CLOCK=sim and DI_INSTRUCTIONS=true in docker-compose.yml): the parity
tests depend on the demo's as-of time and on acknowledgements being the demo's simulated ones. A test that exercises
the real loop turns both on for itself (tests/test_milestone_rt1048.py).
"""

import os

os.environ["DI_CLOCK"] = "pinned"  # before di is imported: settings are read once
os.environ["DI_INSTRUCTIONS"] = "false"
os.environ["DI_WORKFLOW_TRIGGERS"] = "false"  # plan 6 C6: no triggered runs (test_triggers turns them on)
os.environ["DI_SOURCE_RETRY_BASE_SECONDS"] = "0.01"  # plan 6 A6: source GET retries wait 10, 20, 40 ms in the suite

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


@pytest.fixture
def client():
    """The shared in-process client (tests/helpers.py)."""
    from tests import helpers

    return helpers.client


@pytest.fixture
def login():
    """`login(user)` -> the Authorization header for that demo account, signed in once per session."""
    from tests import helpers

    return helpers.h


@pytest.fixture(autouse=True)
def clean_jobs():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE job RESTART IDENTITY"))
    return
