"""Plan 9 P9-12.6: call the synthetic subscriber returns and CPE refurbishment mock (cpe_bss): returns, factory resets, lot grades
and the new-subscriber forecast. The mock is no demo source (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`.
Stories NS-CPE-01 to NS-CPE-03. Subscriber references are codes only.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/cpe-returns/api"
KEY = {"x-api-key": "cpe_bss-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "cpe_bss"}).raise_for_status()
        yield c


def get(client, path: str, **params):
    r = client.get(f"{API}/{path}", params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["cpe_bss"]
    assert (s.vendor, s.style, s.base_path) == ("Subscriber returns and CPE refurbishment (synthetic)", "vendor", "/cpe-returns")
    assert "cpe_bss" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "cpe_bss" in MOCKS


def test_every_path_needs_the_key(client):
    for path in ("returns", "factory-resets", "lot-grades", "new-subscriber-forecast"):
        assert client.get(f"{API}/{path}").status_code == 401
        assert client.get(f"{API}/{path}", headers={"x-api-key": "wrong"}).status_code == 401


def test_returns_carry_codes_only(client):
    rows = get(client, "returns")
    assert len(rows) == 1400 and set(rows[0]) == {"serial", "model", "reason", "subscriberRef", "returnedAt"}
    assert {r["reason"] for r in rows} <= {"upgrade", "contract_end", "fault_swap"}
    assert all(r["subscriberRef"].startswith("SUB-") for r in rows)


def test_lot_w47_has_three_serials_without_a_reset(client):
    lots = {x["lotId"]: x for x in get(client, "lot-grades")}
    assert {k: len(v["serials"]) for k, v in lots.items()} == {"LOT-R7-B-W47": 500, "LOT-R7-B-W48": 900}
    assert lots["LOT-R7-B-W47"]["grade"] == "B" and lots["LOT-R7-B-W47"]["model"] == "R7"
    done = {r["serial"] for r in get(client, "factory-resets")}
    assert [s for s in lots["LOT-R7-B-W47"]["serials"] if s not in done] == ["SN-CPE-R7-0101", "SN-CPE-R7-0202", "SN-CPE-R7-0303"]
    assert all(s in done for s in lots["LOT-R7-B-W48"]["serials"])
    one = get(client, "factory-resets", serial="SN-CPE-R7-0001")
    assert [(r["serial"], r["method"], r["firmwareRefreshed"]) for r in one] == [("SN-CPE-R7-0001", "factory_reset", True)]


def test_forecast_and_seed_are_stable(client):
    fc = get(client, "new-subscriber-forecast")
    assert {(r["model"], r["week"]) for r in fc} == {("R7", "2026-W47"), ("R7", "2026-W48")} and all(r["units"] > 0 for r in fc)
    before = [get(client, p) for p in ("returns", "factory-resets", "lot-grades")]
    client.post("/_sim/reset", params={"system": "cpe_bss"}).raise_for_status()
    assert [get(client, p) for p in ("returns", "factory-resets", "lot-grades")] == before
