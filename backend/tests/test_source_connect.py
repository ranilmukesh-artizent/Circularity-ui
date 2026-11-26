"""Plan 3 task 4: `source.connect`, the action behind POST /api/v1/sources (di.services.actions.fabric_sources).

Connects a catalogue system (the same flow as source.update mode "catalog", with the body flat) or provisions a source
whose connector exists but is not connected (AWS IoT, `di.connectors.sync.connect_source`). Allowed, refused, the guard
messages (the demo's) and the effect in the reads; the other source verbs are tested in test_fabric_sources.py.
The module removes the source it connects.
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import forbidden
from tests.helpers import call, client, h

CAT = "workday"  # a catalogue system with no mapping rows: connecting needs no sample read from source-sim
TABLES = ("sync_run", "fetch_log", "raw_record", "sync_cursor", "source_connection", "source_secret", "field_mapping")
_iot: dict = {}


def _cleanup() -> None:
    with engine.begin() as c:
        c.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": CAT + ":%"})
        c.execute(text("DELETE FROM provenance WHERE source_id = :i"), {"i": CAT})
        for t in TABLES:
            c.execute(text(f"DELETE FROM {t} WHERE source_id = :i"), {"i": CAT})  # noqa: S608 - fixed names
        c.execute(text("DELETE FROM failed_record WHERE source_id = :i"), {"i": CAT})
        c.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = :i"), {"i": CAT})
        c.execute(text("DELETE FROM source_system WHERE id = :i"), {"i": CAT})
        c.execute(text("DELETE FROM state_item WHERE collection = 'source_config' AND id = :i"), {"i": CAT})
        c.execute(text("UPDATE action_journal SET undone = true WHERE output_ref->>'source_id' = :i"), {"i": CAT})


def setup_module():
    _cleanup()
    with engine.connect() as c:
        _iot["status"] = c.execute(text("SELECT status FROM source_system WHERE id = 'iot'")).scalar()


def teardown_module():
    _cleanup()
    with engine.begin() as c:
        c.execute(text("UPDATE source_system SET status = :s WHERE id = 'iot'"), {"s": _iot["status"]})


def status(sid: str) -> str | None:
    with engine.connect() as c:
        return c.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": sid}).scalar()


def test_connect_a_catalogue_system_then_it_is_listed_and_journaled():
    r = call("source.connect", {"catalog": CAT, "auth": "key", "scopes": ["read"]}, "developer")
    assert r["ok"], r
    assert r["output"]["source_id"] == CAT and r["output"]["mode"] == "catalog" and r["output"]["queued"] is True
    assert status(CAT) == "live"
    rows = client.get("/api/v1/sources", params={"limit": 500}, headers=h("developer")).json()["items"]
    assert CAT in {s["id"] for s in rows}
    assert client.get(f"/api/v1/sources/{CAT}", headers=h("developer")).json()["id"] == CAT
    again = call("source.connect", {"catalog": CAT, "auth": "key"}, "developer")
    assert again["error"]["code"] == "conflict" and "already connected" in again["error"]["message"]
    entries = client.get("/api/journal", params={"limit": 50}, headers=h("admin")).json()
    assert "source.connect" in str(entries)


def test_the_resource_create_runs_it_and_delete_removes_it():
    _cleanup()
    r = client.post("/api/v1/sources", json={"catalog": CAT, "auth": "key", "scopes": ["read"]}, headers=h("developer"))
    assert r.status_code == 201 and r.json()["source_id"] == CAT, r.text
    r = client.patch(f"/api/v1/sources/{CAT}", json={"action": "pause"}, headers=h("developer"))
    assert r.status_code == 200 and r.json()["paused"]
    r = client.patch(f"/api/v1/sources/{CAT}", json={"action": "resume"}, headers=h("developer"))
    assert r.status_code == 200
    r = client.patch(
        f"/api/v1/sources/{CAT}", json={"action": "rotate", "days": 30, "secret": "a-new-secret-1"}, headers=h("developer")
    )
    assert r.status_code == 200, r.text
    r = client.delete(f"/api/v1/sources/{CAT}", headers=h("developer"))
    assert r.status_code == 200 and client.get(f"/api/v1/sources/{CAT}", headers=h("developer")).status_code == 404


def test_the_guards_say_what_is_wrong():
    _cleanup()
    assert call("source.connect", {"catalog": "nope", "auth": "key"}, "developer")["error"]["code"] == "not_found"
    e = call("source.connect", {"catalog": CAT}, "developer")["error"]
    assert e == {"code": "validation_error", "message": "Choose how Circularity signs in."}
    assert call("source.connect", {}, "developer")["error"]["code"] == "validation_error"
    assert status(CAT) is None  # nothing was created by a refused call


def test_a_role_without_manage_integrations_is_refused():
    r = client.post("/api/actions/source.connect", json={"catalog": CAT, "auth": "key"}, headers=h("planner.a"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope" and status(CAT) is None


def test_an_unknown_body_field_is_422_before_the_action_runs():
    r = client.post("/api/v1/sources", json={"catalog": CAT, "colour": "red"}, headers=h("developer"))
    assert r.status_code == 422 and "colour" in r.json()["error"]["message"] and status(CAT) is None


def test_no_agent_may_connect_a_source():
    assert forbidden("source.connect") and forbidden("source.delete") and forbidden("credentials.rotate")


def test_a_source_with_a_connector_that_is_not_connected_is_provisioned():
    with engine.begin() as c:
        c.execute(text("UPDATE source_system SET status = 'unavailable' WHERE id = 'iot'"))
    r = call("source.connect", {"catalog": "iot"}, "developer")
    assert r["ok"], r
    assert r["output"]["source_id"] == "iot" and status("iot") == "live"
    again = call("source.connect", {"catalog": "iot"}, "developer")
    assert again["error"]["code"] == "conflict"


@pytest.mark.parametrize("sid", ["erp"])
def test_a_demo_source_that_is_connected_is_not_connected_again(sid):
    assert call("source.connect", {"catalog": sid}, "developer")["error"]["code"] in ("conflict", "not_found")


def test_it_is_declared_for_the_catalogue_and_the_session_stays_clean():
    from di.services.actions.registry import ACTIONS

    a = ACTIONS["source.connect"]
    assert a.permission == "manageIntegrations" and a.input["catalog"]["req"] is True
    with SessionLocal() as s:
        assert s.execute(text("SELECT 1")).scalar() == 1
