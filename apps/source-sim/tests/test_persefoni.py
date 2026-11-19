"""B5b contract tests: call the Persefoni mock the way a Persefoni API client does."""

import pytest
from fastapi.testclient import TestClient

from sim import clock
from sim.main import app
from sim.seed import seed
from sim.vendors.persefoni import seed as pf_seed

TOKEN = "/persefoni/oauth/token"
API = "/persefoni/v1"
CLIENT = {"client_id": "circularity-di-connector", "client_secret": "circularity-demo-persefoni-secret"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "esg"}).raise_for_status()
        yield c
        c.post("/_sim/reset", params={"system": "esg"}).raise_for_status()


@pytest.fixture(scope="module")
def auth(client):
    r = client.post(TOKEN, data={"grant_type": "client_credentials", "audience": "https://api.persefoni.com"} | CLIENT)
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def get_all(client, auth, path, **params):
    out, page = [], 1
    while True:
        body = client.get(API + path, headers=auth, params=params | {"page": page, "per_page": 500}).json()
        out += body["data"]
        if not body["links"]["next"]:
            return out
        page += 1


def test_auth(client):
    r = client.get(API + "/footprints")
    assert r.status_code == 401 and r.json()["errors"][0]["code"] == "unauthorized"
    assert "Bearer" in r.headers["WWW-Authenticate"]
    bad = client.post(TOKEN, json={"grant_type": "client_credentials", "client_id": "x", "client_secret": "y"})
    assert bad.status_code == 401 and bad.json()["error"] == "access_denied"
    good = client.post(TOKEN, json={"grant_type": "client_credentials"} | CLIENT)
    assert good.status_code == 200 and good.json()["token_type"] == "Bearer"
    assert client.post(TOKEN, json={"grant_type": "password"} | CLIENT).json()["error"] == "unsupported_grant_type"


def test_factors(client, auth):
    motor = client.get(API + "/emission-factors/ef_embodied_motor", headers=auth).json()["data"]
    assert (motor["factor_kgco2e"], motor["scope"], motor["version"], motor["activity_unit"]) == (
        420.0,
        "Cradle-to-gate",
        "2026.2",
        "unit",
    )
    routes = get_all(client, auth, "/emission-factors", category="avoided_emissions")
    assert {r["route"]: r["share_of_embodied"] for r in routes}["redeploy"] == 0.7
    assert client.get(API + "/emission-factors/nope", headers=auth).json()["errors"][0]["status"] == "404"


def test_footprints_are_activity_times_factor(client, auth):
    s = seed()
    fps = get_all(client, auth, "/footprints", external_reference="RT-1048")
    red = next(f for f in fps if f["route"] == "redeploy")
    assert (red["id"], red["avoided_co2e"], red["co2e_unit"], red["emission_factor_value"], red["avoidance_share"]) == (
        "fp_RT-1048_1",
        0.294,  # 1 unit x 420 kgCO2e/unit x 0.7 = 294 kg
        "mtCO2e",
        420.0,
        0.7,
    )
    every = {f["id"]: f for f in get_all(client, auth, "/footprints", activity_type="closed_decision")}
    for d in s.decisions[:50]:
        assert every[f"fp_{d.id}"]["avoided_co2e"] == pytest.approx(d.co2e / 1000)
    assert every["fp_CS-2001"]["measured_co2e"] == 0.147 and every["fp_CS-2001"]["methodology"] == "measured"
    assert len(pf_seed.activity_docs(s, s.world.as_of)) == len(get_all(client, auth, "/activities"))


def test_paging(client, auth):
    body = client.get(API + "/footprints", headers=auth, params={"per_page": 10, "page": 2}).json()
    assert body["meta"]["page"] == 2 and len(body["data"]) == 10 and body["links"]["prev"] and body["links"]["next"]
    assert client.get(API + "/footprints", headers=auth, params={"per_page": 501}).status_code == 400


def test_create_activity(client, auth):
    now = clock.now().isoformat()
    assert client.get(API + "/footprints", headers=auth, params={"updated_since": now}).json()["meta"]["total_count"] == 0
    base = {
        "activity_type": "route_estimate",
        "asset_id": "PMP-TEST-1",
        "external_reference": "RT-TEST",
        "quantity": 3,
        "quantity_unit": "unit",
        "emission_factor_id": "ef_embodied_pump",
        "route": "resale",
    }
    bad = client.post(API + "/activities", headers=auth, json=base | {"quantity_unit": "kg"})
    assert bad.status_code == 422 and bad.json()["errors"][0]["code"] == "unit_mismatch"
    assert client.post(API + "/activities", headers=auth, json=base | {"quantity": -1}).status_code == 422
    assert (
        client.post(API + "/activities", headers=auth, json=base | {"period": "2025-06"}).json()["errors"][0]["code"]
        == "factor_not_valid"
    )
    r = client.post(API + "/activities", headers=auth, json=base)
    assert r.status_code == 201, r.text
    fp = r.json()["included"][0]
    assert fp["avoided_co2e"] == 0.429  # 3 x 260 x 0.55 = 429 kg
    rep = client.post(
        API + "/activities",
        headers=auth,
        json={
            "activity_type": "closed_decision",
            "asset_id": "PMP-TEST-1",
            "calculation_method": "reported",
            "reported_co2e": 1.5,
            "reported_co2e_unit": "tCO2e",
        },
    )
    assert rep.status_code == 201 and rep.json()["included"][0]["avoided_co2e"] == 1.5
    changed = get_all(client, auth, "/footprints", updated_since=now)
    assert {f["id"] for f in changed} == {fp["id"], rep.json()["included"][0]["id"]}
