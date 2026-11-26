"""Plan 9 P9-10.2: call the synthetic decommission tracker (tn_decom). Stories TN-04, TN-05, TN-12, TN-13."""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/decommission/api/v2"
KEY = {"x-api-key": "tn_decom-demo-key"}
INV = "/network-inventory/api"
INV_KEY = {"x-api-key": "tn_inv-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "tn_decom"}).raise_for_status()
        c.post("/_sim/reset", params={"system": "tn_inv"}).raise_for_status()
        yield c


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["tn_decom"]
    assert (s.vendor, s.style, s.base_path) == ("Decommission tracker (synthetic)", "vendor", "/decommission")
    assert "tn_decom" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "tn_decom" in MOCKS
    assert client.get("/health").json()["missing_schemas"] == []


def test_decommission_needs_the_key(client):
    assert client.get(f"{API}/removal-jobs").status_code == 401
    assert client.get(f"{API}/site-demand", headers={"x-api-key": "wrong"}).status_code == 401


def test_decommission_jobs_and_site_demand(client):
    jobs = client.get(f"{API}/removal-jobs", headers=KEY).json()["jobs"]
    assert len(jobs) == 12 and {j["programme"] for j in jobs} == {"site_swap", "decommission", "reimbursement_programme"}
    assert set(jobs[0]) == {"jobId", "siteId", "removedAt", "programme", "units"}
    assert set(jobs[0]["units"][0]) == {"serial", "model", "siteId"}
    nine = next(j for j in jobs if j["jobId"] == "RJ-09")
    serials = [u["serial"] for u in nine["units"]]
    assert serials == [f"SN-TN-{n:04d}" for n in range(201, 209)]
    known = {e["serial"] for e in client.get(f"{INV}/elements", params={"limit": 200}, headers=INV_KEY).json()["elements"]}
    assert not known & set(serials)  # 8 serials the inventory does not know (yet)
    assert {u["siteId"] for u in nine["units"]} == {"SITE-301"} and nine["siteId"] == "SITE-301"
    elements = client.get(f"{INV}/elements", params={"limit": 200}, headers=INV_KEY).json()["elements"]
    sites = {e["serial"]: e["site"] for e in elements}
    for j in jobs:  # every unit sits at the site the inventory holds for it (P9-10.7)
        for u in j["units"]:
            assert j["jobId"] == "RJ-09" or u["siteId"] == sites[u["serial"]]
    others = [u["serial"] for j in jobs if j["jobId"] != "RJ-09" for u in j["units"]]
    assert others and set(others) <= known
    demand = client.get(f"{API}/site-demand", headers=KEY).json()
    by = {d["demandId"]: d for d in demand}
    assert set(by) == {"SD-112", "SD-207"}
    assert (by["SD-112"]["siteId"], by["SD-112"]["model"], by["SD-112"]["minFirmwareMajor"], by["SD-112"]["region"]) == (
        "SITE-112", "RRU-4410", None, "North",
    )  # fmt: skip
    assert (by["SD-207"]["siteId"], by["SD-207"]["model"], by["SD-207"]["minFirmwareMajor"]) == ("SITE-207", "RTR-880", 7)
    assert all(set(d) == {"demandId", "siteId", "model", "minFirmwareMajor", "needBy", "region"} for d in demand)


def test_decommission_seed_is_the_same_twice(client):
    before = client.get(f"{API}/removal-jobs", headers=KEY).json()
    client.post("/_sim/reset", params={"system": "tn_decom"}).raise_for_status()
    assert client.get(f"{API}/removal-jobs", headers=KEY).json() == before
