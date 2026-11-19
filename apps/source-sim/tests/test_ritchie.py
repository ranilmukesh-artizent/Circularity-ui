"""B5b contract tests: call the Ritchie Bros. Market Data mock (Comparables API v2) as its client would."""

import statistics

import pytest
from fastapi.testclient import TestClient

from sim.main import app

API = "/ritchie/v2"
KEY = {"X-Api-Key": "mkt-demo-key"}


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)  # no lifespan: the reset builds the schema
    c.post("/_sim/reset", params={"system": "mkt"}).raise_for_status()
    yield c
    c.delete("/_sim/faults", params={"system": "mkt"})
    c.post("/_sim/reset", params={"system": "mkt"}).raise_for_status()


def get(client, path, **params):
    r = client.get(API + path, headers=KEY, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def all_results(client, path, **params) -> list[dict]:
    out, offset = [], 0
    while True:
        body = get(client, path, offset=offset, limit=20, **params)
        out += body["results"]
        if body["links"]["next"] is None:
            assert len(out) == body["totalCount"]
            return out
        offset += 20


def amounts(rows):
    return [r["SOLD_PRC_AMT"] for r in rows]


def test_api_key_and_errors(client):
    r = client.get(API + "/comparables")
    assert r.status_code == 401 and r.json()["error"]["code"] == "missing_api_key"
    r = client.get(API + "/comparables", headers={"X-Api-Key": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key" and r.json()["error"]["requestId"]
    r = client.get(API + "/comparables", headers=KEY, params={"colour": "red"})
    assert r.status_code == 400 and r.json()["error"] == r.json()["error"] | {"code": "invalid_parameter", "target": "colour"}
    assert client.get(API + "/comparables", headers=KEY, params={"limit": 501}).status_code == 400
    assert client.get(API + "/comparables", headers=KEY, params={"condition": "MINT"}).status_code == 400
    assert client.get(API + "/comparables/RBC-0000-01", headers=KEY).status_code == 404


def test_offset_paging_and_envelope(client):
    body = get(client, "/comparables", limit=10)
    assert body["offset"] == 0 and body["limit"] == 10 and len(body["results"]) == 10
    assert body["dataAsOf"] == "2026-10-06T14:00:00Z" and body["links"]["next"].endswith("offset=10&limit=10")
    rows = all_results(client, "/subjects/MTR-2041/comparables")
    assert len({r["COMP_ID"] for r in rows}) == 48


def test_rt1048_comparables(client):
    rows = all_results(client, "/subjects/MTR-2041/comparables")
    assert len(rows) == 48  # "48 comparable sales"
    assert statistics.median(amounts(rows)) == pytest.approx(5600 * 83.5, abs=1)
    top = max(rows, key=lambda r: r["SOLD_PRC_AMT"])
    assert (top["SOLD_PRC"], top["DAYS_LISTED"], top["CONDITION"]) == ("8.1 L INR", 17, "VG")  # MAPPINGS.mkt
    assert {(r["MAKE"], r["MODEL"], r["REGION"], r["CONDITION"]) for r in rows} == {("Voltara", "IE3 250M", "IN-West", "VG")}
    # the same set through the search filters (the match rule)
    same = all_results(client, "/comparables", make="voltara", model="IE3 250M", condition="VG", region="IN-West", lotSize=1)
    assert sorted(amounts(same)) == sorted(amounts(rows))
    # RT-1062 has the same make, model and condition but is held in another region
    assert get(client, "/subjects/MTR-2057/comparables")["totalCount"] < 10
    assert get(client, "/comparables", make="Voltara", model="IE3 250M", condition="VG", region="IN")["totalCount"] > 48


def test_rt1049_and_refurbished_scenario(client):
    s = get(client, "/subjects/DRL-0812")
    assert [x["SCENARIO"] for x in s["SCENARIOS"]] == ["AS_IS", "REFURBISHED"]
    rows = all_results(client, "/subjects/DRL-0812/comparables")
    assert len(rows) == 31 and statistics.median(amounts(rows)) == pytest.approx(241 * 83.5, abs=1)
    ref = all_results(client, "/subjects/DRL-0812/comparables", scenario="REFURBISHED")
    assert ref and {r["CONDITION"] for r in ref} == {"EXC"} and all(r["COMP_ID"].startswith("RBR-1049-") for r in ref)
    r = client.get(API + "/subjects/MTR-2041/comparables", headers=KEY, params={"scenario": "REFURBISHED"})
    assert r.status_code == 404


def test_lots_match_by_lot_size(client):
    a = all_results(client, "/subjects/BAT-0119/comparables")  # RT-1044, 8 units
    b = all_results(client, "/subjects/BAT-0126/comparables")  # RT-1052, 20 units, same make/model/condition/region
    assert {r["QTY"] for r in a} == {8} and {r["QTY"] for r in b} == {20}
    assert statistics.median(amounts(b)) == pytest.approx(2560 * 83.5, abs=1)


def test_freshness_stale_feed(client):
    st = get(client, "/feed/status")
    assert st["state"] == "stale" and st["tokenExpired"] and st["lastRefreshAt"] == "2026-10-06T14:00:00Z"
    assert st["pendingRecords"] == 2 and st["ageMinutes"] >= 1140
    rows = all_results(client, "/comparables", **{"class": "DRILL"})
    assert max(r["SOLD_DATE"][6:] + r["SOLD_DATE"][3:5] + r["SOLD_DATE"][:2] for r in rows) < "20261006"
    assert get(client, "/comparables", modifiedSince="2026-10-06T14:00:00Z")["totalCount"] == 0
    idx = all_results(client, "/price-index", **{"class": "motor"})
    assert len(idx) == 12 and idx[-1]["PERIOD"] == "2026-09"


def test_market_summary(client):
    s = get(client, "/market-summary", make="Voltara", model="IE3 250M", condition="VG", region="IN-West", lotSize=1)
    assert s["count"] == 48 and s["medianSoldPrice"]["amount"] == pytest.approx(5600 * 83.5, abs=1)
    assert s["medianDaysListed"] > 0 and s["avgBidders"] > 0


def test_feed_token_renewal_releases_held_back_sales(client):
    assert client.post(API + "/feed/token", headers=KEY, json={"validityDays": 0}).status_code == 400
    assert client.post(API + "/feed/token", headers=KEY, content=b"[1]").status_code == 400
    r = client.post(API + "/feed/token", headers=KEY, json={"validityDays": 30})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["state"] == "current" and not st["tokenExpired"] and st["pendingRecords"] == 0
    rows = all_results(client, "/subjects/MTR-2041/comparables")
    assert len(rows) == 50 and statistics.median(amounts(rows)) == pytest.approx(5600 * 83.5, abs=1)
    late = get(client, "/comparables", modifiedSince="2026-10-06T14:00:00Z")
    assert late["totalCount"] == 2
    ev = client.get("/_sim/outbox", params={"source": "mkt"}).json()
    assert any(e["type"] == "com.rbglobal.marketdata.feed.refreshed" for e in ev)
    client.post("/_sim/reset", params={"system": "mkt"}).raise_for_status()


def test_demo_fault_refuses_the_key(client):
    client.post("/_sim/faults", json={"system": "mkt", "kind": "token_expired"}).raise_for_status()
    try:
        r = client.get(API + "/comparables", headers=KEY)
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"
    finally:
        client.delete("/_sim/faults", params={"system": "mkt"})
    assert client.get(API + "/comparables", headers=KEY).status_code == 200
