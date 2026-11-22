"""B5b: the Teamcenter (plm) adapter against the full Teamcenter mock (SOA over HTTP/JSON).

Needs source-sim running and the worker stopped. Only plm is reset, and only its cursors and queued jobs are touched;
the canonical store is shared, so the module ends with a reset and a full sync that restore the demo's values.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors.http import SourceClient
from di.connectors.registry import ADAPTERS
from di.connectors.sync import ensure_sources, run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store

SIM = get_settings().source_sim_url
SID = "plm"
TC = SIM + "/teamcenter/tc/JsonRestServices"


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def fresh() -> None:
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")  # deliver the reset events now, so they cannot land mid-test
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
                "UPDATE source_system SET status = 'live' WHERE id = :s AND status IN ('unavailable', 'auth_expired', "
                "'failing')"
            ),
            {"s": SID},
        )
        s.commit()
    yield
    fresh()
    run_sync(SID, "manual", full=True)  # put the demo's values back in the shared canonical store


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
    if out["status"] == "partial" and "eadlock" in (out["error"] or ""):  # a concurrent sync of another source
        out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    return out


def delta_reads() -> int:
    a = ADAPTERS[SID]
    with SessionLocal() as s:
        client = SourceClient(SID, SIM + a.base_path, a.auth(), s)
        try:
            cursor = s.execute(
                text("SELECT cursor FROM sync_cursor WHERE source_id = :s AND resource = 'compatibility'"), {"s": SID}
            ).scalar()
            assert cursor
            return sum(1 for _ in a.resources()[0].read(client, cursor))
        finally:
            client.close()
            s.rollback()


def tc(http: httpx.Client, op: str, body: dict) -> dict:
    r = http.post(f"{TC}/{op}", json={"header": {"state": {}, "policy": {}}, "body": body})
    r.raise_for_status()
    return r.json()


def test_initial_sync_maps_the_demo_examples():
    first = sync("initial")
    assert first["records_read"] == 128
    a = canonical("asset", "MTR-2041")
    d = a["data"]
    assert (d["configuration"], d["configuration_item"], d["config_revision"], d["bom_ref"], d["compatibility"]) == (
        "55 kW · IE3 · 250M",
        "MTR-55-IE3-250M",
        "C",
        "BOM-55-C",
        "compatible",
    )
    assert prov(a, "configuration") == ("ITEM_ID", "MTR-55-IE3-250M", "Config decoded")
    assert prov(a, "compatibility") == ("ALT_APPROVED", "Y", "Boolean")
    assert prov(a, "bom_ref") == ("REV", "C", "Revision prefix")
    assert next(p for p in a["provenance"]["configuration"] if p["source_id"] == SID)["authority"] is True
    assert d["approved_alternates"] == []  # its 55 kW alternates have another frame
    assert d["config_release_status"] == "released" and d["config_status"] == "verified"
    assert d["compatible_items"][0] == "MTR-55-IE3-250M"
    assert d["config_properties"]["IEC frame"] == "250M"


def test_unchanged_delta_reads_nothing_and_a_change_is_picked_up():
    assert delta_reads() == 0
    assert sync("schedule")["records_read"] == 0

    with httpx.Client(timeout=30) as http:
        tc(
            http,
            "Core-2011-06-Session/login",
            {
                "credentials": {
                    "user": "di_connector",
                    "password": "Circularity-demo-tc-1",
                    "group": "",
                    "role": "",
                    "locale": "",
                    "descrimator": "t",
                }
            },
        )
        queries = {q["name"]: q["query"] for q in tc(http, "Query-2006-03-SavedQuery/getSavedQueries", {})["queries"]}
        res = tc(
            http,
            "Query-2008-06-SavedQuery/executeSavedQueries",
            {
                "input": [
                    {
                        "query": queries["Nf0 Compatibility Checks"],
                        "entries": ["Asset ID"],
                        "values": ["MTR-2041"],
                        "maxNumToReturn": 0,
                        "limitList": [],
                        "resultsType": 0,
                    }
                ]
            },
        )
        (uid,) = res["arrayOfResults"][0]["objectUIDS"]
        sd = tc(
            http,
            "Core-2010-09-DataManagement/setProperties",
            {
                "info": [
                    {
                        "object": {"uid": uid},
                        "timestamp": "",
                        "vecNameVal": [
                            {"name": "nf0ConfigStatus", "values": ["MISMATCH"]},
                            {"name": "nf0AltApproved", "values": ["N"]},
                            {"name": "nf0Compatibility", "values": ["UNDER_REVIEW"]},
                        ],
                    }
                ],
                "options": [],
            },
        )
        assert sd["updated"] == [uid] and "partialErrors" not in sd

    again = sync("schedule")
    assert again["records_read"] == 1
    a = canonical("asset", "MTR-2041")
    assert (a["data"]["compatibility"], a["data"]["config_status"]) == ("under_review", "mismatch")
    assert prov(a, "compatibility") == ("ALT_APPROVED", "N", "Boolean")
    assert delta_reads() == 0
