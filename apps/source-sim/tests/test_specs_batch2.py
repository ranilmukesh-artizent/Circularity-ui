"""B5, batch 2: system-specific values for ShipLane, Optoro, SafetyCulture, Oracle Depot Repair, Ritchie Bros. and
Machinio (RT-1048 / RT-1049 facts and the demo's MAPPINGS examples). The generic contract runs in
tests/test_generic_specs.py; it is repeated here without the app lifespan, so these systems can be checked on their
own (each test resets only its own system)."""

import statistics

import pytest
from fastapi.testclient import TestClient
from test_generic_specs import SPECS, headers
from test_generic_specs import test_contract as contract

from sim.main import app

MINE = ("tms", "rl", "insp", "repair", "mkt", "dlr")
BY_ID = {s.source_id: s for s in SPECS if s.source_id in MINE}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)  # no lifespan: /_sim/reset?system= builds each schema


def get(client, sid: str, path: str, **params) -> list[dict]:
    spec = BY_ID[sid]
    client.post("/_sim/reset", params={"system": sid}).raise_for_status()
    r = client.get(
        spec.base_path + path,
        headers=headers(client, spec),
        params=params | {spec.paging.size_param if spec.paging.style == "page" else spec.paging.limit_param: 200},
    )
    assert r.status_code == 200, r.text
    return r.json()[spec.paging.items_key]


@pytest.mark.parametrize("sid", MINE)
def test_contract_standalone(client, sid):
    contract(client, BY_ID[sid])


def test_shiplane_lane_and_rate_card(client):
    lane = get(client, "tms", "/lanes", OriginLocationCode="WH-MAA-02", DestinationLocationCode="LOC-CHN-03")
    assert len(lane) == 1  # MAPPINGS.tms: LaneId, RateAmt 3600.00 INR ($43 at 83.5), carrier NLTL
    assert lane[0]["LaneId"] == "WH-MAA-02>LOC-CHN-03" and lane[0]["RateAmt"] == 3600.0 and lane[0]["CarrierSCAC"] == "NLTL"
    assert lane[0]["DistanceKm"] == 34 and round(lane[0]["RateAmt"] / 83.5) == 43
    card = get(client, "tms", "/rate-cards")[0]
    assert card["RateCardId"] == "RC-2026.2" and card["CarrierName"] == "Northline 3PL"
    load = get(client, "tms", "/loads", ReturnReference="RT-1048")
    assert len(load) == 1 and load[0]["ItemId"] == "MTR-2041" and load[0]["DestinationFacilityId"] == "WH01"
    assert load[0]["ETA"].startswith("2026-10-03")


def test_optoro_one_return_per_case(client):
    rows = get(client, "rl", "/returns", CLIENT_REF="RT-1048")
    assert len(rows) == 1 and rows[0]["SKU"] == "MTR-2041" and rows[0]["RECEIVING_FACILITY"] == "WH01"
    assert rows[0]["RECEIVED_AT"].startswith("2026-10-03T") and rows[0]["RECEIVED_AT"].endswith("-04:00")
    ship = get(client, "rl", "/shipments", CLIENT_REF="RT-1048")[0]
    load = get(client, "tms", "/loads", ReturnReference="RT-1048")[0]
    assert ship["TMS_LOAD_ID"] == load["LoadId"] and ship["CARRIER_SCAC"] == load["CarrierSCAC"]


def test_safetyculture_rt_1049(client):
    audits = get(client, "insp", "/audits", asset_id="DRL-0812")
    assert len(audits) == 1
    audits = [a for a in get(client, "insp", "/audits") if a["header_items"]["return_reference"] == "RT-1049"]
    assert len(audits) == 1 and audits[0]["grade_text"] == "Grade B" and audits[0]["media_count"] > 0
    spec = BY_ID["insp"]
    h = headers(client, spec)
    one = client.get(f"{spec.base_path}/audits/{audits[0]['audit_id']}", headers=h)
    assert one.status_code == 200 and one.json()["audit_id"] == audits[0]["audit_id"]
    search = client.get(f"{spec.base_path}/audits/search", headers=h)
    assert search.status_code == 200 and "modified_at" in search.json()["data"][0]
    media = get(client, "insp", "/media", audit_id=audits[0]["audit_id"])
    assert len(media) == audits[0]["media_count"]
    # RT-1048 was inspected by the depot (MRO evidence), not in iAuditor
    assert not [a for a in get(client, "insp", "/audits") if a["header_items"]["return_reference"] == "RT-1048"]


def test_depot_repair_rt_1048(client):
    ro = get(client, "repair", "/repair-orders", serial="MTR-2041")
    assert len(ro) == 1  # MAPPINGS.repair: 1,800.00 USD, "Light repair + test", result B
    ro = ro[0]
    assert (ro["repair_cost"], ro["repair_cost_currency"], ro["scope"], ro["result_state"]) == (
        1800.0,
        "USD",
        "Light repair + test",
        "B",
    )
    assert ro["repair_org"] == "RC01" and ro["current_location"] == "WH01" and ro["receiving_inspection"]["grade"] == "B"
    assert [p["part_number"] for p in ro["parts"]][:2] == ["SKF-6316-2Z/C3", "SKF-6314-2Z/C3"]
    tasks = get(client, "repair", "/repair-tasks", repair_number=ro["repair_number"])
    assert any(t["task_type"] == "Labour" and t["rate"] == 850.0 for t in tasks)
    tests = get(client, "repair", "/repair-test-results", repair_number=ro["repair_number"])
    assert tests and all(t["result"] == "PASS" for t in tests)


def test_ritchie_stale_and_supports_resale(client):
    rows = get(client, "mkt", "/comparables", SUBJECT_ASSET="MTR-2041")
    assert len(rows) == 48  # "48 comparable sales"
    assert statistics.median(r["SOLD_PRC_AMT"] for r in rows) == pytest.approx(5600 * 83.5, abs=1)
    assert any(r["SOLD_PRC"] == "8.1 L INR" and r["DAYS_LISTED"] == 17 and r["CONDITION"] == "VG" for r in rows)
    allrows = get(client, "mkt", "/comparables", ASSET_CLASS="DRILL")
    assert max(r["SOLD_DT"] for r in allrows) < "2026-10-06"
    drill = [r for r in allrows if r["COMP_ID"].startswith("RBC-1049-")]
    assert len(drill) == 31 and statistics.median(r["SOLD_PRC_AMT"] for r in drill) == pytest.approx(241 * 83.5, abs=1)
    idx = get(client, "mkt", "/price-index", ASSET_CLASS="MOTOR")
    assert max(i["PERIOD"] for i in idx) == "2026-09"


def test_machinio_offers_and_listings(client):
    offers = get(client, "dlr", "/offers", asset_ref="MTR-2041")
    assert len(offers) == 1 and offers[0]["offer_amount"] == 5600.0
    fees = offers[0]["fees"]
    assert fees["freight_inr"] + fees["channel_fee_inr"] == round(800 * 83.5)
    firm = get(client, "dlr", "/offers", status="firm")
    assert any(o["offer_amount"] == 460.0 for o in firm)  # RT-1033 "Offer from dealer"
    listings = get(client, "dlr", "/listings", subject_asset="DRL-0812")
    grade_a = [x for x in listings if x["grade"] == "A"]
    assert len(grade_a) == 14 and all(x["status"] == "active" for x in listings)  # RT-1049: "Grade A listings: 14 open"
