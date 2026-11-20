"""B14: the reference lists (GET /api/screens/reference) are the demo's constants, the same for everyone, and agree with
the other golden files and the backend's own copies of them; the menu (GET /api/screens/nav) is the one each account
sees in the demo (fixtures/golden/screens/nav.json), with its badges and task count.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from di import golden, policy
from di.db import engine
from di.main import app
from di.reads import common, workspace
from di.screens import checks
from di.screens.nav import ISSUE_SQL
from tests import starting

client = TestClient(app)
REF = golden.load("screens/reference")
NAV = golden.load("screens/nav")
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


# ---------------------------------------------------------------- reference
def test_reference_is_the_demos_constants():
    r = client.get("/api/screens/reference")  # the sign-in page reads it before anyone signs in
    assert r.status_code == 200
    assert starting.strict(r.json()) == starting.strict(REF)
    for acct in ("planner-b", "wm-1", "admin"):
        assert client.get("/api/screens/reference", headers=h(acct)).json() == r.json()


def test_reference_by_name():
    r = client.get("/api/screens/reference", params={"names": "MONTHS, ROUTES"})
    assert r.json() == {"MONTHS": REF["MONTHS"], "ROUTES": REF["ROUTES"]}
    r = client.get("/api/screens/reference", params={"names": "MONTHS,NOPE"})
    assert r.status_code == 404


def test_reference_agrees_with_the_other_golden_files():
    world, pol, tools = golden.load("world"), golden.load("policy"), golden.load("tools")
    for name, key in [("MONTHS", "months"), ("TENANTS", "tenants"), ("SITES", "sites"), ("FACILITIES", "facilities"),
                      ("ROUTES", "routes"), ("MODELS", "models"), ("GATES", "gates"), ("CLASSES", "classes"),
                      ("AS_OF", "as_of")]:  # fmt: skip
        assert REF[name] == world[key], name
    assert REF["ROLE_POLICY"] == pol["role_policy"]
    assert REF["PERM_ALIAS"] == pol["perm_alias"]
    assert REF["RB_SECS"] == pol["sections"]
    assert REF["TOOLS"] == tools["tools"]
    assert REF["HARD_RULES"] == tools["hard_rules"]
    assert REF["CANON"] == golden.load("canonical")["models"]
    assert REF["SRC_TYPES"] == golden.load("sources")["types"]


def test_reference_agrees_with_the_backends_copies():
    assert REF["CC_CAP"] == workspace.CC_CAP
    assert REF["CC_REASONS"] == workspace.CC_REASONS
    assert REF["EX_FX"] == common.EX_FX
    assert REF["RISK_LABEL"] == checks.RISK_LABEL
    assert REF["REQ_KIND"] == common.REQ_KIND
    assert {k: round(v, 6) for k, v in workspace.cc_est_per_unit().items()} == REF["CC_EST"]
    assert REF["JSTEPS"] == REF["JSTEPS_AF"] and REF["JMAP"][:11] == [0, 5, 6, 6, 6, 7, 8, 8, 8, 9, 10]


def test_reference_has_no_state():
    """State and per-account data are served by each area's endpoints, assets are bundled with the app."""
    for name in ("ACCOUNTS", "AGENTS", "CLIENT_SERVERS", "MAPPINGS", "SOURCES", "CONFLICTS", "EVENTS", "CALLS", "EXPECTED",
                 "POOLS", "ROWS", "CASE_BY_ID", "ACTIONS", "AF", "S", "ICON", "LOGO", "LOGO_INK"):  # fmt: skip
        assert name not in REF


# ---------------------------------------------------------------- the menu
@pytest.mark.parametrize("acct", list(NAV["accounts"]))
def test_navigation(acct):
    r = client.get("/api/screens/nav", headers=h(acct))
    assert r.status_code == 200, r.text
    out, want = r.json(), NAV["accounts"][acct]
    assert starting.strict(out["groups"]) == starting.strict(want["navigation"])
    assert out["tasks"] == want["tasks"]
    b, wb = out["badges"], want["badges"]
    assert {k: b[k] for k in ("awaiting", "inbox", "integration")} == {k: wb[k] for k in ("awaiting", "inbox", "integration")}
    assert {k: b["sections"][k] for k in ("conf", "inbox", "wffail")} == {
        k: wb["sections"][k] for k in ("conf", "inbox", "wffail")
    }
    # sources stale or unavailable: the connectors' real state, not the demo's. It changes as sources sync (the demo
    # shows 2; a live database can show 1 or more), so the badge is compared with the source table, not the golden file.
    with engine.connect() as conn:
        n = conn.execute(text(ISSUE_SQL)).scalar()
    assert b["sections"]["srcissue"] == n


def test_admin_senior_view():
    out = client.get("/api/screens/nav", params={"cc_mode": "senior"}, headers=h("admin")).json()
    assert starting.strict(out["groups"]) == starting.strict(NAV["admin_senior"])


def test_last_asset_link():
    def asset_href(acct, last):
        g = client.get("/api/screens/nav", params={"last_asset": last}, headers=h(acct)).json()["groups"]
        prod = next(x for x in g if x["id"] == "product")
        return next(k["href"] for k in prod["kids"] if k["id"] == "asset")

    assert asset_href("planner-a", "RT-1049") == "#/product/asset/RT-1049"
    # a case in another tenant falls back to the first visible case
    first = asset_href("planner-b", None)
    assert asset_href("planner-b", "RT-1048") == first != "#/product/asset/RT-1048"


def test_accounts_for_the_sign_in_page():
    r = client.get("/api/screens/nav/accounts")
    assert r.status_code == 200
    got = r.json()
    assert [a["id"] for a in got] == [a.id for a in policy.starting_accounts()]
    assert next(a for a in got if a["id"] == "planner-b")["email"] == "planner.b@northfield.example"


def test_me_carries_the_session():
    """What session.ts needs after sign-in is in /api/auth/me already."""
    me = client.get("/api/auth/me", headers=h("planner-a")).json()
    assert {"account", "home", "permissions", "pages", "tenants", "warehouse"} <= set(me)
    assert me["account"]["email"] == "planner.a@northfield.example"
