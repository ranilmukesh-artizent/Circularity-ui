"""B14: the Home and utility-page reads give what the facade (apps/web/src/api/home.ts) gives today, for all 11 accounts.

Golden data: fixtures/golden/screens/home.json (apps/web/scripts/golden/home_command.mjs), from the starting state.
Numbers went through the golden script's plain(): floats rounded to 1e-6; the comparison rounds the server's answer the
same way. Booleans compare strictly (tests/starting.py).

Two golden values are synthetic in the demo and are not compared, by design (see di/screens/home.py):
- a failing workflow alert's `s` ends with " · <age of the last run>", drawn at random when the demo seeds its
  workflows; the server answers the failure note alone, so the age is cut from the expected text;
- Home's activity includes the demo's seeded workflow runs (random times and record counts): the server has none, so
  the expected activity is the demo's own frActivity with those runs removed (`activity_without_workflow_runs`).
"""

import os
import re

import pytest
from fastapi.testclient import TestClient

from di import golden
from di.engine.jsmath import js_round
from di.main import app
from tests import starting

client = TestClient(app)
HOME = golden.load("screens/home")
ACCOUNTS = sorted(HOME)
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


def get(path: str, user: str, **params):
    r = client.get("/api/screens/home" + path, params=params, headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def plain(x):
    """The golden script's rounding, applied to the server's answer, with strict booleans."""
    if isinstance(x, bool):
        return x
    if isinstance(x, float):
        return js_round(x * 1e6) / 1e6
    if isinstance(x, dict):
        return {k: plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [plain(v) for v in x]
    return x


def same(got, expected) -> None:
    assert starting.strict(plain(got)) == starting.strict(expected)


def test_every_account_is_in_the_golden_file():
    assert len(ACCOUNTS) == 11


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_briefing(acct):
    same(get("/briefing", acct), HOME[acct]["briefing"])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_tasks(acct):
    same(get("/tasks", acct), HOME[acct]["tasks"])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_alerts(acct):
    expected = [
        {**a, "s": re.sub(r" · [^·]* ago$", "", a["s"])} if a["kind"] == "wf" else a  # the run's random age (docstring)
        for a in HOME[acct]["alerts"]
    ]
    same(get("/alerts", acct), expected)


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_kpis(acct):
    same(get("/kpis", acct), HOME[acct]["kpis"])


@pytest.mark.parametrize("win", ["live", "today", "week"])
@pytest.mark.parametrize("acct", ACCOUNTS)
def test_activity(acct, win):
    same(get("/activity", acct, win=win), HOME[acct]["activity_without_workflow_runs"][win])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_activity_matches_the_facade_where_there_are_no_workflow_runs(acct):
    """Accounts that cannot open the Workflow Studio or the Source Map never see workflow runs: the facade's own output."""
    g = HOME[acct]
    for win in ("live", "today", "week"):
        if not any(r["ic"] == "workflow" for r in g["activity"][win]):
            same(get("/activity", acct, win=win), g["activity"][win])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_middle_panel(acct):
    same(get("/middle", acct), HOME[acct]["middle"])


@pytest.mark.parametrize("per", ["30", "90", "365"])
@pytest.mark.parametrize("acct", ACCOUNTS)
def test_figures(acct, per):
    same(get("/figures", acct, per=per), HOME[acct]["figures"][per])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_reports(acct):
    same(get("/reports", acct), HOME[acct]["reports"])


REPORT_CASES = [
    pytest.param(acct, rid, key, id=f"{acct}-{rid}-{key}")
    for acct in ACCOUNTS
    for rid, by in HOME[acct]["report_rows"].items()
    for key in by
]


@pytest.mark.parametrize(("acct", "rid", "key"), REPORT_CASES)
def test_report_rows(acct, rid, key):
    tenant, period = key.split("|")
    same(get(f"/reports/{rid}", acct, tenant=tenant, period=period), HOME[acct]["report_rows"][rid][key])


def test_every_listed_report_but_the_audit_extract_is_covered():
    for acct in ACCOUNTS:
        listed = {r["id"] for r in HOME[acct]["reports"]} - {"audit"}
        assert set(HOME[acct]["report_rows"]) == listed


def test_the_audit_extract_is_the_audit_area_s():
    r = client.get("/api/screens/home/reports/audit", headers=h("admin"))
    assert r.status_code == 404


def test_a_report_the_account_cannot_open_is_not_found():
    r = client.get("/api/screens/home/reports/health", headers=h("planner-a"))
    assert r.status_code == 404


def test_a_tenant_outside_the_account_is_refused():
    r = client.get("/api/screens/home/reports/pva", params={"tenant": "Customer B"}, headers=h("planner-a"))
    assert r.status_code == 403


def test_signed_out_is_refused():
    assert client.get("/api/screens/home/briefing").status_code == 401
