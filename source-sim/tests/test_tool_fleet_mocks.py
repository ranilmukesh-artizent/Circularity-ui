"""Plan 9, P9-3.2: the recall register (`recall`), connected-tool telematics (`tooltel`) and tool service, stock and trade
demand (`parts`) mocks, three extra systems beside the demo's 21.

The generic contract (auth, paging, filters, bad parameter) runs in tests/test_generic_specs.py; it is repeated here
without the app lifespan so each system can be checked on its own. Each module-level fixture resets only its system.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_generic_specs import SPECS, headers
from test_generic_specs import test_contract as contract

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID
from sim.generic.specs.fleet_contracts import build as fleet_build
from sim.main import MOCKS, app

SPEC = {s.source_id: s for s in SPECS if s.source_id in ("recall", "tooltel", "parts")}
RECALL, TEL, PARTS = SPEC["recall"], SPEC["tooltel"], SPEC["parts"]
CLASSES = ("CMH", "BRK", "DCD", "CRH", "AGR", "LSR")
PACK_PARTS = {  # tool_fleet.json classes.<cls>.parts
    "CMH": ("Motor armature", "Gearbox", "Electronics module", "Piston and seal kit"),
    "BRK": ("Motor", "Impact mechanism", "Chisel holder", "Handle and vibration damper"),
    "DCD": ("Drill motor", "Gearbox", "Drill stand", "Control electronics"),
    "CRH": ("Brushless motor", "Electronics module", "Chuck assembly"),
    "AGR": ("Armature", "Gear set", "On/off switch"),
    "LSR": ("Laser module", "Rotor head", "Receiver"),
}


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    for sid in SPEC:
        c.post("/_sim/reset", params={"system": sid}).raise_for_status()
    return c


def every(client, spec, path: str, **params) -> list[dict]:
    out, offset = [], 0
    while offset is not None:
        r = client.get(spec.base_path + path, headers=headers(client, spec), params={"limit": 200, "offset": offset, **params})
        assert r.status_code == 200, r.text
        body = r.json()
        out += body["items"]
        offset = body["next"]
    return out


def test_the_three_are_extra_systems_not_demo_ones():
    for sid, base in (("recall", "/recalls/api"), ("tooltel", "/tooltel/v2"), ("parts", "/parts/api")):
        assert EXTRA_BY_ID[sid].schema == sid and EXTRA_BY_ID[sid].base_path == base
        assert sid not in BY_SOURCE_ID and sid in MOCKS
    assert len(BY_SOURCE_ID) == 21
    assert RECALL.title == "Safety recall register (synthetic)" and TEL.title == "Connected-tool telematics (synthetic)"
    assert PARTS.title == "Tool service, stock and trade demand (synthetic)"
    assert (RECALL.auth.kind, TEL.auth.kind, PARTS.auth.kind) == ("api_key", "oauth_cc", "api_key")


@pytest.mark.parametrize("sid", ["recall", "tooltel", "parts"])
def test_contract_standalone(client, sid):
    contract(client, SPEC[sid])
    client.post("/_sim/reset", params={"system": sid}).raise_for_status()


@pytest.mark.parametrize("sid", ["recall", "parts"])
def test_needs_the_api_key(client, sid):
    first = SPEC[sid].resources[0]
    assert client.get(SPEC[sid].base_path + first.path).status_code == 401
    assert client.get(SPEC[sid].base_path + first.path, headers={SPEC[sid].auth.header: "wrong"}).status_code == 401


def test_telematics_needs_a_bearer_token(client):
    assert client.get(TEL.base_path + "/tools").status_code == 401
    assert client.get(TEL.base_path + "/tools", headers={"Authorization": "Bearer nope"}).status_code == 401


# ------------------------------------------------------------------ recalls
def test_recall_notices_fixtures(client):
    notices = {n["recallId"]: n for n in every(client, RECALL, "/notices")}
    a, b = notices["RC-2026-014"], notices["RC-2026-017"]
    assert (a["toolClass"], a["serialFrom"], a["serialTo"], a["remedy"], a["affectedParts"], a["status"]) == (
        "CRH", "CRH-44000", "CRH-44999", "replace", ["Brushless motor"], "active",
    )  # fmt: skip
    assert (b["toolClass"], b["serialFrom"], b["serialTo"], b["remedy"], b["affectedParts"], b["status"]) == (
        "BRK", "BRK-51000", "BRK-51999", "repair", ["Impact mechanism"], "active",
    )  # fmt: skip
    for n in notices.values():
        assert n["recallId"].startswith("RC-2026-0") and n["remedy"] in ("repair", "replace", "refund")
        assert n["status"] in ("active", "closed") and date.fromisoformat(n["publishedAt"][:10])
        assert set(n["affectedParts"]) <= set(PACK_PARTS[n["toolClass"]]), n  # component names of the pack's class
        assert n["serialFrom"].startswith(n["toolClass"]) and n["serialFrom"] <= n["serialTo"]


# ------------------------------------------------------------------ telematics
def test_telematics_fixtures(client):
    tools = {t["serial"]: t for t in every(client, TEL, "/tools")}
    t = tools["CMH-48213"]
    assert (t["runHours"], t["highLoadShare"], t["events"], t["coveragePct"]) == (
        820, 0.30, {"overheat": 0, "drop": 0, "overload": 0}, 95,
    )  # fmt: skip
    assert t["lastSeen"].startswith("2026-10-04")
    assert tools["CMH-48777"]["lastSeen"].startswith("2026-09-29")  # eight days before 2026-10-07
    assert tools["CRH-44120"]["coveragePct"] == 80
    for t in tools.values():
        assert set(t["events"]) == {"overheat", "drop", "overload"} and 0 <= t["highLoadShare"] <= 1
        assert 0 <= t["coveragePct"] <= 100 and t["runHours"] >= 0


def test_thirty_fleet_serials_have_no_telematics(client):
    tools = {t["serial"] for t in every(client, TEL, "/tools")}
    serials = {ln["serial"] for ln in fleet_build()["lines"]}
    assert len(serials - tools) == 30
    assert {"CMH-48213", "CRH-44120", "BRK-51007", "AGR-20991"} <= tools  # the named ones are connected


# ------------------------------------------------------------------ parts, stock and trade demand
def test_parts_seed_sizes_and_shapes(client):
    ros = every(client, PARTS, "/repair-orders/open")
    assert len(ros) == 120 and all(r["roId"].startswith("RO-6") for r in ros)
    for r in ros:
        assert r["partName"] in PACK_PARTS[r["toolClass"]] and isinstance(r["backorder"], bool) and r["customer"]
        assert date.fromisoformat(r["needBy"][:10])
    assert any(r["backorder"] for r in ros) and not all(r["backorder"] for r in ros)
    cat = every(client, PARTS, "/catalogue")
    assert len(cat) == 90 and all(c["partNo"] and c["price"] > 0 and c["market"] and c["toolClass"] in CLASSES for c in cat)
    assert all(c["partName"] in PACK_PARTS[c["toolClass"]] for c in cat)
    units = every(client, PARTS, "/refurbished-units")
    assert len(units) == 48 and all(u["unitId"].startswith("RU-7") for u in units)
    for cls in CLASSES:
        mine = [u for u in units if u["toolClass"] == cls]
        assert len(mine) == 8 and all(35 <= u["rulPct"] <= 85 for u in mine)
    assert {u["status"] for u in units} == {"available", "reserved"} and all(u["grade"] in "ABCD" for u in units)
    sos = every(client, PARTS, "/sales-orders")
    assert len(sos) == 20 and all(s["soId"].startswith("SO-8") and s["price"] > 0 and s["site"] for s in sos)
    pool = every(client, PARTS, "/pool-requests")
    assert len(pool) == 10 and all(p["requestId"].startswith("TPR-") and p["quoteRef"].startswith("PR-") for p in pool)
    assert all(p["avoidedPurchase"] > 0 for p in pool)
    bids = every(client, PARTS, "/trade-bids")
    assert len(bids) == 30 and all(b["bidId"].startswith("BID-") and b["dealer"] and b["gradeMin"] in "ABCD" for b in bids)
    assert all(b["price"] > 0 and date.fromisoformat(b["expires"][:10]) for b in bids)


def test_parts_filters_and_one_document(client):
    units = every(client, PARTS, "/refurbished-units", toolClass="CRH")
    assert len(units) == 8
    one = client.get(PARTS.base_path + "/refurbished-units/" + units[0]["unitId"], headers=headers(client, PARTS))
    assert one.status_code == 200 and one.json() == units[0]


def test_seeds_are_deterministic(client):
    before = {sid: {r.path: every(client, spec, r.path) for r in spec.resources} for sid, spec in SPEC.items()}
    for sid in SPEC:
        client.post("/_sim/reset", params={"system": sid}).raise_for_status()
    after = {sid: {r.path: every(client, spec, r.path) for r in spec.resources} for sid, spec in SPEC.items()}
    assert before == after
