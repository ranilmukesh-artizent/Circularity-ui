"""MVP-2.7: simulating a candidate rule set against the published one on a queue (Domain spec D9; the prototype's
fSim). The golden comparison waits for the valuers (MVP-6.1/6.2 add `test_sim_matches_golden`)."""

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from di.services.modeler.compile import CompiledRule
from di.services.modeler.simulate import Decision, Flip, SimResult, simulate
from di.services.modeler.templates import load_template

NO_RESELL = [CompiledRule("BR-09", {}, "exclude", "resell", "every return: never pre-owned sale")]
VALUES = {"A": {"resell": 100.0, "refurb": 80.0}, "B": {"harvest": 50.0, "resell": 40.0}}


def _stub(c: Mapping[str, Any], rules: Sequence[CompiledRule]) -> Decision:
    """Best path by value, minus excluded paths; a rule set also adds 5 to every candidate net of case B."""
    banned = {r.path for r in rules if r.action == "exclude"}
    options = {k: v + (5 if rules and c["id"] == "B" else 0) for k, v in VALUES[c["id"]].items() if k not in banned}
    best = max(options, key=lambda k: options[k])
    return Decision(best, options[best], {"days": 10.0 if best == "resell" else 30.0})


@pytest.mark.parametrize("key", ["tool_fleet", "industrial"])
def test_simulate_with_stub_decider(key):
    out = simulate(load_template(key), [], NO_RESELL, [{"id": "A"}, {"id": "B"}], _stub)
    assert out == SimResult("equip", 2, [Flip("A", "resell", "refurb", -20.0)], -15.0, {})


def test_simulate_device_extras():
    lots = [{"id": "A", "qty": 10, "doh": 40}, {"id": "B", "qty": 30, "doh": 5}]
    out = simulate(load_template("device"), [], NO_RESELL, lots, _stub)
    assert (out.kind, out.n, out.flips) == ("device", 2, [Flip("A", "resell", "refurb", -200.0)])
    assert out.dv == pytest.approx(10 * (80 - 100) + 30 * (55 - 50))
    assert out.extra == pytest.approx({
        "u": 40, "cash": 10 * 80 + 30 * 55, "days": 30.0, "dd": 30.0 - (10 * 10 + 30 * 30) / 40, "dl": 10 - 0,
    })  # fmt: skip


# ---------------------------------------------------------------- P9-8.15: per-node counts of a simulation
def test_per_node_counts_by_rule_scope():
    from di.services.modeler.flow import default_flow, fe, fn
    from di.services.modeler.per_node import per_node

    t = load_template("tool_fleet")
    g = default_flow(t)
    gate = next(n["id"] for n in g["nodes"] if n["t"] == "gate")
    dec = next(n["id"] for n in g["nodes"] if n["t"] == "decision")
    g["nodes"].append(fn("r-X", "rule", 320, 200, "", "", rid="X", action="exclude", path="resell", scope={"grade": ["C"]}))
    g["edges"] += [fe(gate, "r-X"), fe("r-X", dec)]
    queue = [{"id": f"Q{i}", "grade": gr} for i, gr in enumerate("ABCCD")]
    out = per_node(t, g, queue)
    assert out["r-X"] == {"in": 5, "out": 3, "examples": ["Q2", "Q3"]}
    assert out[dec] == {"in": 5, "out": 5, "examples": ["Q0", "Q1", "Q2"]}
