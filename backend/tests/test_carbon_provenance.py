"""P9-1.12 (X-12): CO2e avoided, shown with its provenance on every card. Avoided, not inventory (B 5.7).

Information only: no route, net or ranking changes. The demand rule gives d = 1 on a confirmed named order and the
pack's forecast otherwise; the rule for each segment is `valuer.carbon.d_rule`.
"""

from typing import Any

from di.services.modeler import carbon
from di.services.modeler.pack import Pack, load_pack
from di.services.modeler.valuers import device, medical_rental, telecom_network, tool_fleet, used_cars
from tests import test_valuer_medical_rental as mr_t
from tests import test_valuer_telecom_network as tn_t
from tests import test_valuer_used_cars as uc_t

LOT = {"id": "LOT-T", "brand": "Apple", "model": "iPhone 15", "band": "0-24m", "grade": "A", "ref": 470, "qty": 10, "doh": 5}


def _cmh() -> dict[str, Any]:
    return next(c for c in tool_fleet.sample_queue() if c["cls"] == "CMH")


def _dest_kind(case: dict[str, Any], path: str) -> str | None:
    dest = tool_fleet.value(case, path, queue=[case])["dest"]
    return dest["kind"] if dest else None


def _with_rule(rule: str, **params: float) -> Pack:
    pack = load_pack("tool_fleet")
    carbon_ref = pack.valuer.carbon.model_copy(update={"d_rule": rule})
    valuer = pack.valuer.model_copy(update={"carbon": carbon_ref, "params": {**pack.valuer.params, **params}})
    return pack.model_copy(update={"valuer": valuer})


def test_x_12_avoided_not_inventory_label():
    v = tool_fleet.value(_cmh(), "release")
    assert v["co2Prov"] is not None
    assert v["co2Prov"]["label"] == "avoided, not inventory"
    assert device.score(LOT, "auction")["co2Prov"]["label"] == "avoided, not inventory"


def test_x_12_factor_source_and_year_on_card():
    prov = tool_fleet.value(_cmh(), "release")["co2Prov"]
    assert prov["set"] == "cfs-2026.2"
    assert {f["name"] for f in prov["factors"]} >= {"e_new", "d", "e_prep", "e_log"}
    for f in prov["factors"]:
        assert f["source"], f
        assert f["year"] == 2026, f


def test_x_12_same_inputs_same_number():
    case = _cmh()
    queue = tool_fleet.sample_queue()
    first = tool_fleet.value(case, "release", queue=queue)
    again = tool_fleet.value(case, "release", queue=list(reversed(queue)))
    assert first["co2"] == again["co2"]
    assert first["co2Prov"] == again["co2Prov"]
    assert device.score(LOT, "auction") == device.score(LOT, "auction")


def test_x_12_d_from_demand_line():
    case = next(c for c in tool_fleet.sample_queue() if c["cls"] == "CMH" and _dest_kind(c, "release") == "lease")
    # 62 x 1 - 0 - 1.5 = 60.5, rounded as the demo rounds
    assert tool_fleet.value(case, "release", queue=[case])["co2"] == 61
    no_order = {**case, "dem": {**case["dem"], "lease": []}}
    # 62 x 0.5 - 0 - 1.5 = 29.5
    assert tool_fleet.value(no_order, "release", queue=[no_order])["co2"] == 30


def test_x_12_segment_d_rules():
    low = carbon.co2_avoided(_with_rule("low", d_low=0.1), "CMH", "release", 1, confirmed=True)
    assert low is not None and low.kg == 5  # 62 x 0.1 - 1.5 = 4.7
    transport = carbon.co2_avoided(_with_rule("transport_only"), "CMH", "release", 1, confirmed=True)
    assert transport is not None
    assert transport.kg is None  # no avoided figure
    assert transport.transport_kg == 1.5  # e_log x qty is shown
    assert carbon.co2_avoided(_with_rule("none"), "CMH", "release", 1, confirmed=True) is None


def test_x_12_no_provenance_no_figure():
    pack = load_pack("tool_fleet")
    assert carbon.co2_avoided(pack, "ZZZ", "release", 1, confirmed=True) is None
    assert carbon.co2_avoided(pack, "CMH", "nowhere", 1, confirmed=True) is None
    other_set = pack.valuer.carbon.model_copy(update={"set": "other"})
    other = pack.model_copy(update={"valuer": pack.valuer.model_copy(update={"carbon": other_set})})
    assert carbon.co2_avoided(other, "CMH", "release", 1, confirmed=True) is None


def test_x_12_three_packs_have_factor_source():
    """Used cars, telecom network and medical rental name cfs-2026.2: a case of each gets a factor source, not "no factor
    source on file" (carbon.json's sample factors; low demand, named demand and transport only respectively)."""
    uc = {v["k"]: v for v in used_cars.value_routes(uc_t.facts_s1(), load_pack("used_cars"), None)}
    assert uc["retail:LOT-S"]["co2"] == 175  # 7000 x carbon_d 0.05 - 150 - 25
    tn = {v["k"]: v for v in telecom_network.value_routes(tn_t.facts_s1(), load_pack("telecom_network"), None)}
    assert tn["redeploy"]["co2"] == 436  # radio 450 x 1 (named site demand) - 8 - 6
    mr = {v["k"]: v for v in medical_rental.value_routes(mr_t.S1, load_pack("medical_rental"), mr_t.AS_OF)}
    assert mr["rerent:REQ-2"]["co2"] is None  # transport only: a re-rent avoids nothing new
    assert mr["rerent:REQ-2"]["co2Prov"]["transportKg"] == 2.5
    for prov in (uc["retail:LOT-S"]["co2Prov"], tn["redeploy"]["co2Prov"], mr["rerent:REQ-2"]["co2Prov"]):
        assert prov["set"] == "cfs-2026.2"
        assert prov["factors"], prov
        assert all(f["source"] and f["year"] == 2026 for f in prov["factors"]), prov
