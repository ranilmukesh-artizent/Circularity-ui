"""Plan 9 P9-11.2: call the synthetic asset management system (mr_assets) the way a JSON-API client does.

Not a demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`.
Stories: MR-04, MR-09 (age and residual value of the device), MR-17 (devices that hold patient data).
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/asset-management/api"
KEY = {"x-api-key": "mr_assets-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "mr_assets"}).raise_for_status()
        yield c


def devices(client, **params) -> list[dict]:
    r = client.get(f"{API}/devices", params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["mr_assets"]
    assert (s.vendor, s.style, s.base_path) == ("Asset management (synthetic)", "vendor", "/asset-management")
    assert "mr_assets" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "mr_assets" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_asset_mgmt_needs_the_key(client):
    assert client.get(f"{API}/devices").status_code == 401
    assert client.get(f"{API}/devices", headers={"x-api-key": "wrong"}).status_code == 401
    assert client.get(f"{API}/devices/SYN-MR-IP-0001").status_code == 401


def test_asset_mgmt_devices(client):
    rows = devices(client)
    assert len(rows) == 80 and len({r["tag"] for r in rows}) == 80
    assert set(rows[0]) == {
        "tag", "serial", "model", "deviceClass", "manufacturerCode", "inServiceDate", "bookValue", "residualSaleValue",
        "hasPatientData",
    }  # fmt: skip
    one = rows[0]
    assert (one["tag"], one["deviceClass"]) == ("SYN-MR-IP-0001", "infusion_pump")
    assert (one["bookValue"], one["residualSaleValue"]) == (1150, 1100)
    assert one["inServiceDate"] == "2023-10-07"  # 3 years before the demo's as-of date
    assert {r["deviceClass"] for r in rows} == {
        "infusion_pump", "patient_monitor", "electric_bed", "syringe_driver", "transport_ventilator", "pulse_oximeter",
    }  # fmt: skip
    assert {r["hasPatientData"] for r in rows if r["deviceClass"] == "patient_monitor"} == {True}
    assert {r["hasPatientData"] for r in rows if r["deviceClass"] != "patient_monitor"} == {False}
    assert all(r["residualSaleValue"] <= r["bookValue"] for r in rows)
    assert len(devices(client, deviceClass="infusion_pump")) == 50
    assert all(r["tag"].startswith("SYN-MR-") for r in rows)


def test_asset_mgmt_one_device(client):
    r = client.get(f"{API}/devices/SYN-MR-IP-0001", headers=KEY)
    assert r.status_code == 200 and r.json()["serial"] == devices(client)[0]["serial"]
    assert client.get(f"{API}/devices/SYN-MR-IP-9999", headers=KEY).status_code == 404
