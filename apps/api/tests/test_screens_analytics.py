"""B14: the Analytics page's data (GET /api/screens/analytics, analytics.models) gives the demo's answers, for all 11
accounts (fixtures/golden/screens/analytics.json, from apps/web/scripts/golden/analytics_audit.mjs).

For each account, 12 filter combinations the page offers (tenant, class, route, month range, model version) under three
top-bar tenant filters: the closed decisions returned (ids, in order, and each row as the demo's ROWS has it), the
page's totals (metrics), the model versions' statistics and the agent answer beside predicted vs actual.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from di import golden, policy
from di.db import engine
from di.engine.jsmath import js_round
from di.main import app
from tests import starting

client = TestClient(app)
G = golden.load("screens/analytics")
ROWS = {r["id"]: r for r in golden.load("decisions")}
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


def norm(x):
    """The dump's normalisation (numbers to 1e-6), with booleans kept apart from numbers."""
    if isinstance(x, bool):
        return ("bool", x)
    if isinstance(x, float):
        return js_round(x * 1e6) / 1e6
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items()}
    if isinstance(x, list):
        return [norm(v) for v in x]
    return x


def sees(acct: str) -> bool:
    return policy.can_page(policy.account(acct), "analytics")


VIEWS = [
    pytest.param(acct, v, id=f"{acct}-{v['tenant_filter']}-{v['filter']}")
    for acct, x in G["accounts"].items()
    for v in x["views"]
]


@pytest.mark.parametrize(("acct", "view"), VIEWS)
def test_rows_and_metrics(acct, view):
    f = G["filters"][view["filter"]]
    params = {k: v for k, v in f.items() if v != ""} | {"tenant_filter": view["tenant_filter"]}
    r = client.get("/api/screens/analytics", params=params, headers=h(acct))
    if not sees(acct):
        assert r.status_code == 403
        return
    assert r.status_code == 200, r.text
    out = r.json()
    assert [x["id"] for x in out["rows"]] == view["row_ids"]
    assert norm(out["rows"]) == norm([ROWS[i] for i in view["row_ids"]])
    want = dict(view["metrics"])
    rc_n = want.pop("rc_n")
    assert sum(1 for x in out["rows"] if x["status"] == "reconciled") == rc_n  # metrics.rc, rebuilt by the page
    assert norm(out["metrics"]) == norm(want)


@pytest.mark.parametrize("acct", list(G["accounts"]))
def test_model_stats_and_telemetry(acct):
    r = client.get("/api/screens/analytics", headers=h(acct))
    if not sees(acct):
        assert r.status_code == 403
        return
    out = r.json()
    assert norm(out["model_stats"]) == norm(G["model_stats"])
    assert out["telemetry_unavailable"] is G["telemetry_unavailable"]
    # read from the connector's state, which agrees with the demo
    with engine.connect() as conn:
        st = conn.execute(text("SELECT status FROM source_system WHERE id = 'iot'")).scalar()
    assert out["telemetry_unavailable"] is ((st or "unavailable") == "unavailable")


@pytest.mark.parametrize("acct", list(G["accounts"]))
def test_analytics_models_action(acct):
    r = client.post("/api/actions/analytics.models", json={}, headers=h(acct))
    out = r.json()
    got = {"ok": True, "output": out["output"]} if out.get("ok") else {"ok": False, "error": out["error"]}
    assert norm(got) == norm(G["accounts"][acct]["models"])


def test_every_account_is_covered():
    assert len(G["accounts"]) == 11
    assert all(len(x["views"]) == 3 * len(G["filters"]) for x in G["accounts"].values())
