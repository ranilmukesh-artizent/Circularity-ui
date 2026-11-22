"""Plan 6 follow-ups in the Connection Fabric (found by frontend/scripts/smoke-fabric.mjs):

1. A source connected from the catalogue (or made by hand) can get an ingest workflow: workflow.create read only the
   demo's SOURCES and refused it ("Choose a system first."); now its guard and graph read the sources as they are now.
   The new workflow validates with 0 errors and its Test run reads the source.
3. A catalogue source deleted and connected again under the same id starts clean: no sync runs, fetches, records,
   cursors, held records, webhook events, mapping versions or credentials of its predecessor. Undo of the delete (the
   journal) still brings the deleted source back with its data, so the purge happens when it is connected again.
4. The credential typed in the Connect dialog is the one stored; source.sandboxKey gives the simulated system's
   sandbox key (the dialog prefills it), and Test connection with another key fails at Auth.

The module removes the catalogue source it connects (starting.reset), so later parity tests see the seeded state.
"""

from sqlalchemy import text

from di.connectors import catalog, secrets
from di.core.db import SessionLocal, engine
from di.repositories.common import SOURCES
from tests import starting
from tests.helpers import call, client, h

REF_ERP = SOURCES["erp"]
CAT = "postgres"
DEV = "developer"
TABLES = ("sync_run", "fetch_log", "raw_record", "sync_cursor", "failed_record", "webhook_event")


def setup_module():
    starting.reset()


def teardown_module():
    with engine.begin() as c:
        c.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = :i"), {"i": CAT})
        for t in (*TABLES, "field_mapping", "source_connection", "source_secret"):
            c.execute(text(f"DELETE FROM {t} WHERE source_id = :i"), {"i": CAT})  # noqa: S608 - fixed names
    starting.reset()


def _maps() -> list:
    r = call("mapping.catalogSuggest", {"catalog_id": CAT}, DEV)
    assert r["ok"], r
    return r["output"]["rows"]


def _connect(secret: str | None = None) -> dict:
    body = {"mode": "catalog", "id": "", "d": {"catalog": CAT, "auth": "key", "scopes": ["read"]}, "maps": _maps(), "ops": {}}
    if secret is not None:
        body["secret"] = secret
    r = call("source.update", body, DEV)
    assert r["ok"], r
    return r["output"]


def _ensure_connected() -> None:
    with engine.connect() as c:
        there = c.execute(text("SELECT 1 FROM source_system WHERE id = :i"), {"i": CAT}).first()
    if there is None or CAT not in [
        x["id"] for x in client.get("/api/screens/integration/sources", headers=h(DEV)).json()["sources"]
    ]:
        _connect(catalog.template(CAT)["demo_secret"])


def _count(t: str) -> int:
    with engine.connect() as c:
        return c.execute(text(f"SELECT count(*) FROM {t} WHERE source_id = :i"), {"i": CAT}).scalar_one()  # noqa: S608


# ---------------------------------------------------------------- 4. the typed credential
def test_sandbox_key_is_the_mocks_synthetic_key():
    r = call("source.sandboxKey", {"catalog_id": CAT}, DEV)
    assert r["ok"], r
    assert r["output"] == {"catalog_id": CAT, "key": catalog.template(CAT)["demo_secret"]}
    assert call("source.sandboxKey", {"catalog_id": "nope"}, DEV)["error"]["code"] == "not_found"
    assert not call("source.sandboxKey", {"catalog_id": CAT}, "planner.a")["ok"]


def test_test_connection_uses_the_typed_key():
    good = call(
        "source.test", {"source_id": "cat:" + CAT, "auth": "API key", "secret": catalog.template(CAT)["demo_secret"]}, DEV
    )
    assert good["ok"] and good["output"]["ok"], good
    bad = call("source.test", {"source_id": "cat:" + CAT, "auth": "API key", "secret": "not-the-sandbox-key"}, DEV)
    assert bad["ok"] and not bad["output"]["ok"], bad
    steps = bad["output"]["steps"]
    assert len(steps) == 3 and steps[0]["ok"] and steps[1]["ok"] and not steps[2]["ok"], steps  # DNS, TLS, then Auth
    assert "401" in steps[2]["msg"]


def test_the_typed_key_is_stored():
    starting.reset()
    _connect("typed-by-the-person-01")
    with SessionLocal() as s:
        assert secrets.active_secret(s, CAT) == "typed-by-the-person-01"
    starting.reset()
    _connect()  # none typed (the API): the mock's sandbox key
    with SessionLocal() as s:
        assert secrets.active_secret(s, CAT) == catalog.template(CAT)["demo_secret"]


# ---------------------------------------------------------------- 1. a workflow for a catalogue source
def test_ingest_workflow_for_a_catalogue_source():
    _ensure_connected()
    r = call("workflow.create", {"type": "ingest", "src": CAT}, DEV)
    assert r["ok"], r
    wid = r["output"]["id"]
    try:
        assert "PostgreSQL" in r["output"]["name"] or "postgres" in r["output"]["name"].lower(), r
        v = call("workflow.validate", {"id": wid}, DEV)
        assert v["ok"] and v["output"]["errors"] == [], v
        t = call("workflow.testRun", {"id": wid, "sample": 5}, DEV)
        assert t["ok"], t
        o = t["output"]
        assert o["states"]["r"] == "success" and o["counts"]["r"]["out"] > 0, o
        assert o["status"] == "success", o
    finally:
        call("workflow.delete", {"id": wid}, DEV)


def test_no_workflow_for_an_unknown_or_deleted_source():
    r = call("workflow.create", {"type": "ingest", "src": "nope"}, DEV)
    assert r["error"] == {"code": "validation_error", "message": "Choose a system first."}, r
    # a read-only catalogue source gets no outbound workflow
    _ensure_connected()
    r = call("workflow.create", {"type": "out", "src": CAT}, DEV)
    assert not r["ok"] and r["error"]["code"] == "validation_error", r


def test_demo_source_workflow_unchanged():
    """A demo source's New workflow is built exactly as before (the demo's reference record)."""
    from di.services.actions.workflow_builder import minimal_graph

    r = call("workflow.create", {"type": "ingest", "src": "erp"}, DEV)
    assert r["ok"], r
    wid = r["output"]["id"]
    try:
        from di.core import state

        with SessionLocal() as s:
            w = state.get(s, "workflows", wid)
        assert w["name"] == "Ingest · " + REF_ERP["vendor"] and w["owner"] == REF_ERP["owner"], w
        assert w["trig"] == ({"t": "schedule", "min": REF_ERP["interval"]} if REF_ERP.get("interval") else {"t": "event"})
        assert w["graph"] == minimal_graph(w["tpl"]), w  # built from the demo's reference record (no live overlay)
    finally:
        call("workflow.delete", {"id": wid}, DEV)


# ---------------------------------------------------------------- 3. connected again under the same id
def _seed_history() -> None:
    """What a predecessor leaves: a failed sync with its 401, records, a cursor, a held record, a webhook event."""
    with engine.begin() as c:
        run = c.execute(
            text("INSERT INTO sync_run (source_id, trigger, status, records_read, error) VALUES (:i, 'manual', 'failed', 900, "
                 "'HTTP 401') RETURNING id"),
            {"i": CAT},
        ).scalar_one()  # fmt: skip
        c.execute(text("INSERT INTO fetch_log (run_id, source_id, method, url, status) VALUES (:r, :i, 'GET', 'x', 401)"),
                  {"r": run, "i": CAT})  # fmt: skip
        c.execute(
            text("INSERT INTO raw_record (source_id, resource, ext_id, payload) VALUES (:i, 'old', 'OLD-1', '{}')"), {"i": CAT}
        )
        c.execute(text("INSERT INTO sync_cursor (source_id, resource, cursor) VALUES (:i, 'old', 'x') ON CONFLICT DO NOTHING"),
                  {"i": CAT})  # fmt: skip
        c.execute(
            text("INSERT INTO failed_record (run_kind, run_id, source_id, step, reason, status) "
                 "VALUES ('sync', CAST(:r AS text), :i, 'map', 'old', 'held')"),
            {"r": run, "i": CAT},
        )  # fmt: skip
        c.execute(
            text("INSERT INTO webhook_event (event_id, source_id) VALUES ('old-evt', :i) ON CONFLICT DO NOTHING"), {"i": CAT}
        )


def test_reconnected_catalogue_source_starts_clean():
    starting.reset()
    _connect("first-key-000001")
    _seed_history()
    with engine.connect() as c:
        versions_before = c.execute(text("SELECT count(*) FROM field_mapping WHERE source_id = :i"), {"i": CAT}).scalar_one()
    assert versions_before >= 1 and all(_count(t) >= 1 for t in TABLES)
    d = call("source.delete", {"source_id": CAT}, DEV)
    assert d["ok"], d
    assert all(_count(t) >= 1 for t in TABLES)  # Undo can still bring it back with its data
    _connect()
    # the worker may already run the new source's first sync, so look for the predecessor's own rows
    assert _old_rows() == dict.fromkeys(TABLES, 0)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM field_mapping WHERE source_id = :i"), {"i": CAT}).scalar_one() == 1
        assert c.execute(text("SELECT max(version) FROM source_secret WHERE source_id = :i"), {"i": CAT}).scalar_one() == 1
    with SessionLocal() as s:
        assert secrets.active_secret(s, CAT) == catalog.template(CAT)["demo_secret"]


def _old_rows() -> dict[str, int]:
    """The rows _seed_history wrote that are still there, per table."""
    q = {
        "sync_run": "error = 'HTTP 401'",
        "fetch_log": "url = 'x'",
        "raw_record": "ext_id = 'OLD-1'",
        "sync_cursor": "resource = 'old'",
        "failed_record": "reason = 'old'",
        "webhook_event": "event_id = 'old-evt'",
    }
    with engine.connect() as c:
        return {t: c.execute(text(f"SELECT count(*) FROM {t} WHERE source_id = :i AND {w}"), {"i": CAT}).scalar_one()  # noqa: S608
                for t, w in q.items()}  # fmt: skip


def test_undo_of_a_delete_keeps_the_data():
    starting.reset()
    _connect()
    _seed_history()
    d = call("source.delete", {"source_id": CAT}, DEV)
    assert d["ok"], d
    u = client.post("/api/journal/undo", json={"seqs": [d["seq"]]}, headers=h("admin"))
    assert u.status_code == 200, u.text
    assert all(_count(t) >= 1 for t in TABLES)
    assert CAT in [x["id"] for x in client.get("/api/screens/integration/sources", headers=h(DEV)).json()["sources"]]
