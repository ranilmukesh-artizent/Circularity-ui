"""P9-12.6 (stories NS-CPE-01, NS-CPE-02, NS-CPE-03): telecom CPE lots, a decision per lot of one model and grade.

The lot is the case. Its device lines come from the records the mock `cpe_bss` serves (built here as literals) read through the
real adapter. NS-CPE-01: a lot under the standing policy's limit is approved by the policy, a larger one waits for a person.
NS-CPE-02: a line with no factory-reset record is held and the rest are released; a record that arrives releases its line on
its own. NS-CPE-03: the redeploy route's carbon is "avoided, not inventory" with the factor set and each factor's source and
year. Synthetic data; the carbon factors are placeholders. Kinective's Legal team reviews the gates (G-DATA-1, G-DS-1, G-WEEE-2)
before they are relied on.
"""

import pytest
from sqlalchemy import text

from di import worker
from di.core import state
from di.core.db import SessionLocal
from di.services.modeler import carbon
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import standard
from tests import cpefixtures as cpe
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy
POLICY = {"max_value": 20000, "min_confidence": 0.75, "routes": ["refurbish_redeploy"]}  # "lots under $20,000"


@pytest.fixture(autouse=True)
def fresh():
    cpe.start()
    yield
    cpe.finish()


def _activate(owner: str = "admin") -> str:
    body = {"pack": "telecom_cpe", "org_unit_id": cpe.ORG, "name": "Lots under $20,000", "rules": POLICY, "owner": owner}
    pid = cpe.ok(call("standingPolicy.save", body, "admin"))["id"]
    cpe.ok(call("standingPolicy.submit", {"id": pid}, "admin"))
    cpe.ok(call("standingPolicy.approve", {"id": pid}, "approver"))
    return pid


def _policy_log() -> list[str]:
    with SessionLocal() as s:
        return [e["note"] for e in state.items(s, "events") if e.get("type") == "decision.approved.policy"]


def test_ns_cpe_01_lot_approved_by_policy():
    pid = _activate()
    cpe.sync_lot("LOT-R7-B-W47")
    small = cpe.open_lot("LOT-R7-B-W47")
    assert cpe.route(small, "refurbish_redeploy")["net"] == 15500.0 and small["recommendation"]["id"] == "refurbish_redeploy"
    cpe.ok(call("decision.submit", {"case_id": small["id"]}, "admin"))
    after = cpe.get(small["id"])
    assert after["stage"] == "approved" and after["approval"]["by"] == f"policy {pid} v1"
    assert _policy_log() == [f"Approved by policy {pid} v1, owner admin"]

    cpe.sync_lot("LOT-R7-B-W48")
    big = cpe.open_lot("LOT-R7-B-W48")
    assert cpe.route(big, "refurbish_redeploy")["net"] == 27900.0
    cpe.ok(call("decision.submit", {"case_id": big["id"]}, "admin"))
    held = cpe.get(big["id"])
    assert held["stage"] == "awaiting_approval" and held.get("submitted") and not held.get("approval")
    assert len(_policy_log()) == 1  # still only the small lot


def test_ns_cpe_02_reset_record_per_serial():
    serials = cpe.sync_lot("LOT-R7-B-W47-GAP")
    c = cpe.open_lot("LOT-R7-B-W47-GAP")
    lot = c["lot"]
    assert (lot["qty"], lot["released"], lot["held"]) == (500, 497, 3)
    assert [x["serial"] for x in lot["lines"] if x["status"] == "held"] == [cpe.serial(n) for n in (3101, 3202, 3303)]
    assert len(lot["lines"]) == 500 and {x["serial"] for x in lot["lines"]} == set(serials)
    assert cpe.route(c, "refurbish_redeploy")["net"] == 15407.0  # 497 released units at 31

    cpe.add_reset(3202)  # the record arrives: the line releases on its own, the lot is valued again
    with SessionLocal() as s:
        queued = s.execute(
            text("SELECT count(*) FROM job WHERE kind = 'case.gateRecheck' AND payload->>'asset_key' = :k"),
            {"k": cpe.lot_key("LOT-R7-B-W47-GAP")},
        ).scalar_one()
    assert queued == 1
    worker.HANDLERS["case.gateRecheck"]({"asset_key": cpe.lot_key("LOT-R7-B-W47-GAP")})
    after = cpe.get(c["id"])
    assert (after["lot"]["released"], after["lot"]["held"]) == (498, 2)
    assert cpe.route(after, "refurbish_redeploy")["net"] == 15438.0


def test_ns_cpe_03_carbon_with_provenance():
    cpe.sync_lot("LOT-R7-B-W47")
    c = cpe.open_lot("LOT-R7-B-W47")
    r = cpe.route(c, "refurbish_redeploy")
    prov = r["co2Prov"]
    assert prov["set"] == "cpe_gsma_2025" and prov["label"] == "avoided, not inventory"
    names = {f["name"]: f for f in prov["factors"]}
    assert set(names) == {"e_new", "d", "e_prep", "e_log"} and names["d"]["value"] == 1  # against the new-subscriber forecast
    assert all(f["source"].startswith("Synthetic placeholder") and f["year"] == 2025 for f in prov["factors"])
    assert r["co2"] == 37250  # (80 x 1 - 4 - 1.5) x 500
    pack = load_pack("telecom_cpe")
    again = standard.value_routes(c, pack)
    assert next(v for v in again if v["k"] == "refurbish_redeploy")["co2"] == r["co2"]  # the same inputs, the same number
    assert carbon.co2_avoided(pack, "x", "broker", 500, confirmed=False) is None  # a factor-less route shows no figure
