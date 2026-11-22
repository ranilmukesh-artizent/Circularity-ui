"""Plan 6 A2: a source's connector calls the URL and signs in with the secret stored for it (di.connectors.connection).

- the demo sources have a seeded connection on source-sim (the adapter's base path), so they read as before
- editing a demo source's endpoint to a wrong host makes the next sync fail at connect, naming the host; entering the
  demo's endpoint again puts it back on source-sim and it syncs again
- rotating to a wrong secret: the system refuses it (401) and the source is auth_expired
- source.update stores the connection settings it is given and the secret, encrypted (never in the journal)

Uses Maximo (eam): a single API key, two small resources. The module puts eam back as it was (connection, secret,
status) when it ends.
"""

import httpx
from sqlalchemy import text

from di.connectors import connection, secrets
from di.connectors.sync import ensure_sources, run_sync
from di.core import golden
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from tests.helpers import call, client, h

SID = "eam"
SIM = get_settings().source_sim_url.rstrip("/")
REF = {s["id"]: s for s in golden.load("sources")["sources"]}
_saved: dict = {}


def setup_module():
    httpx.delete(SIM + "/_sim/faults", params={"system": SID}, timeout=10)
    with SessionLocal() as s:
        ensure_sources(s)
        _saved["row"] = s.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": SID}).scalar_one()
        s.execute(text("UPDATE source_system SET status = 'live' WHERE id = :i"), {"i": SID})
        s.commit()


def teardown_module():
    with engine.begin() as c:
        c.execute(text("DELETE FROM source_secret WHERE source_id = :i"), {"i": SID})
        c.execute(text("UPDATE source_system SET status = :st WHERE id = :i"), {"st": _saved["row"], "i": SID})
        c.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = :i"), {"i": SID})
    with SessionLocal() as s:
        connection.restore_default(s, SID)
        s.commit()


def edit(**d) -> dict:
    got = client.get(f"/api/screens/integration/sources/{SID}", headers=h("developer")).json()
    src = got["source"]
    keys = ("type", "name", "vendor", "ver", "env", "url", "method", "cfg", "interval", "auth", "owner")
    body = {"mode": "edit", "id": SID, "d": {k: src[k] for k in keys} | d.pop("d", {}), "maps": got["mappings"],
            "ops": {"read": src["read"], "write": src["write"]}, "note": ""} | d  # fmt: skip
    return call("source.update", body, "developer")


def status() -> str:
    with engine.connect() as c:
        return c.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": SID}).scalar_one()


def test_demo_sources_are_seeded_on_source_sim():
    with SessionLocal() as s:
        conn = connection.connection_for(s, SID)
        n = s.execute(text("SELECT count(*) FROM source_connection WHERE updated_by IS NULL")).scalar_one()
    assert conn.base_url == SIM + "/maximo/api" and conn.auth_kind == "builtin" and conn.updated_by is None
    assert n >= 21
    assert run_sync(SID, "manual")["status"] in ("ok", "partial")


def test_wrong_host_fails_at_connect_and_restoring_syncs_again():
    r = edit(d={"url": "https://wrong-host.invalid/maximo/api"})
    assert r["ok"] and r["output"]["changes"] == ["endpoint"], r
    with SessionLocal() as s:
        assert connection.connection_for(s, SID).base_url == "https://wrong-host.invalid/maximo/api"
    out = run_sync(SID, "manual")
    assert out["status"] == "failed" and "wrong-host.invalid" in out["error"], out
    assert status() == "failing"
    back = edit(d={"url": REF[SID]["url"]})
    assert back["ok"], back
    with SessionLocal() as s:
        conn = connection.connection_for(s, SID)
    assert conn.base_url == SIM + "/maximo/api" and conn.updated_by is None
    out = run_sync(SID, "manual", full=True)
    assert out["status"] in ("ok", "partial") and out["records_read"] > 0, out
    assert status() == "live"


def test_a_wrong_secret_is_refused_by_the_system():
    r = call("credentials.rotate", {"source_id": SID, "days": 90, "secret": "not-the-maximo-key"}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual")
    assert out["status"] == "failed" and "401" in out["error"], out
    assert status() == "auth_expired"
    # the right one (source-sim's demo key for Maximo) signs in again
    r = call("credentials.rotate", {"source_id": SID, "days": 90, "secret": "circularity-demo-maximo-apikey"}, "developer")
    assert r["ok"], r
    assert run_sync(SID, "manual")["status"] in ("ok", "partial")
    assert status() == "live"


def test_source_update_stores_the_connection_and_the_secret():
    plain = "update-stored-Secret-77QQ"
    r = edit(conn={"auth_params": {"header": "apikey"}}, secret=plain)
    assert r["ok"] and "connection settings" in r["output"]["changes"] and "credential" in r["output"]["changes"], r
    with SessionLocal() as s:
        assert connection.connection_for(s, SID).auth_params == {"header": "apikey"}
        assert secrets.active_secret(s, SID) == plain
        stored = s.execute(text("SELECT input::text FROM action_journal WHERE seq = :q"), {"q": r["seq"]}).scalar_one()
    assert plain not in stored
    bad = edit(conn={"auth_params": {"client_secret": "x"}})
    assert bad["error"]["code"] == "validation_error", bad
    bad = edit(conn={"auth_kind": "magic"})
    assert bad["error"] == {"code": "validation_error", "message": "No authentication kind magic."}
