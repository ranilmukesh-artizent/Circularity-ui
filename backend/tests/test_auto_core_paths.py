"""Plan 9, P9-12.8 (R19 and R20, stories NS-CORE-01 and NS-CORE-03): the cores pack's decision does not depend on the path.

`test_paths_agree_auto_core`: for a full, a partial and a rejected core, the core opened as a case (intake), valued again
(`intake.revalue`), simulated (the Modeler's queue decider), decided again (`decide_case`), replayed (`replay` as of the case's
date) and run through the stage chain (`run_chain`, no model key) gets the same route and the same net to the cent.
`test_order_invariant_auto_core`: gates, then business rules, then valuation and ranking: a rule that requires remanufacturing
never revives it for a core the acceptance gate rejected, and the hold follows the gate. Later pack tasks extend these tests.
"""

import json
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from di.core import clock
from di.core.db import SessionLocal, engine
from di.repositories.flows import FlowRow
from di.repositories.live_rules import flow_version, live_pack
from di.repositories.replay import Batch
from di.services.actions.modeler_sim import template_decider
from di.services.actions.pipeline import SYSTEM, CallContext
from di.services.agents import chain
from di.services.cases import intake, store
from di.services.cases.decide import TRACE, Decision, decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import PACKS_DIR
from di.services.replay import run as replay_run
from tests import flowkit, starting
from tests.helpers import call
from tests.test_ns_core import CRACKED, FULL, PARTIAL, _core, _ok

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

ORG = "Customer A"


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
    doc = json.loads((PACKS_DIR / "auto_core.json").read_text(encoding="utf-8"))
    doc["version"] = "1.9.3"  # the shipped pack, imported and published as the org's
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    yield
    starting.reset()
    flowkit.reset_flows()


def _open(core: dict) -> dict[str, Any]:
    body = {"org_unit_id": ORG, "template_key": "auto_core", "asset_key": f"PC-{core['coreId']}", "reason": "manual",
            "facts": {"family": "alternator", "deposit": 85}}  # fmt: skip
    cid = _ok(call("case.open", body, "planner-a"))["case_id"]
    with SessionLocal() as s:  # the core record the adapter writes (the gate reads it from the case), then valued as it is
        cur = store.get(s, cid, for_update=True)
        assert cur is not None
        cur["core"] = core
        intake.revalue(s, cur)
        store.save(s, cur)
        s.commit()
    return _get(cid)


def _get(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _rec(c: dict[str, Any]) -> tuple[str | None, float]:
    r = c.get("recommendation")
    return (r["id"], r["net"]) if r else (None, 0.0)


def _replayed(c: dict[str, Any]) -> tuple[str | None, float]:
    when = clock.now()
    known = {k: c["valuer"][k] for k in ("family", "deposit")} | {"core": c["core"]}  # the facts a history row would carry
    facts = {k: {"value": v, "at": when - timedelta(days=1)} for k, v in known.items()}
    with SessionLocal() as s:
        pack, fv = live_pack(s, c), flow_version(s, c)
    it = {"item_id": c["id"], "decided_at": when, "cls": None, "market": None, "actual_route": "scrap", "realised_value": 1.0,
          "facts": facts}  # fmt: skip
    got: list[Decision] = []

    def decide(*a, **k) -> Decision:
        got.append(decide_case(*a, **k))
        return got[-1]

    replay_run.replay(Batch(1, c["template"], ORG, 1, 0, None, {}), [it], fv, pack=pack, decide=decide)
    return got[0].route, got[0].net


def _simulated(c: dict[str, Any]) -> tuple[str | None, float]:
    with SessionLocal() as s:
        f = FlowRow(0, "auto_core", ORG, "Cores", "pub", 0, None, None, None, None, {}, clock.now())
        ctx = CallContext(actor=SYSTEM, session=s, run_id=None, now=clock.now())
        d = template_decider(ctx, f)(c, ())
    return d.best, d.net


def _chained(cid: str) -> tuple[str | None, float] | None:
    with SessionLocal() as s:
        run = chain.run_chain(s, cid, account="planner-a")
        s.commit()
    val = next((r.output["best"] for r in run.stages if r.stage == "valuation"), None)
    return (val["route"], val["net"]) if val else None


@pytest.mark.parametrize(("core", "route"), [(FULL, "reman"), (PARTIAL, "reman"), (CRACKED, "harvest")])
def test_paths_agree_auto_core(core: dict, route: str):
    c = _open(core)
    seen = {"opened": _rec(c)}
    with SessionLocal() as s:
        cur = store.get(s, c["id"], for_update=True)
        assert cur is not None
        intake.revalue(s, cur)
        store.save(s, cur)
        s.commit()
    c = _get(c["id"])
    seen["reevaluated"] = _rec(c)
    seen["simulation"] = _simulated(c)
    with SessionLocal() as s:
        d = decide_case(c["id"], live_pack(s, c), flow_version(s, c), session=s)
    seen["decide_case"] = (d.route, d.net)
    seen["replay"] = _replayed(c)
    if (chained := _chained(c["id"])) is not None:  # the chain stops before the valuation while a hold waits
        seen["run_chain"] = chained
    assert not (off := {k: v for k, v in seen.items() if v[0] != route}), off
    nets = [p[1] for p in seen.values()]
    assert max(nets) - min(nets) < 0.005, seen


def test_order_invariant_auto_core():
    c = _open(CRACKED)
    with SessionLocal() as s:
        stored = store.get(s, c["id"])
        assert stored is not None
        require_reman = CompiledRule("BR-CORE-1", {}, "require", "reman", "always remanufacture")
        d = decide_case(c["id"], live_pack(s, stored), FlowVersion(None, 3, (require_reman,)), session=s)
    assert d.trace == TRACE  # gates, valuation, queue plan, rules, rank
    assert [g.gate_id for g in d.gates if not g.passed] == ["CORE-ACCEPT"]
    reman = next(r for r in d.routes if r["id"] == "reman")
    assert reman["excluded"] and "no_cracks" in reman["failReason"]  # the gate's reason stays
    assert d.rules_applied == [] and d.route == "harvest"  # the rule never brings the rejected route back
    full = _open(_core("C-0010"))
    with SessionLocal() as s:
        stored = store.get(s, full["id"])
        assert stored is not None
        d = decide_case(full["id"], live_pack(s, stored), FlowVersion(None, 3, (require_reman,)), session=s)
    assert d.route == "reman" and d.rules_applied == ["BR-CORE-1"]
