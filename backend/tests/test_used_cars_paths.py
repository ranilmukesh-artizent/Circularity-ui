"""Plan 9, P9-9.11 (R19 and R20, stories UC-11 and UC-12): the used-car pack's decision does not depend on the path.

`test_paths_agree_used_cars`: for UC-S1 to UC-S8 the car opened as a case (intake), re-evaluated (`case.reevaluate`), simulated
(the Modeler's queue under the published flow), decided again (`decide_case`), replayed (`replay` as of the case's date) and run
through the stage chain (`run_chain`, no model key) gets the same channel, or the same "held, no route", and the same net to the
cent. `test_order_invariant_used_cars`: gates, compliance guardrails, business rules and diversions, then valuation, then
ranking and the hold: no rule or shortcut revives a channel the title gate blocked; the 133,000-mile shortcut still runs the
title, odometer and recall gates first. Later used-car tasks extend these two tests when they add a path.
"""

from datetime import timedelta
from typing import Any

import pytest

from di.core import clock
from di.core.db import SessionLocal
from di.repositories.flows import FlowRow
from di.repositories.live_rules import flow_version, live_pack
from di.repositories.replay import Batch
from di.services.actions.modeler_sim import template_decider
from di.services.actions.pipeline import SYSTEM, CallContext
from di.services.agents import chain
from di.services.cases import car_facts, intake, store
from di.services.cases.decide import TRACE, Decision, decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import Diversion, Pack
from di.services.replay import run as replay_run
from tests import flowkit
from tests import ucfixtures as uc
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy


@pytest.fixture(autouse=True)
def fresh():
    uc.start()
    flowkit.reset_flows()
    yield
    uc.finish()
    flowkit.reset_flows()


def _flat(s, c: dict[str, Any]) -> dict[str, Any]:
    """The car's canonical facts as a history row carries them: dotted names, and the gate evidence the case holds."""
    facts = {f"{model}.{k}": v for model, data in car_facts.records(s, str(c["assetId"])).items() for k, v in data.items()}
    facts |= {
        k: c[k] for k in ("grade", "evidenceRecords", "odometer", "recall", "title", "vehicle", "assetId", "owner") if k in c
    }
    return facts


def _replayed(c: dict[str, Any]) -> tuple[str | None, float]:
    """The channel and net of a replay of the same facts, as of the same date, through the one decider."""
    when = clock.now()
    with SessionLocal() as s:
        facts = {k: {"value": v, "at": when - timedelta(days=1)} for k, v in _flat(s, c).items()}
        pack, fv = live_pack(s, c), flow_version(s, c)
    it = {"item_id": c["id"], "decided_at": when, "cls": None, "market": None, "actual_route": "auction", "realised_value": 1.0,
          "facts": facts}  # fmt: skip
    got: list[Decision] = []

    def decide(*a, **k) -> Decision:
        got.append(decide_case(*a, **k))
        return got[-1]

    replay_run.replay(Batch(1, c["template"], uc.ORG, 1, 0, None, {}), [it], fv, pack=pack, decide=decide)
    return got[0].route, got[0].net


def _replayed_history(c: dict[str, Any]) -> tuple[str | None, float]:
    """The same car replayed the way a history file carries it (P9-9.15): dotted scalar facts only, each dated the day before
    the decision, and the gates' evidence built from them by `car_facts.replay_case` (no `evidenceRecords`, `title`, `odometer`
    or `recall` given). No fact is from the future: the leakage list is empty."""
    when = clock.now()
    with SessionLocal() as s:
        recs = car_facts.records(s, str(c["assetId"]))
        pack, fv = live_pack(s, c), flow_version(s, c)
    facts = {f"{m}.{k}": {"value": v, "at": when - timedelta(days=1)} for m, data in recs.items() for k, v in data.items()}
    facts["market.salvage_buyer_reports"] = {"value": True, "at": when - timedelta(days=1)}  # a history row states it
    it = {"item_id": c["id"], "decided_at": when, "cls": None, "market": None, "actual_route": "auction", "realised_value": 1.0,
          "facts": facts}  # fmt: skip
    got: list[Decision] = []

    def decide(*a, **k) -> Decision:
        got.append(decide_case(*a, **k))
        return got[-1]

    report = replay_run.replay(Batch(1, c["template"], uc.ORG, 1, 0, None, {}), [it], fv, pack=pack, decide=decide)
    assert report.leakage == []
    return got[0].route, got[0].net


def _simulated(c: dict[str, Any]) -> tuple[str | None, float]:
    """What the Modeler's simulation decides the case as: `template_decider`, the decider `flow.simulate` and the queue run each
    live case through (no used-car flow is published yet, so no flow row: a flow of version 0 and no rules)."""
    with SessionLocal() as s:
        f = FlowRow(0, "used_cars", uc.ORG, "Used cars", "pub", 0, None, None, None, None, {}, clock.now())
        ctx = CallContext(actor=SYSTEM, session=s, run_id=None, now=clock.now())
        d = template_decider(ctx, f)(c, ())
    return d.best, d.net


def _chained(cid: str) -> tuple[str | None, float] | None:
    with SessionLocal() as s:
        run = chain.run_chain(s, cid, account="planner-a")
        s.commit()
    val = next((r.output["best"] for r in run.stages if r.stage == "valuation"), None)
    return (val["route"], val["net"]) if val else None


def _rec(c: dict[str, Any]) -> tuple[str | None, float]:
    r = c.get("recommendation")
    return (r["id"], r["net"]) if r else (None, 0.0)


@pytest.mark.parametrize("n", range(1, 9))
def test_paths_agree_used_cars(n: int):
    c = uc.open_car(n)
    seen = {"opened": _rec(c)}
    if c["recommendation"]:  # the decision goes back for another look
        assert call("decision.submit", {"case_id": c["id"]}, "planner-a")["ok"]
        assert call("decision.decline", {"case_id": c["id"], "reason": "Check again."}, "approver")["ok"]
        assert call("case.reevaluate", {"case_id": c["id"]}, "planner-a")["ok"]
        c = uc.get(c["id"])
    else:  # held for evidence: valued again, as a gate recheck does
        with SessionLocal() as s:
            cur = store.get(s, c["id"], for_update=True)
            assert cur is not None
            intake.revalue(s, cur)
            store.save(s, cur)
            s.commit()
        c = uc.get(c["id"])
    seen["reevaluated"] = _rec(c)
    seen["simulation"] = _simulated(c)
    with SessionLocal() as s:
        d = decide_case(c["id"], live_pack(s, c), flow_version(s, c), session=s)
    seen["decide_case"] = (d.route, d.net)
    seen["replay"] = _replayed(c)
    seen["replay_history"] = _replayed_history(c)  # the samples as a history file carries them (P9-9.15)
    if (chained := _chained(c["id"])) is not None:  # the chain stops before the valuation while a hold waits
        seen["run_chain"] = chained
    assert len({p[0] for p in seen.values()}) == 1, seen
    nets = [p[1] for p in seen.values()]
    assert max(nets) - min(nets) < 0.005, seen


def test_paths_agree_used_cars_gives_the_expected_channels():
    """The eight samples, so a path that agrees on nothing cannot pass: who is held, who is blocked from retail."""
    got = {n: _rec(uc.open_car(n)) for n in range(1, 9)}
    assert got[1] == ("retail:LOT-S", 21489.50) and got[3] == (None, 0.0) and got[4] == (None, 0.0)
    assert got[2][0] == "dealer_trade"  # an open recall blocks retail: the partner bid beats the auction
    assert got[5][0] == "retail:LOT-S" and got[6][0] == "retail:LOT-S"  # 133,000 miles and the EV: no shortcut in the pack
    assert got[7][0] == "dealer_trade"  # recon $2,800 takes retail below the partner bid, and the decision is held
    assert got[8] == ("salvage", 3720.0)  # recon $16,500: only the salvage bid is left worth more than retail


def _flow(*rules: CompiledRule) -> FlowVersion:
    return FlowVersion(None, 3, tuple(rules))


def _with_miles_shortcut(pack: Pack) -> Pack:
    d = Diversion(op_id="DV-UC-MILES", stage="condition", kind="shortcut", to="auction",
                  when=[{"fact": "asset.mileage_at_return", "op": "gte", "value": 120000}])  # fmt: skip
    return pack.model_copy(update={"diversions": [d]})


def _decide(cid: str, flow: FlowVersion) -> Decision:
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        return decide_case(cid, _with_miles_shortcut(live_pack(s, c)), flow, session=s)


PREFER_RETAIL = CompiledRule("BR-UC-1", {}, "require", "retail", "prefer retail")


def test_order_invariant_used_cars():
    c = uc.open_car(3)  # UC-S3: an open lien
    d = _decide(c["id"], _flow(PREFER_RETAIL))
    assert d.trace == TRACE  # gates, valuation, queue plan, rules, rank; the hold follows the gates, last
    assert [g.gate_id for g in d.gates if not g.passed] == ["G-VEH-TITLE"]
    assert all(r["excluded"] for r in d.routes) and d.recommendation is None and d.route is None
    assert d.rules_applied == [] and d.hold is not None and d.hold["gates"] == ["G-VEH-TITLE"]
    retail = [r for r in d.routes if r["id"].startswith("retail")]
    assert retail and all("Clear title" in r["failReason"] for r in retail)  # the first failed gate's reason stays

    # the shortcut cannot bring it back either: a lien car with 133,000 miles still goes nowhere
    lien = uc.open_car(15, like=5, lien=True)
    d = _decide(lien["id"], _flow(PREFER_RETAIL))
    assert d.diversions == ["DV-UC-MILES"] and d.preferred is None and d.route is None
    assert all(r["excluded"] for r in d.routes)


def test_order_invariant_used_cars_shortcut_runs_after_the_gates():
    c = uc.open_car(5)  # UC-S5: 133,000 miles, shortcut to the auction
    d = _decide(c["id"], _flow())
    ids = [g.gate_id for g in d.gates]
    assert [i for i in ids if i in ("G-VEH-TITLE", "G-VEH-ODO", "G-VEH-RECALL")] == ["G-VEH-TITLE", "G-VEH-ODO", "G-VEH-RECALL"]
    assert all(g.passed for g in d.gates)
    assert d.diversions == ["DV-UC-MILES"] and d.route == "auction" and d.preferred == "auction"
    recalled = uc.open_car(25, like=5, recall=True)  # an open recall blocks retail before the shortcut looks at the channels
    d = _decide(recalled["id"], _flow(PREFER_RETAIL))
    assert next(r for r in d.routes if r["id"] == "retail:LOT-S")["excluded"] and d.route == "auction"
    assert d.rules_applied == [] or all(not r["excluded"] for r in d.routes if r["id"] == "auction")


def _with_ev_step(pack: Pack) -> Pack:
    d = Diversion(op_id="DV-UC-EV", stage="condition", kind="step", step="battery_assessment", owner_role="inspection_lead",
                  when=[{"fact": "asset.powertrain", "op": "eq", "value": "ev"}])  # fmt: skip
    return pack.model_copy(update={"diversions": [d]})


def test_order_invariant_used_cars_assessment_sits_between_the_gates_and_valuation():
    """P9-9.14: with DV-UC-EV in force the gates of stages 2 and 3 run first, the assessment step is listed at the Condition
    stage, and no channel is valued until the assessment's result is on file."""
    c = uc.open_car(6)  # UC-S6: an EV
    with SessionLocal() as s:
        stored = store.get(s, c["id"])
        assert stored is not None
        d = decide_case(c["id"], _with_ev_step(live_pack(s, stored)), _flow(), session=s)
    assert d.trace == TRACE  # gates, valuation, queue plan, rules, rank
    assert [g.gate_id for g in d.gates][:3] == ["G-VEH-TITLE", "G-VEH-ODO", "G-VEH-RECALL"] and all(g.passed for g in d.gates)
    assert [(x["gate"], x["step"], x["stage"]) for x in d.required_steps] == [("DV-UC-EV", "battery_assessment", "condition")]
    assert d.diversions == ["DV-UC-EV"] and d.route is None and d.recommendation is None
    assert d.hold is not None and d.hold["gates"] == ["battery_assessment"]
    assert all(r["excluded"] for r in d.routes) and any("battery assessment" in r["failReason"] for r in d.routes)
    done = {"assessmentId": "BA-0001", "vin": uc.vin(6), "status": "complete", "batterySoh": 74,
            "result": "pack_replacement_needed"}  # fmt: skip
    uc.write("uc_insp", "battery_assessments", done | {"org_unit_id": uc.ORG})
    with SessionLocal() as s:
        stored = store.get(s, c["id"])
        assert stored is not None
        d = decide_case(c["id"], _with_ev_step(live_pack(s, stored)), _flow(), session=s)
    assert d.hold is None and d.recommendation is not None and any(not r["excluded"] for r in d.routes)  # priced on its own
