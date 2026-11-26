"""Plan 9 P9-12.2: call the synthetic IT service management and CMDB (it_cmdb) the way a JSON-API client does.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in
`x-api-key`. Story NS-IT-01.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/itsm-cmdb/api"
KEY = {"x-api-key": "it_cmdb-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "it_cmdb"}).raise_for_status()
        yield c


def every_ci(client, **params) -> list[dict]:
    r = client.get(f"{API}/now/cis", params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["it_cmdb"]
    assert (s.vendor, s.style, s.base_path) == ("IT service management and CMDB (synthetic)", "vendor", "/itsm-cmdb")
    assert "it_cmdb" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "it_cmdb" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_cis_need_the_key(client):
    assert client.get(f"{API}/now/cis").status_code == 401
    assert client.get(f"{API}/now/cis", headers={"x-api-key": "wrong"}).status_code == 401


def test_cmdb_seed_shape_and_filter(client):
    rows = every_ci(client)
    assert len(rows) == 70 and rows[0]["serial"] == "SN-IT-0001" and "SN-IT-9999" not in {r["serial"] for r in rows}
    assert set(rows[0]) == {
        "ciId", "serial", "model", "assetClass", "ownerOrg", "securityLevel", "leaseRef", "lessorReturnRequired",
        "consentToResell", "newPrice", "media",
    }  # fmt: skip
    assert {r["assetClass"] for r in rows} == {"laptop", "desktop", "server", "network"}
    leased = [r for r in rows if r["leaseRef"]]
    assert leased and all(r["lessorReturnRequired"] and not r["consentToResell"] for r in leased)
    assert all(m["type"] in ("ssd", "hdd") for r in rows for m in r["media"])
    one = every_ci(client, serial="SN-IT-0005")
    assert [r["serial"] for r in one] == ["SN-IT-0005"] and every_ci(client, serial="SN-NOPE") == []


def test_cmdb_seed_is_the_same_twice(client):
    before = every_ci(client)
    client.post("/_sim/reset", params={"system": "it_cmdb"}).raise_for_status()
    assert every_ci(client) == before
