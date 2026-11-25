"""Plan 9, P9-3.1: the legacy depot repair log mock (source `repairlog`, an extra system beside the demo's 21).

The generic contract runs in tests/test_generic_specs.py; it is repeated here without the app lifespan. Each test
resets only `repairlog` (its seed reads the fleet mock's returned serials from the same code, not from the database).
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_generic_specs import SPECS, headers
from test_generic_specs import test_contract as contract

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID
from sim.generic.specs.fleet_contracts import build
from sim.main import MOCKS, app

SPEC = next(s for s in SPECS if s.source_id == "repairlog")
BASE = SPEC.base_path


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.post("/_sim/reset", params={"system": "repairlog"}).raise_for_status()
    return c


def every(client, path: str, **params) -> list[dict]:
    out, page = [], 1
    while page is not None:
        r = client.get(BASE + path, headers=headers(client, SPEC), params={"page_size": 200, "page": page, **params})
        assert r.status_code == 200, r.text
        body = r.json()
        out += body["items"]
        page = body["next"]
    return out


@pytest.fixture(scope="module")
def orders(client):
    return every(client, "/repair-orders")


def test_repairlog_is_an_extra_system_not_a_demo_one():
    assert EXTRA_BY_ID["repairlog"].schema == "repairlog" and EXTRA_BY_ID["repairlog"].base_path == "/repairlog/api"
    assert "repairlog" not in BY_SOURCE_ID and "repairlog" in MOCKS


def test_contract_standalone(client):
    contract(client, SPEC)
    client.post("/_sim/reset", params={"system": "repairlog"}).raise_for_status()


def test_needs_basic_auth(client):
    assert client.get(BASE + "/repair-orders").status_code == 401
    assert client.get(BASE + "/repair-orders", auth=("di-connector", "wrong")).status_code == 401


def test_repair_log_seed_has_history_depth(orders):
    closed = [o for o in orders if o["status"] == "closed"]
    assert len(closed) >= 2400
    lo, hi = date(2023, 10, 7), date(2026, 10, 7)
    commonest = max({o["faultCode"] for o in closed if o["toolClass"] == "CMH"}, key=lambda f: sum(
        1 for o in closed if o["toolClass"] == "CMH" and o["faultCode"] == f))  # fmt: skip
    band = [
        o for o in closed
        if o["toolClass"] == "CMH" and 25 <= o["ageMonths"] <= 36 and o["faultCode"] == commonest
        and lo <= date.fromisoformat(o["closedAt"][:10]) <= hi
    ]  # fmt: skip
    assert len(band) >= 50
    for cls in ("CMH", "BRK", "DCD", "CRH", "AGR", "LSR"):
        for a, b in ((1, 24), (25, 36), (37, 60)):
            cell = [o for o in closed if o["toolClass"] == cls and a <= o["ageMonths"] <= b]
            top = {}
            for o in cell:
                top[o["faultCode"]] = top.get(o["faultCode"], 0) + 1
            assert sorted(top.values(), reverse=True)[1] >= 60, (cls, a, b)


def test_repair_order_shape(orders):
    o = next(x for x in orders if x["status"] == "closed")
    assert o["roId"].startswith("DR-5") and o["grade"] in "ABCD" and o["testResult"] in ("pass", "fail")
    assert all({"name", "replaced", "runHoursAtReplacement"} <= set(c) for c in o["components"])
    assert o["labourHours"] > 0 and o["partsCost"] >= 0 and o["labourRate"] > 0
    open_ = [x for x in orders if x["status"] == "open"]
    assert open_ and all(x["grade"] is None and x["testResult"] is None and x["closedAt"] is None for x in open_)
    assert len({x["roId"] for x in orders}) == len(orders)


def test_returned_serials_are_graded_except_the_late_one(orders):
    returned = [r["serial"] for r in build()["returns"]]  # the fleet mock's 18 open returns
    assert len(returned) == 18
    by_serial = {}
    for o in orders:
        by_serial.setdefault(o["serial"], []).append(o)
    for serial in returned:
        graded = [o for o in by_serial[serial] if o["grade"]]
        if serial == "CMH-48213":
            assert not graded and [o["status"] for o in by_serial[serial]] == ["open"]
        else:
            assert len(graded) == 1 and graded[0]["status"] == "closed", serial


def test_teardowns(client):
    td = every(client, "/teardowns")
    assert len(td) == 900
    assert {t["verdict"] for t in td} == {"worn_out", "serviceable"}
    assert all(t["tdId"].startswith("TD-") and t["runHours"] > 0 and t["component"] for t in td)
    one = client.get(BASE + "/teardowns/" + td[0]["tdId"], headers=headers(client, SPEC))
    assert one.status_code == 200 and one.json() == td[0]


def test_repair_log_seed_is_deterministic(client, orders):
    client.post("/_sim/reset", params={"system": "repairlog"}).raise_for_status()
    assert every(client, "/repair-orders") == orders
