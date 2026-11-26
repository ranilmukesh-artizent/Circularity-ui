"""P9-12.10 (stories NS-B2C-01, NS-B2C-02): serialised retail returns. A returned phone with an IMEI is valued by the device
pack's valuer (the channel scores of `valuer.device`), an item without a serial is refused `not_serialised`, and an unsold jacket
cannot be destroyed (`exit` fails G-ESPR-1) unless the item names an allowed exception; `donate` and `recycle` stay open.
The ban is the EU Ecodesign regulation's (Regulation (EU) 2024/1781, large companies from 19 Jul 2026): the text is a research
summary and Kinective's Legal team must review it before it is relied on. Synthetic data; no retailer is named."""

import pytest

from di.services.actions.registry import ActionError
from di.services.cases import intake
from di.services.modeler.valuers import device
from tests import starting
from tests.b2c_serial_kit import IMEI, JACKET, PHONE, case, clean, open_item, publish_pack
from tests.device_registry import seed_registry

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

SALE = {"buynow", "offers", "auction", "market", "wholesale"}  # the pack's device_channels
BAN = "Destruction of unsold apparel and footwear is banned; reuse, donation or recycling first"


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    clean()
    publish_pack()
    yield
    clean()
    starting.reset()


def _route(c: dict, rid: str) -> dict:
    return next(r for r in c["routes"] if r["id"] == rid)


def test_ns_b2c_01_phone_valued_by_device_pack():
    seed_registry(IMEI)  # a clear registry check and a wipe certificate: the device gates pass
    c = case(open_item(dict(PHONE))["id"])
    lot = intake.device_lot("X", {k: v for k, v in PHONE.items() if v is not None})
    want = {x["k"]: x for x in device.decide(lot, [])["all"]}  # the device pack's valuation of the same facts
    assert {"buynow", "offers", "auction"} <= set(want)
    for k, x in want.items():
        if k not in SALE:
            continue  # the pack takes only its `device_channels` from the device valuer; see the recycle check below
        got = _route(c, k)
        assert not got["excluded"] and abs(got["net"] - x["score"]) < 0.005, (k, got["net"], x["score"])
    # Decision (27 Nov): `recycle` is the retail pack's own route (P9-12.10: device channels from the device valuer, `donate`,
    # `recycle`, `exit` from the pack's value lines). The device pack gained its own `recycle` (a certified recycler's material
    # value less its fee, P9-6.15), so `device.decide` now prices a route of the same id differently; the retail pack must not
    # follow it. Retail recycle = ref * recycle_share - recycle_cost = 300 * 0.03 - 2.
    assert "recycle" in want and abs(want["recycle"]["score"] - _route(c, "recycle")["net"]) > 0.005
    assert abs(_route(c, "recycle")["net"] - (PHONE["ref"] * 0.03 - 2)) < 0.005
    assert c["recommendation"] is not None and c["recommendation"]["id"] == device.decide(lot, [])["best"]["k"]
    assert {r["id"] for r in c["routes"]} == {"buynow", "offers", "auction", "market", "wholesale", "donate", "recycle", "exit"}
    assert c["valuer"]["imei"] == IMEI and c.get("gateHold") is None


def test_ns_b2c_01_item_without_a_serial_is_refused():
    facts = {k: v for k, v in PHONE.items() if k not in ("serial", "imei")}
    with pytest.raises(ActionError) as e:
        open_item(facts)
    assert e.value.code == "not_serialised"


def test_ns_b2c_02_apparel_exit_blocked():
    c = case(open_item(dict(JACKET))["id"])
    exit_ = _route(c, "exit")
    assert exit_["excluded"] and BAN in exit_["failReason"]
    for k in ("donate", "recycle"):
        assert not _route(c, k)["excluded"]
    assert c["recommendation"]["id"] in ("donate", "recycle")
    assert all(_route(c, k)["excluded"] for k in ("buynow", "offers", "auction", "market", "wholesale"))  # not a device


def test_ns_b2c_02_exception_evidence_lets_exit_pass_and_is_kept():
    evidence = {"exception": "safety", "ref": "EV-2026-0042"}
    c = case(open_item(JACKET | {"exceptionEvidence": evidence})["id"])
    assert not _route(c, "exit")["excluded"]
    assert c["valuer"]["exceptionEvidence"] == evidence  # the reference stays on the case


def test_ns_b2c_02_an_exception_not_allowed_does_not_pass():
    c = case(open_item(JACKET | {"exceptionEvidence": {"exception": "overstock", "ref": "EV-1"}})["id"])
    assert _route(c, "exit")["excluded"] and BAN in _route(c, "exit")["failReason"]


def test_ns_b2c_02_sold_footwear_may_exit():
    shoe = JACKET | {"itemClass": "footwear", "unsold": False, "sku": "SH-9-42", "serial": "SN-B2C-0003", "itemId": "RET-3"}
    assert not _route(case(open_item(shoe)["id"]), "exit")["excluded"]  # the ban is for unsold goods
