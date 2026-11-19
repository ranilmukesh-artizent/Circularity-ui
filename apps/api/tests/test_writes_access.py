"""B12: the access actions give the demo's results (fixtures/golden/writes.json): tenant-access requests, MCP
proposals, the Approver's delegations and the identity actions (directory, role mapping, out-of-office).

Each golden scenario ran in a fresh copy of the demo, so each starts here from the starting state (see
test_writes_decisions): cases reopened, workspace collections reseeded (requests, the accounts as mapped, the
directory), delegations on, no tenant grants, an empty journal. Every call is replayed over HTTP and compared exactly,
then every read the dump observed afterwards. The state is reset afterwards too, so a later test sees the original
accounts.

Tokens are issued once per account and kept across scenarios: the server looks the signed-in account up by id on
every request, so an identity mapping (access.mapIdentity) takes effect without signing in again, as in the demo.
"""

import pytest
from sqlalchemy import text

from di import golden, policy, state
from di.cases import store
from di.db import SessionLocal, engine
from tests.test_writes_decisions import Replay, _strict, call, client, h

WRITES = golden.load("writes")
SCENARIOS = ["tenant_access", "mcp_proposals", "delegation", "identity"]


def _reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE delegation SET enabled = true"))
        conn.execute(text("DELETE FROM tenant_grant"))
        conn.execute(text("DELETE FROM domain_event"))
        conn.execute(text("DELETE FROM case_stage_log WHERE seq IS NOT NULL"))
        conn.execute(text("DELETE FROM action_journal"))
    store.reset()
    state.reset()


@pytest.fixture
def fresh():
    _reset()
    yield
    _reset()


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario(fresh, name):
    sc, r = WRITES[name], Replay()
    for k, step in enumerate(sc["calls"]):
        r.check(step, f"{name} call {k}: {step['as']} {step['action']}")
    for k, step in enumerate(sc["observed"]):
        got = call(step["action"], step["input"], step["as"])
        exp = step["result"]
        if step["action"] == "access.lookup":
            # an unlimited approval limit: the dump's "Infinity" is null on the server (see test_reads_workspace)
            exp = {**exp, "output": {**exp["output"], "rows": [
                {**x, "limit": None if x["limit"] == "Infinity" else x["limit"]} for x in exp["output"]["rows"]]}}  # fmt: skip
        assert _strict(got) == _strict(exp), f"{name} read {k}: {step['as']} {step['action']} {step['input']}"


def test_mapping_changes_the_signed_in_account_and_reset_restores_it(fresh):
    """After a remap, the same token signs in as the changed account (scope, label); a reset restores it."""
    got = call("access.mapIdentity", {"acct": "planner-b", "field": "role", "value": "Warehouse Manager"}, "admin")
    assert got["output"] == {"acct": "planner-b", "label": "Warehouse Manager · Warehouse 2"}
    me = client.get("/api/auth/me", headers=h("planner-b")).json()
    assert me["account"]["role"] == "Warehouse Manager" and me["warehouse"] == "Warehouse 2"
    assert call("cases.list", {"limit": 1}, "planner-b")["ok"]
    _reset()
    me = client.get("/api/auth/me", headers=h("planner-b")).json()
    assert me["account"]["label"] == "Planner · Customer B" and me["warehouse"] is None


def test_planner_approves_once_the_limit_is_raised(fresh):
    """The demo's later can(): a Planner may approve once the Planner approval limit is above $0."""
    a = policy.account("planner-b")
    assert not policy.can(a, "approve")
    assert policy.can(a, "approve", policy.Context(limits={"Planner": 5000}))
    assert policy.limit_for(a, policy.Context(limits={"Planner": None})) == float("inf")


def test_approved_proposal_joins_the_mcp_servers(fresh):
    body = {
        "name": "Fleet telemetry",
        "owner": "Ops",
        "purpose": "Read run hours.",
        "tools": ["t"],
        "access": "read",
        "data": "d",
    }
    rid = call("mcp.propose", body, "developer")["output"]["id"]
    assert call("access.decideRequest", {"id": rid, "decision": "approve"}, "admin")["ok"]
    with SessionLocal() as s:
        ids = [x["id"] for x in state.items(s, "mcp_servers")]
    assert ids[-1] == f"prop-{rid}"
