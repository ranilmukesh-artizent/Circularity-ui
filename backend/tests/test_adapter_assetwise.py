"""B5b: the Bentley AssetWise (eng) adapter against the full AssetWise mock (data warehouse OData v4, IMS tokens).

Needs source-sim running and the worker stopped. Only eng is reset, and only its cursors and queued jobs are touched;
the module ends with a reset and a full sync that restore the demo's values.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors.http import SourceClient
from di.connectors.registry import ADAPTERS
from di.connectors.sync import ensure_sources, run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store

SIM = get_settings().source_sim_url
SID = "eng"
ODATA = SIM + "/assetwise/eB/Service/OData/Engineering"
CONNECTOR = ("di.connector", "Circularity-demo-aw-1")
APPROVER = ("eng.approver", "Circularity-demo-aw-approver")


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def fresh() -> None:
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = :s"), {"s": SID})
        conn.execute(
            text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = :s"), {"s": SID}
        )


@pytest.fixture(scope="module", autouse=True)
def clean():
    fresh()
    with SessionLocal() as s:
        ensure_sources(s)
        s.execute(
            text(
                "UPDATE source_system SET status = 'live' WHERE id = :s AND status IN ('unavailable', 'auth_expired', "
                "'failing')"
            ),
            {"s": SID},
        )
        s.commit()
    yield
    fresh()
    run_sync(SID, "manual", full=True)


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def prov(rec: dict, field: str) -> tuple:
    p = next(x for x in rec["provenance"][field] if x["source_id"] == SID)
    return p["source_field"], p["source_value"], p["transform"]


def sync(trigger: str) -> dict:
    out = run_sync(SID, trigger)
    if out["status"] == "partial" and "eadlock" in (out["error"] or ""):
        out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    return out


def delta_reads() -> int:
    a = ADAPTERS[SID]
    with SessionLocal() as s:
        client = SourceClient(SID, SIM + a.base_path, a.auth(), s)
        try:
            cursor = s.execute(
                text("SELECT cursor FROM sync_cursor WHERE source_id = :s AND resource = 'assessments'"), {"s": SID}
            ).scalar()
            assert cursor
            return sum(1 for _ in a.resources()[0].read(client, cursor))
        finally:
            client.close()
            s.rollback()


def test_initial_sync_maps_the_demo_examples():
    first = sync("initial")
    assert first["records_read"] > 90
    c = canonical("condition", "MTR-2041")
    d = c["data"]
    assert (d["life_assessment"], d["standard"], d["requalification"]) == ("36 months", "IEC 60034-1", "approved")
    assert prov(c, "life_assessment") == ("RUL_MONTHS", 36, "Months; source & confidence retained")
    assert prov(c, "standard") == ("STANDARD_REF", "IEC 60034-1", "Pass-through")
    assert prov(c, "requalification") == ("REQUAL_STATUS", "APPROVED", "Status map")
    assert d["life_range"] == {"low": 30, "high": 40} and d["next_inspection"] == "2027-04-01"
    assert (d["assessment_approval"], d["assessment_validity"]) == ("approved", "valid")
    assert d["assessment_valid_until"] > "2028-01-01"  # 24 months (IEC 60034-1 interval) from approval
    motor = canonical("condition", "class:motor")["data"]
    assert motor["requal_interval_months"] == 24 and motor["min_life_months"] == 12
    assert {x["id"] for x in motor["limits"]} >= {"LIM-MTR-RUL", "LIM-MTR-INS"}


def test_unchanged_delta_reads_nothing_and_an_approval_is_picked_up():
    assert delta_reads() == 0
    again = sync("schedule")
    assert again["records_read"] == 6  # the standards (one per class) are reference data, read in full

    draft = httpx.get(
        f"{ODATA}/LifeAssessments", auth=CONNECTOR, timeout=30, params={"$filter": "APPROVAL_STATUS eq 'Draft'", "$top": "1"}
    ).json()["value"][0]
    url = f"{ODATA}/LifeAssessments('{draft['ASSESSMENT_ID']}')"
    r = httpx.patch(
        url,
        auth=CONNECTOR,
        json={"RUL_MONTHS": 30, "RUL_LOW_MONTHS": 25, "RUL_HIGH_MONTHS": 34, "CONFIDENCE": "MEDIUM"},
        timeout=30,
    )
    assert r.status_code == 204, r.text
    assert httpx.post(url + "/AssetWise.Submit", auth=CONNECTOR, timeout=30).status_code == 204
    assert httpx.post(url + "/AssetWise.Approve", auth=CONNECTOR, timeout=30).status_code == 403  # not the submitter
    assert httpx.post(url + "/AssetWise.Approve", auth=APPROVER, json={"Comment": "ok"}, timeout=30).status_code == 204

    out = sync("schedule")
    assert out["records_read"] == 6 + 1
    d = canonical("condition", draft["ASSET_ID"])["data"]
    assert (d["life_assessment"], d["requalification"], d["assessment_approval"], d["assessment_validity"]) == (
        "30 months",
        "approved",
        "approved",
        "valid",
    )
    assert d["assessment_approved_by"] == "eng.approver"
    assert delta_reads() == 0
