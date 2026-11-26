"""P9-12.3 (R19 and R20, stories NS-IT-02, NS-IT-03): the ITAD pack's decision does not depend on the path.

`test_paths_agree_itad`: for IT-S1 to IT-S8 the case decided directly, decided with the facts in another order, and replayed as of
its date through the one decider get the same route (or none) and the same net. `test_order_invariant_itad`: gates first, then
valuation, then the rules and the rank; a business rule never revives a route the sanitisation gate blocked. Synthetic data."""

from datetime import timedelta

import pytest

from di.core import clock
from di.repositories.replay import Batch
from di.services.cases.decide import Decision, decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.replay import run as replay_run
from tests import itkit

ORDER = ("gates", "valuation", "queue_plan", "rules", "rank")
FV = FlowVersion(None, 1, ())


def _replayed(n: int) -> tuple[str | None, float]:
    when = clock.now()
    flat = itkit.facts(f"IT-S{n}")
    facts = {k: {"value": v, "at": when - timedelta(days=1)} for k, v in flat.items()}
    it = {"item_id": f"IT-S{n}", "decided_at": when, "cls": flat["asset.asset_class"], "market": None,
          "actual_route": "resell", "realised_value": 1.0, "facts": facts}  # fmt: skip
    got: list[Decision] = []

    def decide(*a, **k) -> Decision:
        got.append(decide_case(*a, **k))
        return got[-1]

    replay_run.replay(Batch(1, "itad", "Customer A", 1, 0, None, {}), [it], FV, pack=itkit.pack(), decide=decide)
    return got[0].route, got[0].net


@pytest.mark.parametrize("n", range(1, 9))
def test_paths_agree_itad(n: int):
    d = itkit.decide(itkit.case(f"IT-S{n}"))
    shuffled = dict(reversed(list(itkit.facts(f"IT-S{n}").items())))
    d2 = itkit.decide({"id": "X", **itkit.nest(shuffled)})
    seen = {"direct": (d.route, d.net), "reordered": (d2.route, d2.net), "replay": _replayed(n)}
    assert len({p[0] for p in seen.values()}) == 1, seen
    assert max(p[1] for p in seen.values()) - min(p[1] for p in seen.values()) < 0.005, seen


def test_paths_agree_itad_gives_the_expected_routes():
    assert itkit.decide(itkit.case("IT-S2")).route == "redeploy"  # cleared only: it may stay, not leave
    assert itkit.decide(itkit.case("IT-S1")).route is not None  # purged: every route is open


def test_order_invariant_itad():
    rule = CompiledRule("BR-9", {}, "require", "resell", "Resell everything")
    d = decide_case(itkit.case("IT-S2"), itkit.pack(), FlowVersion(None, 1, (rule,)))
    assert d.trace == ORDER
    assert next(g.gate_id for g in d.gates if not g.passed) == "G-DATA-1"  # the sanitisation gate speaks first
    resell = itkit.route(d, "resell")
    assert resell["excluded"] and "MS-S-1" in resell["failReason"]  # the rule never brings back what the gate excluded
    assert d.route != "resell"
