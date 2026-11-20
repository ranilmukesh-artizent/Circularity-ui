"""B5b contract tests: call the Aras Innovator mock the way an Aras RESTful API (OData) client does."""

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.db import engine
from sim.main import app

ROOT = "/aras/InnovatorServer"
ODATA = ROOT + "/server/odata"
LOGIN = {
    "grant_type": "password",
    "scope": "Innovator",
    "client_id": "IOMApp",
    "username": "di-connector",
    "password": hashlib.md5(b"Circularity-demo-aras-1").hexdigest(),  # noqa: S324 - the vendor's protocol
    "database": "InnovatorDB",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "bom"}).raise_for_status()
        tok = c.post(ROOT + "/oauthserver/connect/token", data=LOGIN).json()["access_token"]
        c.headers["Authorization"] = "Bearer " + tok
        yield c
        c.post("/_sim/reset", params={"system": "bom"}).raise_for_status()


def get(client, path: str, **params) -> dict:
    r = client.get(ODATA + path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def one(client, itemtype: str, flt: str, **params) -> dict:
    (row,) = get(client, f"/{itemtype}", **{"$filter": flt} | params)["value"]
    return row


# ---------------------------------------------------------------- authentication
def test_oauth_server_discovery_and_token_errors():
    with TestClient(app) as c:
        loc = c.get(ROOT + "/Server/OAuthServerDiscovery.aspx").json()["locations"][0]["uri"]
        assert loc.endswith("/aras/InnovatorServer/oauthserver/")
        conf = c.get(ROOT + "/oauthserver/.well-known/openid-configuration").json()
        assert conf["token_endpoint"].endswith("/oauthserver/connect/token") and conf["issuer"] == "OAuthServer"
        url = ROOT + "/oauthserver/connect/token"
        ok = c.post(url, data=LOGIN).json()
        assert ok["token_type"] == "Bearer" and ok["expires_in"] == 3600
        assert c.post(url, data=LOGIN | {"password": "Circularity-demo-aras-1"}).json()["error"] == "invalid_grant"  # not hashed
        assert c.post(url, data=LOGIN | {"database": "Other"}).json()["error"] == "invalid_grant"
        assert c.post(url, data=LOGIN | {"client_id": "Nobody"}).json()["error"] == "invalid_client"
        assert c.post(url, data=LOGIN | {"scope": "openid"}).json()["error"] == "invalid_scope"
        r = c.post(url, data=LOGIN | {"grant_type": "client_credentials"})
        assert r.status_code == 400 and r.json()["error"] == "unsupported_grant_type"
        r = c.get(ODATA + "/Part")
        assert r.status_code == 401 and r.json()["code"] == "401" and r.json()["details"]["message"]
        assert c.get(ODATA + "/Part", headers={"Authorization": "Bearer nope"}).status_code == 401


# ---------------------------------------------------------------- reading
def test_the_demo_mapping_example(client):
    """MAPPINGS.bom: Part.item_number P-55-ROT-01 → components[0] Rotor assembly; Part BOM.quantity 1; Part.state Released."""
    expand = "Part BOM($orderby=sort_order;$expand=related_id($select=item_number,name,state,nf_harvestable))"
    top = one(client, "Part", "item_number eq 'MTR-55-IE3-250M'", **{"$expand": expand})
    assert (top["name"], top["state"], top["major_rev"], top["classification"]) == (
        "Industrial motor 55 kW · IE3 · 250M",
        "Released",
        "C",
        "Product",
    )
    assert top["@odata.id"] == f"Part('{top['id']}')" and len(top["id"]) == 32 and top["id"] == top["id"].upper()
    first = top["Part BOM"][0]
    assert (first["quantity"], first["sort_order"]) == (1, 10)
    assert first["related_id"] | {} == first["related_id"] | {
        "item_number": "P-55-ROT-01",
        "name": "Rotor assembly",
        "state": "Released",
        "nf_harvestable": "0",
    }
    assert "source_id" not in first  # item properties appear only when selected or expanded
    bearings = one(client, "Part", "item_number eq 'P-55-BRG-01'")
    lines = get(client, f"/Part('{bearings['id']}')/Part BOM", **{"$expand": "related_id($select=item_number)"})["value"]
    assert {x["related_id"]["item_number"] for x in lines} == {"SKF-6316-2Z/C3", "SKF-6314-2Z/C3", "VLT-SK-250M"}
    mp = one(client, "Manufacturer Part", "item_number eq '6316-2Z/C3'", **{"$expand": "manufacturer($select=name)"})
    assert mp["manufacturer"]["name"] == "SKF"
    skf = one(client, "Part", "item_number eq 'SKF-6316-2Z/C3'")
    assert (skf["cost"], skf["nf_cost_currency"], skf["make_buy"], skf["classification"]) == (13400.0, "INR", "Buy", "Component")


def test_navigation_select_and_counts(client):
    top = one(client, "Part", "item_number eq 'MTR-55-IE3-250M'", **{"$select": "item_number,created_by_id"})
    assert set(top) == {
        "@odata.id",
        "id",
        "item_number",
        "created_by_id@aras.id",
        "created_by_id@aras.type",
        "created_by_id@aras.keyed_name",
    }
    assert top["created_by_id@aras.keyed_name"] == "Innovator Admin"
    pid = top["id"]
    assert get(client, f"/Part('{pid}')/item_number")["value"] == "MTR-55-IE3-250M"
    assert client.get(ODATA + f"/Part('{pid}')/item_number/$value").text == "MTR-55-IE3-250M"
    line = get(client, f"/Part('{pid}')/Part BOM", **{"$top": "1"})["value"][0]
    assert get(client, f"/Part BOM('{line['id']}')/related_id")["item_number"] == "P-55-ROT-01"
    total = int(client.get(ODATA + "/Part/$count").text)
    assert get(client, "/Part", **{"$count": "true", "$top": "1"})["@odata.count"] == total > 500
    # Aras's bracketed names: parts with a BOM line of quantity 2 (the seal kit under the 250M bearing set)
    hits = get(client, "/Part", **{"$filter": "[Part BOM]/quantity eq 2", "$select": "item_number"})["value"]
    assert "P-55-BRG-01" in {h["item_number"] for h in hits}
    assert {
        h["item_number"]
        for h in get(
            client, "/Part", **{"$filter": "startswith(item_number,'SKF-') and cost gt 12000", "$select": "item_number"}
        )["value"]
    } == {"SKF-6316-2Z/C3"}


def test_server_driven_paging(client):
    n = int(client.get(ODATA + "/Part/$count", params={"$filter": "classification eq 'Component'"}).text)
    seen, url, params = [], ODATA + "/Part", {"$filter": "classification eq 'Component'", "$select": "item_number"}
    while url:
        r = client.get(url, params=params, headers={"Prefer": "odata.maxpagesize=20"})
        body = r.json()
        assert len(body["value"]) <= 20 and r.headers["Preference-Applied"] == "odata.maxpagesize=20"
        seen += [v["item_number"] for v in body["value"]]
        url, params = body.get("@odata.nextLink"), None
        assert url is None or "$skiptoken=" in url
    assert len(seen) == len(set(seen)) == n
    assert len(get(client, "/Part", **{"$filter": "classification eq 'Component'"})["value"]) == n  # no paging unless asked


def test_errors(client):
    r = client.get(ODATA + "/Gizmo")
    assert r.status_code == 404 and r.json()["details"]["target"] == "AML"
    r = client.get(ODATA + "/Part", params={"$filter": "colour eq 'red'"})
    assert r.status_code == 400 and r.json()["message"] == "Bad Request" and "colour" in r.json()["details"]["message"]
    assert client.get(ODATA + "/Part", params={"$filter": "item_number eq"}).status_code == 400
    assert client.get(ODATA + "/Part('00000000000000000000000000000000')").status_code == 404


# ---------------------------------------------------------------- writes and lifecycle rules
def test_writes_follow_the_lifecycle(client):
    top = one(client, "Part", "item_number eq 'MTR-55-IE3-250M'")
    r = client.patch(ODATA + f"/Part('{top['id']}')", json={"name": "renamed"})
    assert r.status_code == 400 and "Released" in r.json()["details"]["message"]
    asm = one(client, "Part", "item_number eq 'P-55-ROT-01'")
    r = client.post(
        ODATA + f"/Part('{top['id']}')/Part BOM", json={"quantity": 1, "related_id@odata.bind": f"Part('{asm['id']}')"}
    )
    assert r.status_code == 400  # the BOM of a released part is frozen

    r = client.post(ODATA + "/Part", json={"item_number": "P-55-ROT-02", "name": "Rotor assembly (reman)", "cost": 120.5})
    assert r.status_code == 201 and r.headers["Location"].endswith(f"Part('{r.json()['id']}')")
    new = r.json()
    assert (new["state"], new["major_rev"], new["generation"]) == ("Preliminary", "A", 1)
    assert client.post(ODATA + "/Part", json={"item_number": "P-55-ROT-02"}).status_code == 400  # unique item_number
    assert client.post(ODATA + "/Part", json={"name": "no number"}).status_code == 400
    r = client.patch(
        ODATA + f"/Part('{new['id']}')", json={"description": "Remanufactured rotor"}, headers={"Prefer": "return=minimal"}
    )
    assert r.status_code == 204
    r = client.patch(ODATA + f"/Part('{new['id']}')", json={"state": "Released"})
    assert r.status_code == 400  # state changes only through the lifecycle
    upd = get(client, f"/Part('{new['id']}')", **{"$select": "description,modified_on,modified_by_id"})
    assert upd["description"] == "Remanufactured rotor" and upd["modified_by_id@aras.keyed_name"] == "Circularity Connector"

    skf = one(client, "Manufacturer", "name eq 'SKF'")
    r = client.post(
        ODATA + f"/Part('{top['id']}')/Part AML",
        json={"related_id": {"item_number": "SKF-55-ALT", "manufacturer@odata.bind": f"Manufacturer('{skf['id']}')"}},
    )
    assert r.status_code == 201 and r.json()["state"] == "Approved"
    aml = get(client, f"/Part('{top['id']}')/Part AML", **{"$expand": "related_id($select=item_number)"})["value"]
    assert "SKF-55-ALT" in {a["related_id"]["item_number"] for a in aml}
    changed = get(
        client, "/Part AML", **{"$filter": f"modified_on gt '{upd['modified_on']}' or modified_on eq '{upd['modified_on']}'"}
    )
    assert changed["value"]
    with engine.connect() as conn:
        types = {r.type for r in conn.execute(text("SELECT type FROM sim.outbox WHERE source = 'bom'"))}
    assert {"com.aras.innovator.Part.created", "com.aras.innovator.Part.updated", "com.aras.innovator.PartAML.created"} <= types
