"""Plan 9, P9-12.6 (R19 and R20; stories NS-CPE-01 and NS-CPE-02): a telecom CPE lot's decision does not depend on the path.

`test_paths_agree_telecom_cpe`: for each sample lot (the lot is the case) the lot opened as a case, valued again (the gate
re-check's path), decided again (`decide_case`) and simulated (the Modeler's `template_decider`) gets the same route and the same
net to the cent. `test_order_invariant_telecom_cpe`: valuation, then the business rules, then the ranking: a rule that prefers a
route changes the route and never a net. The history replay of a lot is not part of this test (no history file for CPE yet).
"""

from typing import Any

import pytest

from di.core import clock
from di.core.db import SessionLocal
from di.repositories.flows import FlowRow
from di.repositories.live_rules import flow_version, live_pack
from di.services.actions.modeler_sim import template_decider
from di.services.actions.pipeline import SYSTEM, CallContext
from di.services.cases import intake, store
from di.services.cases.decide import TRACE, Decision, decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from tests import cpefixtures as cpe
from tests import flowkit

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")


@pytest.fixture(autouse=True)
def fresh():
    cpe.start()
    flowkit.reset_flows()
    yield
    cpe.finish()
    flowkit.reset_flows()


def _rec(c: dict[str, Any]) -> tuple[str | None, float]:
    r = c.get("recommendation")
    return (r["id"], r["net"]) if r else (None, 0.0)


def _simulated(c: dict[str, Any]) -> tuple[str | None, float]:
    with SessionLocal() as s:
        f = FlowRow(0, "telecom_cpe", cpe.ORG, "Telecom CPE", "pub", 0, None, None, None, None, {}, clock.now())
        ctx = CallContext(actor=SYSTEM, session=s, run_id=None, now=clock.now())
        d = template_decider(ctx, f)(c, ())
    return d.best, d.net


@pytest.mark.parametrize("lot_id", list(cpe.LOTS))
def test_paths_agree_telecom_cpe(lot_id: str):
    cpe.sync_lot(lot_id)
    c = cpe.open_lot(lot_id)
    seen = {"opened": _rec(c)}
    with SessionLocal() as s:
        cur = store.get(s, c["id"], for_update=True)
        assert cur is not None
        intake.revalue(s, cur)
        store.save(s, cur)
        s.commit()
    c = cpe.get(c["id"])
    seen["revalued"] = _rec(c)
    with SessionLocal() as s:
        d = decide_case(c["id"], live_pack(s, c), flow_version(s, c), session=s)
    seen["decide_case"] = (d.route, d.net)
    seen["simulation"] = _simulated(c)
    assert len({p[0] for p in seen.values()}) == 1, seen
    assert max(p[1] for p in seen.values()) - min(p[1] for p in seen.values()) < 0.005, seen


def test_paths_agree_telecom_cpe_gives_the_expected_routes():
    """The sample lots, so a path that agrees on nothing cannot pass: redeploy wins at 31 a unit on the released units."""
    got = {}
    for lot_id in cpe.LOTS:
        cpe.sync_lot(lot_id)
        got[lot_id] = _rec(cpe.open_lot(lot_id))
    assert got["LOT-R7-B-W47"] == ("refurbish_redeploy", 15500.0) and got["LOT-R7-B-W48"] == ("refurbish_redeploy", 27900.0)
    assert got["LOT-R7-B-W47-GAP"] == ("refurbish_redeploy", 15407.0)  # three units have no reset record yet
    assert got["LOT-R7-C-W47"][0] == "refurbish_redeploy"


def test_order_invariant_telecom_cpe():
    cpe.sync_lot("LOT-R7-B-W47")
    c = cpe.open_lot("LOT-R7-B-W47")
    with SessionLocal() as s:
        pack, plain = live_pack(s, c), decide_case(c["id"], live_pack(s, c), FlowVersion(None, 3, ()), session=s)
        rule = CompiledRule("BR-CPE-1", {}, "require", "broker", "prefer the broker")
        d: Decision = decide_case(c["id"], pack, FlowVersion(None, 3, (rule,)), session=s)
    assert d.trace == TRACE  # gates, valuation, rules, rank
    assert plain.route == "refurbish_redeploy" and d.route == "broker" and d.rules_applied == ["BR-CPE-1"]
    nets = {r["id"]: r["net"] for r in d.routes}
    assert nets == {r["id"]: r["net"] for r in plain.routes}  # a rule moves the choice, never a net
