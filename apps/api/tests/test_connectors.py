"""B9: connectors fill the canonical store from source-sim over HTTP (docs/backend-steps.md).

Needs source-sim running (docker compose). Stop the worker while these run (`docker compose stop worker`), so its
scheduled syncs do not race the tests.
"""

import hashlib
import hmac
import json

import httpx
import pytest
from sqlalchemy import text

from di.canonical import store
from di.canonical.store import Fact
from di.config import get_settings
from di.connectors.sync import ensure_sources, run_sync
from di.db import SessionLocal, engine
from tests.helpers import client, h

SIM = get_settings().source_sim_url
TABLES = ("conflict", "canonical", "provenance", "raw_record", "fetch_log", "sync_cursor", "sync_run")


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


@pytest.fixture(scope="module", autouse=True)
def clean():
    sim("DELETE", "/_sim/faults")
    for s in ("erp", "proc"):
        sim("POST", "/_sim/reset", params={"system": s})
    sim("POST", "/_sim/webhooks/deliver")  # deliver the reset events now, so they cannot land mid-test
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))
        for t in TABLES:
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - TABLES is a fixed list of table names
        conn.execute(text("DELETE FROM source_system"))
    with SessionLocal() as s:
        ensure_sources(s)
    yield
    sim("DELETE", "/_sim/faults")
    for s in ("erp", "proc"):
        sim("POST", "/_sim/reset", params={"system": s})


def canonical(model, key):
    with SessionLocal() as s:
        return store.get(s, model, key)


def test_sources_registered():
    with SessionLocal() as s:
        rows = dict(s.execute(text("SELECT id, status FROM source_system")).all())
    assert len(rows) == 21 and rows["erp"] == "live" and rows["iot"] == "unavailable"


def test_s4_full_sync_fills_the_purchase_baseline_with_provenance():
    out = run_sync("erp", "initial")
    assert out["status"] == "ok", out
    assert out["records_read"] >= 128 + 128 + 46
    po = canonical("demand", "PO-49048")
    assert (
        po["data"]["purchase_baseline"] == 12000.0
        and po["data"]["ship_to_site"] == "Site 3"
        and po["data"]["status"] == "confirmed"
    )
    prov = po["provenance"]["purchase_baseline"][0]
    assert prov["source_id"] == "erp" and prov["authority"] is True
    assert (prov["source_field"], prov["source_value"], prov["transform"]) == (
        "EKPO-NETPR",
        "1002000.00 INR",
        "Currency at 83.5 (rate dated 2026-10-06)",
    )
    asset = canonical("asset", "MTR-2041")
    assert asset["data"]["stock_location"] == "Warehouse 1" and asset["data"]["stock_qty"] == 1.0
    with SessionLocal() as s:
        logged = s.execute(text("SELECT count(*) FROM fetch_log WHERE source_id = 'erp' AND status = 200")).scalar_one()
        src = s.execute(text("SELECT status, last_success_at, completeness FROM source_system WHERE id = 'erp'")).one()
    assert logged >= 3 and src.status == "live" and src.last_success_at and float(src.completeness) == 100.0


def test_delta_sync_reads_only_changes():
    assert run_sync("erp", "schedule")["records_read"] == 0
    # a goods movement in S/4: RT-1048's motor moves from Warehouse 1 to Site 3
    auth = ("DI_CONNECTOR", "Circularity-demo-1")
    with httpx.Client(base_url=SIM, auth=auth, timeout=30) as c:
        tok = c.get("/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/", headers={"x-csrf-token": "Fetch"}).headers["x-csrf-token"]
        r = c.post(
            "/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader",
            headers={"x-csrf-token": tok},
            json={
                "GoodsMovementCode": "04",
                "to_MaterialDocumentItem": [
                    {
                        "Material": "MTR-2041",
                        "Plant": "2010",
                        "GoodsMovementType": "301",
                        "IssuingOrReceivingPlant": "1030",
                        "IssuingOrReceivingStorageLoc": "RT01",
                        "QuantityInEntryUnit": "1",
                    }
                ],
            },
        )
        assert r.status_code == 201, r.text
    out = run_sync("erp", "webhook")
    assert 1 <= out["records_read"] <= 4  # the two changed stock rows (and nothing else)
    assert canonical("asset", "MTR-2041")["data"]["stock_location"] == "Site 3"


def test_ariba_quote_matches_the_demo_mapping():
    out = run_sync("proc", "initial")
    assert out["status"] == "ok" and out["records_read"] == 46
    d = canonical("demand", "PO-49048")["data"]
    assert (d["purchase_alternative"], d["supplier_lead_time"], d["supplier_ref"]) == (11300.0, 21, "SUP-88120")
    assert d["purchase_baseline"] == 12000.0  # S/4's facts and Ariba's facts land on the same record


def test_conflicts_name_the_authority_and_close_when_sources_agree():
    with SessionLocal() as s:
        store.apply(s, "eam", [Fact("asset", "TEST-1", "owner_tenant", "Customer B")], 91)
        store.apply(s, "lease", [Fact("asset", "TEST-1", "owner_tenant", "Customer A")], 95)
        s.commit()
        assert store.get(s, "asset", "TEST-1")["data"]["owner_tenant"] == "Customer A"  # lease has authority over ownership
        c = s.execute(text("SELECT * FROM conflict WHERE key = 'TEST-1'")).mappings().one()
        assert c["status"] == "open" and c["authority"] == "lease" and c["values"] == {"eam": "Customer B", "lease": "Customer A"}
        store.apply(s, "eam", [Fact("asset", "TEST-1", "owner_tenant", "Customer A")], 91)
        s.commit()
        assert s.execute(text("SELECT status FROM conflict WHERE key = 'TEST-1'")).scalar_one() == "resolved"
        # numbers within 0.5% agree (rounding), beyond that they conflict
        store.apply(s, "erp", [Fact("demand", "TEST-2", "purchase_baseline", 12000.0)], 97)
        store.apply(s, "proc", [Fact("demand", "TEST-2", "purchase_baseline", 12030.0)], 90)
        store.apply(s, "erp", [Fact("demand", "TEST-3", "purchase_baseline", 12000.0)], 97)
        store.apply(s, "proc", [Fact("demand", "TEST-3", "purchase_baseline", 13000.0)], 90)
        s.commit()
        open_ = set(s.execute(text("SELECT key FROM conflict WHERE status = 'open' AND key LIKE 'TEST-%'")).scalars())
    assert open_ == {"TEST-3"}


def test_conflict_actions():
    with SessionLocal() as s:
        cid = s.execute(text("SELECT id FROM conflict WHERE key = 'TEST-3' AND status = 'open'")).scalar_one()
    r = client.post("/api/actions/conflict.resolve", json={"id": f"CF-{cid}"}, headers=h("planner.a"))
    assert r.status_code == 403  # Planners do not manage integrations
    r = client.post("/api/actions/conflict.resolve", json={"id": f"CF-{cid}"}, headers=h("developer"))
    assert r.status_code == 200 and r.json()["output"]["kept"] == "erp"
    r = client.post("/api/actions/conflict.resolve", json={"id": f"CF-{cid}"}, headers=h("developer"))
    assert r.status_code == 409


def test_source_sync_action_queues_one_job():
    r = client.post("/api/actions/source.sync", json={"source_id": "erp"}, headers=h("developer"))
    assert r.status_code == 200 and r.json()["output"]["queued"] is True
    again = client.post("/api/actions/source.sync", json={"source_id": "erp"}, headers=h("admin")).json()["output"]
    assert again["queued"] is False
    assert client.post("/api/actions/source.sync", json={"source_id": "iot"}, headers=h("developer")).status_code == 404
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))


def test_failures_set_the_source_status():
    sim("POST", "/_sim/faults", json={"system": "erp", "kind": "unavailable"})
    out = run_sync("erp", "manual")
    assert out["status"] == "failed" and "503" in out["error"]
    sim("DELETE", "/_sim/faults")
    sim("POST", "/_sim/faults", json={"system": "proc", "kind": "token_expired"})
    assert run_sync("proc", "manual")["status"] == "failed"
    sim("DELETE", "/_sim/faults")
    with SessionLocal() as s:
        st = dict(s.execute(text("SELECT id, status FROM source_system WHERE id IN ('erp','proc')")).all())
    assert st == {"erp": "failing", "proc": "auth_expired"}
    assert run_sync("erp", "manual")["status"] == "ok"  # recovers on the next good sync
    with SessionLocal() as s:
        assert s.execute(text("SELECT status FROM source_system WHERE id = 'erp'")).scalar_one() == "live"


def test_sources_and_canonical_endpoints():
    rows = client.get("/api/sources", headers=h("developer")).json()
    erp = next(r for r in rows if r["id"] == "erp")
    assert erp["connector"] and erp["fresh_minutes"] is not None and erp["facts"] > 0
    assert client.get("/api/sources", headers=h("planner.a")).status_code == 403
    rec = client.get("/api/canonical/demand/PO-49048", headers=h("ops")).json()
    assert rec["data"]["purchase_alternative"] == 11300.0
    assert client.get("/api/canonical/demand/NOPE", headers=h("ops")).status_code == 404
    assert (
        client.get("/api/fetch-log", params={"source": "proc", "limit": 5}, headers=h("admin")).json()[0]["source_id"] == "proc"
    )


def test_webhook_intake():
    body = json.dumps({"specversion": "1.0", "id": "1", "source": "/source-sim/erp", "type": "x"}).encode()
    sig = "sha256=" + hmac.new(get_settings().webhook_secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
    r = client.post(
        "/api/webhooks/source-sim", content=body, headers={"x-sim-signature": sig, "content-type": "application/json"}
    )
    assert r.status_code == 202 and r.json()["accepted"] and r.json()["queued_job"]
    bad = client.post("/api/webhooks/source-sim", content=body, headers={"x-sim-signature": "sha256=00"})
    assert bad.status_code == 401
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))


def test_webhook_rejects_a_body_that_does_not_match_its_signature():
    body = json.dumps({"specversion": "1.0", "id": "3", "source": "/source-sim/erp", "type": "x"}).encode()
    sig = "sha256=" + hmac.new(get_settings().webhook_secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
    r = client.post("/api/webhooks/source-sim", content=body + b" ", headers={"x-sim-signature": sig})
    assert r.status_code == 401 and r.json()["error"]["code"] == "bad_signature"


def test_periodic_puts_back_a_lost_webhook_subscription():
    from di import worker

    url = get_settings().webhook_url
    ours = [x for x in sim("GET", "/_sim/webhooks").json() if x["url"] == url]
    try:
        for x in ours:
            sim("DELETE", f"/_sim/webhooks/{x['id']}")
        assert not any(x["url"] == url for x in sim("GET", "/_sim/webhooks").json())
        worker.periodic()
        assert [x["url"] for x in sim("GET", "/_sim/webhooks").json()].count(url) == 1
    finally:
        if ours and not any(x["url"] == url for x in sim("GET", "/_sim/webhooks").json()):
            sim(
                "POST",
                "/_sim/webhooks",
                json={"url": url, "sources": [], "secret": get_settings().webhook_secret.get_secret_value()},
            )
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))


def test_reset_event_voids_the_cursors():
    run_sync("erp", "manual")
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM sync_cursor WHERE source_id = 'erp'")).scalar_one() > 0
    body = json.dumps({"specversion": "1.0", "id": "2", "source": "/source-sim/erp", "type": "sim.reset"}).encode()
    sig = "sha256=" + hmac.new(get_settings().webhook_secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
    assert client.post("/api/webhooks/source-sim", content=body, headers={"x-sim-signature": sig}).status_code == 202
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM sync_cursor WHERE source_id = 'erp'")).scalar_one() == 0
    assert run_sync("erp", "webhook")["records_read"] >= 128  # a full read
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))
