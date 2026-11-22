"""B6: simulated clock, scheduled work, webhook delivery and fault injection (docs/backend-steps.md)."""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.core import clock, scheduler, webhooks
from sim.core.db import engine
from sim.core.events import emit
from sim.main import app

AUTH = ("DI_CONNECTOR", "Circularity-demo-1")
PRODUCT = "/sap/opu/odata/sap/API_PRODUCT_SRV/A_Product('MTR-2041')"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.delete("/_sim/faults")
        yield c
        c.delete("/_sim/faults")
        # only the subscriptions these tests made (to http://receiver/...), even if a test failed before its cleanup
        with engine.begin() as conn:
            ours = conn.execute(text("SELECT id FROM sim.subscriptions WHERE url LIKE 'http://receiver/%'")).scalars().all()
            for sub_id in ours:
                webhooks.unsubscribe(conn, sub_id)


def at(s: str) -> datetime:
    return datetime.fromisoformat(s)


# ---------------- clock
def test_clock_starts_at_as_of_and_advances(client):
    c0 = client.get("/_sim/clock").json()
    assert c0["as_of"] == "2026-10-07T09:00:00+00:00" and at(c0["now"]) >= clock.AS_OF
    c1 = client.post("/_sim/clock/advance", json={"days": 2, "hours": 3}).json()
    assert at(c1["now"]) - at(c0["now"]) >= timedelta(days=2, hours=3)
    assert client.post("/_sim/clock/speed", json={"speed": -1}).status_code == 400
    paused = client.post("/_sim/clock/speed", json={"speed": 0}).json()
    assert client.get("/_sim/clock").json()["now"] == paused["now"]
    client.post("/_sim/clock/speed", json={"speed": 1})


def test_writes_are_stamped_with_simulated_time(client):
    """An S/4 goods movement made now carries simulated time, which delta reads see."""
    client.post("/_sim/reset", params={"system": "erp"})
    before = at(client.get("/_sim/clock").json()["now"])
    r = client.get("/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/", auth=AUTH, headers={"x-csrf-token": "Fetch"})
    h = {"x-csrf-token": r.headers["x-csrf-token"]}
    md = client.post(
        "/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader",
        auth=AUTH,
        headers=h,
        json={
            "GoodsMovementCode": "05",
            "to_MaterialDocumentItem": [
                {"Material": "MTR-2041", "Plant": "2010", "GoodsMovementType": "501", "QuantityInEntryUnit": "1"}
            ],
        },
    )
    assert md.status_code == 201
    stamp = int(md.json()["d"]["LastChangeDateTime"][6:-7]) / 1000
    assert abs(stamp - before.timestamp()) < 120
    with engine.connect() as conn:
        ev = conn.execute(text("SELECT time FROM sim.outbox WHERE source='erp' ORDER BY id DESC LIMIT 1")).scalar_one()
    assert abs((ev - before).total_seconds()) < 120
    client.post("/_sim/reset", params={"system": "erp"})


# ---------------- scheduler
@scheduler.handler("test.complete")
def _complete(conn, payload):
    emit(conn, "erp", "test.completed", payload["ref"], payload)


@scheduler.handler("test.boom")
def _boom(conn, payload):
    raise RuntimeError("boom")


def test_scheduled_work_runs_when_the_clock_reaches_it(client):
    with engine.begin() as conn:
        due = clock.now(conn) + timedelta(days=3)
        scheduler.schedule(conn, due, "test.complete", {"ref": "WO-1"}, source="test")
        scheduler.schedule(conn, due, "test.boom", {}, source="test")
    assert scheduler.tick() == 0  # not yet
    assert any(p["handler"] == "test.complete" for p in client.get("/_sim/scheduled").json())
    ran = client.post("/_sim/clock/advance", json={"days": 3, "minutes": 1}).json()["scheduled_ran"]
    assert ran >= 2  # the failing one is recorded, the other still runs
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM sim.outbox WHERE type='test.completed'")).scalar_one() == 1
        err = conn.execute(text("SELECT error FROM sim.scheduled WHERE handler='test.boom'")).scalar_one()
        assert "boom" in err
        conn.execute(text("DELETE FROM sim.outbox WHERE type='test.completed'"))
        scheduler.clear(conn, ["test"])
    with pytest.raises(KeyError), engine.begin() as conn:
        scheduler.schedule(conn, clock.now(conn), "no.such.handler", {})


# ---------------- webhooks
def test_events_are_delivered_as_signed_cloudevents_and_retried(client):
    with engine.begin() as conn:
        conn.execute(text("UPDATE sim.outbox SET delivered_at = now() WHERE delivered_at IS NULL"))  # only new events
    sub = client.post("/_sim/webhooks", json={"url": "http://receiver/hook", "sources": ["erp"], "secret": "s3cret"}).json()["id"]
    other = client.post("/_sim/webhooks", json={"url": "http://receiver/other", "sources": ["eam"], "secret": "x"}).json()["id"]
    with engine.begin() as conn:
        emit(conn, "erp", "sap.s4.beh.test.v1.Thing.Created.v1", "T-1", {"n": 1})
    received, fail = [], {"left": 1}

    def post(url, body, headers):
        if url != "http://receiver/hook":
            return 204  # other subscribers (e.g. a running di-api) are not part of this test
        if fail["left"]:
            fail["left"] -= 1
            return 503
        received.append((url, body, headers))
        return 204

    # Drive passes until ours succeeds, making the pending retry due each time. (Tests have their own database since
    # A6, so the running service's dispatcher no longer races us; the loop stays as a cheap guard.)
    webhooks.deliver(post)  # the first attempt fails (ours returns 503)
    assert received == []
    for _ in range(20):
        with engine.begin() as conn:
            conn.execute(text("UPDATE sim.deliveries SET next_at = now() - interval '1 second' WHERE status = 'pending'"))
        webhooks.deliver(post)
        if received:
            break
    assert len(received) == 1
    with engine.begin() as conn:
        attempts = conn.execute(text("SELECT attempts FROM sim.deliveries WHERE subscription_id = :s"), {"s": sub}).scalar_one()
    assert attempts >= 2  # retried after the failure
    url, body, headers = received[0]
    ev = json.loads(body)
    assert url == "http://receiver/hook" and ev["specversion"] == "1.0" and ev["type"] == "sap.s4.beh.test.v1.Thing.Created.v1"
    assert ev["source"] == "/source-sim/erp" and ev["data"] == {"n": 1}
    assert headers["x-sim-signature"] == webhooks.sign("s3cret", body)
    status = client.get("/_sim/webhooks/status").json()
    assert status["undelivered_events"] == 0
    client.delete(f"/_sim/webhooks/{sub}")
    client.delete(f"/_sim/webhooks/{other}")


def test_a_subscription_needs_its_own_signing_secret(client):
    """No shared default secret: a subscriber that sends none (or an empty one) is refused."""
    for body in ({"url": "http://receiver/nosecret", "sources": []}, {"url": "http://receiver/nosecret", "secret": ""}):
        r = client.post("/_sim/webhooks", json=body)
        assert r.status_code == 422, r.text
    assert not any(s["url"] == "http://receiver/nosecret" for s in client.get("/_sim/webhooks").json())


def test_tests_run_on_their_own_database():
    """The live service keeps `sources`; tests work on `sources_test` (conftest), so neither disturbs the other."""
    assert engine.url.database == "sources_test"


def test_deliver_skips_a_delivery_whose_event_vanished(client):
    """A delivery whose outbox row was deleted meanwhile (a reset, a test's cleanup) is dropped, not fatal."""
    sub = client.post("/_sim/webhooks", json={"url": "http://receiver/gone", "sources": ["erp"], "secret": "x"}).json()["id"]
    with engine.begin() as conn:
        gone = conn.execute(text("SELECT coalesce(max(id), 0) + 1000 FROM sim.outbox")).scalar_one()
        conn.execute(
            text(
                "INSERT INTO sim.deliveries (outbox_id, subscription_id, status, attempts, next_at) "
                "VALUES (:o, :s, 'pending', 0, now() - interval '1 second')"
            ),
            {"o": gone, "s": sub},
        )
    posted = []
    webhooks.deliver(lambda url, body, headers: posted.append(url) or 204)
    assert "http://receiver/gone" not in posted
    with engine.connect() as conn:
        left = conn.execute(text("SELECT count(*) FROM sim.deliveries WHERE outbox_id = :o"), {"o": gone}).scalar_one()
    assert left == 0
    client.delete(f"/_sim/webhooks/{sub}")


def test_sink_receives(client):
    client.post("/_sim/sink", json={"type": "x"})
    assert client.get("/_sim/sink", params={"clear": True}).json()[-1]["event"] == {"type": "x"}


# ---------------- faults
def test_error_and_unavailable_faults(client):
    assert client.get(PRODUCT, auth=AUTH).status_code == 200
    f = client.post("/_sim/faults", json={"system": "erp", "kind": "error", "value": 502, "every": 2}).json()["id"]
    codes = [client.get(PRODUCT, auth=AUTH).status_code for _ in range(4)]
    assert codes == [200, 502, 200, 502]
    client.delete("/_sim/faults", params={"system": "erp"})
    client.post("/_sim/faults", json={"system": "erp", "kind": "unavailable"})
    assert client.get(PRODUCT, auth=AUTH).status_code == 503
    assert client.get("/health").status_code == 200  # control endpoints are never faulted
    client.delete("/_sim/faults", params={"system": "erp"})
    assert client.get(PRODUCT, auth=AUTH).status_code == 200
    assert f


def test_token_expired_refuses_bearer_but_not_basic(client):
    tok = client.post(
        "/sap/bc/sec/oauth2/token", data={"grant_type": "client_credentials"}, auth=("di-connector", "circularity-demo-secret")
    ).json()["access_token"]
    bearer = {"Authorization": "Bearer " + tok}
    assert client.get(PRODUCT, headers=bearer).status_code == 200
    client.post("/_sim/faults", json={"system": "erp", "kind": "token_expired"})
    r = client.get(PRODUCT, headers=bearer)
    assert r.status_code == 401 and "invalid_token" in r.headers["www-authenticate"]
    assert client.get(PRODUCT, auth=AUTH).status_code == 200
    client.delete("/_sim/faults", params={"system": "erp"})


def test_faults_can_expire_on_the_simulated_clock(client):
    client.post("/_sim/faults", json={"system": "erp", "kind": "unavailable", "minutes": 30})
    assert client.get(PRODUCT, auth=AUTH).status_code == 503
    client.post("/_sim/clock/advance", json={"minutes": 31})
    assert client.get(PRODUCT, auth=AUTH).status_code == 200
    client.delete("/_sim/faults")


def test_demo_faults_and_validation(client):
    demo = client.post("/_sim/faults/demo").json()
    assert demo["faults"][0]["system"] == "mkt"
    assert [f["kind"] for f in client.get("/_sim/faults").json()] == ["token_expired"]
    assert client.post("/_sim/faults", json={"system": "erp", "kind": "meteor"}).status_code == 400
    assert client.post("/_sim/faults", json={"system": "nope", "kind": "error"}).status_code == 400
    client.delete("/_sim/faults")


def test_demo_fault_blocks_ritchie_api_key(client):
    """The demo's starting state: Ritchie Bros. Market Data's feed token expired, so its API key is refused."""
    key = {"X-Api-Key": "mkt-demo-key"}
    assert client.get("/ritchie/v2/comparables", headers=key).status_code == 200
    client.post("/_sim/faults/demo")
    r = client.get("/ritchie/v2/comparables", headers=key)
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"
    client.delete("/_sim/faults")
    assert client.get("/ritchie/v2/comparables", headers=key).status_code == 200


# ---------------- robustness (refactor F4)
def test_fan_out_marks_events_no_subscription_wants_as_delivered(client):
    """R2: an event that matches no subscription is marked delivered, so unmatched events don't pile up at the head of
    the outbox and starve the fan-out (it looks at the oldest 500 undelivered events) of the events a subscriber wants."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE sim.outbox SET delivered_at = now() WHERE delivered_at IS NULL"))  # only new events
    sub = client.post("/_sim/webhooks", json={"url": "http://receiver/starve", "sources": ["erp"], "secret": "x"}).json()["id"]
    with engine.begin() as conn:
        first = conn.execute(text("SELECT coalesce(max(id), 0) + 1 FROM sim.outbox")).scalar_one()
        for i in range(501):
            emit(conn, "eam", "test.Unmatched.v1", f"U-{i}", {"i": i})
        emit(conn, "erp", "test.Wanted.v1", "W-1", {"n": 1})
        wanted = conn.execute(text("SELECT max(id) FROM sim.outbox")).scalar_one()
    received = []
    webhooks.deliver(lambda url, body, headers: received.append((url, json.loads(body)["id"])) or 204)  # one pass
    assert ("http://receiver/starve", str(wanted)) in received
    with engine.connect() as conn:
        left = conn.execute(
            text("SELECT count(*) FROM sim.outbox WHERE id >= :f AND delivered_at IS NULL"), {"f": first}
        ).scalar_one()
    assert left == 0
    assert client.get("/_sim/webhooks/status").json()["undelivered_events"] == 0
    client.delete(f"/_sim/webhooks/{sub}")


def test_a_per_system_reset_keeps_other_systems_faults(client, monkeypatch):
    """R3: with the demo faults on, resetting one system re-applies only that system's demo faults; a fault set on
    another system survives."""
    from sim.core.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_faults", True)
    client.delete("/_sim/faults")
    client.post("/_sim/faults/demo")
    eam = client.post("/_sim/faults", json={"system": "eam", "kind": "error", "value": 502, "every": 1000}).json()["id"]
    try:
        assert client.post("/_sim/reset", params={"system": "erp"}).status_code == 200
        after = client.get("/_sim/faults").json()
        assert eam in [f["id"] for f in after]
        assert sorted((f["system"], f["kind"]) for f in after) == [("eam", "error"), ("mkt", "token_expired")]
    finally:
        client.delete("/_sim/faults")
