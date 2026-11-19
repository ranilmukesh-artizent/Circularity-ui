"""B5b: the MasterControl (qms) adapter against source-sim's full MasterControl mock.

Needs source-sim running and the worker stopped. Only qms is reset, and only its cursors and queued jobs are touched.
"""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text

from di.canonical import store
from di.config import get_settings
from di.connectors.http import SourceClient
from di.connectors.registry import ADAPTERS
from di.connectors.sync import ensure_sources, run_sync
from di.db import SessionLocal, engine

SIM = get_settings().source_sim_url
SID = "qms"
API = SIM + "/mastercontrol/mc/api"
KEY = {"X-API-KEY": "circularity-demo-mastercontrol-apikey"}


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, path if path.startswith("http") else SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def clear() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = :s"), {"s": SID})
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = :s"), {"s": SID})


@pytest.fixture(scope="module", autouse=True)
def clean():
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    clear()
    with SessionLocal() as s:
        ensure_sources(s)
        s.execute(
            text("UPDATE source_system SET status = 'live' WHERE id = :s AND status IN ('unavailable', 'auth_expired')"),
            {"s": SID},
        )
        s.commit()
    yield
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    clear()
    run_sync(SID, "manual", full=True)  # put the seeded certificates back into the shared canonical store
    clear()


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def prov(rec: dict, field: str) -> tuple:
    p = next(x for x in rec["provenance"][field] if x["source_id"] == SID)
    return p["source_field"], p["source_value"], p["transform"]


def initial() -> dict:
    out = run_sync(SID, "initial")
    if out["status"] == "partial" and "Deadlock" in (out["error"] or ""):
        out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] > 0, out
    return out


def delta_reads() -> int:
    a = ADAPTERS[SID]
    n = 0
    with SessionLocal() as s:
        client = SourceClient(SID, SIM + a.base_path, a.auth(), s)
        try:
            for res in a.resources():
                if res.delta:
                    cursor = s.execute(
                        text("SELECT cursor FROM sync_cursor WHERE source_id = :s AND resource = :r"), {"s": SID, "r": res.name}
                    ).scalar()
                    assert cursor
                    n += sum(1 for _ in res.read(client, cursor))
        finally:
            client.close()
            s.rollback()
    return n


def sim_today() -> date:
    return datetime.fromisoformat(sim("GET", "/_sim/clock").json()["now"]).astimezone(UTC).date()


def new_cert(number: str, asset: str, cert_type: str, issued: date, expiry: date) -> dict:
    body = {
        "certificateNumber": number,
        "certificateType": cert_type,
        "issuedDate": issued.isoformat(),
        "dataFields": {
            "ASSET_ID": asset,
            "CERT_EXPIRY": expiry.isoformat(),
            "TEST_RESULT": "PASS",
            "CERTIFIED_LIFE_MONTHS": 12,
            "DOCUMENT_NUMBER": "POL-REUSE-MTR",
        },
    }
    return sim("POST", API + "/v2/certificates", headers=KEY, json=body).json()


def test_initial_sync_reproduces_the_demo_mappings():
    first = initial()
    c = canonical("condition", "MTR-2041")
    d = c["data"]
    assert d["certificates"][0]["expires"] == "2027-03-01" and d["certificates"][0]["ref"] == "QMS-2906"
    assert d["certificates"][0]["status"] == "active" and d["certificate_status"] == "active"
    assert d["certified_life_months"] == 24 and d["certificate_expiry"] == "2027-03-01"
    assert prov(c, "certificate_expiry") == ("CERT_EXPIRY", "2027-03-01", "ISO date")
    assert prov(c, "policy") == ("REUSE_CLASS", "ALLOWED_CAT2", "Policy map v3.2") and d["policy"] == "reuse_permitted"
    assert prov(c, "qualification") == ("TEST_RESULT", "PASS", "Result map") and d["qualification"] == "passed"
    assert next(p for p in c["provenance"]["certificates"] if p["source_id"] == SID)["authority"] is True
    rq = canonical("condition", "CTL-0122")["data"]  # the demo's CF-32: QMS says requalified 12 Sep
    assert rq["qualification"] == "requalified" and rq["requalified_on"] == "2026-09-12"
    motor = canonical("condition", "class:motor")
    # only the Effective revision is policy: not the superseded 3.1, not the draft 3.3 (ALLOWED_CAT1)
    assert motor["data"]["policy"] == "reuse_permitted" and motor["data"]["policy_version"] == "3.2"
    assert motor["data"]["policy_ref"] == "POL-REUSE-MTR" and len(motor["data"]["required_tests"]) == 4
    assert prov(motor, "policy") == ("REUSE_CLASS", "ALLOWED_CAT2", "Policy map v3.2")

    # an unchanged delta reads nothing; the next scheduled sync reads only the (full-read) policies
    assert delta_reads() == 0
    again = run_sync(SID, "schedule")
    assert again["status"] == "ok" and again["records_read"] < first["records_read"], again


def test_a_new_certificate_is_picked_up_by_the_delta():
    today = sim_today()
    rec = new_cert("RQ-MTR-2041-T", "MTR-2041", "REQUALIFICATION", today - timedelta(days=1), today + timedelta(days=365))
    assert rec["status"] == "Active"
    assert delta_reads() == 1  # the whole set of MTR-2041
    out = run_sync(SID, "schedule")
    assert out["status"] == "ok", out
    d = canonical("condition", "MTR-2041")["data"]
    assert {c["ref"] for c in d["certificates"]} == {"QMS-2906", "RQ-MTR-2041-T"}
    assert d["cert_ref"] == "QMS-2906" and d["certificate_expiry"] == "2027-03-01"  # the life certificate stays first
    assert delta_reads() == 0


def test_an_expired_certificate_shows_as_expired():
    today = sim_today()
    rec = new_cert("QMS-T-EXP", "TEST-QMS-EXPIRED", "LIFE_CERTIFICATION", today - timedelta(days=400), today - timedelta(days=1))
    assert rec["status"] == "Expired"
    out = run_sync(SID, "schedule")
    assert out["status"] == "ok", out
    c = canonical("condition", "TEST-QMS-EXPIRED")
    d = c["data"]
    assert d["certificate_status"] == "expired" and d["certificates"][0]["status"] == "expired"
    assert d["certificate_expiry"] == (today - timedelta(days=1)).isoformat()
    assert prov(c, "certificate_status") == ("status", "Expired", "Status map")
