"""B11: the workspace reads give the demo's answers (fixtures/golden/reads.json), for all 11 accounts.

inbox.get, receiving.plan, access.lookup (4 inputs) and kpi.explain (7 figures), called over HTTP as the frontend
does, from the starting state (cases reopened, delegations on, no tenant grants).

The golden file went through the dump script's `plain()`: numbers rounded to 1e-6 and non-finite numbers written as
strings. The comparison applies the same rounding to the server's answer. One difference is by design: an unlimited
approval limit is the demo's Infinity, which the dump wrote as "Infinity" and which JSON has no number for; the server
sends null (what the demo's own JSON.stringify writes), so the expected "Infinity" is read as null.
"""

import pytest
from sqlalchemy import text

from di import golden, state
from di.cases import store
from di.db import engine
from tests.helpers import client, h, norm, with_live_inbox

READS = golden.load("reads")
ACTIONS = ("inbox.get", "receiving.plan", "access.lookup", "kpi.explain")


def call(action: str, body: dict, user: str) -> dict:
    r = client.post(f"/api/actions/{action}", json=body, headers=h(user))
    out = r.json()
    if out.get("ok"):
        return {"ok": True, "output": out["output"]}
    return {"ok": False, "error": out["error"]}


def setup_module():
    with engine.begin() as conn:
        conn.execute(text("UPDATE delegation SET enabled = true"))
        conn.execute(text("DELETE FROM tenant_grant"))
        # the starting state has an empty journal: the case run reads who acted from it
        conn.execute(text("DELETE FROM domain_event"))
        conn.execute(text("DELETE FROM case_stage_log WHERE seq IS NOT NULL"))
        conn.execute(text("DELETE FROM action_journal"))
    store.reset()
    state.reset()  # the workspace collections (events, notes ...) back to their starting values


def _expected(x):
    """The golden answer, with "Infinity" (an unlimited approval limit) read as null; see the module docstring."""
    if x == "Infinity":
        return None
    if isinstance(x, dict):
        return {k: _expected(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_expected(v) for v in x]
    return x


READS_UNDER_TEST = [
    pytest.param(acct, x["action"], x["input"], x["result"], id=f"{acct}-{x['action']}-{k}")
    for acct, reads in READS["other_reads"].items()
    for k, x in enumerate(reads)
    if x["action"] in ACTIONS
]


@pytest.mark.parametrize(("acct", "action", "body", "expected"), READS_UNDER_TEST)
def test_workspace_read(acct, action, body, expected):
    """The Developer's inbox (inbox.get) is the demo's but its stale or unconnected sources (decision-log D-Fabric):
    its Source-map items and its briefing's sources line read the live Connection Fabric, as Home's briefing does."""
    got = call(action, body, acct)
    want = _expected(expected)
    if acct == "developer" and action == "inbox.get":
        want = {**want, "output": with_live_inbox(want["output"], got["output"])}
    assert norm(got) == norm(want)


def test_every_golden_read_is_covered():
    assert len(READS["other_reads"]) == 11
    assert len(READS_UNDER_TEST) == 11 * (1 + 1 + 4 + 7)
