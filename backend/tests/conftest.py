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
from pydantic_ai import models
from sqlalchemy import text

from di.core.db import SessionLocal, engine

# No test reaches a provider. The dev database may hold a real key (the model-first readers, flow_reader and Ask, find it); any
# model call a test did not fake now fails closed and the caller's deterministic path answers. The one deliberately live test
# (test_ask.py::test_live_groq_...) turns it back on for itself with monkeypatch.
models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture(autouse=True)
def no_model_waits(monkeypatch):
    """A model-first caller waits (up to 20 and 60 s) for a model cooling down in the shared dev database; tests never sleep."""
    from di.services.agents.playbooks import flow_reader
    from di.services.ask import model as ask_model

    monkeypatch.setattr(flow_reader, "WAIT_FOR_MODEL", 0)
    monkeypatch.setattr(ask_model, "WAIT_FOR_MODEL", 0)


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


@pytest.fixture
def no_synced_conflicts(monkeypatch):
    """Plan 9 (P9-2.4): the hold policy holds a `limits` stage's write when the case's asset has an open conflict. On a
    stack whose Connection Fabric has synced, the demo assets (RT-1048's included) have hundreds of open conflicts; on
    a fresh database they have none. Tests about the agent chain's order, records or traces, not about holds, use this
    fixture (`pytestmark = pytest.mark.usefixtures("no_synced_conflicts")`) so they give the same answer on both; the
    open-exception half of the case state stays real. test_hold_policy covers conflict holds through evaluate_hold."""
    from di.services.actions import hold

    real = hold._case_state
    monkeypatch.setattr(hold, "_case_state", lambda *a, **k: (real(*a, **k)[0], False))


@pytest.fixture
def no_synced_demand(monkeypatch):
    """Plan 9 (P9-3.12): every open tool-fleet case reads the live named demand of the `fleet` and `parts` sources
    (di.repositories.tool_demand), whose records carry no org unit and so reach every org. On a stack whose Connection Fabric
    has synced, the fleet mock's renewals (FC-30101-R and others) are offered to every case and change the queue plan; on a
    fresh database there are none. Tests about the queue plan or the panel's own orders use this fixture
    (`pytestmark = pytest.mark.usefixtures("no_synced_demand")`) so they give the same answer on both: the demand records
    that exist when the test starts are not offered, and the rows the test seeds itself are."""
    from di.repositories import tool_demand

    with SessionLocal() as s:
        synced = set(s.execute(text("SELECT key FROM canonical WHERE model = 'demand'")).scalars())
    real = tool_demand.named_demand

    def named_demand(*a, **k):
        d = real(*a, **k)
        proj = d.get("proj")
        return d | {
            "lease": [x for x in d["lease"] if x["id"] not in synced],
            "so": [x for x in d["so"] if x["id"] not in synced],
            "bid": [x for x in d["bid"] if x["id"] not in synced],
            "proj": None if proj and proj["id"] in synced else proj,
            "wo": {p: [x for x in xs if x["id"] not in synced] for p, xs in d["wo"].items()},
        }

    monkeypatch.setattr(tool_demand, "named_demand", named_demand)
