"""B5: values in the generic mocks for lease, plm, bom, qms, eng, esg and rcy that the demo shows (RT-1048 and the
MAPPINGS examples). The shared contract (paging, auth, filters, 404) is in test_generic_specs.py."""

import base64
import csv
import hashlib
import io

import pytest
from fastapi.testclient import TestClient

from sim.generic.spec import credentials
from sim.generic.specs import aras, assetwise, mastercontrol, oracle_lease, persefoni, sims, teamcenter
from sim.main import app
from sim.seed import seed


def by(items: list[dict], key: str, value) -> list[dict]:
    return [x for x in items if x.get(key) == value]


def test_lease_mapping_example():
    d = oracle_lease.SPEC.seed(seed())
    (c,) = by(d["leaseContracts"], "ASSET_NUMBER", "MTR-2041")
    assert c["LEASE_CONTRACT_ID"] == "LC-004417"
    assert (c["CONTRACT_END_DATE"], c["LESSEE_NAME"]) == ("2026-12-31", "CUSTOMER_A")
    assert (c["MONTHLY_RENTAL"], c["CURRENCY_CODE"]) == (2400.0, "USD")
    (r,) = by(d["leaseRenewals"], "ASSET_NUMBER", "MTR-2041")
    assert (r["LEASE_OPPORTUNITY_ID"], r["STATUS"], r["PROPOSED_TERM_MONTHS"]) == ("LS-5530", "FORECAST", 30)
    (a,) = by(d["leaseAssets"], "ASSET_NUMBER", "MTR-2077")  # conflict CF-31: lease says Customer A
    assert a["OWNER_NAME"] == "CUSTOMER_A"
    assert len(d["leaseRenewals"]) == sum(1 for c in seed().cases.values() if c.facts.demand.lease)


def test_teamcenter_mapping_example():
    d = teamcenter.SPEC.seed(seed())
    (cmp,) = by(d["compatibility"], "ASSET_ID", "MTR-2041")
    assert (cmp["ITEM_ID"], cmp["ALT_APPROVED"], cmp["COMPATIBILITY"]) == ("MTR-55-IE3-250M", "Y", "COMPATIBLE")
    (item,) = by(d["items"], "ITEM_ID", "MTR-55-IE3-250M")
    assert (item["OBJECT_NAME"], item["REV"], item["BOM_REF"]) == ("55 kW · IE3 · 250M", "C", "BOM-55-C")
    assert len(d["compatibility"]) == 128


def test_aras_mapping_example():
    d = aras.SPEC.seed(seed())
    (top,) = by(d["Part"], "item_number", "MTR-55-IE3-250M")
    lines = sorted(by(d["Part_BOM"], "source_id", top["id"]), key=lambda x: x["sort_order"])
    first = next(p for p in d["Part"] if p["id"] == lines[0]["related_id"])
    assert (first["item_number"], first["name"], first["state"]) == ("P-55-ROT-01", "Rotor assembly", "Released")
    assert lines[0]["quantity"] == 1
    bearings = next(p for p in d["Part"] if p["item_number"] == "P-55-BRG-01")
    kids = {x["related_item_number"] for x in by(d["Part_BOM"], "source_id", bearings["id"])}
    assert kids == {"SKF-6316-2Z/C3", "SKF-6314-2Z/C3", "VLT-SK-250M"}
    assert by(d["Manufacturer_Part"], "item_number", "6316-2Z/C3")[0]["manufacturer"] == "SKF"


def test_mastercontrol_certifies_rt_1048_for_24_months():
    d = mastercontrol.SPEC.seed(seed())
    (cert,) = by(d["certificates"], "ASSET_ID", "MTR-2041")
    assert (cert["CERT_NUMBER"], cert["CERTIFIED_LIFE_MONTHS"]) == ("QMS-2906", 24)
    assert (cert["CERT_EXPIRY"], cert["REUSE_CLASS"], cert["TEST_RESULT"]) == ("2027-03-01", "ALLOWED_CAT2", "PASS")
    assert by(d["certificates"], "ASSET_ID", "CTL-0122")[0]["ISSUE_DATE"] == "2026-09-12"  # conflict CF-32


def test_assetwise_mapping_example():
    d = assetwise.SPEC.seed(seed())
    (a,) = by(d["assessments"], "ASSET_ID", "MTR-2041")
    assert (a["RUL_MONTHS"], a["STANDARD_REF"], a["REQUAL_STATUS"]) == (36, "IEC 60034-1", "APPROVED")
    assert (a["RUL_LOW_MONTHS"], a["RUL_HIGH_MONTHS"]) == (30, 40)
    missing = [c for c in seed().cases.values() if any(e.k == "eng" and e.state == "missing" for e in c.facts.evidence)]
    assert len(d["assessments"]) == 128 - len(missing)


def test_persefoni_matches_the_decisions():
    s = seed()
    d = persefoni.SPEC.seed(s)
    fp = {x["id"]: x for x in d["footprints"]}
    for dec in s.decisions:
        assert fp[f"fp_{dec.id}"]["avoided_co2e_kg"] == dec.co2e
    rt = [x for x in d["footprints"] if x["activity_id"] == "RT-1048" and x["route"] == "redeploy"]
    assert rt[0]["avoided_co2e_kg"] == 294.0  # 420 kgCO2e x 0.7
    (motor,) = by(d["emission-factors"], "id", "ef_embodied_motor")
    assert (motor["factor_kgco2e"], motor["scope"]) == (420.0, "Cradle-to-gate")


def test_sims_files_are_signed():
    (rates,) = by(sims.SPEC.seed(seed())["files"], "fileName", "partner-rates.csv")
    assert hashlib.sha256(rates["content"].encode()).hexdigest() == rates["sha256"]
    cu = next(r for r in csv.DictReader(io.StringIO(rates["content"])) if r["MATERIAL"] == "Cu")
    assert (cu["VND_CERT"], cu["RATE_TNE"]) == ("ISO14001-VA", "Cu 7.8k")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_lease_over_http(client):
    spec = oracle_lease.SPEC
    tok = client.post(
        spec.base_path + "/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=("di-connector", credentials(spec)["client_secret"]),
    ).json()["access_token"]
    r = client.get(spec.base_path + "/leaseContracts/LC-004417", headers={"Authorization": "Bearer " + tok})
    assert r.status_code == 200 and r.json()["MONTHLY_RENTAL"] == 2400.0


def test_sims_over_http(client):
    c = credentials(sims.SPEC)
    h = {"Authorization": "Basic " + base64.b64encode(f"{c['user']}:{c['password']}".encode()).decode()}
    names = [f["fileName"] for f in client.get("/sims/outbound", headers=h).json()["files"]]
    assert "partner-rates.csv" in names and "manifest.json" in names
    assert client.get("/sims/outbound/partner-rates.csv", headers=h).json()["contentType"] == "text/csv"
