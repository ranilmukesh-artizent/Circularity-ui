"""B17: the Connection Fabric's source lifecycle (di.actions.fabric_sources): save and create connections, connect from
the catalogue, delete and undo, reconnect, rotate credentials, pause, resume, disconnect and the connection test.

These change source_system rows, which `starting.reset()` leaves alone, so the module restores every row it touched
(and source-sim's faults) when it ends, and removes the sources it created: the screens' parity tests that run after
see the seeded state.
"""

import httpx
import pytest
from sqlalchemy import text

from di import golden
from di.config import get_settings
from di.connectors import sync
from di.db import SessionLocal, engine
from di.reads.common import AS_OF
from tests import starting
from tests.helpers import call, client, h

REF = {s["id"]: s for s in golden.load("sources")["sources"]}
COLS = "status, vendor, interval_min, owner, note, last_sync_at, last_success_at, completeness, confidence"
SIM_FAULTS = get_settings().source_sim_url.rstrip("/") + "/_sim/faults"
_saved: dict = {}


def setup_module():
    starting.reset()
    with engine.connect() as c:
        _saved["rows"] = {r[0]: r for r in c.execute(text(f"SELECT id, {COLS} FROM source_system")).all()}  # noqa: S608 - fixed columns
    try:
        _saved["faults"] = httpx.get(SIM_FAULTS, timeout=5).json()
    except httpx.HTTPError:
        _saved["faults"] = None


def teardown_module():
    rows = _saved["rows"]
    if _saved["faults"] is not None:  # source-sim's faults as they were (the Ritchie Bros. expired token)
        for system in {f["system"] for f in _saved["faults"]} | {"mkt"}:
            httpx.delete(SIM_FAULTS, params={"system": system}, timeout=5)
        for f in _saved["faults"]:
            body = {k: f.get(k) for k in ("system", "kind", "value", "every", "note") if f.get(k) is not None}
            httpx.post(SIM_FAULTS, json=body, timeout=5)
    with engine.begin() as c:
        made = [i for i in c.execute(text("SELECT id FROM source_system")).scalars() if i not in rows]
        for t in ("sync_run", "fetch_log", "raw_record", "sync_cursor"):
            c.execute(text(f"DELETE FROM {t} WHERE source_id = ANY(:i)"), {"i": made})  # noqa: S608 - fixed names
        c.execute(text("DELETE FROM source_system WHERE id = ANY(:i)"), {"i": made})
        c.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))
        for sid, r in rows.items():
            c.execute(
                text(
                    "UPDATE source_system SET status = :st, vendor = :v, interval_min = :iv, owner = :o, note = :n, "
                    "last_sync_at = :ls, last_success_at = :lo, completeness = :cp, confidence = :cf WHERE id = :i"
                ),
                {
                    "st": r[1],
                    "v": r[2],
                    "iv": r[3],
                    "o": r[4],
                    "n": r[5],
                    "ls": r[6],
                    "lo": r[7],
                    "cp": r[8],
                    "cf": r[9],
                    "i": sid,
                },
            )
    starting.reset()


def detail(sid: str, user: str = "developer") -> dict:
    r = client.get(f"/api/screens/integration/sources/{sid}", headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def listed(path: str = "sources") -> dict:
    return client.get(f"/api/screens/integration/{path}", headers=h("developer")).json()


def db_status(sid: str) -> str:
    with engine.connect() as c:
        return c.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": sid}).scalar_one()


def draft_of(s: dict) -> dict:
    """The drawer's draftOf."""
    keys = ("type", "name", "vendor", "ver", "env", "url", "method", "cfg", "interval", "auth", "owner")
    return {k: s[k] for k in keys}


def edit(sid: str, **change) -> dict:
    got = detail(sid)
    s = got["source"]
    body = {"mode": "edit", "id": sid, "d": draft_of(s) | change.pop("d", {}), "maps": change.pop("maps", got["mappings"]),
            "ops": change.pop("ops", {"read": s["read"], "write": s["write"]}), "note": ""}  # fmt: skip
    return call("source.update", body, "developer")


# a live source whose endpoint is its URL (the drawer's buildUrl gives it back unchanged)
EDITABLE = next(i for i, s in REF.items() if s["method"] in ("api", "native", "event") and s["status"] == "live" and s["url"])


# ---------------------------------------------------------------- source.update
def test_save_a_changed_configuration():
    before = detail(EDITABLE)["source"]
    r = edit(EDITABLE, d={"owner": "Integration Engineering"})
    a, b = before["cfgVer"].split(".")
    assert r["ok"], r
    assert r["output"] == {
        "mode": "edit", "source_id": EDITABLE, "name": before["name"], "ver": f"{a}.{int(b) + 1}", "changes": ["owner"],
        "wasOff": False,
    }  # fmt: skip
    s = detail(EDITABLE)["source"]
    assert s["owner"] == "Integration Engineering" and s["cfgVer"] == r["output"]["ver"]
    assert s["audit"][0] | {"ts": 0} == {"ver": s["cfgVer"], "who": "Developer", "ts": 0, "change": "Updated owner", "prep": None}
    assert s["audit"][1:] == before["audit"]
    # the same again: nothing to save (the demo's text)
    again = edit(EDITABLE)
    assert again["error"] == {"code": "conflict", "message": "No changes to save."}
    ev = client.get("/api/screens/integration/events", headers=h("admin")).json()["events"][0]
    assert ev["type"] == "connector.updated" and ev["note"] == f"Config v{s['cfgVer']}: owner"


def test_save_a_field_mapping():
    got = detail(EDITABLE)
    maps = got["mappings"][:-1]
    r = edit(EDITABLE, maps=maps)
    assert r["ok"] and r["output"]["changes"] == [f"field mapping ({len(maps)} rows)"], r
    assert detail(EDITABLE)["mappings"] == maps
    assert listed("map")["mappings"][EDITABLE] == maps
    assert listed("models")["mappings"][EDITABLE] == maps


def test_create_a_connection_by_hand():
    d = {"type": "erp", "name": "Second ERP", "vendor": "SAP S/4HANA", "ver": "", "env": "Test",
         "url": "https://erp2.example/api", "method": "api", "cfg": {"spec": "OData"}, "interval": 15,
         "auth": "OAuth 2.0 client credentials", "owner": ""}  # fmt: skip
    body = {"mode": "new", "id": "", "d": d, "maps": [["MATNR", "M-1", "asset.asset_id", "M-1", "Pass-through"]],
            "ops": {"read": ["GET /materials", " "], "write": []}, "note": ""}  # fmt: skip
    r = call("source.update", body, "developer")
    assert r["ok"], r
    assert r["output"] == {"mode": "new", "source_id": "erp_2", "name": "Second ERP", "vendor": "SAP S/4HANA", "csv": False}
    s = detail("erp_2")["source"]
    assert (s["status"], s["owner"], s["read"], s["rw"], s["cfgVer"], s["mode"]) == (
        "live", "Unassigned", ["GET /materials"], "Read", "1.0", "API extractor · Polling · 15 min",
    )  # fmt: skip
    assert s["audit"][0]["change"] == "Connection created" and s["credDays"] == 180
    assert s["runs"][0]["note"].startswith("First sync (synthetic)") and s["records"] == s["runs"][0]["rows"] > 0
    assert detail("erp_2")["mappings"] == body["maps"]
    # nothing simulated behind it: a sync is refused with the reason
    sy = call("source.sync", {"source_id": "erp_2"}, "developer")
    assert sy["error"]["code"] == "conflict" and "nothing to sync" in sy["error"]["message"]
    # ensure_sources (at start-up) leaves it live
    with SessionLocal() as ss:
        sync.ensure_sources(ss)
    assert db_status("erp_2") == "live"


def test_connect_from_the_catalogue():
    cat = listed("overview")
    c = next(x for x in cat["catalog"] if not x["connected"])
    maps = [["a.b", "1", "asset.asset_id", "1", 97], ["c.d", "2", "asset.location", "Site 3", 60]]
    body = {
        "mode": "catalog",
        "id": "",
        "d": {"catalog": c["id"], "auth": "key", "scopes": ["read", "events"]},
        "maps": maps,
        "ops": {},
    }
    r = call("source.update", body, "developer")
    assert r["ok"], r
    o = r["output"]
    assert o["mode"] == "catalog" and o["source_id"] == c["id"] and o["vendor"] == c["vendor"] and o["records"] >= 1200
    after = listed("overview")
    assert c["id"] not in after["available"] and next(x for x in after["catalog"] if x["id"] == c["id"])["connected"]
    row = next(i for i in after["integrations"] if i["src"] == c["id"])
    assert row["status"] in ("connected", "manual") and row["vendor"] == c["vendor"]
    got = detail(c["id"])
    s = got["source"]
    assert s["auth"] == "API key" and s["mode"] == ("Controlled CSV import" if c["type"] == "store" else "API + events")
    assert s["audit"][0]["change"] == "Connected from the catalogue" and s["records"] == o["records"]
    assert got["mappings"] == [
        [*m[:4], "Accepted from the agent’s suggestion"] for m in [[str(y) for y in x] for x in body["maps"]]
    ]
    assert s["runs"][0]["rows"] == o["records"] and s["owner"] == "Integration Engineering"
    assert call("source.update", body, "developer")["error"] == {
        "code": "conflict",
        "message": f"{c['vendor']} is already connected.",
    }


# ---------------------------------------------------------------- delete and undo
def test_delete_then_undo_restores_the_source():
    sid = "dlr"
    s = detail(sid)["source"]
    maps = detail(sid)["mappings"]
    r = call("source.delete", {"source_id": sid}, "admin")
    assert r["ok"] and r["output"] == {"source_id": sid, "name": s["name"], "vendor": s["vendor"]}, r
    assert sid not in [x["id"] for x in listed()["sources"]]
    assert sid not in [i["src"] for i in listed("overview")["integrations"]]
    assert client.get(f"/api/screens/integration/sources/{sid}", headers=h("admin")).status_code == 404
    assert sid not in listed("map")["mappings"]
    assert call("source.sync", {"source_id": sid}, "admin")["error"] == {"code": "not_found", "message": f"No source {sid}."}
    assert call("source.delete", {"source_id": sid}, "admin")["error"]["code"] == "not_found"
    u = client.post("/api/journal/undo", json={"seqs": [r["seq"]]}, headers=h("admin"))
    assert u.status_code == 200, u.text
    back = detail(sid)
    assert back["source"]["name"] == s["name"] and back["mappings"] == maps
    assert sid in [x["id"] for x in listed()["sources"]]


# ---------------------------------------------------------------- pause, resume, disconnect, reconnect
def test_pause_and_resume():
    sid = "eam"
    was = db_status(sid)
    r = call("source.pause", {"source_id": sid}, "developer")
    assert r["ok"] and r["output"]["paused"] and isinstance(r["output"]["workflows"], int), r
    s = detail(sid)["source"]
    shown = {"failing": "stale", "auth_expired": "stale"}.get(was, was)  # the demo keeps the status it had
    assert (s["status"], s["paused"], s["connectorStatus"]) == (shown, True, "paused")
    assert call("source.pause", {"source_id": sid}, "developer")["error"]["code"] == "conflict"
    assert call("source.sync", {"source_id": sid}, "developer")["error"]["code"] == "conflict"
    with SessionLocal() as ss:
        assert sid not in sync.enqueue_due(ss)
    st = next(i for i in listed("overview")["integrations"] if i["src"] == sid)["status"]
    assert st == "paused"
    r = call("source.resume", {"source_id": sid}, "developer")
    assert r["ok"] and db_status(sid) == was and "paused" not in detail(sid)["source"]
    assert call("source.resume", {"source_id": sid}, "developer")["error"]["message"] == f"{s['name']} is not paused."


def test_disconnect_and_reconnect():
    sid = "wms"
    s = detail(sid)["source"]
    bad = call("source.disconnect", {"source_id": sid, "confirm": "nope"}, "admin")
    assert bad["error"] == {"code": "validation_error", "message": f"Type {s['vendor']} to confirm."}
    r = call("source.disconnect", {"source_id": sid, "confirm": s["vendor"]}, "admin")
    assert r["ok"], r
    d = detail(sid)["source"]
    assert (d["status"], d["disconnected"], d["discBy"], d["lastSync"], d["fresh"]) == ("unavailable", True, "Admin", None, "—")
    assert d["audit"][0]["change"] == "Disconnected; settings kept for reconnect"
    assert next(i for i in listed("overview")["integrations"] if i["src"] == sid)["status"] == "disconnected"
    assert call("source.sync", {"source_id": sid}, "admin")["error"]["code"] == "conflict"
    test = call("source.test", {"source_id": sid}, "admin")["output"]
    assert test["steps"] == [{"ok": False, "msg": "No route to host: the system is not provisioned"}] and not test["ok"]
    r = call("source.reconnect", {"source_id": sid}, "admin")
    assert r["ok"] and r["output"]["queued"], r
    back = detail(sid)["source"]
    assert back["status"] == "live" and "disconnected" not in back
    assert back["audit"][0]["change"] == "Token refreshed and feed re-synced"


def test_reconnect_a_stale_feed_refreshes_its_token():
    if _saved["faults"] is None or not any(f["system"] == "mkt" and f["kind"] == "token_expired" for f in _saved["faults"]):
        httpx.post(SIM_FAULTS, json={"system": "mkt", "kind": "token_expired"}, timeout=5)
    with engine.begin() as c:
        c.execute(text("UPDATE source_system SET status = 'auth_expired' WHERE id = 'mkt'"))
    assert detail("mkt")["source"]["status"] == "stale"
    t = call("source.test", {"source_id": "mkt"}, "developer")["output"]
    assert [x["ok"] for x in t["steps"]] == [True, True, False] and t["steps"][2]["msg"] == "Token rejected: expired"
    r = call("source.reconnect", {"source_id": "mkt"}, "developer")
    assert r["ok"], r
    assert db_status("mkt") == "live" and detail("mkt")["source"].get("note") is None
    faults = httpx.get(SIM_FAULTS, timeout=5).json()
    assert not any(f["system"] == "mkt" and f["kind"] == "token_expired" for f in faults)
    t = call("source.test", {"source_id": "mkt"}, "developer")["output"]
    assert t["ok"] and len(t["steps"]) == 5, t


# ---------------------------------------------------------------- credentials
def test_rotate_credentials():
    sid = "crm"
    short = call("credentials.rotate", {"source_id": sid, "days": 90, "secret": "short"}, "developer")
    assert short["error"] == {"code": "validation_error", "message": "Enter at least 8 characters."}
    r = call("credentials.rotate", {"source_id": sid, "days": 90, "secret": "a-new-secret-123"}, "developer")
    assert r["ok"] and r["output"]["stale"] is False, r
    s = detail(sid)["source"]
    assert (s["credAt"], s["credDays"], s["audit"][0]["change"]) == (AS_OF, 90, "Credentials rotated")
    with engine.connect() as c:
        stored = c.execute(text("SELECT input FROM action_journal WHERE seq = :s"), {"s": r["seq"]}).scalar_one()
    assert "secret" not in stored and "a-new-secret-123" not in str(stored)
    # the Re-authenticate dialog's renewal (frCxDone): 180 days, recorded as a re-authentication
    r = call("credentials.rotate", {"source_id": sid, "days": 180, "reauth": True}, "developer")
    assert r["ok"], r
    s = detail(sid)["source"]
    assert (s["credDays"], s["audit"][0]["change"]) == (180, "Re-authenticated; credential renewed")


# ---------------------------------------------------------------- the connection test
def test_connection_test_probes_the_connector():
    t = call("source.test", {"source_id": "iot"}, "developer")["output"]
    assert t["steps"] == [{"ok": False, "msg": "No route to host: the system is not provisioned"}]
    t = call("source.test", {"source_id": "erp"}, "developer")["output"]
    assert t["ok"] and [x["ok"] for x in t["steps"]] == [True] * 5, t
    s = detail("erp")["source"]
    host = s["url"].split("://")[-1].split("/")[0]
    assert t["steps"][0]["msg"].startswith(host + " → 10.") and t["steps"][1]["msg"] == "TLS 1.3 · certificate valid"
    assert t["steps"][2]["msg"] == s["auth"] and t["steps"][4]["msg"].endswith(" ms")
    # a catalogue system being connected: nothing simulated behind it, said so
    cat = call("source.test", {"source_id": "cat:salesforce_x", "auth": "OAuth 2.0"}, "developer")
    assert cat["error"]["code"] == "not_found"
    c = golden.load("screens/reference")["CATALOG"][-1]
    t = call("source.test", {"source_id": "cat:" + c["id"], "auth": "API key"}, "developer")["output"]
    assert (
        t["ok"] and t["steps"][0]["msg"].startswith(c["id"] + ".northfield.example → 10.") and t["steps"][2]["msg"] == "API key"
    )
    assert "nothing was read" in t["steps"][4]["msg"]
    # the drawer's one-line test of a draft
    d = call(
        "source.test",
        {"source_id": "erp", "draft": {"method": "native", "url": s["url"], "auth": s["auth"], "read": 2, "write": 1}},
        "developer",
    )
    assert (
        d["output"]["ok"]
        and d["output"]["msg"].startswith("Native connector reached in ")
        and d["output"]["msg"].endswith("2 read and 1 write operations available.")
    )
    nothing = call(
        "source.test",
        {"draft": {"method": "api", "url": "https://x.example", "auth": "API key", "read": 1, "write": 0}},
        "developer",
    )
    assert nothing["output"]["ok"] and "nothing was reached" in nothing["output"]["msg"]


def test_people_without_the_permission_are_refused():
    for action, body in (("source.pause", {"source_id": "erp"}), ("source.disconnect", {"source_id": "erp", "confirm": "x"})):
        r = client.post(f"/api/actions/{action}", json=body, headers=h("planner.a"))
        assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope"


@pytest.mark.parametrize("action", ["source.update", "source.delete", "source.reconnect", "credentials.rotate"])
def test_unknown_source(action):
    body = {"source_id": "nope", "days": 90} if action != "source.update" else {
        "mode": "edit", "id": "nope", "d": {"method": "api", "name": "x"}, "maps": [], "ops": {}}  # fmt: skip
    assert call(action, body, "developer")["error"] == {"code": "not_found", "message": "No source nope."}


# ---------------------------------------------------------------- the demo reset
def test_demo_reset_removes_created_sources_and_restores_paused_ones():
    c = next(x for x in listed("overview")["catalog"] if not x["connected"])
    body = {
        "mode": "catalog",
        "id": "",
        "d": {"catalog": c["id"], "auth": "key", "scopes": ["read"]},
        "maps": [["a.b", "1", "asset.asset_id", "1", 97]],
        "ops": {},
    }
    r = call("source.update", body, "developer")
    assert r["ok"], r
    assert call("source.pause", {"source_id": "wms"}, "developer")["ok"]
    assert db_status("wms") == "paused"
    starting.reset()
    with engine.connect() as cn:
        assert cn.execute(text("SELECT count(*) FROM source_system WHERE id = :i"), {"i": c["id"]}).scalar() == 0
        assert cn.execute(text("SELECT count(*) FROM sync_run WHERE source_id = :i"), {"i": c["id"]}).scalar() == 0
    assert db_status("wms") == "live"
    o = listed("overview")
    assert c["id"] in o["available"] and "paused" not in detail("wms")["source"]
