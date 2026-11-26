"""Plan 9, P9-10.9 (story TN-11): the telecom valuer values all five routes of a decommissioned unit net of what each costs.

Sample TN-S1 (radio RRU-4410, new price 9,800, open demand SD-112 at a North site, North use probability 0.55, best broker bid
3,400, two boards needed for repairs worth 1,150 and 640, 14 kg) is valued on the inputs the mocks serve: the spares planning's
catalogue price and per-region use probability and six-month need (P9-10.4), the broker's bids (P9-10.5) and the bench's
weight. Every number is a parameter of the pack. Pure: no database, no source-sim.
"""

import copy
from typing import Any

from di.services.cases.decide import _valuer_kind, decide_case
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import Pack, load_pack
from di.services.modeler.valuers import VALUERS, telecom_network
from di.services.modeler.valuers.tool_fleet import PathValue

PACK = load_pack("telecom_network")
NEEDED = "A region needs this model within 6 months"


def facts_s1(**over: Any) -> dict[str, Any]:
    """TN-S1: an RRU-4410 in the US with an open site demand and a spares pool that North draws from."""
    f: dict[str, Any] = {
        "asset": {
            "class": "radio", "model": "RRU-4410", "firmware": "9.1", "region": "US", "spares_region": "North", "weight_kg": 14,
        },
        "market": {"new_price": 9800, "broker_bids": [
            {"bidId": "B-1", "unitPrice": 3100, "qty": 1}, {"bidId": "B-2", "unitPrice": 3400, "qty": 1},
        ]},
        "demand": {
            "open_site_demand": True, "id": "SD-112", "site": "SITE-N-014",
            "use_probability": {"North": 0.55, "South": 0.2}, "need_6m": {"North": 2, "South": 0},
            "board_needs": [{"part": "PSU-board", "value": 1150}, {"part": "RF-board", "value": 640}],
        },
    }  # fmt: skip
    return f | over


def by_id(values: list[PathValue]) -> dict[str, PathValue]:
    return {v["k"]: v for v in values}


def test_tn_11_five_routes_net():
    v = by_id(telecom_network.value_routes(facts_s1(), PACK, None))
    assert list(v) == ["redeploy", "spare", "resell", "harvest", "recycle"]
    assert (v["redeploy"]["ok"], v["redeploy"]["net"]) == (True, 9435.00)
    assert (v["spare"]["ok"], v["spare"]["net"]) == (True, 5078.00)
    assert (v["resell"]["ok"], v["resell"]["why"]) == (False, NEEDED)
    assert (v["harvest"]["ok"], v["harvest"]["net"]) == (True, 1650.00)
    assert (v["recycle"]["ok"], v["recycle"]["net"]) == (True, -49.80)


def test_tn_11_new_spend_avoided_is_the_value_line():
    v = by_id(telecom_network.value_routes(facts_s1(), PACK, None))
    for k, amt in (("redeploy", 9800), ("spare", 5390)):
        first = v[k]["lines"][0]
        assert (first["type"], first["label"], first["kind"], first["amt"]) == ("v", "New spend avoided", "purchase", amt)
    assert v["redeploy"]["dest"]["site"] == "SITE-N-014" and v["redeploy"]["dest"]["demand"] == "SD-112"


def test_tn_11_firmware_upgrade_cost_when_behind():
    f = facts_s1()
    f["asset"] |= {"firmware": "5.2"}
    f["demand"] |= {"firmware_min_major": 7}  # TN-S8: 5.2 for a demand needing 7
    r = by_id(telecom_network.value_routes(f, PACK, None))["redeploy"]
    assert ("Firmware upgrade", 140.0) in [(x["label"], x["amt"]) for x in r["lines"]]
    assert r["net"] == 9435.00 - 140
    f["demand"]["firmware_min_major"] = 6  # one major behind: below the pack's limit of two
    r = by_id(telecom_network.value_routes(f, PACK, None))["redeploy"]
    assert "Firmware upgrade" not in [x["label"] for x in r["lines"]] and r["net"] == 9435.00


def test_tn_11_line_kinds_and_types():
    v = by_id(telecom_network.value_routes(facts_s1(), PACK, None))
    kinds = {k: {x["kind"] for x in r["lines"]} for k, r in v.items()}
    assert kinds["redeploy"] == {"purchase", "prep", "fees"} and kinds["spare"] == {"purchase", "prep", "fees"}
    assert (kinds["resell"], kinds["harvest"], kinds["recycle"]) == ({"sale", "fees"}, {"parts", "prep"}, {"material", "fees"})
    assert [(x["label"], x["type"]) for x in v["spare"]["lines"]][-3:] == [
        ("Refurbishment", "c"),
        ("Holding as a spare", "h"),
        ("Logistics", "c"),
    ]
    assert v["spare"]["hold"] == 72 and v["spare"]["cost"] == 240


def test_tn_11_resell_value_is_the_best_bid_when_no_region_needs_the_model():
    f = facts_s1()
    f["demand"]["need_6m"] = {"North": 0, "South": 0}
    r = by_id(telecom_network.value_routes(f, PACK, None))["resell"]
    assert (r["ok"], r["gross"], r["net"]) == (True, 3400, 3400 - 272 - 60 - 150)
    assert [x["label"] for x in r["lines"]] == ["Best broker bid", "Broker fee", "Logistics", "Export compliance"]


def test_tn_11_missing_inputs_are_named_not_made_up():
    f = facts_s1()
    del f["market"]["new_price"], f["market"]["broker_bids"], f["demand"]["board_needs"], f["asset"]["weight_kg"]
    f["demand"]["open_site_demand"] = False
    del f["demand"]["use_probability"]
    v = by_id(telecom_network.value_routes(f, PACK, None))
    assert (v["redeploy"]["ok"], v["redeploy"]["why"]) == (False, "No open site demand")
    assert v["spare"]["ok"] is False and v["spare"]["misses"] == ["market.new_price", "demand.use_probability"]
    assert (v["resell"]["ok"], v["resell"]["misses"]) == (False, ["market.broker_bids"])
    assert (v["harvest"]["ok"], v["harvest"]["why"]) == (False, "No open repair need for a board")
    assert (v["recycle"]["ok"], v["recycle"]["misses"]) == (False, ["asset.weight_kg"])


def test_tn_11_redeploy_needs_a_named_demand_not_a_forecast():
    f = facts_s1()
    f["demand"]["open_site_demand"] = False
    r = by_id(telecom_network.value_routes(f, PACK, None))
    assert (r["redeploy"]["ok"], r["redeploy"]["why"], r["redeploy"]["lines"]) == (False, "No open site demand", [])
    assert r["spare"]["ok"]  # a spare is valued on the use forecast, with no named demand


def test_tn_11_params_come_from_pack():
    doc = copy.deepcopy(PACK.model_dump())
    doc["valuer"]["params"]["params"] |= {"spare_horizon_months": 6, "material_per_kg": 2}
    pack = Pack.model_validate(doc)
    v = by_id(telecom_network.value_routes(facts_s1(), pack, None))
    assert v["spare"]["net"] == 5078.00 + 36
    assert v["recycle"]["net"] == 28 - 15 - 60


def test_tn_11_flat_dotted_facts_read_like_nested():
    f = facts_s1()
    flat: dict[str, Any] = {}
    for group, rec in f.items():
        flat |= {f"{group}.{k}": x for k, x in rec.items()}
    assert telecom_network.value_routes(flat, PACK, None) == telecom_network.value_routes(f, PACK, None)


def test_tn_11_scalar_region_inputs_are_the_units_own_cell():
    f = facts_s1()
    f["demand"] |= {"use_probability": 0.55, "need_6m": 0}
    v = by_id(telecom_network.value_routes(f, PACK, None))
    assert v["spare"]["net"] == 5078.00 and v["resell"]["ok"]


def test_tn_11_registered_and_decide_case_values_the_five_routes():
    assert VALUERS["telecom_network"] is telecom_network.value_routes
    assert _valuer_kind(PACK) == "telecom_network"
    case = {"id": "TN-S1", "template": "telecom_network", "valuer": facts_s1(), "assetId": "asset.Customer A:SYNTN000000000001"}
    d = decide_case(case, PACK, FlowVersion(None, 0, ()))
    named = {r["id"]: r for r in d.routes}
    assert list(named) == ["redeploy", "spare", "resell", "harvest", "recycle"]
    assert (named["redeploy"]["net"], named["spare"]["net"], named["harvest"]["net"]) == (9435.0, 5078.0, 1650.0)
    assert named["resell"]["excluded"] and named["redeploy"]["dest"]["site"] == "SITE-N-014"
