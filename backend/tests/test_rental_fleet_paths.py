"""P9-12.5 (R19 and R20, stories NS-RC-01 to NS-RC-03): the rental fleet pack's decision does not depend on the path.

`RF-S1` ... `RF-S8` (the pack's replay samples) are opened as cases from data (intake), valued again, run through the Modeler's
simulation, decided again (`decide_case`) and replayed: the same route and the same net, to the cent (R19). A business rule or
a diversion revives nothing a gate blocked (R20). Synthetic data.
"""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.core import clock, policy
from di.core.auth import load_context
from di.core.db import SessionLocal, engine
from di.repositories.flows import FlowRow
from di.repositories.live_rules import flow_version, live_pack
from di.services.actions.modeler_sim import template_decider
from di.services.actions.pipeline import Actor, CallContext
from di.services.canonical.schema import serial_key
from di.services.cases import intake
from di.services.cases import store as cases
from di.services.cases.decide import decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import Diversion
from tests import flowkit, starting
from tests.helpers import call
from tests.test_ns_rc_valuation import case_of

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG = "Customer A"
PACK_FILE = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "rental_fleet.json"
SAMPLES = [f"RF-S{n}" for n in range(1, 9)]


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        conn.execute(text("DELETE FROM pack_version"))


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK_FILE.read_text(encoding="utf-8")))
    doc["version"] = "1.9.6"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    yield
    _clean()
    flowkit.reset_flows()
    starting.reset()


def _get(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _open(sample: str) -> dict[str, Any]:
    facts = case_of(sample)
    body = {"org_unit_id": ORG, "template_key": "rental_fleet", "reason": "rental_return", "facts": facts,
            "asset_key": serial_key(ORG, facts["asset"]["machine_id"])}  # fmt: skip
    return _get(_ok(call("case.open", body, "planner-a"))["case_id"])


def _rec(c: dict[str, Any]) -> tuple[str | None, float]:
    r = c.get("recommendation")
    return (r["id"], r["net"]) if r else (None, 0.0)


def _simulated(c: dict[str, Any]) -> tuple[str | None, float]:
    f = FlowRow(0, "rental_fleet", ORG, "Off-rent machines", "pub", 1, None, None, None, None, {}, clock.now())
    with SessionLocal() as s:
        pctx = load_context(s)
        ctx = CallContext(actor=Actor(account=policy.account("planner-a", pctx), ctx=pctx), session=s)
        d = template_decider(ctx, f)(c, ())
    return d.best, d.net


def _replayed(c: dict[str, Any], pack, fv) -> tuple[str | None, float]:
    from di.repositories.replay import Batch
    from di.services.replay import run as replay_run

    when = max(clock.now(), datetime(2026, 12, 1, tzinfo=UTC))
    known = {**(c.get("valuer") or {})} | {k: c[k] for k in ("evidenceRecords",) if k in c}
    facts = {k: {"value": v, "at": when - timedelta(days=1)} for k, v in known.items()}
    it = {"item_id": f"T-RF-{c['id']}", "decided_at": when, "cls": None, "market": None, "actual_route": "retail",
          "realised_value": 1.0, "facts": facts}  # fmt: skip
    got: list = []

    def decide(*a, **k):
        got.append(decide_case(*a, **k))
        return got[-1]

    replay_run.replay(Batch(1, c["template"], ORG, 1, 0, None, {}), [it], fv, pack=pack, decide=decide)
    return got[0].route, got[0].net


@pytest.mark.parametrize("sample", SAMPLES)
def test_paths_agree_rental_fleet(sample: str):
    """Intake, re-evaluation, the simulation, `decide_case` and replay give one route and net for RF-S1 ... RF-S8."""
    c = _open(sample)
    seen = {"opened": _rec(c)}
    with SessionLocal() as s:
        c2 = cases.get(s, c["id"], for_update=True)
        assert c2 is not None
        intake.revalue(s, c2)
        cases.save(s, c2)
        s.commit()
    c2 = _get(c["id"])
    seen["reevaluated"] = _rec(c2)
    seen["simulation"] = _simulated(c2)
    with SessionLocal() as s:
        pack, fv = live_pack(s, c2), flow_version(s, c2)
        d = decide_case(c["id"], pack, fv, session=s)
        seen["decide_case"] = (d.route, d.net)
        seen["replay"] = _replayed(c2, pack, fv)
    assert len({p[0] for p in seen.values()}) == 1, seen
    nets = [p[1] for p in seen.values()]
    assert max(nets) - min(nets) < 0.005, seen


def test_paths_agree_rental_fleet_gives_the_expected_route():
    """So a path that agrees on nothing cannot pass: RF-S1 re-rents, net 27,600."""
    route, net = _rec(_open("RF-S1"))
    assert route == "rerent" and round(net, 2) == 27600.00


def test_order_invariant_rental_fleet():
    """R20: a rule that prefers re-rent and a shortcut to re-rent revive no route a gate blocked. RF-S4 is a scissor lift: its
    gate G-SAFE-1 names `rerent`, `transfer_branch`, `retail`, `auction` and `dealer`."""
    c = _open("RF-S4")
    shortcut = Diversion(op_id="DV-RF-RERENT", stage="decide", kind="shortcut", to="rerent",
                         when=[{"fact": "asset.branch", "op": "eq", "value": "BR-1"}])  # fmt: skip
    with SessionLocal() as s:
        stored = cases.get(s, c["id"])
        assert stored is not None
        pack = live_pack(s, stored).model_copy(update={"diversions": [shortcut]})
        flow = FlowVersion(None, 3, (CompiledRule("BR-RF-1", {}, "prefer", "rerent", "prefer re-rent"),))
        plain = decide_case(c["id"], live_pack(s, stored), FlowVersion(None, 3, ()), session=s)
        d = decide_case(c["id"], pack, flow, session=s)
    blocked = {r["id"] for r in plain.routes if r["excluded"]}
    assert {r["id"] for r in d.routes if r["excluded"]} >= blocked, [(r["id"], r["failReason"]) for r in d.routes]
    assert d.route not in blocked
