"""P9-0.6: the carbon factor set and the CO2e line in both valuers (information only: no route or net changes)."""

import pytest

from di.core import golden
from di.services.modeler.carbon import co2_avoided
from di.services.modeler.templates import load_template
from di.services.modeler.valuers import device, tool_fleet
from di.services.modeler.valuers.routes_adapter import to_routes
from tests import starting
from tests.helpers import client, h

NET_TOL = 1e-6


def setup_module():
    starting.reset()


def _cmh_case():
    return next(c for c in tool_fleet.sample_queue() if c["cls"] == "CMH")


def test_tool_fleet_co2_line():
    v = tool_fleet.value(_cmh_case(), "release")
    assert v["co2"] == 43  # 62 x 0.7 = 43.4
    assert v["co2Src"].startswith("cfs-2026.1")
    assert v["co2Src"] == "cfs-2026.1 · Sample value (synthetic), 2026"


def test_device_co2_per_lot():
    lot = {**device.sample_lots()[0], "qty": 10}
    assert device.score(lot, "auction")["co2"] == 275  # 55 x 0.5 x 10
    assert device.score(lot, "auction")["co2Src"].startswith("cfs-2026.1")


def test_no_factor_gives_none():
    assert co2_avoided("tool_fleet", "ZZZ", "release", 1) is None
    assert co2_avoided("tool_fleet", "CMH", "nowhere", 1) is None
    assert co2_avoided("no_such_pack", None, "release", 1) is None


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
    assert routes["release"]["co2"] == 43
    assert routes["release"]["co2Src"].startswith("cfs-2026.1")


def test_industrial_co2_unchanged():
    want = golden.load("screens/case")["cases"]["RT-1048"]["analysis"]["ranking"]
    r = client.get("/api/screens/case/RT-1048/analysis", headers=h("admin"))
    assert r.status_code == 200, r.text
    got = r.json()["ranking"]
    assert [(x["route"], x["co2"]) for x in got] == [(x["route"], x["co2"]) for x in want]
    assert all("co2Src" not in x for x in got)


def test_same_inputs_same_co2():
    assert co2_avoided("tool_fleet", "CMH", "release", 1) == co2_avoided("tool_fleet", "CMH", "release", 1)
    assert co2_avoided("device", None, "auction", 10) == co2_avoided("device", None, "auction", 10)
