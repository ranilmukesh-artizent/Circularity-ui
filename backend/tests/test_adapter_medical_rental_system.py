"""Plan 9, P9-11.2: the rental system (source `mr_rental`) adapter against source-sim's synthetic rental mock.

`mr_rental` is no demo source: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. Registered (di.connectors.extra) and synced, it fills `asset.*` and `demand.*` facts keyed by
`tag_key(org unit, tag)`. The mapping tests run on literal records; the sync test needs source-sim running with the mock
(restart it after the change, R14) and is skipped, with the reason, when it lacks it.

The module starts and ends with the demo reset (tests/starting.py), which removes the sources it registered, and removes
the facts it wrote.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.adapters.medical_rental_system import haversine_miles
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.connectors.sync import run_sync
from di.core import golden
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store
from di.services.canonical.schema import check_fact, tag_key
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "mr_rental"
API = SIM + "/rental-system/api"
KEY = {"x-api-key": "mr_rental-demo-key"}
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
ORG = "Customer A"
TAG = "SYN-MR-IP-0001"
EAST = {"depotId": "EAST", "latitude": 40.0, "longitude": -75.0, "region": "EAST"}


def _request(req_id: str, hospital: str, lat: float, lon: float) -> dict:
    return {
        "reqId": req_id, "hospitalId": hospital, "deviceClass": "infusion_pump", "startDate": "2026-11-27", "days": 30,
        "region": "EAST", "requestedAt": "2026-11-25T14:00:00+00:00", "latitude": lat, "longitude": lon,
    }  # fmt: skip


DEMAND = {
    "tag": TAG, "depot": EAST, "org_unit_id": ORG,
    "requests": [
        _request("REQ-1", "HOSP-A", 40.1737, -75.0),
        _request("REQ-2", "HOSP-B", 40.0, -74.9054),
        _request("REQ-3", "HOSP-C", 39.3053, -75.0),
    ],
    "forecast": [
        {"region": "EAST", "weekStart": "2026-11-30", "requests": 24},
        {"region": "EAST", "weekStart": "2026-12-07", "requests": 12},
    ],
}  # fmt: skip
RETURN = {
    "returnId": "RET-0010", "tag": "SYN-MR-IP-0010", "hospitalId": "HOSP-D", "ward": "Isolation Ward 1", "wardType": "isolation",
    "depot": "EAST", "checkedInAt": "2026-11-17T06:00:00+00:00", "previousRentalEnd": "2026-11-16", "org_unit_id": ORG,
}  # fmt: skip


def _row(n: int, total: float, decon: float, service: float) -> dict:
    return {
        "returnId": f"RET-{n:04d}", "tag": f"SYN-MR-IP-{n:04d}", "depot": "EAST", "checkedInAt": "2026-11-20T06:00:00+00:00",
        "waitingDays": {"decon_queue": decon, "service": service, "transport": round(total - decon - service, 1)},
        "totalDays": total,
    }  # fmt: skip


TURNAROUND = {
    "tag": TAG, "org_unit_id": ORG, "depot": "EAST", "days": 14,
    "own": _row(1, 3.0, 1.8, 0.6),
    "rows": [_row(1, 3.0, 1.8, 0.6), _row(2, 3.8, 2.4, 0.8)],
}  # fmt: skip


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["mr_assets", "mr_rental"]})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYN-MR-%"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/returns", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the rental system mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


# ------------------------------------------------------------------ mapping (literal records)
def test_haversine_miles():
    assert haversine_miles(40.0, -75.0, 40.0, -75.0) == 0
    assert round(haversine_miles(40.0, -75.0, 41.0, -75.0), 1) == 69.1  # one degree of latitude


def test_adapters_medical_rental_map_facts():
    """Distances 12, 5 and 48 miles from East for SYN-MR-IP-0001, by the haversine formula, whole miles."""
    facts = ADAPTERS[SID].map(Record("demand", TAG, DEMAND))
    assert {f.key for f in facts} == {tag_key(ORG, TAG)} and {f.model for f in facts} == {"demand"}
    by = {f.field: f.value for f in facts}
    reqs = by["rental_requests"]
    assert [(r["req_id"], r["hospital_id"], r["distance_miles"]) for r in reqs] == [
        ("REQ-1", "HOSP-A", 12),
        ("REQ-2", "HOSP-B", 5),
        ("REQ-3", "HOSP-C", 48),
    ]
    assert all(isinstance(r["distance_miles"], int) for r in reqs)
    assert (reqs[0]["device_class"], reqs[0]["start_date"], reqs[0]["days"]) == ("infusion_pump", "2026-11-27", 30)
    assert by["region_forecast"] == [{"week_start": "2026-11-30", "requests": 24}, {"week_start": "2026-12-07", "requests": 12}]
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_medical_rental_maps_return_facts():
    facts = ADAPTERS[SID].map(Record("returns", "RET-0010", RETURN))
    assert {f.key for f in facts} == {tag_key(ORG, "SYN-MR-IP-0010")} and {f.model for f in facts} == {"asset"}
    by = {f.field: f.value for f in facts}
    assert by == {
        "tag": "SYN-MR-IP-0010", "depot": "EAST", "checked_in_at": "2026-11-17T06:00:00+00:00", "hospital": "HOSP-D",
        "ward_type": "isolation",
    }  # fmt: skip
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_medical_rental_maps_turnaround():
    facts = ADAPTERS[SID].map(Record("turnaround", "RET-0001", TURNAROUND))
    assert {f.key for f in facts} == {tag_key(ORG, TAG)} and [f.field for f in facts] == ["turnaround"]
    t = facts[0].value
    assert (t["depot"], t["window_days"], t["returns"], t["avg_days"]) == ("EAST", 14, 2, 3.4)
    assert t["by_cause_avg_days"] == {"decon_queue": 2.1, "service": 0.7, "transport": 0.6}
    assert t["own_days"] == 3.0 and t["own_waiting_days"] == {"decon_queue": 1.8, "service": 0.6, "transport": 0.6}
    assert check_fact(facts[0]) is None


def test_adapter_medical_rental_without_an_org_unit_is_shared():
    facts = ADAPTERS[SID].map(Record("demand", TAG, DEMAND | {"org_unit_id": None}))
    assert {f.key for f in facts} == {tag_key(None, TAG)}


def test_adapter_medical_rental_is_registered_unconnected():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "rental"
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and SID not in ids
    assert run_sync(SID, "manual")["status"] == "skipped"


# ------------------------------------------------------------------ a sync against the mock
@needs_mock
def test_adapter_medical_rental_sync_against_the_mock():
    """After register(s, "mr_rental", "Customer A") and a sync, the returns hold depot, demand and turnaround facts."""
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    asset = canonical("asset", tag_key(ORG, TAG))["data"]
    assert (asset["tag"], asset["depot"], asset["hospital"], asset["ward_type"]) == (TAG, "EAST", "HOSP-A", "general")
    assert canonical("asset", tag_key(ORG, "SYN-MR-IP-0011"))["data"]["ward_type"] == "isolation"
    assert asset["turnaround"]["depot"] == "EAST" and asset["turnaround"]["avg_days"] == 3.4
    demand = canonical("demand", tag_key(ORG, TAG))["data"]
    assert [(r["req_id"], r["distance_miles"]) for r in demand["rental_requests"]] == [
        ("REQ-1", 12),
        ("REQ-2", 5),
        ("REQ-3", 48),
        ("REQ-4", 5),
    ]
    assert len(demand["region_forecast"]) == 8
    assert min(demand["region_forecast"], key=lambda w: w["requests"])["week_start"] == "2026-12-07"
    west = canonical("asset", tag_key(ORG, "SYN-MR-IP-0024"))["data"]
    assert west["depot"] == "WEST" and west["turnaround"]["avg_days"] == 1.6
