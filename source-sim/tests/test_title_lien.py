"""Plan 9 P9-9.3: call the synthetic title and lien service (uc_title) the way a JSON-API client does.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS), so the demo's
systems and counts stay as they were. API key in `x-api-key`. Title, lien and brand rules are state law and differ: the
mock models generic evidence only (its summary text needs review by Kinective's Legal team).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.core import scheduler
from sim.core.db import engine
from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/title-lien/api/v2"
KEY = {"x-api-key": "uc_title-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/clock/reset").raise_for_status()
        c.post("/_sim/reset", params={"system": "uc_title"}).raise_for_status()
        yield c
        c.post("/_sim/reset", params={"system": "uc_title"}).raise_for_status()
        c.post("/_sim/clock/reset").raise_for_status()


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def every_title(client, **params) -> list[dict]:
    out, offset = [], 0
    while offset is not None:
        r = client.get(f"{API}/titles", params={"limit": 40, "offset": offset} | params, headers=KEY)
        assert r.status_code == 200, r.text
        out += r.json()["items"]
        offset = r.json()["next"]
    return out


def release_events() -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT data FROM sim.outbox WHERE source = 'uc_title' AND type = 'title.lien.released'"))
        return [r[0] for r in rows]


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["uc_title"]
    assert (s.vendor, s.style, s.base_path) == ("Title and lien service (synthetic)", "vendor", "/title-lien")
    assert "uc_title" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "uc_title" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_title_lien_needs_the_key(client):
    assert client.get(f"{API}/titles").status_code == 401
    assert client.get(f"{API}/titles/{vin(1)}", headers={"x-api-key": "wrong"}).status_code == 401
    assert client.post(f"{API}/lien-release-requests", json={}).status_code == 401


def test_title_lien_seed(client):
    rows = every_title(client)
    assert [r["vin"] for r in rows] == [vin(n) for n in range(1, 101)]
    by = {r["vin"]: r for r in rows}
    assert set(rows[0]) == {"vin", "titleStatus", "brand", "brandSource", "liens", "checkedAt"}
    three = by[vin(3)]
    assert three["titleStatus"] == "lien" and three["brand"] is None
    (lien,) = three["liens"]
    assert set(lien) == {"lienId", "holderRef", "amount", "released", "releaseRef", "releasedAt"}
    assert lien["released"] is False and lien["releaseRef"] is None and lien["holderRef"].startswith("H-")
    assert by[vin(70)]["titleStatus"] == "lien" and len(by[vin(70)]["liens"]) == 1
    assert [n for n in range(1, 101) if by[vin(n)]["titleStatus"] == "lien"] == [3, 70]
    assert [(n, by[vin(n)]["brand"]) for n in (21, 22, 23)] == [(21, "flood"), (22, "rebuilt"), (23, "salvage")]
    assert by[vin(21)]["brandSource"] in {"state title", "national title database"}
    assert [n for n in range(1, 101) if by[vin(n)]["brand"]] == [21, 22, 23]
    assert by[vin(1)]["titleStatus"] == "clear" and by[vin(1)]["liens"] == [] and by[vin(1)]["brandSource"] is None


def test_title_lien_one_title_paging_and_since(client):
    one = client.get(f"{API}/titles/{vin(21)}", headers=KEY)
    assert one.status_code == 200 and one.json()["brand"] == "flood"
    assert client.get(f"{API}/titles/SYNUC999999999999", headers=KEY).status_code == 404
    first = client.get(f"{API}/titles", params={"limit": 25}, headers=KEY).json()
    assert (len(first["items"]), first["next"], first["total"]) == (25, 25, 100)
    assert client.get(f"{API}/titles", params={"limit": 0}, headers=KEY).status_code == 400
    assert client.get(f"{API}/titles", params={"updatedSince": "yesterday"}, headers=KEY).status_code == 400
    assert every_title(client, updatedSince="2030-01-01T00:00:00Z") == []
    assert len(every_title(client, updatedSince="2020-01-01")) == 100


def test_title_lien_same_seed_same_json(client):
    before = every_title(client)
    client.post("/_sim/clock/reset").raise_for_status()
    client.post("/_sim/reset", params={"system": "uc_title"}).raise_for_status()
    assert every_title(client) == before


def test_title_lien_release_is_scheduled(client):
    """Two simulated days after seeding VIN ...003's lien is released: `clear`, a release ref, one outbox event."""
    client.post("/_sim/clock/reset").raise_for_status()
    client.post("/_sim/reset", params={"system": "uc_title"}).raise_for_status()
    scheduler.tick()
    assert client.get(f"{API}/titles/{vin(3)}", headers=KEY).json()["titleStatus"] == "lien" and release_events() == []
    client.post("/_sim/clock/advance", json={"days": 1}).raise_for_status()
    scheduler.tick()
    assert client.get(f"{API}/titles/{vin(3)}", headers=KEY).json()["titleStatus"] == "lien"
    client.post("/_sim/clock/advance", json={"days": 1.1}).raise_for_status()
    scheduler.tick()
    t = client.get(f"{API}/titles/{vin(3)}", headers=KEY).json()
    assert t["titleStatus"] == "clear"
    (lien,) = t["liens"]
    assert lien["released"] is True and lien["releaseRef"].startswith("LR-") and lien["releasedAt"]
    (event,) = release_events()
    assert event["vin"] == vin(3) and event["releaseRef"] == lien["releaseRef"] and event["lienId"] == lien["lienId"]
    other = client.get(f"{API}/titles/{vin(70)}", headers=KEY).json()
    assert other["titleStatus"] == "lien" and other["liens"][0]["released"] is False  # VIN ...070 never releases
    scheduler.tick()
    assert len(release_events()) == 1
    assert [x["vin"] for x in every_title(client, updatedSince="2026-10-08T00:00:00Z")] == [vin(3)]


def test_title_lien_release_request(client):
    client.post("/_sim/clock/reset").raise_for_status()
    client.post("/_sim/reset", params={"system": "uc_title"}).raise_for_status()
    lien_id = client.get(f"{API}/titles/{vin(70)}", headers=KEY).json()["liens"][0]["lienId"]
    r = client.post(f"{API}/lien-release-requests", json={"vin": vin(70), "lienId": lien_id}, headers=KEY)
    assert r.status_code == 202 and r.json()["requestId"].startswith("LRR-")
    again = client.post(
        f"{API}/lien-release-requests", json={"vin": vin(70), "lienId": lien_id}, headers=KEY | {"Idempotency-Key": "k1"}
    )
    repeat = client.post(
        f"{API}/lien-release-requests", json={"vin": vin(70), "lienId": lien_id}, headers=KEY | {"Idempotency-Key": "k1"}
    )
    assert again.status_code == repeat.status_code == 202 and again.json() == repeat.json() != r.json()
    assert client.get(f"{API}/titles/{vin(70)}", headers=KEY).json()["titleStatus"] == "lien"  # a request releases nothing
    bad = [
        ({"vin": vin(70)}, 422),
        ({"vin": "SYNUC999999999999", "lienId": "LN-0001"}, 404),
        ({"vin": vin(70), "lienId": "LN-9999"}, 404),
        ({"vin": vin(1), "lienId": lien_id}, 404),
    ]
    for body, code in bad:
        assert client.post(f"{API}/lien-release-requests", json=body, headers=KEY).status_code == code, body
    assert client.post(f"{API}/lien-release-requests", content=b"not json", headers=KEY).status_code == 400
