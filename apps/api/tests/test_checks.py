"""B14: the data checks (GET /api/checks) give the demo's runInvariants() results, for all 11 accounts
(fixtures/golden/screens/checks.json, from apps/web/scripts/golden/analytics_audit.mjs; the Admin's list is also in
figures.json → invariants), and they all pass on the starting state.

The demo's checks that test the browser page itself (its buttons and handlers, and the rule-based agent's intent and
safety tests) cannot run on the backend; the endpoint lists them under not_run, and every other check must match the
demo's name, result and detail exactly.
"""

import os

import pytest
from fastapi.testclient import TestClient

from di import golden
from di.main import app
from tests import starting

client = TestClient(app)
G = golden.load("screens/checks")
FIGURES = golden.load("figures")
_tokens: dict[str, dict] = {}


@pytest.fixture(scope="module", autouse=True)
def _start():
    if os.environ.get("B14_PARALLEL") != "1":
        starting.reset()


def h(user: str) -> dict:
    if user not in _tokens:
        r = client.post("/api/auth/login", json={"username": user, "password": "x"})
        assert r.status_code == 200, r.text
        _tokens[user] = {"Authorization": "Bearer " + r.json()["access_token"]}
    return _tokens[user]


@pytest.mark.parametrize("acct", list(G["accounts"]))
def test_checks_match_the_demo(acct):
    r = client.get("/api/checks", headers=h(acct))
    assert r.status_code == 200, r.text
    out = r.json()
    not_run = {x["name"] for x in out["not_run"]}
    golden_names = [x["name"] for x in G["accounts"][acct]]
    assert not_run <= set(golden_names)
    want = [x for x in G["accounts"][acct] if x["name"] not in not_run]
    got = [{k: v for k, v in x.items() if k != "data"} for x in out["checks"]]
    assert starting.strict(got) == starting.strict(want)
    assert len(got) + len(not_run) == len(golden_names)
    assert out["passed"] == out["total"] == len(got)


def test_admin_list_is_the_b1_figures():
    assert G["accounts"]["admin"] == FIGURES["invariants"]


def test_what_each_check_reads():
    out = client.get("/api/checks", headers=h("admin")).json()
    assert {x["data"] for x in out["checks"]} == {"cases", "decisions", "catalog", "journal"}
    assert len(out["checks"]) == 27 and len(out["not_run"]) == 4  # B16b runs the safety and intent-catalogue checks


def test_needs_sign_in():
    assert client.get("/api/checks").status_code == 401
