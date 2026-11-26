"""Plan 9 P9-12.8: call the synthetic core returns mock (core_ret): the returned cores with their inspection checks, and the
dealers' return history.

The mock is no demo source (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`. Stories NS-CORE-01, NS-CORE-03.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/core-returns/api"
KEY = {"x-api-key": "core_ret-demo-key"}
CHECKS = {"housing_intact", "no_cracks", "complete", "family_match"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "core_ret"}).raise_for_status()
        yield c


def get(client, path: str, **params):
    r = client.get(f"{API}/{path}", params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["core_ret"]
    assert (s.vendor, s.style, s.base_path) == ("Core returns system (synthetic)", "vendor", "/core-returns")
    assert "core_ret" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "core_ret" in MOCKS


def test_cores_and_history_need_the_key(client):
    for path in ("cores", "dealer-history"):
        assert client.get(f"{API}/{path}").status_code == 401
        assert client.get(f"{API}/{path}", headers={"x-api-key": "wrong"}).status_code == 401


def test_cores_have_the_checks(client):
    rows = {c["coreId"]: c for c in get(client, "cores")}
    assert set(rows["C-0001"]) == {
        "coreId", "dealerId", "declaredPartNumber", "observedPartNumber", "deposit", "checks", "receivedAt",
    }  # fmt: skip
    assert all(set(c["checks"]) == CHECKS for c in rows.values())
    assert all(rows["C-0001"]["checks"].values())  # a clean core
    assert rows["C-0002"]["checks"]["complete"] is False  # the bracket is missing
    assert rows["C-0003"]["checks"]["no_cracks"] is False  # cracked
    mismatch = rows["C-0004"]
    assert (mismatch["declaredPartNumber"], mismatch["observedPartNumber"]) == ("ALT-1450", "STR-2210")
    assert mismatch["checks"]["family_match"] is False
    assert rows["C-0005"]["dealerId"] == "D-17"


def test_dealer_history_filters_by_dealer(client):
    rows = get(client, "dealer-history", dealerId="D-17")
    assert rows and {r["dealerId"] for r in rows} == {"D-17"}
    assert set(rows[0]) == {"dealerId", "coreId", "outcome", "at"}
    assert {r["outcome"] for r in rows} <= {"accepted", "rejected"}
    recent = [r for r in rows if r["outcome"] == "rejected" and r["at"] >= "2026-08-22"]  # 90 days before 2026-11-20
    assert len(recent) == 3 and len([r for r in rows if r["outcome"] == "rejected"]) == 4  # one is older than 90 days
    assert len(get(client, "dealer-history")) > len(rows)


def test_core_seed_is_the_same_twice(client):
    before = get(client, "cores"), get(client, "dealer-history")
    client.post("/_sim/reset", params={"system": "core_ret"}).raise_for_status()
    assert (get(client, "cores"), get(client, "dealer-history")) == before
