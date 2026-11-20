"""B5 contract tests: call the ServiceNow FSM mock the way a ServiceNow Table API client does (docs/BACKEND_STEPS.md)."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.db import engine
from sim.main import app

API = "/servicenow/api/now/table"
AUTH = ("di.integration", "Circularity-demo-sn-1")
CLIENT = {"client_id": "circularity-di", "client_secret": "circularity-demo-sn-secret"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "fsm"}).raise_for_status()
        yield c


@pytest.fixture(scope="module")
def bearer(client):
    r = client.post("/servicenow/oauth_token.do", data={"grant_type": "client_credentials"} | CLIENT)
    assert r.status_code == 200
    tok = r.json()
    assert tok["token_type"] == "Bearer" and tok["expires_in"] == 1799 and tok["refresh_token"]
    return {"Authorization": "Bearer " + tok["access_token"]}


def get(client, table, **params):
    r = client.get(f"{API}/{table}", auth=AUTH, params=params)
    assert r.status_code == 200, r.text
    return r


def rows(client, table, **params):
    return get(client, table, **params).json()["result"]


def one(client, table, query, **params):
    result = rows(client, table, sysparm_query=query, **params)
    assert len(result) == 1, result
    return result[0]


# ---------------- security
def test_requires_authentication(client):
    r = client.get(f"{API}/wm_order")
    assert r.status_code == 401
    assert r.json() == {
        "error": {"message": "User Not Authenticated", "detail": "Required to provide Auth information"},
        "status": "failure",
    }
    assert client.get(f"{API}/wm_order", auth=("di.integration", "wrong")).status_code == 401
    assert client.get(f"{API}/wm_order", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_oauth_grants(client, bearer):
    assert client.get(f"{API}/wm_order", headers=bearer, params={"sysparm_limit": 1}).status_code == 200
    bad = client.post("/servicenow/oauth_token.do", data={"grant_type": "client_credentials", "client_id": "circularity-di"})
    assert bad.status_code == 401 and bad.json()["error_description"] == "access_denied"
    pw = client.post(
        "/servicenow/oauth_token.do",
        data={"grant_type": "password", "username": AUTH[0], "password": AUTH[1]} | CLIENT,
    ).json()
    assert client.get(f"{API}/sys_user/x", headers={"Authorization": "Bearer " + pw["access_token"]}).status_code == 404
    wrong_pw = {"grant_type": "password", "username": AUTH[0], "password": "x"} | CLIENT
    assert client.post("/servicenow/oauth_token.do", data=wrong_pw).status_code == 401
    refreshed = client.post(
        "/servicenow/oauth_token.do", data={"grant_type": "refresh_token", "refresh_token": pw["refresh_token"]} | CLIENT
    )
    assert refreshed.status_code == 200 and refreshed.json()["access_token"] != pw["access_token"]


def test_errors_look_like_servicenow(client):
    r = client.get(f"{API}/wm_orderx", auth=AUTH)
    assert r.status_code == 400 and r.json()["error"]["message"] == "Invalid table wm_orderx"
    r = client.get(f"{API}/wm_order/0123456789abcdef0123456789abcdef", auth=AUTH)
    assert r.status_code == 404 and r.json()["error"]["message"] == "No Record found" and r.json()["status"] == "failure"
    r = client.post(f"{API}/core_company", auth=AUTH, json={"name": "X"})
    assert r.status_code == 403 and "ACL Exception Insert Failed" in r.json()["error"]["detail"]


# ---------------- the demo's mapping examples (MAPPINGS.fsm, source fields)
def test_mtr_2041_asset_record(client):
    a = one(client, "alm_asset", "asset_tag=MTR-2041", sysparm_display_value="true", sysparm_exclude_reference_link="true")
    assert a["serial_number"] == "SN-77120-A"  # alm_asset.serial_number → FSM:SN-77120-A
    assert (a["company"], a["location"], a["install_status"], a["substatus"]) == (
        "Customer A",
        "Warehouse 1",
        "In stock",
        "available",
    )
    assert a["model"] == "Voltara Industrial motor 55 kW"
    assert re.fullmatch(r"[0-9a-f]{32}", a["sys_id"])


def test_wo0010382_closed_visit(client):
    """wm_order.number WO0010382; wm_task.state 3 (closed complete) closed 2026-09-30 14:05:11 by tech.0412 after 2.5 h."""
    o = one(client, "wm_order", "number=WO0010382")
    assert o["state"] == "3" and o["asset"]["value"] and o["asset"]["link"].endswith(f"/alm_asset/{o['asset']['value']}")
    t = one(
        client,
        "wm_task",
        "parent.number=WO0010382",
        sysparm_fields="number,state,closed_at,work_duration,assigned_to.user_name,parent,u_labour_rate",
    )
    assert set(t) == {"number", "state", "closed_at", "work_duration", "assigned_to.user_name", "parent", "u_labour_rate"}
    assert (t["state"], t["closed_at"], t["assigned_to.user_name"]) == ("3", "2026-09-30 14:05:11", "tech.0412")
    assert t["work_duration"] == "1970-01-01 02:30:00" and t["u_labour_rate"] == "1100.00"
    assert t["parent"]["value"] == o["sys_id"] and t["number"].startswith("WOT")
    shown = rows(client, "wm_task", sysparm_query="parent.number=WO0010382", sysparm_display_value="true")[0]
    assert shown["state"] == "Closed Complete" and shown["work_duration"] == "2 Hours 30 Minutes"
    assert shown["assigned_to"]["display_value"] == "Arun Prakash"


def test_rt_1048_demand_at_site_3(client):
    """RT-1048: Customer A needs a 55 kW motor at Site 3 (Chennai Foundry) in 10 days, OMS order SO-48102."""
    o = one(
        client,
        "wm_order",
        "location.u_site_code=Site 3^u_work_type=Install^correlation_id=SO-48102",
        sysparm_display_value="all",
    )
    assert o["company"]["display_value"] == "Customer A" and o["location"]["display_value"] == "Chennai Foundry"
    assert o["state"] == {"display_value": "Ready", "value": "10"}
    assert o["expected_start"]["value"] == "2026-10-17 09:00:00"
    assert o["u_model_required"]["display_value"] == "Voltara Industrial motor 55 kW"
    task = one(client, "wm_task", f"parent={o['sys_id']['value']}")
    assert task["state"] == "10" and task["assigned_to"] == ""


def test_every_site_demand_case_has_an_order(client):
    from sim.seed import seed

    expected = sum(1 for c in seed().cases.values() if c.facts.demand.site)
    r = get(client, "wm_order", sysparm_query="u_work_typeINInstall,Delivery", sysparm_limit=1)
    assert int(r.headers["X-Total-Count"]) == expected


# ---------------- encoded queries
def test_and_or_and_new_query(client):
    closed = int(get(client, "wm_task", sysparm_query="state=3", sysparm_limit=1).headers["X-Total-Count"])
    incomplete = int(get(client, "wm_task", sysparm_query="state=4", sysparm_limit=1).headers["X-Total-Count"])
    either = get(client, "wm_task", sysparm_query="state=3^ORstate=4", sysparm_limit=1)
    assert int(either.headers["X-Total-Count"]) == closed + incomplete > 0
    nq = get(client, "wm_task", sysparm_query="state=3^NQstate=4", sysparm_limit=1)
    assert nq.headers["X-Total-Count"] == either.headers["X-Total-Count"]
    both = rows(client, "wm_order", sysparm_query="number=WO0010382^ORnumber=WO0010001^state=3", sysparm_fields="number")
    assert {r["number"] for r in both} <= {"WO0010382", "WO0010001"} and {"number": "WO0010382"} in both


def test_operators(client):
    starts = rows(client, "wm_order", sysparm_query="numberSTARTSWITHWO00103^ORDERBYDESCnumber", sysparm_fields="number")
    assert starts and all(r["number"].startswith("WO00103") for r in starts)
    assert [r["number"] for r in starts] == sorted((r["number"] for r in starts), reverse=True)
    ends = rows(client, "alm_asset", sysparm_query="asset_tagENDSWITH2041", sysparm_fields="asset_tag")
    assert {"asset_tag": "MTR-2041"} in ends
    like = rows(client, "wm_order", sysparm_query="short_descriptionLIKEremove industrial motor", sysparm_fields="u_work_type")
    assert like and all(r["u_work_type"] == "Decommission" for r in like)
    not_in = rows(client, "wm_task", sysparm_query="stateNOT IN3,4,7^state!=1", sysparm_fields="state")
    assert not_in and all(r["state"] in ("10", "16", "2", "18") for r in not_in)
    empty = rows(client, "wm_order", sysparm_query="closed_atISEMPTY", sysparm_fields="state")
    assert empty and all(r["state"] not in ("3", "4") for r in empty)
    filled = get(client, "wm_order", sysparm_query="closed_atISNOTEMPTY", sysparm_limit=1).headers["X-Total-Count"]
    assert int(filled) + len(empty) == int(get(client, "wm_order", sysparm_limit=1).headers["X-Total-Count"])
    big = rows(client, "sm_part_requirement", sysparm_query="unit_cost>=10000^ORDERBYunit_cost", sysparm_fields="unit_cost")
    assert big and all(float(r["unit_cost"]) >= 10000 for r in big)
    early = rows(client, "wm_task", sysparm_query="closed_at<2026-01-01 00:00:00^closed_atISNOTEMPTY", sysparm_fields="closed_at")
    assert early and all(r["closed_at"] < "2026-01-01" for r in early)


def test_reference_by_display_value_and_dot_walk(client):
    by_name = get(client, "wm_order", sysparm_query="company=Customer A", sysparm_limit=1).headers["X-Total-Count"]
    company = one(client, "core_company", "name=Customer A")
    by_id = get(client, "wm_order", sysparm_query=f"company={company['sys_id']}", sysparm_limit=1).headers["X-Total-Count"]
    assert by_name == by_id and int(by_id) > 0
    walked = rows(client, "sm_part_requirement", sysparm_query="task.parent.location.u_site_code=Site 3", sysparm_limit=5)
    assert walked


def test_invalid_field_matches_nothing(client):
    assert rows(client, "wm_order", sysparm_query="no_such_field=1") == []
    assert client.get(f"{API}/wm_order", auth=AUTH, params={"sysparm_query": "state~~3"}).status_code == 400


# ---------------- paging
def test_paging_headers_and_walk(client):
    total = int(get(client, "wm_task", sysparm_limit=1).headers["X-Total-Count"])
    seen, offset = [], 0
    while True:
        r = get(client, "wm_task", sysparm_limit=100, sysparm_offset=offset, sysparm_fields="sys_id")
        assert int(r.headers["X-Total-Count"]) == total
        links = {rel: url for url, rel in re.findall(r'<([^>]+)>;rel="(\w+)"', r.headers["Link"])}
        assert "first" in links and "last" in links and ("prev" in links) == (offset > 0)
        seen += [x["sys_id"] for x in r.json()["result"]]
        if "next" not in links:
            break
        assert "sysparm_offset=" + str(offset + 100) in links["next"] and "sysparm_limit=100" in links["next"]
        offset += 100
    assert len(seen) == len(set(seen)) == total


# ---------------- fields and display values
def test_reference_shapes(client):
    q = "number=WO0010382"
    plain = one(client, "wm_order", q, sysparm_fields="company")["company"]
    assert set(plain) == {"link", "value"} and plain["link"].endswith("/servicenow/api/now/table/core_company/" + plain["value"])
    assert (
        one(client, "wm_order", q, sysparm_fields="company", sysparm_exclude_reference_link="true")["company"] == plain["value"]
    )
    shown = one(client, "wm_order", q, sysparm_fields="company", sysparm_display_value="true")["company"]
    assert shown == {"display_value": "Customer A", "link": plain["link"]}
    both = one(client, "wm_order", q, sysparm_fields="company,state", sysparm_display_value="all")
    assert both["company"] == {"display_value": "Customer A", "link": plain["link"], "value": plain["value"]}
    assert both["state"] == {"display_value": "Closed Complete", "value": "3"}
    single = client.get(f"{API}/wm_order/{one(client, 'wm_order', q)['sys_id']}", auth=AUTH, params={"sysparm_fields": "number"})
    assert single.json() == {"result": {"number": "WO0010382"}}


# ---------------- writes, events and delta reads
def test_create_order_dispatch_and_close(client, bearer):
    # field service demand raised by di (SOURCES.fsm write: POST /table/wm_order)
    r = client.post(
        f"{API}/wm_order",
        headers=bearer,
        json={
            "short_description": "Install redeployed industrial motor MTR-2041",
            "location": "Chennai Foundry",
            "asset": one(client, "alm_asset", "asset_tag=MTR-2041")["sys_id"],
            "correlation_id": "RT-1048",
            "u_work_type": "Install",
            "state": "10",
            "bogus_field": "ignored",
        },
    )
    assert r.status_code == 201, r.text
    o = r.json()["result"]
    assert r.headers["Location"].endswith(f"/table/wm_order/{o['sys_id']}")
    assert re.fullmatch(r"WO\d{7}", o["number"]) and o["number"] > "WO0010382"
    assert o["state"] == "10" and o["sys_created_by"] == "di.integration" and "bogus_field" not in o
    company = one(client, "core_company", "name=Customer A")["sys_id"]
    assert o["company"]["value"] == company  # inherited from the site
    t = client.post(f"{API}/wm_task", auth=AUTH, json={"parent": o["sys_id"], "short_description": "Install motor"}).json()[
        "result"
    ]
    assert t["state"] == "1" and t["location"]["value"] == o["location"]["value"] and t["number"].startswith("WOT")

    # dispatch (SOURCES.fsm write: PATCH /table/wm_task/{sys_id})
    tech = one(client, "sys_user", "user_name=tech.0412")["sys_id"]
    d = client.patch(f"{API}/wm_task/{t['sys_id']}", headers=bearer, json={"assigned_to": tech, "state": "10"}).json()["result"]
    assert d["state"] == "10" and d["assigned_to"]["value"] == tech
    d = client.patch(f"{API}/wm_task/{t['sys_id']}", headers=bearer, json={"assigned_to": "tech.0463"}).json()["result"]
    assert d["state"] == "16" and d["sys_mod_count"] == "2"  # assigning a pending task makes it Assigned
    done = client.patch(
        f"{API}/wm_task/{t['sys_id']}", headers=bearer, json={"state": "3", "work_duration": "1970-01-01 03:15:00"}
    ).json()["result"]
    assert done["closed_at"] and done["actual_work_end"] and done["work_duration"] == "1970-01-01 03:15:00"
    order = client.get(f"{API}/wm_order/{o['sys_id']}", auth=AUTH, params={"sysparm_display_value": "true"}).json()["result"]
    assert order["state"] == "Closed Complete" and order["closed_at"]

    # delta read: only what changed after the as-of time
    delta = rows(client, "wm_order", sysparm_query="sys_updated_on>2026-10-07 09:00:00", sysparm_fields="number")
    assert delta == [{"number": o["number"]}]
    gs = rows(client, "wm_task", sysparm_query="sys_updated_on>javascript:gs.dateGenerate('2026-10-07','09:00:00')")
    assert [x["sys_id"] for x in gs] == [t["sys_id"]]

    # outbox events
    with engine.connect() as conn:
        types = list(
            conn.execute(
                text("SELECT type FROM sim.outbox WHERE source = 'fsm' AND subject = ANY(:s) ORDER BY id"),
                {"s": [o["sys_id"], t["sys_id"]]},
            ).scalars()
        )
    assert types == [
        "servicenow.wm_order.created",
        "servicenow.wm_task.created",
        "servicenow.wm_task.updated",
        "servicenow.wm_task.updated",
        "servicenow.wm_order.updated",  # Scheduled: a task was assigned
        "servicenow.wm_task.updated",
        "servicenow.wm_order.updated",  # Closed Complete: its last task closed
    ]


def test_write_validation(client):
    r = client.post(f"{API}/wm_order", auth=AUTH, json={"location": "Atlantis"})
    assert r.status_code == 400 and r.json()["status"] == "failure"
    assert client.post(f"{API}/wm_order", auth=AUTH, json={"opened_at": "yesterday"}).status_code == 400
    assert client.patch(f"{API}/wm_task/0123456789abcdef0123456789abcdef", auth=AUTH, json={"state": "3"}).status_code == 404
    assert client.patch(f"{API}/alm_asset/0123456789abcdef0123456789abcdef", auth=AUTH, json={}).status_code == 403
