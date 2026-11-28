"""Plan 9, P9-3.1: the fleet contract system mock (source `fleet`, an extra system beside the demo's 21).

The generic contract (auth, paging, filters, create, bad parameter) runs in tests/test_generic_specs.py; it is repeated
here without the app lifespan so this system can be checked on its own. Each test resets only `fleet`.
"""

import pytest
from fastapi.testclient import TestClient
from test_generic_specs import SPECS, headers
from test_generic_specs import test_contract as contract

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID
from sim.main import MOCKS, app

SPEC = next(s for s in SPECS if s.source_id == "fleet")
BASE = SPEC.base_path


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)  # no lifespan: /_sim/reset?system= builds the schema
    c.post("/_sim/reset", params={"system": "fleet"}).raise_for_status()
    return c


def get(client, path: str, **params) -> dict:
    r = client.get(BASE + path, headers=headers(client, SPEC), params=params)
    assert r.status_code == 200, r.text
    return r.json()


def every(client, path: str, **params) -> list[dict]:
    out, offset = [], 0
    while offset is not None:
        page = get(client, path, limit=200, offset=offset, **params)
        out += page["items"]
        offset = page["next"]
    return out


def test_fleet_is_an_extra_system_not_a_demo_one():
    assert EXTRA_BY_ID["fleet"].schema == "fleet" and EXTRA_BY_ID["fleet"].base_path == "/fleet/api/v1"
    assert "fleet" not in BY_SOURCE_ID and len(BY_SOURCE_ID) == 21 and "fleet" in MOCKS


def test_contract_standalone(client):
    contract(client, SPEC)
    client.post("/_sim/reset", params={"system": "fleet"}).raise_for_status()


def test_needs_the_api_key(client):
    assert client.get(BASE + "/contracts").status_code == 401
    assert client.get(BASE + "/contracts", headers={"x-api-key": "wrong"}).status_code == 401


def test_fleet_mock_serves_named_fixtures(client):
    items = get(client, "/contract-lines", serial="CMH-48213")["items"]
    assert len(items) == 1
    line = items[0]
    assert (line["contractId"], line["status"], line["returnReason"], line["lineId"]) == (
        "FC-30117", "returned", "end_of_term", "FL-30117-03",
    )  # fmt: skip
    c = get(client, "/contracts/FC-30117")
    assert (c["customer"], c["market"], c["status"], c["endDate"], c["noticeDate"], c["keyAccount"]) == (
        "Brightline Mechanical", "US", "active", "2027-01-05", None, False,
    )  # fmt: skip
    assert len(c["lineIds"]) == 14 and "FL-30117-03" in c["lineIds"] and c["rateCardVersion"] == "v4"
    g = get(client, "/contracts/FC-30121")
    assert (g["customer"], g["market"], g["endDate"], g["noticeDate"]) == ("Granite Civil", "DE", "2027-06-30", "2027-01-05")
    w = get(client, "/contracts/FC-30140")
    assert w["customer"] == "Westmark Supply" and w["keyAccount"] is True
    swap = get(client, "/contract-lines", serial="CRH-44120")["items"][0]
    assert (swap["contractId"], swap["returnReason"]) == ("FC-30140", "swap")
    theft = get(client, "/contract-lines", serial="BRK-51007")["items"][0]
    assert (theft["returnReason"], theft["theftClaimOpen"], theft["claimRef"]) == ("theft_recovered", True, "CLM-7781")
    lost = get(client, "/contract-lines", serial="AGR-20991")["items"][0]
    assert (lost["status"], lost["nonReturnFee"]) == ("closed_not_returned", 180)
    r = get(client, "/renewals/FC-30117-R")
    assert (r["toolClass"], r["site"], r["rateMonth"], r["termMonths"], r["kind"], r["needBy"]) == (
        "CMH", "Houston", 55, 12, "lease", "2026-10-26",
    )  # fmt: skip


def test_fleet_seed_sizes(client):
    contracts = every(client, "/contracts")
    lines = every(client, "/contract-lines")
    assert len(contracts) == 41 and len(lines) == 403  # 40 + FC-30141, the service desk's 71 tools
    assert sum(1 for x in lines if x["toolClass"] == "BAT") == 12
    assert {x["toolClass"] for x in lines} == {"CMH", "BRK", "DCD", "CRH", "AGR", "LSR", "BAT"}
    assert len({x["serial"] for x in lines}) == 403
    assert len(every(client, "/returns")) == 18 and len(every(client, "/renewals")) == 25
    assert len(every(client, "/contract-history")) == 60
    assert every(client, "/proposals") == [] and every(client, "/draft-lines") == []
    assert {c["status"] for c in contracts} == {"active", "evergreen", "ended", "terminated"}
    assert {c["market"] for c in contracts} <= {"DE", "UK", "US", "AU", "FR"}
    assert sum(1 for c in contracts if c["noticeDate"]) <= 8
    ids = {x["lineId"] for x in lines}
    assert all(set(c["lineIds"]) <= ids for c in contracts)


def test_fleet_holds_an_active_line_for_every_service_desk_tool(client):
    """Every serial the service desk's tickets name has an active line of FC-30141, a US contract of Fleet North America,
    so GR-07 passes for the tickets' tools (P9-4); the contract adds no return or renewal."""
    from sim.vendors.servicenow.seed import ticket_serials

    serials = ticket_serials()
    assert len(serials) == 71 and {"CRH-46042", "CMH-45000", "CRH-45021"} <= set(serials)
    by_serial = {x["serial"]: x for x in every(client, "/contract-lines")}
    for s in serials:
        ln = by_serial[s]
        got = (ln["contractId"], ln["status"], ln["damageChargeOpen"], ln["theftClaimOpen"])
        assert got == ("FC-30141", "active", False, False), s
    c = get(client, "/contracts/FC-30141")
    assert (c["market"], c["ownerOrg"], c["status"], c["keyAccount"], c["renewalStatus"]) == (
        "US", "Fleet North America", "active", False, None,
    )  # fmt: skip
    assert len(c["lineIds"]) == 71
    assert not any(r["contractId"] == "FC-30141" for r in every(client, "/returns") + every(client, "/renewals"))


def test_fleet_returns_match_their_lines(client):
    by_serial = {x["serial"]: x for x in every(client, "/contract-lines")}
    rets = every(client, "/returns")
    assert {r["kind"] for r in rets} <= {"contract_end", "swap", "service_order", "pool_excess"}
    assert {r["site"] for r in rets} <= {"Houston", "Denver", "Atlanta", "Chicago", "Phoenix"}
    for r in rets:
        ln = by_serial[r["serial"]]
        assert ln["status"] == "returned" and ln["lineId"] == r["lineId"] and ln["contractId"] == r["contractId"]
    assert next(r for r in rets if r["serial"] == "CMH-48213")["site"] == "Houston"


def test_fleet_seed_is_deterministic(client):
    before = every(client, "/contract-lines")
    client.post("/_sim/reset", params={"system": "fleet"}).raise_for_status()
    assert every(client, "/contract-lines") == before


def test_fleet_mock_delta_and_paging(client):
    client.post("/_sim/reset", params={"system": "fleet"}).raise_for_status()
    first = get(client, "/contract-lines", limit=50, offset=0)
    assert len(first["items"]) == 50 and first["next"] == 50 and first["total"] == 403
    second = get(client, "/contract-lines", limit=50, offset=first["next"])
    assert second["items"][0]["lineId"] != first["items"][0]["lineId"]
    seen, nxt = [], 0
    while nxt is not None:
        page = get(client, "/contract-lines", limit=200, offset=nxt)
        seen += page["items"]
        nxt = page["next"]
    assert len(seen) == 403
    since = "2026-10-07T09:00:00Z"
    assert get(client, "/contract-lines", updated_since=since)["total"] == 0
    r = client.patch(BASE + "/contract-lines/FL-30117-03", headers=headers(client, SPEC), json={"damageChargeOpen": True})
    assert r.status_code == 200 and r.json()["damageChargeOpen"] is True
    delta = get(client, "/contract-lines", updated_since=since)
    assert delta["total"] == 1 and delta["items"][0]["lineId"] == "FL-30117-03"
    client.post("/_sim/reset", params={"system": "fleet"}).raise_for_status()


def test_fleet_proposals_and_draft_lines_are_created_by_clients(client):
    h = headers(client, SPEC)
    made = client.post(BASE + "/proposals", headers=h, json={"contractId": "FC-30117"})
    assert made.status_code == 201 and made.json()["proposalId"].startswith("FP-")
    draft = client.post(BASE + "/draft-lines", headers=h, json={"proposalId": made.json()["proposalId"]})
    assert draft.status_code == 201 and draft.json()["draftLineId"].startswith("FD-")
    client.post("/_sim/reset", params={"system": "fleet"}).raise_for_status()
