"""Plan 8 MVP-9.2 contract tests: call the PTC Windchill mock the way a Windchill REST Services (ProdMgmt) client does.

The mock is synthetic and not a demo source: it registers beside the 21 demo systems (sim/core/registry.py
EXTRA_SYSTEMS), so the demo's systems and counts stay as they were.
"""

import base64

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, CATALOG_BY_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app
from sim.seed import seed
from sim.vendors.aras.seed import items as aras_items
from sim.vendors.windchill import seed as wc_seed

ODATA = "/Windchill/servlet/odata/ProdMgmt"
AUTH = {"Authorization": "Basic " + base64.b64encode(b"di_connector:Circularity-demo-wc-1").decode()}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "plm_wc"}).raise_for_status()
        yield c


def parts(client, **params) -> dict:
    r = client.get(f"{ODATA}/Parts", params=params, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def every_part(client) -> list[dict]:
    """All parts, following the server's @odata.nextLink."""
    out, url = [], f"{ODATA}/Parts"
    while url:
        r = client.get(url, headers=AUTH)
        assert r.status_code == 200, r.text
        out += r.json()["value"]
        url = r.json().get("@odata.nextLink")
    return out


def structure(client, pid: str):
    return client.post(f"{ODATA}/Parts('{pid}')/PTC.ProdMgmt.GetPartStructure", json={}, headers=AUTH)


# ------------------------------------------------------------------ registry
def test_registered_beside_the_demo_systems():
    assert EXTRA_BY_ID["plm_wc"].vendor == "PTC Windchill" and EXTRA_BY_ID["plm_wc"].schema == "windchill"
    assert "plm_wc" not in BY_SOURCE_ID and "plm_wc" not in CATALOG_BY_ID and len(SYSTEMS) == 21
    assert "plm_wc" in MOCKS


def test_health_stays_ok_with_the_demo_count(client):
    body = client.get("/health").json()
    assert (body["status"], body["systems"], body["missing_schemas"]) == ("ok", 21, [])
    listed = {s["source_id"]: s for s in client.get("/_sim/systems").json()}
    assert listed["plm_wc"]["implemented"] and len(listed) == 21 + len(EXTRA_BY_ID)


# ------------------------------------------------------------------ auth
def test_needs_basic_auth(client):
    r = client.get(f"{ODATA}/Parts")
    assert r.status_code == 401 and r.headers["WWW-Authenticate"].startswith("Basic")
    bad = {"Authorization": "Basic " + base64.b64encode(b"di_connector:wrong").decode()}
    assert client.get(f"{ODATA}/Parts", headers=bad).status_code == 401


# ------------------------------------------------------------------ parts and paging
def test_parts_shape(client):
    body = parts(client, **{"$top": 1})
    assert body["@odata.context"].endswith("$metadata#Parts")
    (p,) = body["value"]
    assert set(p) >= {"ID", "Number", "Name", "Version", "Iteration", "State", "UnitCost"}
    assert p["ID"].startswith("OR:wt.part.WTPart:") and set(p["State"]) >= {"Value"}
    assert isinstance(p["UnitCost"], int | float)


def test_paging(client):
    first = parts(client)
    assert len(first["value"]) == 25 and "$skip=25" in first["@odata.nextLink"].replace("%24", "$")
    seen = every_part(client)  # server-driven: pages of 25 linked by @odata.nextLink
    assert len(seen) == 48 and len({p["ID"] for p in seen}) == 48 and seen[:25] == first["value"]
    page = parts(client, **{"$top": 15, "$skip": 15})  # client-driven: $top caps the answer, no link
    assert page["value"] == seen[15:30] and "@odata.nextLink" not in page
    assert parts(client, **{"$top": 5, "$skip": 45})["value"] == seen[45:]
    capped = parts(client, **{"$top": 30})  # more than a page: the link asks for the rest of the 30 only
    rest = client.get(capped["@odata.nextLink"], headers=AUTH).json()
    assert capped["value"] + rest["value"] == seen[:30] and "@odata.nextLink" not in rest
    assert parts(client, **{"$skip": 60})["value"] == []
    for bad in ({"$top": "-1"}, {"$top": "x"}, {"$skip": "-3"}):
        r = client.get(f"{ODATA}/Parts", params=bad, headers=AUTH)
        assert r.status_code == 400 and r.json()["error"]["message"], bad


def test_forty_parts_eight_assemblies_overlapping_aras(client):
    everything = every_part(client)
    asm = [p for p in everything if structure(client, p["ID"]).json()["value"][0]["Uses"]]
    assert len(asm) == 8 and len(everything) - len(asm) == 40
    aras = {i["data"].get("item_number") for i in aras_items(seed()) if i["itemtype"] == "Part"}
    shared = {p["Number"] for p in everything} & aras
    assert len(shared) == 5
    used = {u["Part"]["Number"] for a in asm for u in structure(client, a["ID"]).json()["value"][0]["Uses"]}
    assert shared <= used  # where-used across systems: every shared number sits in a Windchill assembly


# ------------------------------------------------------------------ structure
def test_structure_of_one_assembly(client):
    by_number = {p["Number"]: p for p in every_part(client)}
    first = wc_seed.ASSEMBLIES[0]
    r = structure(client, by_number[first.number]["ID"])
    assert r.status_code == 200, r.text
    (root,) = r.json()["value"]
    assert root["Number"] == first.number
    assert [(u["Quantity"], u["Part"]["Number"]) for u in root["Uses"]] == [(q, n) for n, q in first.uses]
    assert all(u["Part"]["Version"] == by_number[u["Part"]["Number"]]["Version"] for u in root["Uses"])
    leaf = next(p for p in by_number.values() if p["Number"] not in {a.number for a in wc_seed.ASSEMBLIES})
    assert structure(client, leaf["ID"]).json()["value"] == [{"Number": leaf["Number"], "Uses": []}]
    missing = structure(client, "OR:wt.part.WTPart:1")
    assert missing.status_code == 404 and missing.json()["error"]["code"]
    assert client.post(f"{ODATA}/Parts('{leaf['ID']}')/PTC.ProdMgmt.GetPartStructure").status_code == 401


# ------------------------------------------------------------------ determinism
def test_seed_is_deterministic(client):
    assert wc_seed.parts() == wc_seed.parts() and wc_seed.usages() == wc_seed.usages()
    before = every_part(client)
    client.post("/_sim/reset", params={"system": "plm_wc"}).raise_for_status()
    assert every_part(client) == before
    assert before[0] == {
        "ID": "OR:wt.part.WTPart:100001", "Number": "0000100001", "Name": before[0]["Name"], "Version": "A",
        "Iteration": "1", "State": {"Value": "RELEASED", "Display": "Released"}, "UnitCost": before[0]["UnitCost"],
    }  # fmt: skip
