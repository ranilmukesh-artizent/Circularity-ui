"""Catalogue systems map what their mock really holds (plan 6, track T8, after A3/A4).

- mapping.catalogSuggest {catalog_id}: the template's rows (di.connectors.catalog), each with a sample read from the
  system's mock; only source fields the mock's records have; a system with no circularity data suggests nothing
- connecting PostgreSQL / Snowflake from the catalogue saves the accepted template rows; the first sync fails no record
  and writes facts only for the accepted fields, on keys of their own ("postgres:MTR-2041"), never on a demo key
- connecting Workday HCM (no rows): records land in raw_record, no fact, no failed record

The module removes every source it made and the facts they wrote.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors import catalog, connection
from di.connectors.configured import ConfiguredAdapter
from di.connectors.mapping import _MISSING, lookup
from di.connectors.sync import run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from tests.helpers import call

SIM = get_settings().source_sim_url.rstrip("/")
IDS = ["postgres", "snowflake", "workday"]
TABLES = ("sync_run", "fetch_log", "raw_record", "sync_cursor", "source_connection", "source_secret", "field_mapping")


def setup_module():
    _cleanup()


def teardown_module():
    _cleanup()


def _cleanup() -> None:
    with engine.begin() as c:
        for sid in IDS:
            c.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": sid + ":%"})
            c.execute(text('DELETE FROM conflict WHERE jsonb_exists("values", :s)'), {"s": sid})
        c.execute(text("DELETE FROM provenance WHERE source_id = ANY(:i)"), {"i": IDS})
        for t in TABLES:
            c.execute(text(f"DELETE FROM {t} WHERE source_id = ANY(:i)"), {"i": IDS})  # noqa: S608 - fixed names
        c.execute(text("DELETE FROM failed_record WHERE source_id = ANY(:i)"), {"i": IDS})
        c.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = ANY(:i)"), {"i": IDS})
        c.execute(text("DELETE FROM source_system WHERE id = ANY(:i)"), {"i": IDS})
        c.execute(text("DELETE FROM state_item WHERE collection = 'source_config' AND id = ANY(:i)"), {"i": IDS})


def mock_records(sid: str) -> dict[str, list[dict]]:
    """Every record the mock of `sid` holds, per resource, read straight from source-sim with its demo credential."""
    t = catalog.template(sid)
    conn = connection.Connection(sid, SIM + t["base_path"], "rest", t["auth_kind"], t["auth_params"], t["paging"], t["resources"])
    a = ConfiguredAdapter(conn)
    from di.connectors.http import SourceClient

    with SessionLocal() as s:
        client = SourceClient(sid, conn.base_url, a.auth(conn, t["demo_secret"]), s)
        try:
            return {r["name"]: [row for row, _ in a.pages(client, r, None)] for r in t["resources"]}
        finally:
            client.close()
            s.rollback()


def suggest(sid: str) -> list[list]:
    r = call("mapping.catalogSuggest", {"catalog_id": sid}, "developer")
    assert r["ok"], r
    return r["output"]["rows"]


def connect(sid: str, maps: list) -> dict:
    httpx.post(SIM + "/_sim/reset", params={"system": sid}, timeout=60).raise_for_status()
    body = {"mode": "catalog", "id": "", "d": {"catalog": sid, "auth": "oauth", "scopes": ["read"]}, "maps": maps, "ops": {}}
    r = call("source.update", body, "developer")
    assert r["ok"], r
    return r["output"]


def facts_of(sid: str) -> list:
    with engine.connect() as c:
        return c.execute(text("SELECT model, key, field FROM provenance WHERE source_id = :s"), {"s": sid}).all()


@pytest.mark.parametrize("sid", ["postgres", "mysql", "sqlserver", "snowflake", "dynamics", "ebs", "excel"])
def test_suggest_returns_template_rows_the_mock_really_has(sid):
    rows = suggest(sid)
    assert rows, sid
    recs = mock_records(sid)
    for src, _sample, target, _norm, conf, resource in rows:
        assert conf >= 85, rows  # High: an exact template row
        assert "." in target and not target.endswith(".key"), rows  # the key rows are not offered: they are always kept
        assert any(lookup(rec, src) is not _MISSING for rec in recs[resource]), (sid, resource, src)


@pytest.mark.parametrize("sid", ["workday", "jira", "confluence", "teams", "gdrive", "s3", "azureblob", "netsuite"])
def test_systems_without_circularity_data_suggest_nothing(sid):
    assert suggest(sid) == []


def test_suggest_needs_a_known_system_and_the_permission():
    assert call("mapping.catalogSuggest", {"catalog_id": "nope"}, "developer")["error"]["code"] == "not_found"
    assert not call("mapping.catalogSuggest", {"catalog_id": "postgres"}, "planner.a")["ok"]


def test_connect_postgres_maps_its_records_without_failures():
    rows = suggest("postgres")
    accepted = [r for r in rows if r[2] != "asset.manufacturer"]  # the person unticks one row
    assert len(accepted) == len(rows) - 1
    connect("postgres", accepted)
    recs = mock_records("postgres")
    out = run_sync("postgres", "initial", full=True)
    n = sum(len(v) for v in recs.values())
    assert out["records_read"] == n and out["records_failed"] == 0 and out["status"] == "ok", out
    assert out["facts_written"] > 0, out
    got = facts_of("postgres")
    fields = {f"{m}.{f}" for m, _, f in got}
    assert fields == {r[2] for r in accepted}, fields
    assert all(k.startswith("postgres:") for _, k, _ in got)  # keys of their own: never a demo asset's
    a0 = recs["asset_register"][0]
    with engine.connect() as c:
        data = c.execute(
            text("SELECT data FROM canonical WHERE model = 'asset' AND key = :k"), {"k": "postgres:" + a0["asset_id"]}
        ).scalar_one()
        assert data["asset_id"] == a0["asset_id"] and data["description"] == a0["description"], data
        assert "manufacturer" not in data
        held = c.execute(text("SELECT count(*) FROM failed_record WHERE source_id = 'postgres'")).scalar_one()
        assert held == 0
        opened = c.execute(text("SELECT count(*) FROM conflict WHERE jsonb_exists(\"values\", 'postgres')")).scalar_one()
        assert opened == 0
    with SessionLocal() as s:  # the saved mapping: the accepted rows and the key rows, nothing from FR_SAMPLE
        from di.connectors import mapping

        saved = mapping.active_rows(s, "postgres")
    assert {f"{r.model}.{r.field}" for r in saved} == {r[2] for r in accepted} | {"asset.key"}
    assert all(r.resource in ("asset_register", "work_orders") for r in saved)


def test_connect_snowflake_writes_asset_and_condition_facts():
    rows = suggest("snowflake")
    connect("snowflake", rows)
    out = run_sync("snowflake", "initial", full=True)
    assert out["records_failed"] == 0 and out["status"] == "ok" and out["facts_written"] > 0, out
    got = facts_of("snowflake")
    assert {m for m, _, _ in got} >= {"asset", "condition"}
    assert all(k.startswith("snowflake:") for _, k, _ in got)
    with engine.connect() as c:
        g = c.execute(text("SELECT value FROM provenance WHERE source_id = 'snowflake' AND field = 'grade' LIMIT 1")).scalar_one()
    assert g in ("A", "B", "C", "D"), g


def test_connect_workday_keeps_its_records_and_writes_no_fact():
    out = connect("workday", [])  # nothing to accept: Workday holds no asset, condition or demand data
    assert out["queued"] is True
    seeded = sum(len(v) for v in mock_records("workday").values())
    res = run_sync("workday", "initial", full=True)
    assert res["records_read"] == seeded and res["records_failed"] == 0 and res["status"] == "ok", res
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM raw_record WHERE source_id = 'workday'")).scalar_one() == seeded
    assert facts_of("workday") == []
