"""P9-12.9 (R19, R20; stories NS-MED-01 and NS-MED-03): medical capital cases decided by every path give one route and one net,
and no rule or diversion revives a route a gate blocked. Cases are opened with facts only (the standard valuer's lines read them).
Legal note: the wording of the gates needs review by Kinective's Legal team before it is relied on.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories.live_rules import flow_version, live_pack
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key, tag_key
from di.services.canonical.store import Fact
from di.services.cases import intake
from di.services.cases import store as cases
from di.services.cases.decide import decide_case
from di.services.modeler import simulate as sim
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.templates import template_of_pack
from tests import flowkit, starting
from tests.helpers import call

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "medical_capital.json"
BASE = {
    "cls": "infusion_pump", "age_years": 4, "resale_price": 4000, "refurb_cost": 1200, "parts_value": 500, "single_use": False,
    "origin_market": "US", "target_market": "US", "udi": "UDI-0001", "service_record_ref": "SR-1", "recalls_closed": True,
}  # fmt: skip
ORDER = ("gates", "valuation", "queue_plan", "rules", "rank")


def tag(n: int) -> str:
    return f"SYN-MC-{n:04d}"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SYN-MC-%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYN-MC-%"})


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.4"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    yield
    _clean()
    flowkit.reset_flows()
    starting.reset()


def _open(n: int, facts: dict[str, Any]) -> dict:
    key = tag_key(ORG, tag(n))
    row = {"asset_key": key, "type": "field_safety_status", "result": "pass", "ref": "R-1",
           "at": "2026-11-01T00:00:00+00:00", "value": {}}  # fmt: skip
    with SessionLocal() as s:  # the biomedical system's field safety status (G-MED-FSN reads it): no open notice
        canonical.apply(
            s, "manual", [Fact("compliance", compliance_key(key, "field_safety_status"), f, v) for f, v in row.items()]
        )
        s.commit()
    body = {"org_unit_id": ORG, "template_key": "medical_capital", "asset_key": key, "reason": "trade_in",
            "facts": {"tag": tag(n)} | facts}  # fmt: skip
    return _get(_ok(call("case.open", body, "planner-a"))["case_id"])


def _get(cid: str) -> dict:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


SCENARIOS: dict[str, dict[str, Any]] = {
    "MC-S1": {},  # no assessment recorded: refurbish and resale is stopped, resale as is is the best
    "MC-S2": {"cls": "patient_monitor"},  # patient data without a sanitisation record: every release route fails
    "MC-S3": {"single_use": True},  # single-use: only recycling is left
    "MC-S4": {"target_market": "EU", "udi": None, "recalls_closed": False},  # cross-market with nothing to show
    "MC-S5": {"target_market": "EU"},  # cross-market, complete
}


def _seen(c: dict) -> tuple[str | None, float]:
    r = c.get("recommendation")
    return (r["id"] if r else None, r["net"] if r else 0.0)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_paths_agree_medical_capital(scenario: str):
    """Intake, re-evaluation, the Modeler's simulation, `decide_case` and a mapping of the case's facts give one route and net."""
    c = _open(int(scenario[-1]), BASE | SCENARIOS[scenario])
    seen = {"opened": _seen(c)}
    with SessionLocal() as s:
        c2 = cases.get(s, c["id"], for_update=True)
        assert c2 is not None
        intake.revalue(s, c2)
        cases.save(s, c2)
        s.commit()
    c2 = _get(c["id"])
    seen["reevaluated"] = _seen(c2)
    with SessionLocal() as s:
        pack, fv = live_pack(s, c2), flow_version(s, c2)
        d = decide_case(c["id"], pack, fv, session=s)
        seen["decide_case"] = (d.route, d.net)
        f = decide_case(dict(c2["valuer"]) | {"id": "F", "evidenceRecords": c2["evidenceRecords"]}, pack, fv)
        seen["facts"] = (f.route, f.net)
        t = sim.simulate(
            template_of_pack(pack), (), (), [c2],
            lambda case, rules: sim.decision_to_sim(decide_case(case, pack, FlowVersion(None, fv.ver, tuple(rules)), session=s)),
        )  # fmt: skip
        assert t.flips == [] and t.dv == 0
    assert len({p[0] for p in seen.values()}) == 1, seen
    nets = [p[1] for p in seen.values()]
    assert max(nets) - min(nets) < 0.005, seen


def test_order_invariant_medical_capital():
    """R20 with a monitor that has no sanitisation record: the rule "prefer harvest" revives nothing; every route stays out and
    the case is held with no recommendation."""
    c = _open(2, BASE | {"cls": "patient_monitor"})
    assert c["gateHold"]["gates"] == ["G-DATA-3"] and c["recommendation"] is None
    with SessionLocal() as s:
        pack = live_pack(s, c)
        rule = CompiledRule("BR-1", {}, "prefer", "harvest", "prefer harvest")
        d = decide_case(c["id"], pack, FlowVersion(None, 3, (rule,)), session=s)
    assert d.trace == ORDER
    assert d.recommendation is None and d.route is None and d.hold is not None
    assert all(r["excluded"] for r in d.routes) and all("Sanitisation record required" in r["failReason"] for r in d.routes)
