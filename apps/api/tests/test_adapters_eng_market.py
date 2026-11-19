"""B9: the engineering, quality, sustainability and market adapters against source-sim's generic mocks.

Oracle Lease (lease), Teamcenter (plm), Aras (bom), MasterControl (qms), AssetWise (eng), Persefoni (esg),
Ritchie Bros. (mkt), Machinio (dlr) and the Sims CSV drop (rcy). Needs source-sim running; keep the worker stopped
(`docker compose stop worker`) so scheduled syncs do not race the tests. Only these nine systems are reset, and only
their cursors and jobs are touched, so other connector tests can share the database.
"""

import json

import httpx
import pytest
from sqlalchemy import text

from di.canonical import store
from di.config import get_settings
from di.connectors.adapters import sims
from di.connectors.http import SourceClient
from di.connectors.registry import ADAPTERS
from di.connectors.sync import ensure_sources, run_sync
from di.db import SessionLocal, engine

SIM = get_settings().source_sim_url
MINE = ("lease", "plm", "bom", "qms", "eng", "esg", "mkt", "dlr", "rcy")


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def forget_jobs() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = ANY(:m)"),
            {"m": list(MINE)},
        )


@pytest.fixture(scope="module", autouse=True)
def clean():
    sim("DELETE", "/_sim/faults", params={"system": "mkt"})
    for s in MINE:
        sim("POST", "/_sim/reset", params={"system": s})
    sim("POST", "/_sim/webhooks/deliver")  # deliver the reset events now, so they cannot land mid-test
    with SessionLocal() as s:
        ensure_sources(s)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = ANY(:m)"), {"m": list(MINE)})
        # registered before these adapters existed: make them syncable
        conn.execute(
            text("UPDATE source_system SET status = 'live' WHERE id = ANY(:m) AND status IN ('unavailable', 'auth_expired')"),
            {"m": list(MINE)},
        )
    forget_jobs()
    yield
    sim("DELETE", "/_sim/faults", params={"system": "mkt"})
    forget_jobs()


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def prov(rec: dict, field: str, source_id: str) -> tuple:
    p = next(x for x in rec["provenance"][field] if x["source_id"] == source_id)
    return p["source_field"], p["source_value"], p["transform"]


def sync_ok(source_id: str) -> dict:
    out = run_sync(source_id, "initial")
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] > 0, out
    return out


def delta_reads(source_id: str) -> int:
    """Records an unchanged delta read returns, over every delta resource (from the saved cursors)."""
    a = ADAPTERS[source_id]
    n = 0
    with SessionLocal() as s:
        client = SourceClient(source_id, SIM + a.base_path, a.auth(), s)
        try:
            for res in a.resources():
                if not res.delta:
                    continue
                cursor = s.execute(
                    text("SELECT cursor FROM sync_cursor WHERE source_id = :s AND resource = :r"), {"s": source_id, "r": res.name}
                ).scalar()
                assert cursor, f"no cursor for {source_id}/{res.name}"
                n += sum(1 for _ in res.read(client, cursor))
        finally:
            client.close()
            s.rollback()
    return n


def assert_delta_quiet(source_id: str, first: dict) -> None:
    assert delta_reads(source_id) == 0
    again = run_sync(source_id, "schedule")
    assert again["status"] == "ok" and again["records_read"] < first["records_read"], again
    if all(r.delta for r in ADAPTERS[source_id].resources()):
        assert again["records_read"] == 0


def test_lease_contract_ownership_and_rate():
    first = sync_ok("lease")
    a = canonical("asset", "MTR-2041")
    d = a["data"]
    assert (d["lease_ref"], d["contract_end"], d["owner_tenant"], d["lessee"], d["lease_rate"]) == (
        "LC-004417",
        "2026-12-31",
        "Customer A",
        "Customer A",
        2400.0,
    )
    assert prov(a, "lease_ref", "lease") == ("LEASE_CONTRACT_ID", "LC-004417", "Pass-through")
    assert prov(a, "contract_end", "lease") == ("CONTRACT_END_DATE", "2026-12-31", "ISO date")
    assert prov(a, "owner_tenant", "lease") == ("LESSEE_NAME", "CUSTOMER_A", "Tenant key")
    assert prov(a, "lease_rate", "lease") == ("MONTHLY_RENTAL", "2400.00 USD", "Currency + period normalised")
    assert next(p for p in a["provenance"]["owner_tenant"] if p["source_id"] == "lease")["authority"] is True
    assert canonical("asset", "MTR-2077")["data"]["owner_tenant"] == "Customer A"  # the demo's CF-31: lease says A
    ls = canonical("demand", "LS-5530")["data"]
    assert ls["asset_ref"] == "MTR-2041" and ls["lease_ref"] == "LC-004417" and ls["need_by"] == "2026-12-31"
    assert_delta_quiet("lease", first)


def test_teamcenter_configuration_and_compatibility():
    first = sync_ok("plm")
    a = canonical("asset", "MTR-2041")
    d = a["data"]
    assert (d["configuration"], d["configuration_item"], d["bom_ref"], d["compatibility"]) == (
        "55 kW · IE3 · 250M",
        "MTR-55-IE3-250M",
        "BOM-55-C",
        "compatible",
    )
    assert prov(a, "configuration", "plm") == ("ITEM_ID", "MTR-55-IE3-250M", "Config decoded")
    assert prov(a, "compatibility", "plm") == ("ALT_APPROVED", "Y", "Boolean")
    assert prov(a, "bom_ref", "plm") == ("REV", "C", "Revision prefix")
    assert d["approved_alternates"] == []  # its 55 kW alternates have another frame
    assert_delta_quiet("plm", first)


def test_aras_components_follow_the_configuration():
    sync_ok("bom")  # after plm: the assets of each configuration come from asset.configuration_item
    a = canonical("asset", "MTR-2041")
    comps = a["data"]["components"]
    assert comps[0] == comps[0] | {"name": "Rotor assembly", "part": "P-55-ROT-01", "qty": 1, "harvestable": False}
    assert [c["name"] for c in comps][:3] == ["Rotor assembly", "Stator assembly", "Bearing set"]
    bearings = next(c for c in comps if c["name"] == "Bearing set")
    assert bearings["harvestable"] and {s["part"] for s in bearings["spare_parts"]} >= {"SKF-6316-2Z/C3", "VLT-SK-250M"}
    assert prov(a, "components", "bom")[0::2] == ("Part.item_number", "Part name lookup")
    assert prov(a, "components", "bom")[1][0] == "P-55-ROT-01"
    assert a["data"]["bom_state"] == "released" and prov(a, "bom_state", "bom") == ("Part.state", "Released", "State map")
    assert "Rotor assembly" not in a["data"]["harvestable_components"]


def test_mastercontrol_certificates_and_policy():
    first = sync_ok("qms")
    c = canonical("condition", "MTR-2041")
    d = c["data"]
    assert d["certificates"][0]["expires"] == "2027-03-01" and d["certificates"][0]["ref"] == "QMS-2906"
    assert d["certified_life_months"] == 24 and d["certificate_expiry"] == "2027-03-01"
    assert prov(c, "certificate_expiry", "qms") == ("CERT_EXPIRY", "2027-03-01", "ISO date")
    assert prov(c, "policy", "qms") == ("REUSE_CLASS", "ALLOWED_CAT2", "Policy map v3.2") and d["policy"] == "reuse_permitted"
    assert prov(c, "qualification", "qms") == ("TEST_RESULT", "PASS", "Result map") and d["qualification"] == "passed"
    rq = canonical("condition", "CTL-0122")["data"]  # the demo's CF-32: QMS says requalified 12 Sep
    assert rq["qualification"] == "requalified" and rq["requalified_on"] == "2026-09-12"
    motor = canonical("condition", "class:motor")["data"]
    assert motor["policy"] == "reuse_permitted" and motor["policy_ref"] == "POL-REUSE-MTR" and len(motor["required_tests"]) == 4
    assert_delta_quiet("qms", first)


def test_assetwise_life_assessment():
    first = sync_ok("eng")
    c = canonical("condition", "MTR-2041")
    d = c["data"]
    assert (d["life_assessment"], d["standard"], d["requalification"]) == ("36 months", "IEC 60034-1", "approved")
    assert prov(c, "life_assessment", "eng") == ("RUL_MONTHS", 36, "Months; source & confidence retained")
    assert prov(c, "standard", "eng") == ("STANDARD_REF", "IEC 60034-1", "Pass-through")
    assert prov(c, "requalification", "eng") == ("REQUAL_STATUS", "APPROVED", "Status map")
    assert d["life_range"] == {"low": 30, "high": 40} and d["next_inspection"] == "2027-04-01"
    assert canonical("condition", "class:motor")["data"]["requal_interval_months"] == 24
    assert_delta_quiet("eng", first)


def test_persefoni_factors_and_footprints():
    first = sync_ok("esg")
    f = canonical("sustainability", "class:motor")
    assert f["data"]["emission_factor"] == 420.0 and f["data"]["boundary"] == "cradle-to-gate"
    assert prov(f, "emission_factor", "esg") == ("factor_kgco2e", 420.0, "Unit kept")
    assert prov(f, "boundary", "esg") == ("scope", "Cradle-to-gate", "Boundary map")
    assert canonical("sustainability", "route:redeploy")["data"]["avoided_share"] == 0.7
    s = canonical("sustainability", "MTR-2041")["data"]
    assert s["footprint"]["redeploy"] == 294.0 and s["case_ref"] == "RT-1048" and s["footprint_method"] == "estimated"
    assert canonical("sustainability", "PMP-1007")["data"]["decision_footprints"][0]["measured_kg"] == 147.0
    assert_delta_quiet("esg", first)


def test_ritchie_comparables_and_the_expired_token():
    first = sync_ok("mkt")
    m = canonical("market", "MTR-2041")
    d = m["data"]
    assert d["sale_price"] == 5600.0 and d["comparables_count"] == 48 and d["grade"] == "B"
    assert d["comparable_high"] == 9700.0
    assert prov(m, "comparable_high", "mkt") == ("SOLD_PRC", "8.1 L INR", "Currency + Lakh unit expanded")
    top = next(c for c in d["comparables"] if c["sold_prc"] == "8.1 L INR")
    assert (top["price"], top["days_listed"], top["grade"]) == (9700.0, 17, "B")
    assert prov(m, "grade", "mkt")[0::2] == ("CONDITION", "Dealer grade map")
    assert d["feed_updated_at"] == "2026-10-06T14:00:00+00:00" and d["latest_sale_date"] <= "2026-10-05"
    assert next(p for p in m["provenance"]["sale_price"] if p["source_id"] == "mkt")["authority"] is True
    assert canonical("market", "class:motor")["data"]["price_index_period"] == "2026-09"
    assert_delta_quiet("mkt", first)
    # the demo's starting state: the feed token expired (the same fault as source-sim's DEMO_FAULTS, for mkt only)
    sim("POST", "/_sim/faults", json={"system": "mkt", "kind": "token_expired", "note": "Feed token expired 6 Oct"})
    try:
        out = run_sync("mkt", "manual")
        assert out["status"] == "failed" and "401" in out["error"]
        with SessionLocal() as s:
            assert s.execute(text("SELECT status FROM source_system WHERE id = 'mkt'")).scalar_one() == "auth_expired"
        assert canonical("market", "MTR-2041")["data"]["sale_price"] == 5600.0  # the last fresh comparables stay
    finally:
        sim("DELETE", "/_sim/faults", params={"system": "mkt"})
    assert run_sync("mkt", "manual")["status"] == "ok"
    with SessionLocal() as s:
        assert s.execute(text("SELECT status FROM source_system WHERE id = 'mkt'")).scalar_one() == "live"


def test_machinio_offer_fees_and_listings():
    first = sync_ok("dlr")
    m = canonical("market", "MTR-2041")
    d = m["data"]
    assert (d["dealer_offer"], d["dealer_offer_ref"], d["dealer_fees"], d["dealer_time_to_sell"]) == (
        5600.0,
        "MO-91048",
        800.0,
        12,
    )
    assert prov(m, "dealer_offer", "dlr") == ("offer_amount", 5600.0, "Currency")
    assert d["open_listings"] == 5 and isinstance(d["listing_time_to_sell"], int) and d["listing_grade"] == "B"
    assert d["dealer_fees_detail"]["freight_lanes"] == ["WH-PNQ-01>EXT-BOM"]
    assert_delta_quiet("dlr", first)


def test_sims_drop_verified_and_imported():
    out = sync_ok("rcy")
    v = canonical("vendor", "SIMS-MAA")
    d = v["data"]
    assert d["certification"] == "certified" and d["cert_valid_to"] == "2027-03-31"
    assert prov(v, "certification", "rcy") == ("VND_CERT", "ISO14001-VA", "Certificate table")
    cu = d["material_rates"]["Cu"]
    assert (cu["usd_per_t"], cu["label"]) == (7784, "Cu $7,800 / t") and d["rebates"]["Cu"] == 7784
    sf, sv, tr = prov(v, "material_rates", "rcy")
    assert sf == "RATE_TNE" and "Cu 7.8k" in sv and tr == "Unit + currency"
    assert d["yields"]["motor"]["Cu"] == 11.4 and d["fees"]["LiB"] > 0 and d["custody_certificates"]
    assert canonical("vendor", "VND-U")["data"]["certification"] == "lapsed"
    assert out["records_read"] == 3 + 3  # three vendors, plus rates, yields and custody of the approved one


class FakeClient:
    """Serves a recorded listing to the Sims reader (no HTTP)."""

    def __init__(self, body: dict):
        self.body = body

    def get_json(self, path, params=None):
        return self.body

    def url(self, path):
        return "http://sims.test/sims/outbound" + path

    def note_records(self, n):
        pass


def test_sims_hash_mismatch_is_a_failed_record_not_a_crash():
    body = sim("GET", "/sims/outbound", auth=("di-connector", "rcy-demo")).json()
    rates = next(f for f in body["files"] if f["fileName"] == "partner-rates.csv")
    rates["content"] = rates["content"].replace("650.00", "950.00")  # tampered after signing
    a = ADAPTERS["rcy"]
    records = list(a.read_files(FakeClient(body), None))
    bad = [r for r in records if "integrity_error" in r.payload]
    assert [r.ext_id for r in bad] == ["partner-rates.csv"] and "does not match the manifest" in bad[0].payload["integrity_error"]
    with pytest.raises(sims.IntegrityError):
        a.map(bad[0])
    good = [r for r in records if r not in bad]
    assert {r.resource for r in good} == {"vendor-approvals", "material-yields", "custody-certificates"}
    assert all(a.map(r) for r in good)
    # a manifest that does not verify fails every file
    manifest = next(f for f in body["files"] if f["fileName"] == "manifest.json")
    manifest["content"] = json.dumps(json.loads(manifest["content"]) | {"partner": "someone else"})
    assert all("integrity_error" in r.payload for r in a.read_files(FakeClient(body), None))
