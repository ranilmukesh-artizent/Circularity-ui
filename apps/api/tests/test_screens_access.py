"""B14: the Access page's reads give the demo's answers (fixtures/golden/screens/access.json), for every account.

Everything on the page is at parity with the demo's starting state: accounts, directory, delegations, requests (with
which ones this account may decide), autonomy, limits, agents and metrics. Only an account with the Access page sees
it; the others get 403 out_of_scope.

One field is left out of the comparison: the demo's accounts carry `homeClassic` (the landing page of the classic,
pre-React layout), which the backend's accounts (policy.Account) do not hold and the Access page does not show.
"""

import os

import pytest
from fastapi.testclient import TestClient

from di import golden
from di.main import app
from tests import starting

client = TestClient(app)
G = golden.load("screens/access")
ACCOUNTS = list(G["accounts"])
_tokens: dict[str, dict] = {}


def setup_module():
    if os.environ.get("B14_PARALLEL") != "1":
        starting.reset()


def h(user: str) -> dict:
    if user not in _tokens:
        r = client.post("/api/auth/login", json={"username": user, "password": "x"})
        assert r.status_code == 200, r.text
        _tokens[user] = {"Authorization": "Bearer " + r.json()["access_token"]}
    return _tokens[user]


def expected(acct: str) -> dict:
    secs = G["accounts"][acct]["pages"]["access"]
    can = G["accounts"][acct]["can_decide"]
    out = {
        "accounts": [r | {"account": {k: v for k, v in r["account"].items() if k != "homeClassic"}} for r in G["account_rows"]],
        "identity": {
            "src": G["idp"]["src"],
            "lastSync": G["idp"]["lastSync"],
            "ooo": G["idp"]["ooo"],
            "groups": G["idp"]["groups"],
            "users": [u | {"role": G["idp_user_roles"][u["id"]]} for u in G["idp"]["users"]],
            "roles": G["idp_roles"],
        },
        "delegations": G["delegations"],
        "requests": {
            "requests": [r | {"can_decide": can[r["id"]]} for r in G["requests"]],
            "inbox": G["accounts"][acct]["inbox_requests"],
        },
        "autonomy": {"levels": G["levels"], "types": G["auto_types"], "matrix": G["autonomy"]},
        "limits": {"limits": G["limits"], "self_approve": G["self_approve"], "run_limits": G["run_limits"]},
        "agentsx": {"agents": G["agents"], "hard_rules": G["hard_rules"]},
        "metrics": G["metrics"],
    }
    return {"sections": secs} | {k: out[k] for k in secs}


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_access_page(acct):
    r = client.get("/api/screens/access", headers=h(acct))
    if not G["accounts"][acct]["pages"]["access"]:
        assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope"
        return
    assert r.status_code == 200, r.text
    assert starting.strict(r.json()) == starting.strict(expected(acct))


def test_every_account_and_section_covered():
    assert len(ACCOUNTS) == 11
    assert [a for a in ACCOUNTS if G["accounts"][a]["pages"]["access"]] == ["admin"]
    assert len(G["accounts"]["admin"]["pages"]["access"]) == 8
