"""B5b contract tests: call the Teamcenter mock the way a Teamcenter SOA (JSON over HTTP) client does."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim import clock
from sim.db import engine
from sim.main import app

TC = "/teamcenter/tc/JsonRestServices"
CRED = {
    "user": "di_connector",
    "password": "Circularity-demo-tc-1",
    "group": "",
    "role": "",
    "locale": "en_US",
    "descrimator": "contract-test",
}


def soa(client, op: str, body: dict) -> dict:
    r = client.post(f"{TC}/{op}", json={"header": {"state": {"stateless": True}, "policy": {}}, "body": body})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "plm"}).raise_for_status()
        soa(c, "Core-2011-06-Session/login", {"credentials": CRED})
        yield c
        c.post("/_sim/reset", params={"system": "plm"}).raise_for_status()


@pytest.fixture(scope="module")
def queries(client) -> dict:
    return {q["name"]: q["query"] for q in soa(client, "Query-2006-03-SavedQuery/getSavedQueries", {})["queries"]}


def find(client, queries, name: str, entries: list[str], values: list[str]) -> list[str]:
    res = soa(
        client,
        "Query-2008-06-SavedQuery/executeSavedQueries",
        {
            "input": [
                {
                    "query": queries[name],
                    "entries": entries,
                    "values": values,
                    "maxNumToReturn": 0,
                    "limitList": [],
                    "resultsType": 0,
                }
            ]
        },
    )
    assert res[".QName"].endswith("SavedQuery.SavedQueriesResponse") and "partialErrors" not in res["serviceData"], res
    out = res["arrayOfResults"][0]
    assert out["numOfObjects"] == len(out["objectUIDS"])
    return out["objectUIDS"]


def props(client, uids: list[str], attrs: list[str]) -> dict[str, dict]:
    sd = soa(client, "Core-2006-03-DataManagement/getProperties", {"objects": [{"uid": u} for u in uids], "attributes": attrs})
    return {u: sd["modelObjects"][u]["props"] for u in sd["plain"]}


# ---------------------------------------------------------------- session
def test_login_session_and_exceptions():
    with TestClient(app) as c:
        out = c.post(f"{TC}/Query-2006-03-SavedQuery/getSavedQueries", json={"header": {}, "body": {}}).json()
        assert out[".QName"].endswith("Exceptions.InvalidUserException") and out["code"] == 515117
        bad = soa(c, "Core-2011-06-Session/login", {"credentials": CRED | {"password": "nope"}})
        assert bad[".QName"].endswith("Exceptions.InvalidCredentialsException") and bad["code"] == 515143
        r = c.post(f"{TC}/Core-2011-06-Session/login", json={"header": {}, "body": {"credentials": CRED}})
        assert r.json()[".QName"] == "http://teamcenter.com/Schemas/Core/2011-06/Session.LoginResponse"
        assert r.json()["serverInfo"]["UserID"] == "di_connector" and r.cookies.get("JSESSIONID")
        info = soa(c, "Core-2007-01-Session/getTCSessionInfo", {})
        assert info["extraInfo"]["GroupName"] == "Engineering" and info["extraInfo"]["RoleName"] == "Designer"
        assert "ImanQuery" not in str(soa(c, "Core-2006-03-Session/logout", {}))
        assert soa(c, "Query-2006-03-SavedQuery/getSavedQueries", {})[".QName"].endswith("InvalidUserException")
        assert c.post(f"{TC}/Core-2011-06-Session/login", content=b"not json").json()[".QName"].endswith("ServiceException")


# ---------------------------------------------------------------- reading
def test_saved_queries(client, queries):
    assert {"Item...", "Item Revision...", "Nf0 Compatibility Checks", "Nf0 Alternate Approvals"} <= set(queries)
    fields = soa(client, "Query-2006-03-SavedQuery/describeSavedQueries", {"queries": [queries["Item..."]]})
    assert {"Item ID", "Name", "Modified After"} <= {f["entryName"] for f in fields["fieldLists"][0]["fields"]}
    assert len(find(client, queries, "Nf0 Compatibility Checks", ["Asset ID"], ["*"])) == 128
    bad = soa(
        client,
        "Query-2008-06-SavedQuery/executeSavedQueries",
        {"input": [{"query": queries["Item..."], "entries": ["Colour"], "values": ["red"]}]},
    )
    assert bad["serviceData"]["partialErrors"][0]["errorValues"][0]["code"] == 214005


def test_the_demo_mapping_example(client, queries):
    """MAPPINGS.plm: ITEM_ID MTR-55-IE3-250M → "55 kW · IE3 · 250M"; ALT_APPROVED Y; REV C → BOM-55-C."""
    (check,) = find(client, queries, "Nf0 Compatibility Checks", ["Asset ID"], ["MTR-2041"])
    c = props(
        client,
        [check],
        [
            "nf0AssetId",
            "nf0DesignRevision",
            "nf0AltApproved",
            "nf0ConfigStatus",
            "nf0Compatibility",
            "nf0CompatibleItems",
            "last_mod_date",
        ],
    )[check]
    assert c["nf0AltApproved"] == {"dbValues": ["Y"], "uiValues": ["Y"]}
    assert (c["nf0ConfigStatus"]["dbValues"], c["nf0Compatibility"]["dbValues"]) == (["VERIFIED"], ["COMPATIBLE"])
    assert c["nf0CompatibleItems"]["dbValues"][0] == "MTR-55-IE3-250M"
    assert c["nf0DesignRevision"]["uiValues"] == ["MTR-55-IE3-250M/C;1-55 kW · IE3 · 250M"]
    assert datetime.strptime(c["last_mod_date"]["uiValues"][0], "%d-%b-%Y %H:%M")  # noqa: DTZ007 - parses a display value
    rev_uid = c["nf0DesignRevision"]["dbValues"][0]
    rev = props(
        client,
        [rev_uid],
        ["item_id", "item_revision_id", "object_name", "nf0BomRef", "release_status_list", "items_tag", "nf0ConfigProps"],
    )[rev_uid]
    assert (rev["item_revision_id"]["dbValues"], rev["nf0BomRef"]["dbValues"]) == (["C"], ["BOM-55-C"])
    assert rev["object_name"]["dbValues"] == ["55 kW · IE3 · 250M"] and "IEC frame=250M" in rev["nf0ConfigProps"]["dbValues"]
    status = props(client, rev["release_status_list"]["dbValues"], ["object_name", "date_released"])
    assert [s["object_name"]["dbValues"][0] for s in status.values()] == ["TCM Released"]

    out = soa(
        client,
        "Core-2007-01-DataManagement/getItemFromId",
        {"infos": [{"itemId": "MTR-55-IE3-250M", "revIds": []}], "nRev": 0, "pref": {}},
    )
    assert [r["itemRevision"]["uid"] for r in out["output"][0]["itemRevOutput"]][-1] == rev_uid
    assert len(out["output"][0]["itemRevOutput"]) == 3  # A, B, C
    item = out["output"][0]["item"]["uid"]
    grm = soa(
        client,
        "Core-2007-09-DataManagement/expandGRMRelationsForPrimary",
        {
            "primaryObjects": [{"uid": item}],
            "pref": {"expItemRev": False, "returnRelations": True, "info": [{"relationTypeName": "Nf0AltApproval"}]},
        },
    )
    rels = grm["output"][0]["relationshipData"][0]["relationshipObjects"]
    assert rels and all(r["relation"]["type"] == "Nf0AltApproval" for r in rels)
    approvals = props(client, [r["relation"]["uid"] for r in rels], ["nf0Approved", "nf0Reason"])
    assert {a["nf0Approved"]["dbValues"][0] for a in approvals.values()} == {"N"}  # other 55 kW frames: not approved
    assert {a["nf0Reason"]["dbValues"][0] for a in approvals.values()} == {"Interface differs"}


def test_wildcards_and_partial_errors(client, queries):
    uids = find(client, queries, "Item...", ["Item ID"], ["MTR-55-*"])
    ids = {p["item_id"]["dbValues"][0] for p in props(client, uids, ["item_id"]).values()}
    assert "MTR-55-IE3-250M" in ids and all(i.startswith("MTR-55-") for i in ids)
    sd = soa(
        client,
        "Core-2006-03-DataManagement/getProperties",
        {"objects": [{"uid": uids[0]}, {"uid": "AAAAAAAAAAAAAA"}], "attributes": ["item_id", "no_such_prop"]},
    )
    codes = sorted(e["errorValues"][0]["code"] for e in sd["partialErrors"])
    assert codes == [38015, 515001]


# ---------------------------------------------------------------- writes
def _outbox(subject: str) -> list[dict]:
    with engine.connect() as conn:
        return [
            r.data
            for r in conn.execute(
                text("SELECT data FROM sim.outbox WHERE source='plm' AND subject=:s ORDER BY id"), {"s": subject}
            )
        ]


def test_set_properties_rules(client, queries):
    check = find(client, queries, "Nf0 Compatibility Checks", ["Asset ID"], ["PMP-*"])[0]
    asset = props(client, [check], ["nf0AssetId"])[check]["nf0AssetId"]["dbValues"][0]
    (rev,) = find(client, queries, "Item Revision...", ["Item ID", "Revision"], ["MTR-55-IE3-250M", "C"])

    def setp(uid, nv, ts=""):
        return soa(
            client,
            "Core-2010-09-DataManagement/setProperties",
            {"info": [{"object": {"uid": uid}, "timestamp": ts, "vecNameVal": nv}], "options": []},
        )

    def code(sd):
        return sd["partialErrors"][0]["errorValues"][0]["code"]

    assert code(setp(rev, [{"name": "nf0BomRef", "values": ["X"]}])) == 515034  # released
    assert code(setp(check, [{"name": "nf0ConfigStatus", "values": ["MAYBE"]}])) == 54060  # not in the LOV
    assert code(setp(check, [{"name": "nf0AssetId", "values": ["X"]}])) == 515035  # not modifiable
    assert code(setp(check, [{"name": "nf0ConfigStatus", "values": ["MISMATCH"]}], ts="2020-01-01T00:00:00+00:00")) == 214016

    with engine.connect() as conn:
        before = clock.now(conn)
    sd = setp(check, [{"name": "nf0ConfigStatus", "values": ["MISMATCH"]}, {"name": "nf0AltApproved", "values": ["N"]}])
    assert sd["updated"] == [check] and "partialErrors" not in sd
    stamp = sd["modelObjects"][check]["props"]["last_mod_date"]["dbValues"][0]
    assert datetime.fromisoformat(stamp) >= before.replace(microsecond=0)
    assert _outbox(f"CMP-{asset}")[-1]["changed"] == ["nf0AltApproved", "nf0ConfigStatus"]
    after = (before - timedelta(seconds=1)).strftime("%d-%b-%Y %H:%M:%S")  # Teamcenter dates have whole seconds
    assert check in find(client, queries, "Nf0 Compatibility Checks", ["Modified After"], [after])
    assert find(client, queries, "Item...", ["Modified After"], [after]) == []
