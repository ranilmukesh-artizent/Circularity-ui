"""B5b: the Sims Lifecycle Services adapter, a real SFTP client, against source-sim's SFTP drop (port 2222).

Needs source-sim running; keep the worker stopped so scheduled syncs do not race the tests. Only rcy is reset, and
only its cursors and jobs are touched.
"""

import httpx
import pytest
from sqlalchemy import text

from di.canonical import store
from di.config import get_settings
from di.connectors.adapters import sims
from di.connectors.http import SourceClient, SourceError
from di.connectors.registry import ADAPTERS
from di.connectors.sync import ensure_sources, run_sync
from di.db import SessionLocal, engine

SIM = get_settings().source_sim_url
ADMIN = SIM + "/sims/admin/outbound"


def sim(method: str, url: str, **kw) -> httpx.Response:
    r = httpx.request(method, url if url.startswith("http") else SIM + url, timeout=60, **kw)
    r.raise_for_status()
    return r


def forget_jobs() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = 'rcy'"))


def reset() -> None:
    sim("POST", "/_sim/reset", params={"system": "rcy"})
    sim("POST", "/_sim/webhooks/deliver")  # deliver the reset event now, so it cannot land mid-test
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = 'rcy'"))
    forget_jobs()


@pytest.fixture(scope="module", autouse=True)
def clean():
    with SessionLocal() as s:
        ensure_sources(s)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE source_system SET status = 'live' WHERE id = 'rcy' AND status IN ('unavailable', 'auth_expired')")
        )
    reset()
    yield
    reset()


def canonical(key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, "vendor", key)
    assert rec is not None, f"vendor.{key} missing"
    return rec


def prov(rec: dict, field: str) -> dict:
    return next(x for x in rec["provenance"][field] if x["source_id"] == "rcy")


def test_initial_sync_over_sftp_reproduces_the_facts():
    out = run_sync("rcy", "initial")
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    assert out["records_read"] == 3 + 3  # three vendors, plus rates, yields and custody of the approved one
    v = canonical("SIMS-MAA")
    d = v["data"]
    assert d["certification"] == "certified" and d["cert_valid_to"] == "2027-03-31"
    p = prov(v, "certification")
    assert (p["source_field"], p["source_value"], p["transform"]) == ("VND_CERT", "ISO14001-VA", "Certificate table")
    cu = d["material_rates"]["Cu"]
    assert (cu["usd_per_t"], cu["label"]) == (7784, "Cu $7,800 / t") and d["rebates"]["Cu"] == 7784
    p = prov(v, "material_rates")
    assert p["source_field"] == "RATE_TNE" and "Cu 7.8k" in p["source_value"] and p["transform"] == "Unit + currency"
    assert d["yields"]["motor"]["Cu"] == 11.4 and d["fees"]["LiB"] > 0 and d["custody_certificates"]
    assert canonical("VND-U")["data"]["certification"] == "lapsed"
    with SessionLocal() as s:
        cursor = s.execute(text("SELECT cursor FROM sync_cursor WHERE source_id = 'rcy' AND resource = 'files'")).scalar()
        logged = s.execute(
            text("SELECT url, status, records FROM fetch_log WHERE run_id = :r ORDER BY id"), {"r": out["run_id"]}
        ).all()
        raw = s.execute(text("SELECT request FROM raw_record WHERE source_id = 'rcy' AND resource = 'partner-rates'")).scalar()
    assert cursor == "2026-10-05T09:00:00+00:00"  # the drop's modification time
    assert raw.startswith("sftp://di-connector@") and raw.endswith(":2222/outbound/partner-rates.csv")
    urls = [u for u, _, _ in logged]
    assert urls[0].startswith("CONNECT sftp://") and urls[1].startswith("LIST ") and all(st == 0 for _, st, _ in logged)
    assert sum(u.startswith("GET ") for u in urls) == 10  # 4 CSVs, the manifest and 5 signatures
    with SessionLocal() as s:
        assert s.execute(
            text("SELECT count(*) FROM fetch_log WHERE run_id = :r AND method = 'SFTP'"), {"r": out["run_id"]}
        ).scalar() == len(logged)


def test_unchanged_second_sync_reads_nothing():
    again = run_sync("rcy", "schedule")
    assert again["status"] == "ok" and again["records_read"] == 0, again


def test_tampered_file_is_one_failed_record():
    original = sim("GET", ADMIN + "/partner-rates.csv").content
    sim("PUT", ADMIN + "/partner-rates.csv", content=original.replace(b"650.00", b"950.00"))  # not signed again
    out = run_sync("rcy", "schedule")
    assert out["status"] == "partial" and out["records_failed"] == 1 and out["records_read"] == 1, out
    assert "partner-rates.csv" in out["error"] and "does not match the manifest" in out["error"]
    assert canonical("SIMS-MAA")["data"]["material_rates"]["Cu"]["usd_per_t"] == 7784  # nothing from the bad file
    # the partner publishes the drop again: every file is new, all verify
    sim("POST", "/sims/admin/publish")
    out = run_sync("rcy", "schedule")
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] == 6, out


def test_bad_manifest_signature_fails_every_file():
    reset()
    sim("PUT", ADMIN + "/manifest.json.sig", content=b"0" * 64 + b"\n")
    a = ADAPTERS["rcy"]
    with SessionLocal() as s:
        client = SourceClient("rcy", SIM + a.base_path, a.auth(), s)
        try:
            records = list(a.read_files(client, None))
        finally:
            client.close()
            s.rollback()
    assert len(records) == 4 and all("manifest.json: signature" in r.payload["integrity_error"] for r in records)
    with pytest.raises(sims.IntegrityError):
        a.map(records[0])
    reset()


def test_wrong_password_is_an_auth_error():
    with SessionLocal() as s:
        client = SourceClient("rcy", SIM + "/sims", sims.Auth(), s)
        try:
            with pytest.raises(SourceError) as e:
                sims.Drop(client, *sims.sftp_target(), password="wrong")
            assert e.value.kind == "auth"
        finally:
            client.close()
            s.rollback()
