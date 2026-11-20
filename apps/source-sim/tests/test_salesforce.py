"""B5 contract tests: call the Salesforce mock the way a Salesforce REST client does (docs/backend-steps.md)."""

import base64
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.db import engine
from sim.main import app
from sim.seed import seed
from sim.vendors.salesforce import auth

ROOT = "/salesforce"
BASE = "/services/data/v59.0"
TOKEN_URL = ROOT + "/services/oauth2/token"
JWT_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
CUSTOMER_A = "001Hs00003AbCdE"  # the demo's MAPPINGS.crm Account.Id example


def jwt(**claims) -> str:
    def enc(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    body = {"iss": auth.CLIENT_ID, "sub": auth.INTEGRATION_USER, "aud": "https://login.salesforce.com", "exp": time.time() + 300}
    return f"{enc({'alg': 'RS256'})}.{enc(body | claims)}.c2lnbmF0dXJl"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "crm"}).raise_for_status()
        yield c


@pytest.fixture(scope="module")
def h(client):
    r = client.post(TOKEN_URL, data={"grant_type": JWT_GRANT, "assertion": jwt()})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def api(client, h, method, path, **kw):
    return client.request(method, ROOT + BASE + path, headers=h | kw.pop("headers", {}), **kw)


def soql(client, h, q, batch=None):
    extra = {"Sforce-Query-Options": f"batchSize={batch}"} if batch else {}
    r = api(client, h, "GET", "/query", params={"q": q}, headers=extra)
    assert r.status_code == 200, r.text
    return r.json()


def query_all(client, h, q, batch=None) -> list[dict]:
    body = soql(client, h, q, batch)
    records = body["records"]
    while not body["done"]:
        r = client.get(ROOT + body["nextRecordsUrl"], headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        records += body["records"]
    return records


def error(r, status: int) -> str:
    assert r.status_code == status, r.text
    body = r.json()
    assert isinstance(body, list) and body[0]["message"]
    return body[0]["errorCode"]


def rt1048_opps(client, h) -> dict[str, dict]:
    q = (
        "SELECT Id, Type, StageName, Amount, CloseDate, AccountId, Account.Name, ContractId, Site__c, Lease_Reference__c "
        "FROM Opportunity WHERE Case_Id__c = 'RT-1048'"
    )
    return {r["Type"]: r for r in soql(client, h, q)["records"]}


# ---------------- OAuth 2.0
def test_jwt_bearer_and_client_credentials_tokens(client):
    r = client.post(TOKEN_URL, data={"grant_type": JWT_GRANT, "assertion": jwt(sub="sales.ops@northfield.example")})
    body = r.json()
    assert r.status_code == 200 and body["token_type"] == "Bearer" and body["instance_url"] == "http://testserver/salesforce"
    assert body["issued_at"].isdigit() and body["signature"] and body["id"].endswith(auth.user_id("sales.ops@northfield.example"))
    cc = client.post(
        TOKEN_URL, data={"grant_type": "client_credentials", "client_id": auth.CLIENT_ID, "client_secret": auth.CLIENT_SECRET}
    )
    assert cc.status_code == 200 and cc.json()["access_token"]

    def bad(data):
        r = client.post(TOKEN_URL, data=data)
        assert r.status_code == 400
        return r.json()["error"]

    assert bad({"grant_type": JWT_GRANT, "assertion": jwt(iss="someone-else")}) == "invalid_client_id"
    assert bad({"grant_type": JWT_GRANT, "assertion": jwt(sub="nobody@northfield.example")}) == "invalid_grant"
    assert bad({"grant_type": JWT_GRANT, "assertion": jwt(exp=time.time() - 10)}) == "invalid_grant"
    assert bad({"grant_type": JWT_GRANT, "assertion": jwt(aud="https://example.com")}) == "invalid_grant"
    assert bad({"grant_type": JWT_GRANT, "assertion": "not-a-jwt"}) == "invalid_grant"
    assert bad({"grant_type": "client_credentials", "client_id": auth.CLIENT_ID, "client_secret": "nope"}) == "invalid_client"
    assert bad({"grant_type": "password"}) == "unsupported_grant_type"


def test_api_calls_need_a_valid_session(client, h):
    assert error(client.get(ROOT + BASE + "/sobjects"), 401) == "INVALID_SESSION_ID"
    assert (
        error(client.get(ROOT + BASE + "/sobjects", headers={"Authorization": "Bearer 00D!forged"}), 401) == "INVALID_SESSION_ID"
    )
    assert api(client, h, "GET", "/sobjects").status_code == 200
    assert client.get(ROOT + "/services/data").json()[0]["version"] == "59.0"


# ---------------- delta reads (before anything changes)
def test_seeded_org_has_no_changes_after_the_as_of_time(client, h):
    assert soql(client, h, "SELECT COUNT() FROM Opportunity WHERE SystemModstamp > 2026-10-07T09:00:00Z")["totalSize"] == 0
    assert soql(client, h, "SELECT COUNT() FROM Opportunity WHERE SystemModstamp > 2026-09-01T00:00:00Z")["totalSize"] > 0


# ---------------- the demo's MAPPINGS.crm examples and RT-1048
def test_mappings_crm_examples(client, h):
    # Account.Id 001Hs00003AbCdE → asset.owner_tenant Customer A (15-character id accepted, as in Salesforce)
    acct = soql(client, h, f"SELECT Id, Name, Tenant_Key__c FROM Account WHERE Id = '{CUSTOMER_A}'")["records"]  # noqa: S608 - SOQL sent to the simulator, not SQL run here
    assert [(a["Id"][:15], a["Name"], a["Tenant_Key__c"]) for a in acct] == [(CUSTOMER_A, "Customer A", "CUSTOMER_A")]
    # RT-1048's lease opportunity: StageName 'Proposal' → forecast; CloseDate 2026-12-31; Amount a monthly lease rate
    lease = rt1048_opps(client, h)["Lease"]
    assert lease["StageName"] == "Proposal" and lease["CloseDate"] == "2026-12-31"
    assert lease["AccountId"] == acct[0]["Id"] and lease["Account"]["Name"] == "Customer A"
    assert lease["Amount"] == round(4400 / 30, 2)  # lease income over 30 months, per month
    stage = next(f for f in api(client, h, "GET", "/sobjects/Opportunity/describe").json()["fields"] if f["name"] == "StageName")
    assert {"Proposal", "Closed Won"} <= {p["value"] for p in stage["picklistValues"]}


def test_rt_1048_opportunity_and_contract(client, h):
    opps = rt1048_opps(client, h)
    rep = opps["Replacement"]
    assert (rep["StageName"], rep["Amount"], rep["CloseDate"], rep["Site__c"]) == ("Closed Won", 12000.0, "2026-10-17", "Site 3")
    lease = opps["Lease"]
    c = api(client, h, "GET", f"/sobjects/Contract/{lease['ContractId']}").json()
    assert (c["Name"], c["ContractNumber"], c["Status"], c["Asset_Id__c"]) == ("LS-5530", "00001048", "Draft", "MTR-2041")
    assert (c["StartDate"], c["ContractTerm"], c["EndDate"], c["Monthly_Rate__c"]) == ("2027-01-01", 30, "2029-06-30", 146.67)
    assert c["attributes"] == {"type": "Contract", "url": f"{BASE}/sobjects/Contract/{c['Id']}"}
    contracts = soql(client, h, "SELECT Name FROM Contract WHERE Account.Name = 'Customer A' AND Name = 'LS-5530'")
    assert contracts["totalSize"] == 1


# ---------------- SOQL and paging
def test_query_pages_through_every_opportunity(client, h):
    cases = seed().cases.values()
    expected = sum(c.facts.demand.internal for c in cases) + sum(bool(c.facts.demand.lease) for c in cases)
    assert soql(client, h, "SELECT COUNT() FROM Opportunity")["totalSize"] == expected
    first = soql(client, h, "SELECT Id, Name FROM Opportunity ORDER BY CloseDate, Name", batch=7)
    assert first["totalSize"] == expected and not first["done"] and len(first["records"]) == 7
    assert first["nextRecordsUrl"].startswith(BASE + "/query/01g") and first["nextRecordsUrl"].endswith("-7")
    records = query_all(client, h, "SELECT Id, Name FROM Opportunity ORDER BY CloseDate, Name", batch=7)
    assert len(records) == expected == len({r["Id"] for r in records})
    whole = soql(client, h, "SELECT Id FROM Opportunity ORDER BY CloseDate, Name")
    assert whole["done"] and "nextRecordsUrl" not in whole and [r["Id"] for r in whole["records"]] == [r["Id"] for r in records]
    assert error(client.get(ROOT + BASE + "/query/01gBOGUS-7", headers=h), 400) == "INVALID_QUERY_LOCATOR"


def test_where_order_limit_offset(client, h):
    proposals = soql(client, h, "select id from opportunity where stagename = 'proposal'")["totalSize"]
    won = soql(client, h, "SELECT Id FROM Opportunity WHERE StageName IN ('Closed Won')")["totalSize"]
    total = soql(client, h, "SELECT COUNT() FROM Opportunity")["totalSize"]
    assert proposals + won == total and proposals and won
    assert soql(client, h, "SELECT Id FROM Opportunity WHERE StageName NOT IN ('Closed Won')")["totalSize"] == proposals
    leases = soql(client, h, "SELECT Id FROM Opportunity WHERE Name LIKE '%re-lease%' AND Type = 'Lease'")["totalSize"]
    assert leases == soql(client, h, "SELECT Id FROM Opportunity WHERE Lease_Reference__c != null")["totalSize"]
    mixed = soql(
        client,
        h,
        "SELECT Id, Amount FROM Opportunity WHERE (Type = 'Lease' AND Amount >= 100) OR (Type = 'Replacement' AND Amount < 5000)",
    )
    assert mixed["totalSize"] > 0
    assert all(r["Amount"] is not None for r in mixed["records"])
    rows = soql(
        client, h, "SELECT Name, Amount, CloseDate FROM Opportunity WHERE Amount != NULL ORDER BY Amount DESC, Name LIMIT 5"
    )
    amounts = [r["Amount"] for r in rows["records"]]
    assert rows["totalSize"] == 5 and amounts == sorted(amounts, reverse=True)
    page2 = soql(client, h, "SELECT Name FROM Opportunity WHERE Amount != NULL ORDER BY Amount DESC, Name LIMIT 3 OFFSET 2")
    assert [r["Name"] for r in page2["records"]] == [r["Name"] for r in rows["records"]][2:5]
    accounts = soql(client, h, "SELECT Name FROM Account WHERE NOT Name = 'Customer A' ORDER BY Name DESC")["records"]
    assert [a["Name"] for a in accounts] == ["Customer C", "Customer B"]
    assert soql(client, h, "SELECT Id FROM Task WHERE ActivityDate > 2026-10-01 AND IsClosed = FALSE")["totalSize"] > 0
    recent = soql(client, h, "SELECT COUNT() FROM Account WHERE LastModifiedDate = LAST_N_DAYS:3650")["totalSize"]
    assert recent == 3


def test_query_errors(client, h):
    def err(q):
        return error(api(client, h, "GET", "/query", params={"q": q}), 400)

    assert err("SELECT FROM Opportunity") == "MALFORMED_QUERY"
    assert err("SELECT Id FROM Opportunity WHERE") == "MALFORMED_QUERY"
    assert err("SELECT Id FROM Opportunity WHERE Type = 'Lease' AND Amount > 1 OR Amount < 2") == "MALFORMED_QUERY"
    assert err("SELECT Id FROM Opportunity; DROP TABLE x") == "MALFORMED_QUERY"
    assert err("SELECT Id, Bogus FROM Opportunity") == "INVALID_FIELD"
    assert err("SELECT Id, Nope.Name FROM Opportunity") == "INVALID_FIELD"
    assert err("SELECT Id FROM Opportunity WHERE CloseDate = '2026-12-31'") == "INVALID_FIELD"
    assert err("SELECT Id FROM Opportunity WHERE Amount = '12'") == "INVALID_FIELD"
    assert err("SELECT Id FROM Widget__c") == "INVALID_TYPE"
    assert err("SELECT Id FROM Opportunity OFFSET 2001") == "NUMBER_OUTSIDE_VALID_RANGE"
    # quotes inside a literal are data, never SQL
    assert soql(client, h, "SELECT Id FROM Account WHERE Name = 'x\\' OR \\'1\\'=\\'1'")["totalSize"] == 0


# ---------------- describe and retrieve
def test_describe(client, h):
    g = api(client, h, "GET", "/sobjects").json()
    assert {"Account", "Contact", "Opportunity", "Contract", "Task", "User"} <= {o["name"] for o in g["sobjects"]}
    d = api(client, h, "GET", "/sobjects/Opportunity/describe").json()
    assert d["keyPrefix"] == "006" and d["createable"] and d["updateable"]
    fields = {f["name"]: f for f in d["fields"]}
    assert fields["Amount"]["type"] == "currency" and fields["CloseDate"]["type"] == "date"
    assert fields["AccountId"]["referenceTo"] == ["Account"] and fields["AccountId"]["relationshipName"] == "Account"
    assert fields["SystemModstamp"]["type"] == "datetime" and not fields["SystemModstamp"]["updateable"]
    info = api(client, h, "GET", "/sobjects/Account").json()
    assert info["objectDescribe"]["keyPrefix"] == "001" and len(info["recentItems"]) == 3
    assert error(api(client, h, "GET", "/sobjects/Widget__c/describe"), 404) == "NOT_FOUND"


def test_retrieve(client, h):
    a15 = api(client, h, "GET", f"/sobjects/Account/{CUSTOMER_A}").json()
    a18 = api(client, h, "GET", f"/sobjects/Account/{a15['Id']}", params={"fields": "Name,AccountNumber"}).json()
    assert len(a15["Id"]) == 18 and a15["Name"] == "Customer A"
    assert a15["CreatedDate"].endswith("+0000") and a15["SystemModstamp"] < "2026-10-07T09:00:00.000+0000"
    assert set(a18) == {"attributes", "Name", "AccountNumber"} and a18["AccountNumber"] == "CUST-A"
    assert error(api(client, h, "GET", "/sobjects/Account/001Hs00009ZZZZZ"), 404) == "NOT_FOUND"
    assert error(api(client, h, "GET", "/sobjects/Account/garbage"), 404) == "NOT_FOUND"


# ---------------- writes
def outbox(subject: str) -> list[tuple[str, dict]]:
    with engine.connect() as conn:
        q = text("SELECT type, data FROM sim.outbox WHERE source = 'crm' AND subject = :s ORDER BY id")
        return [(r[0], r[1]) for r in conn.execute(q, {"s": subject})]


def test_create_sale_task(client, h):
    opp = rt1048_opps(client, h)["Replacement"]
    body = {"Subject": "Sale: MTR-2041 to Customer A", "Type": "Sale", "WhatId": opp["Id"][:15], "ActivityDate": "2026-10-10"}
    r = api(client, h, "POST", "/sobjects/Task", json=body)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["success"] is True and created["errors"] == [] and created["id"].startswith("00T") and len(created["id"]) == 18
    task = api(client, h, "GET", f"/sobjects/Task/{created['id']}").json()
    assert (task["Status"], task["Priority"], task["IsClosed"], task["WhatId"]) == ("Not Started", "Normal", False, opp["Id"])
    assert task["AccountId"] == opp["AccountId"] and task["OwnerId"] == auth.user_id(auth.INTEGRATION_USER)
    [(kind, data)] = outbox(created["id"])
    assert kind == "salesforce.Task.created" and data["Subject"] == body["Subject"]
    found = soql(client, h, f"SELECT Id, Account.Name FROM Task WHERE Id = '{created['id']}'")["records"]  # noqa: S608 - SOQL sent to the simulator, not SQL run here
    assert found[0]["Account"]["Name"] == "Customer A"


def test_create_opportunity_and_errors(client, h):
    r = api(
        client, h, "POST", "/sobjects/Opportunity", json={"Name": "New lease", "StageName": "Proposal", "CloseDate": "2026-12-31"}
    )
    assert r.status_code == 201
    opp = api(client, h, "GET", f"/sobjects/Opportunity/{r.json()['id']}").json()
    assert (opp["Probability"], opp["ForecastCategoryName"], opp["IsClosed"]) == (75.0, "Pipeline", False)

    def err(obj, body, status=400):
        return error(api(client, h, "POST", f"/sobjects/{obj}", json=body), status)

    assert err("Opportunity", {"Name": "x"}) == "REQUIRED_FIELD_MISSING"
    assert (
        err("Opportunity", {"Name": "x", "StageName": "Maybe", "CloseDate": "2026-12-31"})
        == "INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST"
    )
    assert err("Opportunity", {"Name": "x", "StageName": "Proposal", "CloseDate": "31/12/2026"}) == "JSON_PARSER_ERROR"
    assert err("Task", {"Bogus__c": 1}) == "INVALID_FIELD"
    assert err("Task", {"IsClosed": True}) == "INVALID_FIELD_FOR_INSERT_UPDATE"
    assert err("Task", {"WhatId": "006Hs0000000000"}) == "INVALID_CROSS_REFERENCE_KEY"
    assert err("Task", {"WhatId": CUSTOMER_A[:3] + "x"}) == "MALFORMED_ID"
    assert err("Task", {"WhoId": CUSTOMER_A}) == "FIELD_INTEGRITY_EXCEPTION"
    assert err("Account", {"Name": "Customer D"}, 403) == "INSUFFICIENT_ACCESS_OR_READONLY"
    bad_json = api(client, h, "POST", "/sobjects/Task", content=b"{nope", headers={"Content-Type": "application/json"})
    assert error(bad_json, 400) == "JSON_PARSER_ERROR"


def test_patch_and_delta_read(client, h):
    lease = rt1048_opps(client, h)["Lease"]
    delta = "SELECT Id, StageName, SystemModstamp FROM Opportunity WHERE SystemModstamp > 2026-10-07T09:00:00Z AND Type = 'Lease'"
    assert lease["Id"] not in {r["Id"] for r in query_all(client, h, delta)}
    r = api(client, h, "PATCH", f"/sobjects/Opportunity/{lease['Id']}", json={"StageName": "Closed Won", "Amount": 150})
    assert r.status_code == 204 and r.content == b""
    changed = {r["Id"]: r for r in query_all(client, h, delta)}
    assert changed[lease["Id"]]["StageName"] == "Closed Won"
    opp = api(client, h, "GET", f"/sobjects/Opportunity/{lease['Id']}").json()
    assert (opp["IsWon"], opp["IsClosed"], opp["Probability"], opp["Amount"]) == (True, True, 100.0, 150.0)
    [(kind, data)] = outbox(lease["Id"])
    assert kind == "salesforce.Opportunity.updated" and data["changedFields"] == ["Amount", "StageName"]
    assert error(api(client, h, "PATCH", f"/sobjects/Opportunity/{lease['Id']}", json={"IsWon": False}), 400) == (
        "INVALID_FIELD_FOR_INSERT_UPDATE"
    )
    assert error(api(client, h, "PATCH", "/sobjects/Opportunity/006Hs0000000000", json={"Amount": 1}), 404) == "NOT_FOUND"
    assert error(api(client, h, "PATCH", f"/sobjects/Contract/{lease['ContractId']}", json={"Status": "Activated"}), 403) == (
        "INSUFFICIENT_ACCESS_OR_READONLY"
    )
