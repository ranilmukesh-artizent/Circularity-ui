"""P9-12.7 (R19, R20; stories NS-BAT-01 to NS-BAT-03): the battery pack's decision does not depend on the path. A pack opened as
a case (intake), valued again (`intake.revalue`), decided again (`decide_case`) and simulated (the Modeler's template decider
under the published rules) gets the same route and the same net to the cent. No rule or diversion revives a route a gate
refused. Legal: the gates' wording needs review by Kinective's Legal team before it is relied on.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.core import clock
from di.core.db import SessionLocal, engine
from di.repositories.flows import FlowRow
from di.repositories.live_rules import flow_version, live_pack
from di.services.actions.modeler_sim import template_decider
from di.services.actions.pipeline import SYSTEM, CallContext
from di.services.canonical.schema import serial_key
from di.services.cases import intake
from di.services.cases import store as cases
from di.services.cases.decide import decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from tests import flowkit, starting
from tests.helpers import call

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "battery.json"
SCENARIOS: dict[str, dict[str, Any]] = {
    "BAT-S1": {"soh_pct": 86, "market": "US"},  # a healthy pack
    "BAT-S2": {"soh_pct": 66, "market": "US"},  # second life
    "BAT-S3": {"soh_pct": 74, "market": "US", "damaged": True},  # damaged: recycle only
    "BAT-S4": {"soh_pct": None, "read_at": None, "market": "US"},  # no BMS reading: recycle only
}


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.5"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
    flowkit.reset_flows()
    starting.reset()


def _open(n: int, over: dict[str, Any]) -> dict[str, Any]:
    facts = {"packId": f"BP-90{n}", "chemistry": "NMC", "soh_pct": 80, "expected_life_years": 6, "read_at": "2026-11-10",
             "market": "US"} | over  # fmt: skip
    body = {"org_unit_id": ORG, "template_key": "battery", "asset_key": serial_key(ORG, f"BP-90{n}"),
            "reason": "pack_replacement", "facts": facts}  # fmt: skip
    cid = _ok(call("case.open", body, "planner-a"))["case_id"]
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _rec(c: dict[str, Any]) -> tuple[str | None, float]:
    r = c.get("recommendation")
    return (r["id"], r["net"]) if r else (None, 0.0)


def _simulated(c: dict[str, Any]) -> tuple[str | None, float]:
    with SessionLocal() as s:
        f = FlowRow(0, "battery", ORG, "Battery packs", "pub", 0, None, None, None, None, {}, clock.now())
        ctx = CallContext(actor=SYSTEM, session=s, run_id=None, now=clock.now())
        d = template_decider(ctx, f)(c, ())
    return d.best, d.net


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_paths_agree_battery(scenario: str):
    n = int(scenario[-1])
    c = _open(n, SCENARIOS[scenario])
    seen = {"opened": _rec(c)}
    with SessionLocal() as s:
        cur = cases.get(s, c["id"], for_update=True)
        assert cur is not None
        intake.revalue(s, cur)
        cases.save(s, cur)
        s.commit()
        seen["reevaluated"] = _rec(cur)
        d = decide_case(c["id"], live_pack(s, cur), flow_version(s, cur), session=s)
        seen["decide_case"] = (d.route, d.net)
    seen["simulation"] = _simulated(cur)
    assert len({p[0] for p in seen.values()}) == 1, seen
    nets = [p[1] for p in seen.values()]
    assert max(nets) - min(nets) < 0.005, seen
    if scenario in ("BAT-S3", "BAT-S4"):  # no permit on file in these samples: recycle is refused too, never a standard lane
        assert seen["opened"][0] in ("recycle", None), seen


def test_order_invariant_battery():
    """R20: the gates run first. A damaged pack stays recycle-only whatever the rule or diversion says."""
    c = _open(3, SCENARIOS["BAT-S3"])
    assert c["recommendation"] is None or c["recommendation"]["id"] == "recycle"
    rules = (CompiledRule("BR-1", {}, "prefer", "reuse", "prefer reuse"),)
    with SessionLocal() as s:
        d = decide_case(c["id"], live_pack(s, c), FlowVersion(None, 3, rules), session=s)
    assert d.trace == ("gates", "valuation", "queue_plan", "rules", "rank")
    by = {r["id"]: r for r in d.routes}
    assert all(by[i]["excluded"] for i in ("reuse", "remanufacture", "repurpose")), by
    assert d.route in ("recycle", None) and d.route != "reuse"
