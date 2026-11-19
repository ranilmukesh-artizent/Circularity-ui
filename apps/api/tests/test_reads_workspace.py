"""B11: the workspace reads give the demo's answers (fixtures/golden/reads.json), for all 11 accounts.

inbox.get, receiving.plan, access.lookup (4 inputs) and kpi.explain (7 figures), called over HTTP as the frontend
does, from the starting state (cases reopened, delegations on, no tenant grants).

The golden file went through the dump script's `plain()`: numbers rounded to 1e-6 and non-finite numbers written as
strings. The comparison applies the same rounding to the server's answer. One difference is by design: an unlimited
approval limit is the demo's Infinity, which the dump wrote as "Infinity" and which JSON has no number for; the server
sends null (what the demo's own JSON.stringify writes), so the expected "Infinity" is read as null.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from di import golden
from di.cases import store
from di.db import engine
from di.engine.jsmath import js_round
from di.main import app

client = TestClient(app)
READS = golden.load("reads")
ACTIONS = ("inbox.get", "receiving.plan", "access.lookup", "kpi.explain")
_tokens: dict[str, dict] = {}


def h(user: str) -> dict:
    if user not in _tokens:
        r = client.post("/api/auth/login", json={"username": user, "password": "x"})
        assert r.status_code == 200, r.text
        _tokens[user] = {"Authorization": "Bearer " + r.json()["access_token"]}
    return _tokens[user]


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
    store.reset()


def _plain(x):
    """The dump's normalisation, applied to the server's answer: floats to 1e-6. Booleans are tagged so they only
    equal booleans (Python's == takes True for 1; JSON does not)."""
    if isinstance(x, bool):
        return ("bool", x)
    if isinstance(x, float):
        return js_round(x * 1e6) / 1e6
    if isinstance(x, int):
        return x
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_plain(v) for v in x]
    return x


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
    got = call(action, body, acct)
    assert _plain(got) == _plain(_expected(expected))


def test_every_golden_read_is_covered():
    assert len(READS["other_reads"]) == 11
    assert len(READS_UNDER_TEST) == 11 * (1 + 1 + 4 + 7)
