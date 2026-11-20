"""B5 contract tests: call the Maximo mock the way a Maximo REST/OSLC client does (docs/backend-steps.md)."""

import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.db import engine
from sim.main import app
from sim.seed import seed

API = "/maximo/api"
KEY = {"apikey": "circularity-demo-maximo-apikey"}
LEAN = {"lean": "1"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "eam"}).raise_for_status()
        yield c


def q(client, os_, **params):
    params = LEAN | {k.replace("_", "."): v for k, v in params.items()}
    r = client.get(f"{API}/os/{os_}", headers=KEY, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def get_all(client, os_, params):
    out, params = [], LEAN | params
    url = f"{API}/os/{os_}"
    while True:
        body = client.get(url, headers=KEY, params=params).json()
        out += body["member"]
        nxt = body["responseInfo"].get("nextPage")
        if not nxt:
            return out
        url, params = nxt["href"], None


# ---------------- security
def test_authentication(client):
    url = f"{API}/os/mxwo"
    r = client.get(url)
    assert r.status_code == 401
    err = r.json()["Error"]
    assert err["reasonCode"] == "BMXAA7901E" and err["statusCode"] == "401" and err["message"].startswith("BMXAA7901E - ")
    assert client.get(url, headers={"apikey": "wrong"}).status_code == 401
    good = base64.b64encode(b"MXINTADM:circularity-demo-1").decode()
    bad = base64.b64encode(b"MXINTADM:nope").decode()
    assert client.get(url, headers={"maxauth": good}, params={"oslc.pageSize": 1}).status_code == 200
    assert client.get(url, headers={"maxauth": bad}).status_code == 401
    assert client.get(url, params={"apikey": KEY["apikey"], "oslc.pageSize": 1}).status_code == 200
    me = client.get(f"{API}/whoami", headers=KEY).json()
    assert me["userName"] == "MXINTADM" and me["defaultOrg"] == "NFIND"
    assert client.post(f"{API}/os/mxwo", json={}).status_code == 401


def test_unknown_object_structure(client):
    r = client.get(f"{API}/os/mxnothing", headers=KEY)
    assert r.status_code == 404 and "Error" in r.json()


# ---------------- RT-1048: MTR-2041, the demo's mapping examples
def test_rt_1048_asset_record(client):
    body = q(client, "mxasset", oslc_where='assetnum="MTR-2041"', oslc_select="*")
    assert len(body["member"]) == 1
    a = body["member"][0]
    assert (a["assetnum"], a["siteid"], a["location"], a["pluscustomer"]) == ("MTR-2041", "WH01", "WH01-RTN", "Customer A")
    assert a["conditioncode"] == "B+"  # CONDITIONCODE B+ -> condition.grade B
    assert a["lastservicedate"] == "2026-03-14T08:20:00+05:30"  # LASTSERVICEDATE, kept in server time
    assert a["manufacturer"] == "Voltara" and a["status"] == "NOT READY" and a["status_description"] == "Not Ready"
    assert a["assettype"] == "MOTOR" and a["criticality"] == 8
    spec = {s["assetattrid"]: s for s in a["assetspec"]}
    assert spec["RATED_PWR"]["numvalue"] == 55000 and spec["RATED_PWR"]["measureunitid"] == "W"  # 55000 W -> 55 kW
    assert a["assetmeter"][0]["metername"] == "RUNHOURS" and a["assetmeter"][0]["lastreading"] == 18450
    one = client.get(a["href"].replace("http://testserver", ""), headers=KEY, params=LEAN).json()
    assert one["assetnum"] == "MTR-2041" and one["href"] == a["href"]


def test_rt_1048_history_and_failure(client):
    wos = q(
        client,
        "mxwo",
        oslc_where='assetnum="MTR-2041"',
        oslc_select="wonum,worktype,status,actfinish,problemcode,actlabcost,supervisor,externalrefid",
        oslc_orderBy="+wonum",
    )["member"]
    assert [w["wonum"] for w in wos] == [f"1048{i:03d}" for i in range(1, len(wos) + 1)]
    cm = [w for w in wos if w["worktype"] == "CM"]
    assert (
        len(cm) == 1 and cm[0]["problemcode"] == "BRG-WEAR" and cm[0]["actlabcost"] == 420.0 and cm[0]["supervisor"] == "R. Kumar"
    )
    pms = [w for w in wos if w["worktype"] == "PM"]
    assert pms and max(w["actfinish"] for w in pms) == "2026-03-14T08:20:00+05:30"
    insp = [w for w in wos if w["worktype"] == "INSP"]
    assert {w["status"] for w in insp} == {"COMP", "WAPPR"}
    assert any(w.get("externalrefid") == "RT-1048" for w in insp)
    fr = q(client, "mxfailurereport", oslc_where=f'wonum="{cm[0]["wonum"]}"', oslc_select="*", oslc_orderBy="linenum")["member"]
    assert [(f["type"], f["failurecode"]) for f in fr] == [
        ("PROBLEM", "BRG-WEAR"),
        ("CAUSE", "LUBE-LOSS"),
        ("REMEDY", "BRG-REPL"),
    ]


def test_every_case_asset_is_registered(client):
    s = seed()
    rows = get_all(
        client,
        "mxasset",
        {"oslc.where": 'siteid in ["WH01","WH02","RC01"]', "oslc.select": "assetnum,siteid", "oslc.pageSize": 100},
    )
    assert {r["assetnum"] for r in rows} == {c.facts.asset_id for c in s.cases.values()}
    installed = q(client, "mxasset", oslc_where='status="OPERATING"', collectioncount="1", oslc_pageSize="1")
    assert installed["responseInfo"]["totalCount"] > 100


def test_executing_cases_have_refurbishment_work_orders(client):
    s = seed()
    wos = get_all(
        client,
        "mxwo",
        {"oslc.where": 'worktype in ["REFURB","TDOWN"]', "oslc.select": "wonum,status,assetnum,siteid,externalrefid"},
    )
    assert wos and all(w["siteid"] == "RC01" for w in wos)
    assert {w["status"] for w in wos} == {"INPRG", "COMP"}
    rt1003 = s.cases["RT-1003"].facts.asset_id
    assert any(w["assetnum"] == rt1003 and w["externalrefid"] == "WO-47034" and w["status"] == "COMP" for w in wos)


# ---------------- query features
def test_select_absent_returns_hrefs_only(client):
    m = q(client, "mxwo", oslc_pageSize="3")["member"]
    assert len(m) == 3 and all(set(x) == {"href"} for x in m)
    assert m[0]["href"].startswith("http://testserver/maximo/api/os/mxwo/_")


def test_where_operators(client):
    sel = "wonum,status,wopriority,description,reportdate,failurecode"
    appr = q(client, "mxwo", oslc_where='status="APPR" and siteid="WH01"', oslc_select=sel)["member"]
    assert appr and all(w["status"] == "APPR" for w in appr)
    either = q(client, "mxwo", oslc_where='(status="COMP" or status="INPRG") and worktype="REFURB"', oslc_select=sel)["member"]
    assert either and {w["status"] for w in either} <= {"COMP", "INPRG"}
    like = q(client, "mxwo", oslc_where='description="%BEARING%"', oslc_select=sel)["member"]
    assert like and all("bearing" in w["description"].lower() for w in like)
    hi = q(client, "mxwo", oslc_where="wopriority<=1", oslc_select=sel)["member"]
    assert hi and all(w["wopriority"] <= 1 for w in hi)
    recent = q(client, "mxwo", oslc_where='reportdate>="2026-10-01T00:00:00+05:30"', oslc_select=sel)["member"]
    assert recent and all(w["reportdate"] >= "2026-10-01" for w in recent)
    not_closed = q(client, "mxwo", oslc_where='status!=["CLOSE","COMP"] and failurecode="*"', oslc_select=sel)["member"]
    assert all(w["status"] not in ("CLOSE", "COMP") and w.get("failurecode") for w in not_closed)
    many = q(client, "mxasset", oslc_where='assetnum in ["MTR-2041","PMP-0320"]', oslc_select="assetnum")["member"]
    assert {a["assetnum"] for a in many} == {"MTR-2041", "PMP-0320"}
    neq = q(client, "mxasset", oslc_where='assetnum="MTR-2041" and status!="OPERATING"', oslc_select="assetnum")["member"]
    assert len(neq) == 1


def test_where_errors(client):
    for bad in ['nosuchattr="x"', 'status="APPR" and', 'status=="x"', 'reportdate>"yesterday"', "status = 'APPR'"]:
        r = client.get(f"{API}/os/mxwo", headers=KEY, params=LEAN | {"oslc.where": bad})
        assert r.status_code == 400, bad
        assert r.json()["Error"]["statusCode"] == "400"


def test_order_by_and_paging(client):
    first = q(
        client, "mxwo", oslc_select="wonum,reportdate", oslc_orderBy="-reportdate,+wonum", oslc_pageSize="25", collectioncount="1"
    )
    info = first["responseInfo"]
    assert info["pagenum"] == 1 and info["totalPages"] == -(-info["totalCount"] // 25) and "nextPage" in info
    dates = [w["reportdate"] for w in first["member"]]
    assert dates == sorted(dates, reverse=True)
    second = client.get(info["nextPage"]["href"], headers=KEY).json()
    assert second["responseInfo"]["pagenum"] == 2 and "previousPage" in second["responseInfo"]
    assert not {w["wonum"] for w in first["member"]} & {w["wonum"] for w in second["member"]}
    every = get_all(client, "mxwo", {"oslc.select": "wonum", "oslc.pageSize": 200})
    assert len(every) == info["totalCount"] and len({(w["href"]) for w in every}) == len(every)
    # a raw '+' arrives as a space: still ascending
    asc = q(client, "mxwo", oslc_select="workorderid", oslc_orderBy=" workorderid", oslc_pageSize="5")["member"]
    assert [w["workorderid"] for w in asc] == sorted(w["workorderid"] for w in asc)


def test_non_lean_form(client):
    r = client.get(
        f"{API}/os/mxwo", headers=KEY, params={"oslc.select": "wonum,status", "oslc.pageSize": 2, "collectioncount": 1}
    )
    body = r.json()
    assert "rdfs:member" in body and body["oslc:responseInfo"]["oslc:totalCount"] > 2
    m = body["rdfs:member"][0]
    assert "rdf:about" in m and "spi:wonum" in m and "spi:status" in m


def test_get_one_by_rest_id_and_workorderid(client):
    w = q(client, "mxwo", oslc_where='wonum="1048001"', oslc_select="*")["member"][0]
    token = w["href"].rsplit("/", 1)[1]
    assert base64.b64decode(token[1:].replace("-", "=")).decode() == f"1048001/{w['siteid']}"
    one = client.get(f"{API}/os/mxwo/{token}", headers=KEY, params=LEAN).json()
    assert one["wonum"] == "1048001" and [s["status"] for s in one["wostatus"]][-1] == "CLOSE"
    assert one["failurereport"][0]["failurecode"] == "BRG-WEAR"
    same = client.get(f"{API}/os/mxwo/{w['workorderid']}", headers=KEY, params=LEAN | {"oslc.select": "wonum"}).json()
    assert same == {"href": w["href"], "wonum": "1048001"}
    r = client.get(f"{API}/os/mxwo/_bm9wZS9OT1BF", headers=KEY)
    assert r.status_code == 404 and r.json()["Error"]["reasonCode"] == "BMXAA8727E"


# ---------------- writes
def _outbox(type_: str, subject: str) -> list[dict]:
    with engine.connect() as conn:
        return [
            r.data
            for r in conn.execute(
                text("SELECT data FROM sim.outbox WHERE source='eam' AND type=:t AND subject=:s ORDER BY id"),
                {"t": type_, "s": subject},
            )
        ]


def test_create_patch_and_delta(client):
    since = "2026-10-07T09:00:00+00:00"
    delta = f'changedate>"{since}"'
    assert q(client, "mxwo", oslc_where=delta, oslc_select="wonum")["member"] == []

    r = client.post(
        f"{API}/os/mxwo",
        headers=KEY | {"properties": "*"},
        params=LEAN,
        json={
            "description": "Refurbish, test and certify - MTR-2041",
            "assetnum": "MTR-2041",
            "worktype": "REFURB",
            "wopriority": 1,
            "estlabhrs": 15.4,
            "estlabcost": 1080,
            "externalrefid": "WO-47397",
            "targstartdate": "2026-10-08T09:00:00+05:30",
        },
    )
    assert r.status_code == 201, r.text
    wo = r.json()
    assert r.headers["location"] == wo["href"]
    assert (wo["status"], wo["siteid"], wo["location"], wo["orgid"]) == ("WAPPR", "WH01", "WH01-RTN", "NFIND")
    assert wo["targstartdate"] == "2026-10-08T09:00:00+05:30" and wo["reportedby"] == "MXINTADM"
    assert _outbox("maximo.workorder.created", wo["wonum"])[0]["assetnum"] == "MTR-2041"
    rid = wo["href"].rsplit("/", 1)[1]

    # no properties header: 201, empty body, Location
    bare = client.post(f"{API}/os/mxwo", headers=KEY, json={"description": "Spot check", "siteid": "RC01"})
    assert bare.status_code == 201 and bare.content == b"" and bare.headers["location"]

    # patch via x-method-override, status change, then a real PATCH
    p = client.post(
        f"{API}/os/mxwo/{rid}",
        headers=KEY | {"x-method-override": "PATCH", "patchtype": "MERGE"},
        json={"status": "APPR", "memo": "Approved by Circularity DI-2026-1048"},
    )
    assert p.status_code == 204
    p = client.patch(
        f"{API}/os/mxwo/{wo['workorderid']}",
        headers=KEY | {"properties": "status,actstart"},
        params=LEAN,
        json={"status": "INPRG"},
    )
    assert p.status_code == 200 and p.json()["status"] == "INPRG" and p.json()["actstart"]
    p = client.post(f"{API}/os/mxwo/{rid}", headers=KEY, params={"action": "wsmethod:changeStatus"}, json={"status": "COMP"})
    assert p.status_code == 204
    after = client.get(f"{API}/os/mxwo/{rid}", headers=KEY, params=LEAN).json()
    assert after["status"] == "COMP" and after["actfinish"]
    assert [s["status"] for s in after["wostatus"]] == ["WAPPR", "APPR", "INPRG", "COMP"]
    assert after["wostatus"][1]["memo"] == "Approved by Circularity DI-2026-1048"
    updates = _outbox("maximo.workorder.updated", wo["wonum"])
    assert [u["status"] for u in updates] == ["APPR", "INPRG", "COMP"] and updates[0]["changed"] == ["status"]

    # complete -> only close; read-only key; bad status
    assert client.patch(f"{API}/os/mxwo/{rid}", headers=KEY, json={"status": "INPRG"}).status_code == 400
    assert client.patch(f"{API}/os/mxwo/{rid}", headers=KEY, json={"wonum": "999"}).status_code == 400
    assert client.patch(f"{API}/os/mxwo/{rid}", headers=KEY, json={"status": "NOPE"}).status_code == 400
    assert client.patch(f"{API}/os/mxwo/{rid}", headers=KEY, json={"status": "CLOSE"}).status_code == 204
    closed = client.patch(f"{API}/os/mxwo/{rid}", headers=KEY, json={"description": "late edit"})
    assert closed.status_code == 400 and "closed" in closed.json()["Error"]["message"]

    # a POST to a resource without override is refused
    assert client.post(f"{API}/os/mxwo/{rid}", headers=KEY, json={"status": "APPR"}).status_code == 400

    # delta read sees exactly the changed work orders
    changed = q(client, "mxwo", oslc_where=delta, oslc_select="wonum")["member"]
    assert {w["wonum"] for w in changed} == {wo["wonum"], _wonum(client, bare.headers["location"])}


def _wonum(client, href: str) -> str:
    return client.get(href.replace("http://testserver", ""), headers=KEY, params=LEAN | {"oslc.select": "wonum"}).json()["wonum"]


def test_create_validation(client):
    def post(body):
        return client.post(f"{API}/os/mxwo", headers=KEY, json=body)

    assert post({"description": "no site"}).json()["Error"]["errorattrname"] == "siteid"
    assert post({"assetnum": "MTR-9999"}).json()["Error"]["reasonCode"] == "BMXAA4049E"
    assert post({"siteid": "XX99"}).status_code == 400
    assert post({"siteid": "RC01", "worktype": "NOPE"}).status_code == 400
    insp = q(client, "mxwo", oslc_where='wonum="1048008"', oslc_select="wonum,siteid")["member"][0]
    assert insp["siteid"] == "WH01"  # the return inspection, at the facility
    dup = post({"siteid": "WH01", "wonum": "1048008"})
    assert dup.status_code == 400 and dup.json()["Error"]["reasonCode"] == "BMXAA4129E"
    assert client.post(f"{API}/os/mxasset", headers=KEY, json={"assetnum": "X"}).status_code == 400
    assert client.post(f"{API}/os/mxwo", headers=KEY, content=b"not json").status_code == 400


def test_asset_update_emits_event(client):
    a = q(client, "mxasset", oslc_where='assetnum="PMP-0320"', oslc_select="assetnum,status")["member"][0]
    rid = a["href"].rsplit("/", 1)[1]
    r = client.post(
        f"{API}/os/mxasset/{rid}",
        headers=KEY | {"x-method-override": "PATCH", "properties": "status,conditioncode"},
        params=LEAN,
        json={"status": "OPERATING", "conditioncode": "B"},
    )
    assert r.status_code == 200 and r.json()["status"] == "OPERATING" and r.json()["conditioncode"] == "B"
    ev = _outbox("maximo.asset.updated", "PMP-0320")[-1]
    assert ev["status"] == "OPERATING" and set(ev["changed"]) == {"status", "conditioncode"}
    assert client.patch(f"{API}/os/mxasset/{rid}", headers=KEY, json={"siteid": "WH02"}).status_code == 400
    assert client.patch(f"{API}/os/mxasset/{rid}", headers=KEY, json={"status": "FLYING"}).status_code == 400
