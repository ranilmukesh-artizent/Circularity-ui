"""B14: the MCP & Tools page's reads give the demo's answers (fixtures/golden/screens/mcp.json), for every account.

All of it is demo configuration and state, so everything is compared exactly: the tools and hard rules, the agents,
the permission matrix for every tenant, the call log (with which cases this account may open), the MCP servers and
the proposals (with which ones this account may decide). Each section needs its section of the MCP page; the others
get 403 out_of_scope.
"""

import os

import pytest
from fastapi.testclient import TestClient

from di import golden
from di.main import app
from tests import starting

client = TestClient(app)
G = golden.load("screens/mcp")
ACCOUNTS = list(G["accounts"])
_tokens: dict[str, dict] = {}
SECTIONS = {
    "tools": "catalog",
    "agents": "agents",
    "matrix": "perms",
    "calls": "calls",
    "client": "client",
    "proposals": "proposals",
}


def setup_module():
    if os.environ.get("B14_PARALLEL") != "1":
        starting.reset()


def h(user: str) -> dict:
    if user not in _tokens:
        r = client.post("/api/auth/login", json={"username": user, "password": "x"})
        assert r.status_code == 200, r.text
        _tokens[user] = {"Authorization": "Bearer " + r.json()["access_token"]}
    return _tokens[user]


def get(acct: str, path: str, **params):
    """The answer, or None when the account may not see that section (checked to be a 403 out_of_scope)."""
    r = client.get(f"/api/screens/mcp/{path}", params=params, headers=h(acct))
    secs = G["accounts"][acct]["pages"]["mcp"] or []
    if SECTIONS[path] not in secs:
        assert r.status_code == 403 and r.json()["detail"]["code"] == "out_of_scope", r.text
        return None
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_tools_and_agents(acct):
    if (got := get(acct, "tools")) is not None:
        assert got == {"tools": G["tools"], "hard_rules": G["hard_rules"]}
    if (got := get(acct, "agents")) is not None:
        assert got == {"agents": G["agents"]}


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_matrix(acct):
    for tenant, rows in G["matrix"].items():
        got = get(acct, "matrix", tenant=tenant)
        if got is None:
            return
        assert got["tenant"] == tenant and got["tools"] == [t["id"] for t in G["tools"]]
        assert got["rows"] == rows


def test_matrix_unknown_tenant():
    assert client.get("/api/screens/mcp/matrix", params={"tenant": "Customer Z"}, headers=h("admin")).status_code == 404


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_calls(acct):
    got = get(acct, "calls")
    if got is None:
        return
    want = [c | {"openable": ok} for c, ok in zip(G["calls"], G["accounts"][acct]["calls_openable"], strict=True)]
    assert starting.strict(got["calls"]) == starting.strict(want)
    assert got["held"] == [c for c in want if c["outcome"] == "held for approval"][:4]
    assert got["counts"]["total"] == len(G["calls"])
    issues = get(acct, "calls", filter="issues", limit=30)
    assert issues["calls"] == [c for c in want if c["outcome"] != "ok"][:30]


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_client_and_proposals(acct):
    if (got := get(acct, "client")) is not None:
        assert got == {"servers": G["client_servers"]}
    if (got := get(acct, "proposals")) is not None:
        can = G["accounts"][acct]["can_decide"]
        want = [r | {"can_decide": can[r["id"]]} for r in golden.load("screens/access")["requests"] if r["kind"] == "mcp"]
        assert starting.strict(got["proposals"]) == starting.strict(want)


def test_some_account_sees_each_section_and_some_does_not():
    for sec in SECTIONS.values():
        seen = [a for a in ACCOUNTS if sec in (G["accounts"][a]["pages"]["mcp"] or [])]
        assert 0 < len(seen) < len(ACCOUNTS)
    # the call log's case links differ by account (tenant boundary and warehouse lock)
    assert len({tuple(G["accounts"][a]["calls_openable"]) for a in ACCOUNTS}) > 1
