"""B5c: the AWS IoT Core (iot) adapter against source-sim's AWS IoT Core mock.

Needs source-sim running. The demo starts iot not provisioned; these tests connect it, and the module fixture puts
the starting state back afterwards (iot unavailable, none of its facts, conflicts, raw records, runs or jobs left).
Only iot is reset in source-sim.
"""

import hashlib
import hmac
import json
import time
from datetime import datetime
from urllib.parse import quote

import httpx
import pytest
from sqlalchemy import text

from di.connectors.adapters.aws_iot import ACCESS_KEY, REGION, SECRET_KEY, sigv4_headers
from di.connectors.http import SourceClient
from di.connectors.registry import ADAPTERS
from di.connectors.sync import disconnect_source, ensure_sources, run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store
from tests.helpers import client, h

SIM = get_settings().source_sim_url
SID = "iot"


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def aws(method: str, plane: str, path: str, params: dict | None = None, body: bytes = b"") -> httpx.Response:
    """A signed call to the mock, as an AWS SDK (or a device's backend) makes it."""
    url = httpx.URL(f"{SIM}/aws-iot/{plane}{path}", params={k: str(v) for k, v in (params or {}).items()})
    h = sigv4_headers(method, url, body, ACCESS_KEY, SECRET_KEY, REGION, {"iot": "iot", "data": "iotdata"}[plane])
    r = httpx.request(method, url, content=body or None, headers=h, timeout=30)
    r.raise_for_status()
    return r


def counts() -> dict:
    """What iot has left in di: everything here is 0 / unavailable in the demo's starting state."""
    with engine.connect() as conn:
        q = lambda sql: conn.execute(text(sql), {"s": SID}).scalar_one()  # noqa: E731
        return {
            "status": q("SELECT status FROM source_system WHERE id = :s"),
            "provenance": q("SELECT count(*) FROM provenance WHERE source_id = :s"),
            "conflicts": q('SELECT count(*) FROM conflict WHERE jsonb_exists("values", :s)'),
            "raw": q("SELECT count(*) FROM raw_record WHERE source_id = :s"),
            "runs": q("SELECT count(*) FROM sync_run WHERE source_id = :s"),
            "cursors": q("SELECT count(*) FROM sync_cursor WHERE source_id = :s"),
            "jobs": q("SELECT count(*) FROM job WHERE payload->>'source_id' = :s"),
            "last_sync": q("SELECT last_sync_at FROM source_system WHERE id = :s"),
        }


STARTING = {
    "status": "unavailable",
    "provenance": 0,
    "conflicts": 0,
    "raw": 0,
    "runs": 0,
    "cursors": 0,
    "jobs": 0,
    "last_sync": None,
}


def run_hours() -> dict[str, float]:
    """The canonical run hours of every asset (Maximo's meter unless iot is connected)."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT key, data->'run_hours' FROM canonical WHERE model = 'asset' AND jsonb_exists(data, 'run_hours')")
        )
        return {k: float(v) for k, v in rows}


def drop_iot_jobs() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = :s"), {"s": SID})


def restore() -> None:
    """Back to the demo's starting state for iot (waits for a sync another process may be running)."""
    with SessionLocal() as s:
        disconnect_source(s, SID)
    for _ in range(60):
        with engine.connect() as conn:
            running = conn.execute(
                text(
                    "SELECT count(*) FROM sync_run WHERE source_id = :s AND status = 'running' "
                    "AND started_at > now() - interval '5 minutes'"
                ),
                {"s": SID},
            ).scalar_one()
        if not running:
            break
        time.sleep(0.5)
    with SessionLocal() as s:
        disconnect_source(s, SID, purge=True)


def ensure_maximo() -> None:
    """These tests compare IoT telemetry with Maximo's meter readings (the canonical run hours before iot connects).
    test_connectors empties the connector tables, so after it Maximo has no facts: sync it here instead of relying on
    the order the test files run in."""
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM provenance WHERE source_id = 'eam' AND field = 'run_hours'")).scalar_one()
    if not n:
        r = run_sync("eam", "manual", full=True)
        assert r["status"] in ("ok", "partial"), r


@pytest.fixture(scope="module", autouse=True)
def clean():
    sim("DELETE", "/_sim/faults", params={"system": SID})
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    with SessionLocal() as s:
        ensure_sources(s)
    ensure_maximo()
    restore()
    before = run_hours()
    yield before
    sim("DELETE", "/_sim/faults", params={"system": SID})
    restore()
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    drop_iot_jobs()
    assert counts() == STARTING
    assert run_hours() == before  # Maximo's meter readings are the canonical run hours again


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def prov(rec: dict, field: str, source: str = SID) -> dict:
    return next(x for x in rec["provenance"][field] if x["source_id"] == source)


def delta_reads() -> set[str]:
    """The things a delta read returns now."""
    a = ADAPTERS[SID]
    n: set[str] = set()
    with SessionLocal() as s:
        c = SourceClient(SID, SIM + a.base_path, a.auth(), s)
        try:
            for res in a.resources():
                cursor = s.execute(
                    text("SELECT cursor FROM sync_cursor WHERE source_id = :s AND resource = :r"), {"s": SID, "r": res.name}
                ).scalar()
                assert cursor, res.name
                n |= {r.ext_id for r in res.read(c, cursor)}
        finally:
            c.close()
            s.rollback()
    return n


def signed_event(ev: dict) -> tuple[bytes, dict]:
    body = json.dumps(ev).encode()
    sig = "sha256=" + hmac.new(get_settings().webhook_secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
    return body, {"x-sim-signature": sig, "content-type": "application/cloudevents+json"}


RULE_EVENT = {
    "specversion": "1.0",
    "id": "test-1",
    "source": "/source-sim/iot",
    "type": "aws.iot.rule.circularity_telemetry",
    "subject": "cm-mtr-2041",
    "time": "2026-10-07T10:00:00Z",
    "data": {"thingName": "cm-mtr-2041", "operatingHours": 18450.0},
}


# ---------------------------------------------------------------- not provisioned: the demo's starting state
def test_starts_not_provisioned():
    with SessionLocal() as s:
        ensure_sources(s)  # registering again does not switch it on
    assert counts() == STARTING
    assert run_sync(SID, "manual") == {"source_id": SID, "status": "skipped", "reason": "unavailable"}
    r = client.post("/api/actions/source.sync", json={"source_id": SID}, headers=h("developer"))
    assert r.status_code == 404 and r.json()["error"]["message"] == "No connector for iot."
    body, headers = signed_event(RULE_EVENT)
    out = client.post("/api/webhooks/source-sim", content=body, headers=headers).json()
    assert out["accepted"] is True and out["queued_job"] is None  # rule deliveries are ignored while not connected
    rows = client.get("/api/screens/integration/sources", headers=h("admin")).json()
    iot = next(x for x in (rows.get("sources") if isinstance(rows, dict) else rows) if x["id"] == SID)
    assert iot["status"] == "unavailable" and iot["records"] == 0


# ---------------------------------------------------------------- connected
def test_connect_needs_permission_and_queues_the_initial_sync():
    assert client.post(f"/api/sources/{SID}/connect", headers=h("planner.a")).status_code == 403
    r = client.post(f"/api/sources/{SID}/connect", headers=h("developer"))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "live" and out["connected"] is True and out["queued_job"]
    drop_iot_jobs()  # the test runs the sync itself
    with engine.connect() as conn:
        st, conf = conn.execute(text("SELECT status, confidence FROM source_system WHERE id = :s"), {"s": SID}).one()
    assert st == "live" and float(conf) == 92.0
    again = client.post(f"/api/sources/{SID}/connect", headers=h("admin")).json()
    assert again["connected"] is False and again["queued_job"] is None
    assert client.post("/api/sources/nope/connect", headers=h("admin")).status_code == 404


def test_full_sync_maps_telemetry_to_the_canonical_model():
    out = run_sync(SID, "initial", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] == 77, out
    a = canonical("asset", "MTR-2041")
    assert a["data"]["iot_thing"] == "cm-mtr-2041" and "IOT:cm-mtr-2041" in a["data"]["source_refs"]
    assert a["data"]["run_hours"] == 18450.0  # agrees with Maximo's RUNHOURS meter: no conflict
    rh = prov(a, "run_hours")
    assert (rh["source_field"], rh["source_value"], rh["authority"]) == ("state.reported.operatingHours", "18,450.0 h", True)
    assert prov(a, "run_hours", "eam")["authority"] is False
    c = canonical("condition", "MTR-2041")["data"]
    assert (c["duty_cycle_pct"], c["vibration_mm_s"], c["vibration_zone"], c["bearing_temp_c"]) == (96.4, 2.8, "B", 66.0)
    assert c["telemetry_at"].endswith("Z") and c["telemetry_events"] == []
    assert prov(canonical("condition", "MTR-2041"), "duty_cycle_pct")["authority"] is True
    with engine.connect() as conn:
        open_ = conn.execute(
            text(
                'SELECT key, "values", authority FROM conflict '
                "WHERE status = 'open' AND model = 'asset' AND field = 'run_hours'"
            )
        ).all()
        rows = conn.execute(text("SELECT count(*), max(id) FROM fetch_log WHERE source_id = :s"), {"s": SID}).one()
    assert rows[0] > 77  # every call is in the fetch log
    # where Maximo's meter is older than the device's counter, a conflict names iot (the authority on Operating hours)
    assert 4 <= len(open_) <= 10 and all(r.authority == SID and set(r.values) >= {"eam", SID} for r in open_)
    assert all(float(r.values[SID]) > float(r.values["eam"]) for r in open_)
    assert "MTR-2041" not in {r.key for r in open_}
    k = open_[0].key
    assert canonical("asset", k)["data"]["run_hours"] == float(open_[0].values[SID])  # the authority's value counts
    # a grade-D asset carries its alarms
    with engine.connect() as conn:
        zone_d = conn.execute(
            text("SELECT key, data FROM canonical WHERE model = 'condition' AND data->>'vibration_zone' = 'D'")
        ).all()
    assert zone_d and all(any(e["type"] == "high-vibration" for e in d["telemetry_events"]) for _, d in zone_d)


def test_connection_fabric_shows_it_connected_with_records():
    rows = client.get("/api/screens/integration/sources", headers=h("admin")).json()
    iot = next(x for x in (rows.get("sources") if isinstance(rows, dict) else rows) if x["id"] == SID)
    assert iot["status"] == "live" and iot["records"] == 77 and iot["lastSync"] is not None
    assert iot["openConflicts"] >= 4


def test_delta_sync_reads_only_what_changed():
    # the online pilot kits report every simulated hour (source-sim's clock keeps running), so they may show up too;
    # the offline kits of returned assets never do, unless they report
    pilot = set(aws("GET", "iot", "/thing-groups/in-service-pilot/things").json()["things"])
    assert delta_reads() <= pilot
    quiet = run_sync(SID, "schedule")
    assert quiet["status"] == "ok" and quiet["records_read"] <= len(pilot), quiet
    # the device reports: it updates its condition shadow and publishes its telemetry (retained)
    now = int(datetime.fromisoformat(sim("GET", "/_sim/clock").json()["now"]).timestamp() * 1000)  # simulated time
    rep = {"operatingHours": 18452.5, "dutyCyclePct": 96.5, "vibrationMmS": 2.9, "bearingTempC": 66.4, "running": True}
    shadow = {"state": {"reported": rep | {"sampleAt": now}}}
    aws("POST", "data", "/things/cm-mtr-2041/shadow", {"name": "condition"}, json.dumps(shadow).encode())
    topic = quote("dt/motors/cm-mtr-2041/telemetry", safe="")
    aws("POST", "data", f"/topics/{topic}", {"qos": 1, "retain": "true"}, json.dumps(rep).encode())
    assert delta_reads() - pilot == {"cm-mtr-2041"}
    out = run_sync(SID, "schedule")
    assert out["status"] == "ok" and 1 <= out["records_read"] <= len(pilot) + 1, out
    a = canonical("asset", "MTR-2041")["data"]
    assert a["run_hours"] == 18452.5 and canonical("condition", "MTR-2041")["data"]["vibration_mm_s"] == 2.9
    assert delta_reads() <= pilot


def test_rule_delivery_queues_a_delta_sync_while_connected():
    body, headers = signed_event(RULE_EVENT | {"id": "test-2"})
    out = client.post("/api/webhooks/source-sim", content=body, headers=headers)
    assert out.status_code == 202 and out.json()["queued_job"], out.text
    assert (
        client.post("/api/webhooks/source-sim", content=body, headers=headers | {"x-sim-signature": "sha256=00"}).status_code
        == 401
    )
    drop_iot_jobs()


def test_throttling_is_retried_and_expired_credentials_show():
    sim("POST", "/_sim/faults", json={"system": SID, "kind": "error", "value": 429, "every": 2})
    try:
        out = run_sync(SID, "manual", full=True)
    finally:
        sim("DELETE", "/_sim/faults", params={"system": SID})
    assert out["status"] == "ok" and out["records_read"] == 77, out
    sim("POST", "/_sim/faults", json={"system": SID, "kind": "token_expired"})
    try:
        bad = run_sync(SID, "manual")
    finally:
        sim("DELETE", "/_sim/faults", params={"system": SID})
    assert bad["status"] == "failed" and "expired" in bad["error"].lower(), bad
    assert counts()["status"] == "auth_expired"
    assert run_sync(SID, "manual")["status"] == "ok" and counts()["status"] == "live"


def test_disconnect_with_purge_restores_the_starting_state(clean):
    assert client.post(f"/api/sources/{SID}/disconnect", headers=h("planner.a")).status_code == 403
    r = client.post(f"/api/sources/{SID}/disconnect", params={"purge": "true"}, headers=h("admin"))
    assert r.status_code == 200 and r.json()["purged"] is True and r.json()["facts_removed"] > 0, r.text
    drop_iot_jobs()
    assert counts() == STARTING
    assert run_hours() == clean
    with engine.connect() as conn:
        conf = conn.execute(text("SELECT confidence, completeness FROM source_system WHERE id = :s"), {"s": SID}).one()
        gone = conn.execute(
            text("SELECT count(*) FROM canonical WHERE jsonb_exists(data, 'iot_thing') OR jsonb_exists(data, 'duty_cycle_pct')")
        ).scalar_one()
    assert float(conf[0]) == 0 and conf[1] is None and gone == 0
    r = client.post("/api/actions/source.sync", json={"source_id": SID}, headers=h("developer"))
    assert r.status_code == 404
