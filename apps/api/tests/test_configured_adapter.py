"""Plan 6 A3: sources without a Python adapter are read by the configured adapter (di.connectors.configured).

- connecting Workday HCM from the catalogue stores its connection and credential and queues a first sync that reads
  the system (source-sim's synthetic mock): records_read equals what the mock holds; Sync now works afterwards
- every catalogue system's template reads its mock to the end (paging, auth)
- a source set up by hand that points at source-sim's sandbox syncs its 25 records
- one that points at an unknown host fails Test connection at DNS

The hand-made sources' mappings name source fields the records do not have, so every record fails with "missing
field ..." (counted, not fatal) and nothing reaches the canonical store. Workday's catalogue template maps nothing
(tests/test_catalog_mappings.py), so its records are kept raw and none fails. The module removes every source it made.
"""

import httpx
import pytest
from sqlalchemy import text

from di.config import get_settings
from di.connectors import catalog, connection, secrets
from di.connectors.configured import ConfiguredAdapter
from di.connectors.registry import adapter_for
from di.connectors.sync import run_sync
from di.db import SessionLocal, engine
from tests.helpers import call

SIM = get_settings().source_sim_url.rstrip("/")
NO_FACTS = [["Worker.Worker_ID", "W-1", "asset.owner_contact", "W-1", 96]]  # no such field in the records
TABLES = ("sync_run", "fetch_log", "raw_record", "sync_cursor", "source_connection", "source_secret", "field_mapping")
_made: list[str] = []


def setup_module():
    _cleanup([*catalog.IDS, "sandbox_src"])


def teardown_module():
    _cleanup(_made)


def _cleanup(ids: list[str]) -> None:
    with engine.begin() as c:
        made = list(
            c.execute(text("SELECT id FROM source_system WHERE id = ANY(:i) OR vendor = 'Sandbox'"), {"i": ids}).scalars()
        ) + list(ids)
        for t in TABLES:
            c.execute(text(f"DELETE FROM {t} WHERE source_id = ANY(:i)"), {"i": made})  # noqa: S608 - fixed names
        if c.execute(text("SELECT to_regclass('failed_record')")).scalar():
            c.execute(text("DELETE FROM failed_record WHERE source_id = ANY(:i)"), {"i": made})
        c.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = ANY(:i)"), {"i": made})
        c.execute(text("DELETE FROM source_system WHERE id = ANY(:i)"), {"i": made})
        c.execute(text("DELETE FROM state_item WHERE collection = 'source_config' AND id = ANY(:i)"), {"i": made})


def mock_count(sid: str) -> int:
    """What the mock of `sid` holds, read straight from source-sim with its demo credential."""
    t = catalog.template(sid)
    conn = connection.Connection(sid, SIM + t["base_path"], "rest", t["auth_kind"], t["auth_params"], t["paging"], t["resources"])
    a = ConfiguredAdapter(conn)
    from di.connectors.http import SourceClient

    with SessionLocal() as s:
        client = SourceClient(sid, conn.base_url, a.auth(conn, t["demo_secret"]), s)
        try:
            return sum(
                1 for r in a.resources() for _ in a.pages(client, next(x for x in t["resources"] if x["name"] == r.name), None)
            )
        finally:
            client.close()
            s.rollback()


def test_connect_workday_from_the_catalogue_reads_its_records():
    httpx.post(SIM + "/_sim/reset", params={"system": "workday"}, timeout=60).raise_for_status()
    body = {"mode": "catalog", "id": "", "d": {"catalog": "workday", "auth": "oauth", "scopes": ["read"]}, "maps": NO_FACTS,
            "ops": {}}  # fmt: skip
    r = call("source.update", body, "developer")
    assert r["ok"], r
    _made.append("workday")
    assert r["output"]["queued"] is True and r["output"]["records"] is None
    with SessionLocal() as s:
        conn = connection.connection_for(s, "workday")
        assert conn.base_url == SIM + "/workday/ccx/api/v1/northfield" and conn.auth_kind == "oauth_cc"
        assert secrets.active_secret(s, "workday") == "workday-demo-secret"
        assert isinstance(adapter_for(s, "workday"), ConfiguredAdapter)
        assert (
            s.execute(
                text("SELECT payload->>'trigger' FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = 'workday'")
            ).scalar()
            == "initial"
        )
    seeded = mock_count("workday")
    out = run_sync("workday", "initial", full=True)
    assert out["records_read"] == seeded > 30, out
    # Workday's template maps nothing, and rows that are not the template's are not saved (T8): kept raw, none failed
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    with engine.connect() as c:
        n = c.execute(text("SELECT count(*) FROM raw_record WHERE source_id = 'workday'")).scalar_one()
        assert n == seeded
        assert c.execute(text("SELECT count(*) FROM provenance WHERE source_id = 'workday'")).scalar_one() == 0
    sy = call("source.sync", {"source_id": "workday"}, "developer")
    assert sy["ok"], sy
    again = run_sync("workday", "manual")  # a delta read: nothing changed in the mock since the first sync
    assert again["status"] in ("ok", "partial") and again["records_read"] <= seeded, again


@pytest.mark.parametrize("sid", [x for x in catalog.IDS if x != "workday"])
def test_every_catalogue_template_reads_its_mock(sid):
    assert mock_count(sid) > 0


def test_a_hand_made_source_on_the_sandbox_syncs():
    d = {"type": "erp", "name": "Sandbox ERP", "vendor": "Sandbox", "ver": "", "env": "Test", "url": SIM + "/sandbox/demo",
         "method": "api", "cfg": {"spec": "REST"}, "interval": 15, "auth": "No authentication", "owner": ""}  # fmt: skip
    body = {"mode": "new", "id": "", "d": d, "maps": [["nope.field", "x", "asset.asset_id", "x", "Pass-through"]],
            "ops": {"read": ["GET /records"], "write": []}, "note": ""}  # fmt: skip
    r = call("source.update", body, "developer")
    assert r["ok"], r
    sid = r["output"]["source_id"]
    _made.append(sid)
    with SessionLocal() as s:
        conn = connection.connection_for(s, sid)
    assert conn.base_url == SIM + "/sandbox/demo" and conn.auth_kind == "none"
    assert conn.resources == [{"name": "records", "path": "/records", "id_field": "id"}]
    out = run_sync(sid, "initial", full=True)
    assert out["records_read"] == 25 and out["records_failed"] == 25, out


def test_a_hand_made_source_on_an_unknown_host_fails_at_dns():
    d = {"type": "erp", "name": "Nowhere ERP", "vendor": "Sandbox", "ver": "", "env": "Test",
         "url": "https://no-such-host.invalid/api", "method": "api", "cfg": {"spec": "REST"}, "interval": 15,
         "auth": "API key", "owner": ""}  # fmt: skip
    body = {"mode": "new", "id": "", "d": d, "maps": [["nope.field", "x", "asset.asset_id", "x", "Pass-through"]],
            "ops": {"read": ["GET /records"], "write": []}, "note": "", "secret": "a-key-for-nowhere"}  # fmt: skip
    r = call("source.update", body, "developer")
    assert r["ok"], r
    sid = r["output"]["source_id"]
    _made.append(sid)
    t = call("source.test", {"source_id": sid}, "developer")["output"]
    assert not t["ok"] and len(t["steps"]) == 1 and not t["steps"][0]["ok"], t
    assert "no-such-host.invalid" in t["steps"][0]["msg"], t
