"""Plan 6 A3: the catalogue systems and the sandbox for hand-made connections.

- one generic mock per catalogue system (the Connection Fabric's 15), registered beside the demo's 21, none of them a
  demo source; each passes the generic contract (tests/test_generic_specs.py runs it for every spec)
- seeds are deterministic: two seeds give the same documents
- the sandbox serves 25 records per name with offset paging, a delta filter and one-record reads, without credentials
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, CATALOG_BY_ID, CATALOG_SYSTEMS
from sim.main import MOCKS, app
from sim.seed import seed

CATALOG = {
    "workday", "jira", "confluence", "postgres", "mysql", "sqlserver", "s3", "azureblob", "excel", "dynamics", "ebs",
    "netsuite", "teams", "gdrive", "snowflake",
}  # fmt: skip


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_one_mock_per_catalogue_system():
    assert set(CATALOG_BY_ID) == CATALOG and len(CATALOG_SYSTEMS) == 15
    assert not CATALOG & set(BY_SOURCE_ID)
    assert set(MOCKS) >= CATALOG and "sandbox" in MOCKS
    schemas = [s.schema for s in CATALOG_SYSTEMS]
    assert len(set(schemas)) == 15 and all(x.startswith("cat_") for x in schemas)


@pytest.mark.parametrize("sid", sorted(CATALOG))
def test_seed_is_deterministic(sid):
    spec = importlib.import_module(f"sim.generic.specs.catalog_{sid}").SPEC
    a, b = spec.seed(seed()), spec.seed(seed())
    assert a == b and sum(len(v) for v in a.values()) > 0


def test_sandbox_records(client):
    r = client.get("/sandbox/demo/records", params={"limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 25 and len(body["items"]) == 10 and body["next"] == 10
    ids = [x["id"] for x in body["items"]]
    rest = client.get("/sandbox/demo/records", params={"limit": 10, "offset": 20}).json()
    assert len(rest["items"]) == 5 and rest["next"] is None
    assert client.get(f"/sandbox/demo/records/{ids[0]}").json() == body["items"][0]
    assert client.get("/sandbox/demo/records/nope").status_code == 404
    other = client.get("/sandbox/other/records").json()["items"]
    assert other[0]["id"] == "other-0001" and len(other) == 25  # every name its own records
    late = client.get("/sandbox/demo/records", params={"updated_since": "2026-10-07T08:59:59Z"}).json()
    assert late["total"] < 25
    assert client.get("/sandbox/Bad Name/records").status_code == 404
    assert client.get("/sandbox/demo/records", params={"limit": 0}).status_code == 400
