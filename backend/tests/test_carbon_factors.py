"""P9-0.6: the carbon factor set and the CO2e line in both valuers (information only: no route or net changes).

P9-1.12: set cfs-2026.2 (the B 5.7 formula, provenance per factor); the expectations below moved with it.
"""

import pytest

from di.core import golden
from di.services.modeler.carbon import co2_avoided
from di.services.modeler.pack import load_pack
from di.services.modeler.templates import load_template
from di.services.modeler.valuers import device, tool_fleet
from di.services.modeler.valuers.routes_adapter import to_routes
from tests import starting
from tests.helpers import client, h

NET_TOL = 1e-6
CMH_RELEASE_CO2 = 61  # 62 x 1 - 0 - 1.5 = 60.5: the sample release lands on a confirmed lease order (30 without one)


def setup_module():
    starting.reset()


def _cmh_case():
    return next(c for c in tool_fleet.sample_queue() if c["cls"] == "CMH")


def test_tool_fleet_co2_line():
    v = tool_fleet.value(_cmh_case(), "release")
    assert v["co2"] == CMH_RELEASE_CO2
    assert v["co2Prov"]["set"] == "cfs-2026.2"
    assert v["co2Prov"]["label"] == "avoided, not inventory"


def test_device_co2_per_lot():
    lot = {**device.sample_lots()[0], "qty": 10}
    assert device.score(lot, "auction")["co2"] == 269  # (55 x 0.5 - 0.2 - 0.4) x 10
    assert device.score(lot, "auction")["co2Prov"]["set"] == "cfs-2026.2"


def test_no_factor_gives_none():
    tf = load_pack("tool_fleet")
    assert co2_avoided(tf, "ZZZ", "release", 1, confirmed=True) is None
    assert co2_avoided(tf, "CMH", "nowhere", 1, confirmed=True) is None


def test_co2_does_not_change_route_or_net():
    golden_tf = golden.load("po/equip_decisions")
    cases = {c["id"]: c for c in tool_fleet.sample_queue()}
    for want in golden_tf["decisions"]:
        got = tool_fleet.decide(cases[want["id"]], tool_fleet.BASEP, golden_tf["rules"])
        assert got["best"]["k"] == want["best"]["k"], want["id"]
        assert got["best"]["net"] == pytest.approx(want["best"]["net"], abs=NET_TOL), want["id"]
    golden_dv = golden.load("po/device_decisions")
    lots = {lot["id"]: lot for lot in device.sample_lots()}
    for want in golden_dv["decisions"]:
        best = device.decide(lots[want["id"]], golden_dv["rules"])["best"]
        assert best is not None
        assert best["k"] == want["best"]["k"], want["id"]
        assert best["score"] == pytest.approx(want["best"]["score"], abs=NET_TOL), want["id"]


def test_routes_carry_co2():
    t = load_template("tool_fleet")
    d = tool_fleet.decide(_cmh_case(), tool_fleet.BASEP, [])
    routes = {r["id"]: r for r in to_routes(t, d["all"])}
    assert routes["release"]["co2"] == CMH_RELEASE_CO2
    assert routes["release"]["co2Prov"]["set"] == "cfs-2026.2"


def test_industrial_co2_unchanged():
    want = golden.load("screens/case")["cases"]["RT-1048"]["analysis"]["ranking"]
    r = client.get("/api/screens/case/RT-1048/analysis", headers=h("admin"))
    assert r.status_code == 200, r.text
    got = r.json()["ranking"]
    assert [(x["route"], x["co2"]) for x in got] == [(x["route"], x["co2"]) for x in want]
    assert all("co2Src" not in x for x in got)


def test_same_inputs_same_co2():
    tf = load_pack("tool_fleet")
    dv = load_pack("device")
    assert co2_avoided(tf, "CMH", "release", 1, confirmed=True) == co2_avoided(tf, "CMH", "release", 1, confirmed=True)
    assert co2_avoided(dv, None, "auction", 10, confirmed=False) == co2_avoided(dv, None, "auction", 10, confirmed=False)
