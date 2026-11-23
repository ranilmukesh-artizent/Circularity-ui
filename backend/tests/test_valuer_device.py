"""MVP-6.2: the device valuer is a port of the PO prototype's device recommerce engine (`dLots`, `dScore`, `dDecide`
and the device branch of `fSim`; docs/reference/po-modeler/recover-app-prototype.html, lines 2328-2352 and 2411-2413).
It must reproduce the goldens frontend/scripts/dump-po-golden.mjs wrote from the prototype (fixtures/golden/po)."""

import pytest

from di.core.golden import load
from di.services.modeler.valuers import device

TOL = 1e-6  # the goldens round numbers to 1e-6


def _same(got: dict, want: dict) -> None:
    assert (got["k"], got["ok"], got["why"]) == (want["k"], want["ok"], want["why"])
    for f in ("cash", "days", "score"):
        assert got[f] == pytest.approx(want[f], abs=TOL), (want["k"], f)


def test_sample_lots_match_golden():
    assert device.sample_lots() == load("po/device_lots")["lots"]


def test_live_rules_match_golden():
    assert load("po/device_decisions")["rules"] == device.LIVE_RULES


def test_device_decisions_match_golden():
    golden = load("po/device_decisions")
    lots = {lot["id"]: lot for lot in device.sample_lots()}
    assert [d["id"] for d in golden["decisions"]] == list(lots)
    for want in golden["decisions"]:
        lot = lots[want["id"]]
        for k, w in zip(device.DCH, want["channels"], strict=True):
            _same(device.score(lot, k), w)
        _same(device.decide(lot, golden["rules"])["best"], want["best"])


def test_device_sim_matches_golden():
    base = load("po/device_decisions")["rules"]
    for row in load("po/sim_cases")["device"]:
        r = row["rule"]
        cand = [*base, {"id": r["rid"], "scope": r["scope"], "action": r["action"], "path": r["path"]}]
        got = device.simulate(base, cand)
        want = row["sim"]
        assert (got["kind"], got["n"], got["u"], got["flips"]) == (want["kind"], want["n"], want["u"], want["flips"])
        for f in ("cash", "days", "dd", "dl", "dv"):
            assert got[f] == pytest.approx(want[f], abs=TOL), f


def test_require_rule_leaves_one_channel():
    lot = device.sample_lots()[0]
    d = device.decide(lot, [{"id": "DR-09", "scope": {}, "action": "require", "path": "auction"}])
    assert d["best"]["k"] == "auction"
    assert [v["k"] for v in d["all"] if v["ok"]] == ["auction"]


def test_rules_that_leave_nothing_are_waived():
    lot = device.sample_lots()[0]
    every = [{"id": f"X{i}", "scope": {}, "action": "exclude", "path": k} for i, k in enumerate(device.DCH)]
    assert device.decide(lot, every)["best"] == device.decide(lot, [])["best"]
