"""B5b contract tests: call the Oracle Lease and Finance Management mock as an EBS Integrated SOA Gateway REST client."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.core.db import engine
from sim.main import app
from sim.seed import seed
from sim.vendors.oracle_lease import routes

REST = "/oracle-lease/webservices/rest"
Q = REST + "/xxoklleasequery"
USER = ("DI_CONNECTOR", "lease-demo-password")


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.post("/_sim/reset", params={"system": "lease"}).raise_for_status()
    yield c
    c.post("/_sim/reset", params={"system": "lease"}).raise_for_status()


def out(r) -> dict:
    assert r.status_code == 200, r.text
    return r.json()["OutputParameters"]


def rows(client, method: str, name: str, **params) -> list[dict]:
    o = out(client.get(f"{Q}/{method}/", auth=USER, params=params | {"P_MAX_RECORDS": 500}))
    assert o["X_RETURN_STATUS"] == "S"
    return o[name][f"{name}_ITEM"]


def asset_return(client, method: str, rec: dict) -> dict:
    body = {
        f"{method.upper()}_Input": {
            "RESTHeader": {"RespApplication": "OKL"},
            "InputParameters": {"P_API_VERSION": "1.0", "P_ARTV_REC": rec},
        }
    }
    return out(client.post(f"{REST}/oklamassetreturn/{method}/", auth=USER, json=body))


def outbox(type_: str) -> list[dict]:
    with engine.connect() as conn:
        q = text("SELECT data FROM sim.outbox WHERE source = 'lease' AND type = :t ORDER BY id")
        return [r.data for r in conn.execute(q, {"t": type_})]


def test_auth_and_faults(client):
    r = client.get(Q + "/get_contracts/")
    assert r.status_code == 401 and r.json()["ISGServiceFault"]["Code"] == "ISG_USER_AUTHENTICATION_FAILED"
    login = client.get(REST + "/login", auth=USER).json()["data"]
    tc = TestClient(app, cookies={login["accessTokenName"]: login["accessToken"]})
    assert tc.get(Q + "/get_contracts/", params={"P_MAX_RECORDS": 1}).status_code == 200
    assert client.get(REST + "/oklamassetreturn/create_asset_return/", auth=USER).status_code == 405


def test_lease_mapping_example(client):
    (c,) = rows(client, "get_contracts", "X_CONTRACTS", P_ASSET_NUMBER="MTR-2041")
    assert (c["LEASE_CONTRACT_ID"], c["CONTRACT_END_DATE"], c["LESSEE_NAME"]) == ("LC-004417", "2026-12-31", "CUSTOMER_A")
    assert (c["MONTHLY_RENTAL"], c["CURRENCY_CODE"], c["CONTRACT_STATUS"]) == (2400.0, "USD", "BOOKED")
    (r,) = rows(client, "get_renewals", "X_RENEWALS", P_ASSET_NUMBER="MTR-2041")
    assert (r["LEASE_OPPORTUNITY_ID"], r["STATUS"], r["PROPOSED_TERM_MONTHS"]) == ("LS-5530", "FORECAST", 30)
    (a,) = rows(client, "get_lease_assets", "X_ASSETS", P_ASSET_NUMBER="MTR-2077")  # conflict CF-31: lease says A
    assert a["OWNER_NAME"] == "CUSTOMER_A" and a["LEASE_STATUS"] == "ON_LEASE"
    assert len(rows(client, "get_renewals", "X_RENEWALS")) == sum(1 for c in seed().cases.values() if c.facts.demand.lease)
    (ret,) = rows(client, "get_asset_returns", "X_ASSET_RETURNS", P_ASSET_NUMBER="MTR-2041")
    assert ret["ARS_CODE"] == "RETURNED" and ret["CONTRACT_NUMBER"] == "LC-004417"


def test_paging_and_delta(client):
    o = out(client.get(Q + "/get_contracts/", auth=USER, params={"P_START_INDEX": 1, "P_MAX_RECORDS": 5}))
    assert o["X_HAS_MORE"] == "Y" and int(o["X_TOTAL_COUNT"]) >= 129
    newest = max(c["LAST_UPDATE_DATE"] for c in rows(client, "get_contracts", "X_CONTRACTS"))
    assert rows(client, "get_contracts", "X_CONTRACTS", P_LAST_UPDATE_DATE_FROM=newest) == []


def test_asset_return_validation(client):
    assert asset_return(client, "create_asset_return", {})["X_RETURN_STATUS"] == "E"
    assert asset_return(client, "create_asset_return", {"KLE_ID": 1})["X_RETURN_STATUS"] == "E"
    (a,) = rows(client, "get_lease_assets", "X_ASSETS", P_ASSET_NUMBER="MTR-2041")
    o = asset_return(client, "create_asset_return", {"KLE_ID": a["KLE_ID"], "ARS_CODE": "RETURNED"})
    assert o["X_RETURN_STATUS"] == "E" and "already" in o["X_MSG_DATA"]
    (b,) = rows(client, "get_lease_assets", "X_ASSETS", P_ASSET_NUMBER="MTR-2077")
    assert asset_return(client, "create_asset_return", {"KLE_ID": b["KLE_ID"], "ARS_CODE": "LOST"})["X_RETURN_STATUS"] == "E"
    future = asset_return(
        client, "create_asset_return", {"KLE_ID": b["KLE_ID"], "ARS_CODE": "RETURNED", "DATE_RETURNED": "2099-01-01"}
    )
    assert future["X_RETURN_STATUS"] == "E"


def test_asset_return_then_term_end(client):
    (a,) = rows(client, "get_lease_assets", "X_ASSETS", P_ASSET_NUMBER="MTR-2077")
    o = asset_return(client, "create_asset_return", {"KLE_ID": a["KLE_ID"], "ART1_CODE": "TERM_EXPIRATION"})
    assert o["X_RETURN_STATUS"] == "S" and o["X_ARTV_REC"]["ARS_CODE"] == "SCHEDULED"
    assert rows(client, "get_lease_assets", "X_ASSETS", P_ASSET_NUMBER="MTR-2077")[0]["LEASE_STATUS"] == "ON_LEASE"
    o = asset_return(client, "update_asset_return", {"KLE_ID": a["KLE_ID"], "ARS_CODE": "RETURNED"})
    assert o["X_RETURN_STATUS"] == "S"
    (a,) = rows(client, "get_lease_assets", "X_ASSETS", P_ASSET_NUMBER="MTR-2077")
    assert a["LEASE_STATUS"] == "RETURNED" and a["RETURN_DATE"]
    assert asset_return(client, "update_asset_return", {"KLE_ID": a["KLE_ID"], "ARS_CODE": "RETURNED"})["X_RETURN_STATUS"] == "E"
    assert outbox("oracle.apps.okl.am.asset_return.returned")[-1]["ASSET_NUMBER"] == "MTR-2077"
    with engine.connect() as conn:
        due = conn.execute(
            text("SELECT payload FROM sim.scheduled WHERE source = 'lease' AND handler = 'okl.contract.term_end' AND NOT done")
        ).scalars()
        assert {"CONTRACT_NUMBER": "LC-005077"} in list(due)
    # the expiration run after 2027-03-31: LC-005077 (asset back) expires; a booked contract whose asset is still out
    # would go evergreen. Run it for a date past every seeded end date.
    with engine.begin() as conn:
        changed = routes.process_term_ends(conn, date(2028, 1, 1))
    assert "LC-005077" in changed and "LC-004417" in changed
    (c,) = rows(client, "get_contracts", "X_CONTRACTS", P_CONTRACT_NUMBER="LC-005077")
    assert c["CONTRACT_STATUS"] == "EXPIRED"
    assert {e["CONTRACT_NUMBER"] for e in outbox("oracle.apps.okl.la.contract.expired")} >= {"LC-005077", "LC-004417"}
    client.post("/_sim/reset", params={"system": "lease"}).raise_for_status()


def test_unreturned_asset_goes_evergreen_then_terminates_on_return(client):
    with engine.begin() as conn:  # put MTR-2077's contract past its end with the asset still out
        routes.process_term_ends(conn, date(2027, 4, 1))
    (c,) = rows(client, "get_contracts", "X_CONTRACTS", P_CONTRACT_NUMBER="LC-005077")
    assert c["CONTRACT_STATUS"] == "EVERGREEN"
    (a,) = rows(client, "get_lease_assets", "X_ASSETS", P_ASSET_NUMBER="MTR-2077")
    assert asset_return(client, "create_asset_return", {"KLE_ID": a["KLE_ID"], "ARS_CODE": "RETURNED"})["X_RETURN_STATUS"] == "S"
    (c,) = rows(client, "get_contracts", "X_CONTRACTS", P_CONTRACT_NUMBER="LC-005077")
    assert c["CONTRACT_STATUS"] == "TERMINATED" and c["DATE_TERMINATED"]
