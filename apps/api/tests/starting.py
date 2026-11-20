"""The demo's starting state, for tests that compare against the golden files.

`reset()` puts di back where a fresh copy of the demo starts: every case reopened from the engine's evaluation, the
workspace collections (events, notes, requests, accounts ...) back to their starting values, delegations on, no tenant
grants, and no journal, events, stage moves made by actions, instructions or queued jobs. Connector data (canonical
store, sync cursors) is left alone.

`strict()` (from tests/helpers.py) makes booleans compare strictly: Python's `==` treats True == 1, which hides real
differences.
"""

from sqlalchemy import text

from di import state
from di.cases import store
from di.db import engine
from tests.helpers import strict  # noqa: F401  (tests call starting.strict)


def reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE delegation SET enabled = true"))
        conn.execute(text("DELETE FROM tenant_grant"))
        conn.execute(text("DELETE FROM domain_event"))
        conn.execute(text("DELETE FROM case_stage_log WHERE seq IS NOT NULL"))
        conn.execute(text("DELETE FROM instruction"))
        conn.execute(text("DELETE FROM action_journal"))
        conn.execute(text("DELETE FROM job WHERE kind <> 'sync.source'"))
    store.reset()
    state.reset()
