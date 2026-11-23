"""The demo's starting state, for tests that compare against the golden files.

`reset()` puts di back where a fresh copy of the demo starts: every case reopened from the engine's evaluation, the
workspace collections (events, notes, requests, accounts ...) back to their starting values, delegations on, no tenant
grants, and no journal, events, stage moves made by actions, instructions or queued jobs. Sources created in the
Connection Fabric are removed and the demo's sources get back their starting status and description
(di.connectors.sync.reset_sources); their connector data (canonical store, sync cursors) is left alone.

`strict()` (from tests/helpers.py) makes booleans compare strictly: Python's `==` treats True == 1, which hides real
differences.
"""

from sqlalchemy import text

from di.connectors.sync import reset_sources
from di.core import state
from di.core.db import engine
from di.services.cases import store
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
        # plan 8 phase 11: the demo's nine agents only, all started (the kill switch is also kept in "agents_off")
        conn.execute(text("DELETE FROM agent_identity WHERE kind <> 'internal'"))
        conn.execute(text("UPDATE agent_identity SET enabled = true"))
        reset_sources(conn)
    store.reset()
    state.reset()
