"""P9-12.10 (R19, R20; stories NS-B2C-01, NS-B2C-02): a `b2c_serial` case decided by intake, `case.reevaluate`, `decide_case` and
the stage chain gives the same route and the same net, to the cent; and the order is gates, valuation, business rules, ranking:
a rule never brings back a route a gate excluded. Every test ends with the starting state."""

import pytest

from di.core.db import SessionLocal
from di.repositories.live_rules import flow_version, live_pack
from di.services.agents import chain
from di.services.cases.decide import decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import load_pack
from tests import starting
from tests.b2c_serial_kit import IMEI, JACKET, PHONE, case, clean, open_item, publish_pack
from tests.device_registry import seed_registry
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    clean()
    publish_pack()
    yield
    clean()
    starting.reset()


def _agree(cid: str) -> None:
    c = case(cid)
    seen = {"opened": (c["recommendation"]["id"], c["recommendation"]["net"])}
    assert call("decision.submit", {"case_id": cid}, "planner-a")["ok"]
    assert call("decision.decline", {"case_id": cid, "reason": "Check again."}, "approver")["ok"]
    assert call("case.reevaluate", {"case_id": cid}, "planner-a")["ok"]
    c = case(cid)
    seen["reevaluated"] = (c["recommendation"]["id"], c["recommendation"]["net"])
    with SessionLocal() as s:
        d = decide_case(cid, live_pack(s, c), flow_version(s, c), session=s)
    seen["decide_case"] = (d.route, d.net)
    with SessionLocal() as s:
        run = chain.run_chain(s, cid, account="planner-a")
    val = next((r.output["best"] for r in run.stages if r.stage == "valuation"), None)
    if val:  # the chain may wait for a person before the valuation
        seen["run_chain"] = (val["route"], val["net"])
    assert len({p[0] for p in seen.values()}) == 1, seen
    nets = [p[1] for p in seen.values()]
    assert max(nets) - min(nets) < 0.005, seen


def test_paths_agree_b2c_serial_phone():
    seed_registry(IMEI)
    _agree(open_item(dict(PHONE))["id"])


def test_paths_agree_b2c_serial_apparel():
    _agree(open_item(dict(JACKET))["id"])


def _decide(facts: dict, *rules: CompiledRule):
    return decide_case({"id": "B2C-9001", "valuer": facts}, load_pack("b2c_serial"), FlowVersion(None, 3, tuple(rules)))


def test_order_invariant_b2c_serial():
    """A phone with a registry hit and no wipe certificate stays blocked: the rule `require buynow` never re-enables a channel."""
    facts = PHONE | {"inputs": {"registry": {"state": "hit", "status": "reported stolen", "hits": ["reported stolen"],
                                              "checked_at": "2026-11-20"},
                                "wipe": {"state": "none", "certificate": None}}}  # fmt: skip
    d = _decide(facts, CompiledRule("DR-9", {}, "require", "buynow", "send every device to Buy Now"))
    assert d.trace.index("gates") < d.trace.index("rules") < d.trace.index("rank")
    assert [g.gate_id for g in d.gates if not g.passed] == ["G-DEV-WIPE", "G-DEV-LOCK"]
    assert next(r for r in d.routes if r["id"] == "buynow")["excluded"]
    assert d.recommendation is None and d.route is None


def test_order_invariant_b2c_serial_rule_cannot_revive_exit():
    """An unsold jacket: a rule that requires `exit` leaves it blocked by G-ESPR-1."""
    d = _decide(JACKET, CompiledRule("DR-8", {}, "require", "exit", "destroy it"))
    exit_ = next(r for r in d.routes if r["id"] == "exit")
    assert exit_["excluded"] and "banned" in exit_["failReason"]
    assert [g.gate_id for g in d.gates if not g.passed] == ["G-ESPR-1"]
    assert d.route != "exit"
