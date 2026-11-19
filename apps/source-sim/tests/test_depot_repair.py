"""B5b contract tests: call the Oracle Depot Repair mock as an EBS Integrated SOA Gateway REST client does."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim import scheduler
from sim.db import engine
from sim.main import app

REST = "/depot-repair/webservices/rest"
Q = REST + "/xxcsdroquery"
USER = ("DI_CONNECTOR", "repair-demo-password")
HEADER = {
    "Responsibility": "DEPOT_REPAIR_SUPER_USER",
    "RespApplication": "CSD",
    "SecurityGroup": "STANDARD",
    "NLSLanguage": "AMERICAN",
}


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.post("/_sim/reset", params={"system": "repair"}).raise_for_status()
    yield c
    c.post("/_sim/reset", params={"system": "repair"}).raise_for_status()


def out(r) -> dict:
    assert r.status_code == 200, r.text
    return r.json()["OutputParameters"]


def orders(client, **params) -> list[dict]:
    o = out(client.get(Q + "/get_repair_orders/", auth=USER, params=params | {"P_MAX_RECORDS": 500}))
    assert o["X_RETURN_STATUS"] == "S"
    return o["X_REPAIR_ORDERS"]["X_REPAIR_ORDERS_ITEM"]


def create(client, rec: dict, **params) -> dict:
    body = {
        "CREATE_REPAIR_ORDER_Input": {
            "RESTHeader": HEADER,
            "InputParameters": {"P_API_VERSION_NUMBER": "1.0", "P_REPLN_REC": rec, **params},
        }
    }
    return out(client.post(REST + "/csdrepairs/create_repair_order/", auth=USER, json=body))


def outbox(type_: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT data FROM sim.outbox WHERE source = 'repair' AND type = :t ORDER BY id"), {"t": type_})
        return [r.data for r in rows]


def test_auth_token_and_faults(client):
    r = client.get(Q + "/get_repair_orders/")
    assert r.status_code == 401 and r.json()["ISGServiceFault"]["Code"] == "ISG_USER_AUTHENTICATION_FAILED"
    assert client.get(Q + "/get_repair_orders/", auth=("DI_CONNECTOR", "x")).status_code == 401
    login = client.post(REST + "/login", auth=USER).json()["data"]
    assert login["ebsVersion"] == "12.2.13"
    tc = TestClient(app, cookies={login["accessTokenName"]: login["accessToken"]})
    assert tc.get(Q + "/get_repair_orders/", params={"P_MAX_RECORDS": 1}).status_code == 200
    bad = client.post(Q + "/get_repair_orders/", auth=USER, json={})
    assert bad.status_code == 405 and bad.json()["ISGServiceFault"]["Code"] == "ISG_UNSUPPORTED_REST_VERB"
    assert client.get(REST + "/nope/x/", auth=USER).status_code == 404
    r = client.post(REST + "/csdrepairs/create_repair_order/", auth=USER, json={"wrong": {}})
    assert r.status_code == 400 and r.json()["ISGServiceFault"]["ServiceDetails"]["OperationName"] == "create_repair_order"
    assert client.get(Q + "/get_repair_orders/", auth=USER, params={"P_MAX_RECORDS": "0"}).status_code == 400


def test_rt_1048_repair_order(client):
    (ro,) = orders(client, P_SERIAL_NUMBER="MTR-2041")  # MAPPINGS.repair: 1,800.00 USD, "Light repair + test", B
    assert (ro["REPAIR_NUMBER"], ro["REPAIR_COST"], ro["CURRENCY_CODE"], ro["SCOPE"], ro["RESULT_STATE"]) == (
        "RO-61048",
        1800.0,
        "USD",
        "Light repair + test",
        "B",
    )
    assert ro["REPAIR_ORG"] == "RC01" and ro["CURRENT_LOCATION"] == "WH01" and ro["RECEIVING_INSPECTION"]["GRADE"] == "B"
    assert ro["ORIGINAL_SOURCE_REFERENCE"] == "RT-1048" and ro["FLOW_STATUS_CODE"] == "ESTIMATE_PENDING_APPROVAL"
    assert [p["PART_NUMBER"] for p in ro["PARTS"]["PARTS_ITEM"]][:2] == ["SKF-6316-2Z/C3", "SKF-6314-2Z/C3"]
    tasks = out(client.get(Q + "/get_repair_tasks/", auth=USER, params={"P_REPAIR_NUMBER": "RO-61048"}))["X_REPAIR_TASKS"]
    assert any(t["TASK_TYPE"] == "Labour" and t["RATE"] == 850.0 for t in tasks["X_REPAIR_TASKS_ITEM"])
    tests = out(client.get(Q + "/get_test_results/", auth=USER, params={"P_REPAIR_NUMBER": "RO-61048"}))["X_TEST_RESULTS"]
    assert tests["X_TEST_RESULTS_ITEM"] and all(t["RESULT"] == "PASS" for t in tests["X_TEST_RESULTS_ITEM"])


def test_paging_and_delta(client):
    o = out(client.get(Q + "/get_repair_orders/", auth=USER, params={"P_START_INDEX": 1, "P_MAX_RECORDS": 10}))
    assert o["X_HAS_MORE"] == "Y" and len(o["X_REPAIR_ORDERS"]["X_REPAIR_ORDERS_ITEM"]) == 10
    every = orders(client)
    assert int(o["X_TOTAL_COUNT"]) == len(every) >= 53
    newest = max(r["LAST_UPDATE_DATE"] for r in every)
    assert orders(client, P_LAST_UPDATE_DATE_FROM=newest) == []


def test_create_validation(client):
    o = create(client, {"REPAIR_TYPE": "Refurbishment"})
    assert o["X_RETURN_STATUS"] == "E" and "SERIAL" in o["X_MSG_DATA"] and o["X_MSG_COUNT"] == "1"
    assert create(client, {"SERIAL_NUMBER": "MTR-2041", "REPAIR_TYPE": "Polish"})["X_RETURN_STATUS"] == "E"
    assert create(client, {"SERIAL_NUMBER": "MTR-2041", "QUANTITY": 0})["X_RETURN_STATUS"] == "E"
    assert create(client, {"SERIAL_NUMBER": "MTR-2041", "ATTRIBUTE3": "Z"})["X_RETURN_STATUS"] == "E"
    assert create(client, {"SERIAL_NUMBER": "MTR-2041"}, P_REPAIR_NUMBER="RO-61048")["X_RETURN_STATUS"] == "E"
    body = {
        "CREATE_REPAIR_ORDER_Input": {"InputParameters": {"P_API_VERSION_NUMBER": "2.0", "P_REPLN_REC": {"SERIAL_NUMBER": "X"}}}
    }
    assert out(client.post(REST + "/csdrepairs/create_repair_order/", auth=USER, json=body))["X_RETURN_STATUS"] == "E"


def test_refurbishment_order_runs_to_closed_on_the_clock(client):
    o = create(
        client,
        {
            "SERIAL_NUMBER": "TST-RPR-1",
            "REPAIR_TYPE": "Refurbishment",
            "ORIGINAL_SOURCE_REFERENCE": "RT-9001",
            "ATTRIBUTE_CATEGORY": "CIRCULARITY",
            "ATTRIBUTE1": "Clean, test and certify",
            "ATTRIBUTE2": "950",
            "ATTRIBUTE3": "A",
        },
    )
    assert o["X_RETURN_STATUS"] == "S" and o["X_REPAIR_NUMBER"].startswith("RO-7")
    rn = o["X_REPAIR_NUMBER"]
    (ro,) = orders(client, P_REPAIR_NUMBER=rn)
    assert (ro["FLOW_STATUS_CODE"], ro["STATUS"], ro["REPAIR_COST"], ro["SCOPE"]) == (
        "OPEN",
        "O",
        950.0,
        "Clean, test and certify",
    )
    assert outbox("oracle.apps.csd.repair.create")[-1]["REPAIR_NUMBER"] == rn
    tasks = out(client.get(Q + "/get_repair_tasks/", auth=USER, params={"P_REPAIR_NUMBER": rn}))["X_REPAIR_TASKS"][
        "X_REPAIR_TASKS_ITEM"
    ]
    assert [t["STATUS"] for t in tasks] == ["PLANNED"]  # unknown item class: bench labour only, 4 h
    # the serial is in repair: a second order for it waits
    client.post("/_sim/clock/advance", json={"hours": 1.5}).raise_for_status()
    scheduler.tick()
    assert orders(client, P_REPAIR_NUMBER=rn)[0]["FLOW_STATUS_CODE"] == "IN_PROGRESS"
    assert create(client, {"SERIAL_NUMBER": "TST-RPR-1"})["X_RETURN_STATUS"] == "E"
    client.post("/_sim/clock/advance", json={"hours": 4}).raise_for_status()
    scheduler.tick()
    (ro,) = orders(client, P_REPAIR_NUMBER=rn)
    assert ro["FLOW_STATUS_CODE"] == "REPAIR_COMPLETE" and ro["RELEASE_TO_SERVICE"]["CERTIFICATE"] == f"RTS-{rn}"
    tests = out(client.get(Q + "/get_test_results/", auth=USER, params={"P_REPAIR_NUMBER": rn}))["X_TEST_RESULTS"][
        "X_TEST_RESULTS_ITEM"
    ]
    assert [t["RESULT"] for t in tests] == ["PASS"]
    client.post("/_sim/clock/advance", json={"hours": 2}).raise_for_status()
    scheduler.tick()
    (ro,) = orders(client, P_REPAIR_NUMBER=rn)
    assert (ro["FLOW_STATUS_CODE"], ro["STATUS"]) == ("CLOSED", "C") and ro["DATE_CLOSED"]
    moves = [e["TO_FLOW_STATUS"] for e in outbox("oracle.apps.csd.repair.status.update") if e["REPAIR_NUMBER"] == rn]
    assert moves == ["IN_PROGRESS", "REPAIR_COMPLETE", "CLOSED"]


def test_rt_1048_refurbishment_uses_its_diagnosis(client):
    o = create(client, {"SERIAL_NUMBER": "MTR-2041", "ATTRIBUTE1": "Light repair + test", "ATTRIBUTE2": 1800, "ATTRIBUTE3": "B"})
    assert o["X_RETURN_STATUS"] == "S"
    (ro,) = orders(client, P_REPAIR_NUMBER=o["X_REPAIR_NUMBER"])
    assert ro["ITEM_CATEGORY"] == "MOTOR" and ro["LABOUR"]["STANDARD_HOURS"] == 22.0 and len(ro["PARTS"]["PARTS_ITEM"]) == 7
    tasks = out(client.get(Q + "/get_repair_tasks/", auth=USER, params={"P_REPAIR_NUMBER": ro["REPAIR_NUMBER"]}))
    assert [t["TASK_TYPE"] for t in tasks["X_REPAIR_TASKS"]["X_REPAIR_TASKS_ITEM"]] == ["Labour"] + ["Machine"] * 4
