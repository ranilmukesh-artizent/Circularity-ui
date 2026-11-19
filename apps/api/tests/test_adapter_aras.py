"""B5b: the Aras Innovator (bom) adapter against the full Aras mock (OData v4 RESTful API).

Needs source-sim running and the worker stopped. The assets of each product come from Teamcenter
(asset.configuration_item), so plm is synced first when the store does not have it yet. Only bom is reset, and only
its cursors and queued jobs are touched; the module ends with a reset and a full sync that restore the demo's values.
"""

import hashlib

import httpx
import pytest
from sqlalchemy import text

from di.canonical import store
from di.config import get_settings
from di.connectors.http import SourceClient
from di.connectors.registry import ADAPTERS
from di.connectors.sync import ensure_sources, run_sync
from di.db import SessionLocal, engine

SIM = get_settings().source_sim_url
SID = "bom"
ARAS = SIM + "/aras/InnovatorServer"


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def fresh() -> None:
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = :s"), {"s": SID})
        conn.execute(
            text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = :s"), {"s": SID}
        )


@pytest.fixture(scope="module", autouse=True)
def clean():
    fresh()
    with SessionLocal() as s:
        ensure_sources(s)
        s.execute(
            text(
                "UPDATE source_system SET status = 'live' WHERE id IN ('bom', 'plm') AND status IN ('unavailable', "
                "'auth_expired', 'failing')"
            )
        )
        s.commit()
        has_plm = s.execute(
            text(
                "SELECT 1 FROM provenance WHERE model = 'asset' AND key = 'MTR-2041' AND "
                "field = 'configuration_item' AND source_id = 'plm'"
            )
        ).first()
    if not has_plm:
        assert run_sync("plm", "manual", full=True)["status"] == "ok"
    yield
    fresh()
    run_sync(SID, "manual", full=True)


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def prov(rec: dict, field: str) -> tuple:
    p = next(x for x in rec["provenance"][field] if x["source_id"] == SID)
    return p["source_field"], p["source_value"], p["transform"]


def sync(trigger: str) -> dict:
    out = run_sync(SID, trigger)
    if out["status"] == "partial" and "eadlock" in (out["error"] or ""):
        out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    return out


def delta_reads() -> int:
    a = ADAPTERS[SID]
    with SessionLocal() as s:
        client = SourceClient(SID, SIM + a.base_path, a.auth(), s)
        try:
            cursor = s.execute(
                text("SELECT cursor FROM sync_cursor WHERE source_id = :s AND resource = 'structure'"), {"s": SID}
            ).scalar()
            assert cursor
            return sum(1 for _ in a.resources()[0].read(client, cursor))
        finally:
            client.close()
            s.rollback()


def aras_client() -> httpx.Client:
    form = {
        "grant_type": "password",
        "scope": "Innovator",
        "client_id": "IOMApp",
        "username": "di-connector",
        "password": hashlib.md5(b"Circularity-demo-aras-1").hexdigest(),
        "database": "InnovatorDB",
    }
    tok = httpx.post(ARAS + "/oauthserver/connect/token", data=form, timeout=30).json()["access_token"]
    return httpx.Client(base_url=ARAS + "/server/odata", headers={"Authorization": "Bearer " + tok}, timeout=30)


def test_initial_sync_maps_the_demo_examples():
    first = sync("initial")
    assert first["records_read"] > 10  # one record per product configuration
    a = canonical("asset", "MTR-2041")
    d = a["data"]
    comps = d["components"]
    assert comps[0] == comps[0] | {
        "name": "Rotor assembly",
        "part": "P-55-ROT-01",
        "qty": 1,
        "harvestable": False,
        "state": "released",
    }
    assert [c["name"] for c in comps][:3] == ["Rotor assembly", "Stator assembly", "Bearing set"]
    bearings = next(c for c in comps if c["name"] == "Bearing set")
    assert bearings["harvestable"] and {s["part"] for s in bearings["spare_parts"]} >= {"SKF-6316-2Z/C3", "VLT-SK-250M"}
    skf = next(s for s in bearings["spare_parts"] if s["part"] == "SKF-6316-2Z/C3")
    assert skf["manufacturer"] == "SKF" and skf["unit_cost"] == round(13400 / 83.5, 2)
    assert prov(a, "components")[0::2] == ("Part.item_number", "Part name lookup")
    assert prov(a, "components")[1][0] == "P-55-ROT-01"
    assert d["bom_state"] == "released" and prov(a, "bom_state") == ("Part.state", "Released", "State map")
    assert (d["bom_item"], d["bom_revision"]) == ("MTR-55-IE3-250M", "C")
    assert "Rotor assembly" not in d["harvestable_components"]
    assert d["manufacturer_parts"] and all(m["part"] for m in d["manufacturer_parts"])


def test_unchanged_delta_reads_nothing_and_a_change_is_picked_up():
    assert delta_reads() == 0
    assert sync("schedule")["records_read"] == 0

    with aras_client() as c:
        (product,) = c.get("/Part", params={"$filter": "item_number eq 'MTR-55-IE3-250M'", "$select": "id"}).json()["value"]
        (skf,) = c.get("/Manufacturer", params={"$filter": "name eq 'SKF'"}).json()["value"]
        # a released Part cannot be edited ...
        assert c.patch(f"/Part('{product['id']}')", json={"name": "renamed"}).status_code == 400
        # ... but a second source can be approved on its AML
        r = c.post(
            f"/Part('{product['id']}')/Part AML",
            headers={"Prefer": "return=minimal"},
            json={"related_id": {"item_number": "SKF-55-IE3-250M", "manufacturer@odata.bind": f"Manufacturer('{skf['id']}')"}},
        )
        assert r.status_code == 204, r.text

    again = sync("schedule")
    assert again["records_read"] == 1
    parts = [m["part"] for m in canonical("asset", "MTR-2041")["data"]["manufacturer_parts"]]
    assert "SKF-55-IE3-250M" in parts
    assert delta_reads() == 0
