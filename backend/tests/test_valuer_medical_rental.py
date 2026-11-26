"""Plan 9, P9-11.8 (story MR-08): the medical rental four-route valuer. Pure: facts and the pack in, `PathValue`s out; the
plug-in is the one `VALUERS` holds, which `decide_case` reads."""

from datetime import UTC, datetime

from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import VALUERS
from di.services.modeler.valuers import medical_rental as mr

AS_OF = datetime(2026, 3, 10, 12, tzinfo=UTC)
REQS = [
    {"req_id": "REQ-1", "hospital_id": "HOSP-1", "start_date": "2026-03-12", "days": 30, "distance_miles": 12},
    {"req_id": "REQ-2", "hospital_id": "HOSP-2", "start_date": "2026-03-12", "days": 30, "distance_miles": 5},
    {"req_id": "REQ-3", "hospital_id": "HOSP-3", "start_date": "2026-03-12", "days": 30, "distance_miles": 48},
]
S1 = {
    "cls": "infusion_pump", "age_years": 3, "book_value": 1150, "residual_sale_value": 1100, "repair_estimate": 0,
    "rentalRequests": REQS,
}  # fmt: skip


def by_k(facts, pack=None):
    return {v["k"]: v for v in mr.value_routes(facts, pack or load_pack("medical_rental"), AS_OF)}


def test_mr_08_four_routes_net():
    v = by_k(S1)
    assert [round(v[k]["net"], 2) for k in ("rerent:REQ-2", "rerent:REQ-1", "rerent:REQ-3")] == [498.00, 488.20, 437.80]
    assert round(v["service_rerent"]["net"], 2) == 232.00
    assert v["refurbish"]["ok"] is False and v["refurbish"]["why"] == "Not considered: device under 6 years"
    assert round(v["retire"]["net"], 2) == 170.00
    assert all(0 < x["dest"]["confidence"] <= 1 for x in v.values())
    assert v["rerent:REQ-2"]["dest"]["name"] == "Re-rent · HOSP-2" and v["rerent:REQ-2"]["dest"]["distance"] == 5
    assert list(v)[:3] == ["rerent:REQ-2", "rerent:REQ-1", "rerent:REQ-3"]


def test_mr_08_refurbish_for_old_device():  # MR-S7, the 7-year bed
    v = by_k({**S1, "cls": "electric_bed", "age_years": 7})
    assert v["refurbish"]["ok"] is True and round(v["refurbish"]["net"], 2) == 1450.00


def test_mr_08_params_from_pack():
    pack = load_pack("medical_rental")
    p = pack.model_copy(deep=True)
    p.valuer.params["params"]["transport_per_mile"] = 1.5
    assert round(by_k(S1, p)["rerent:REQ-2"]["net"], 2) == 497.50
    assert round(by_k(S1)["rerent:REQ-2"]["net"], 2) == 498.00  # the cached pack is untouched


def test_mr_08_least_travel_breaks_a_tie():
    reqs = [{**REQS[2], "req_id": "REQ-A", "distance_miles": 10}, {**REQS[2], "req_id": "REQ-B", "distance_miles": 10}]
    ks = list(by_k({**S1, "rentalRequests": reqs}))
    assert ks[:2] == ["rerent:REQ-A", "rerent:REQ-B"]  # equal net and travel: the request order


def test_mr_08_repair_estimate_replaces_pm_cost_and_no_request_is_not_ok():
    v = by_k({**S1, "repair_estimate": 400})
    assert round(v["service_rerent"]["net"], 2) == 540 - 7 - 35 - 400 - 36
    none = by_k({**S1, "rentalRequests": []})
    assert none["rerent"]["ok"] is False and none["service_rerent"]["ok"] is False


def test_mr_08_retire_reads_harvest_and_sanitisation():
    v = by_k({**S1, "cls": "patient_monitor", "harvest_values": [{"harvest_value": 900}, {"harvest_value": 400}]})
    assert round(v["retire"]["net"], 2) == 1300 + 260 - 1150 - 40 - 25


def test_mr_08_registered_as_plugin():
    assert VALUERS["medical_rental"] is mr.value_routes
