"""P9-1.5 (I-6, R19, story X-04): `decide_case` is the one decider. It loads a case by id (needing a session) or takes its
facts, runs the pack's gates, the locked compliance guardrails, the diversions and business rules, then ranks, and returns
a frozen `Decision`; a customer diversion (the overlay's `add_step`) shows in the decision of the cases it matches. A scan
checks that intake, re-evaluation and simulation never call a valuer's own decide again. Every test ends with the starting
state."""

import ast
from pathlib import Path

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories.live_rules import flow_version, live_pack
from di.services.cases import store
from di.services.cases.decide import Decision, decide_case, write_back
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import load_pack
from tests import flowkit, starting
from tests.helpers import call

ORG = "Customer A"
FACTS = {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 60}
STEP = {"id": "op-1", "op": "add_step", "stage": "match", "when": [{"fact": "keyAccount", "op": "eq", "value": True}],
        "step": "Account-manager review", "owner_role": "Planner"}  # fmt: skip
APP = Path(__file__).resolve().parent.parent / "di"


def _reset_overlays() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM domain_event WHERE type = 'overlay.blocked' OR type LIKE 'action.overlay.%'"))
        conn.execute(text("DELETE FROM action_journal WHERE action LIKE 'overlay.%'"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    _reset_overlays()
    yield
    starting.reset()
    flowkit.reset_flows()
    _reset_overlays()


def _open(asset: str) -> str:
    body = {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": asset, "reason": "manual", "facts": FACTS}
    r = call("case.open", body, "planner-a")
    assert r["ok"], r
    return str(r["output"]["case_id"])


def test_decide_case_returns_a_frozen_decision():
    cid = _open("T-DC-1")
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        pack = live_pack(s, c)
        d = decide_case(cid, pack, flow_version(s, c), session=s)
    assert isinstance(d, Decision) and (d.case_id, d.pack_key, d.pack_version) == (cid, "tool_fleet", pack.version)
    assert d.route == c["recommendation"]["id"] and d.recommendation is not None and d.hold is None
    assert d.trace == ("gates", "compliance", "rules", "rank") and d.flow_ver == c["flowVer"]
    with pytest.raises(AttributeError):
        d.route = "x"  # type: ignore[misc]


def test_decide_case_needs_session_for_id():
    with pytest.raises(TypeError, match="decide_case needs a session to load RT-1049"):
        decide_case("RT-1049", load_pack("tool_fleet"), FlowVersion(None, 0, ()))


def _publish_step() -> None:
    body = {"pack_key": "tool_fleet", "org_unit_id": ORG, "ops": [STEP]}
    ref = {"pack_key": "tool_fleet", "org_unit_id": ORG}
    assert call("overlay.save", body, "planner-a")["ok"]
    assert call("overlay.submit", ref, "planner-a")["ok"]
    assert call("overlay.approve", ref, "approver")["ok"]


def test_x_04_diversion_runs():
    cid = _open("T-DC-2")
    _publish_step()
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        pack, fv = live_pack(s, c), flow_version(s, c)
        plain = decide_case(c, pack, fv, session=s)
        c["keyAccount"] = True
        key = decide_case(c, pack, fv, session=s)
        write_back(c, key)  # decided again, the step is listed once; with the flag gone it is gone
        again = decide_case(c, pack, fv, session=s)
        c["keyAccount"] = False
        gone = decide_case(c, pack, fv, session=s)
    assert len(again.required_steps) == 1 and gone.required_steps == [] and gone.diversions == []
    assert plain.diversions == [] and not [x for x in plain.required_steps if x["step"] == "Account-manager review"]
    assert key.diversions == ["op-1"]
    assert [(x["step"], x["owner"]) for x in key.required_steps if x["gate"] == "op-1"] == [("Account-manager review", "Planner")]
    assert key.route == plain.route and key.net == plain.net  # a step adds work; it never changes the numbers


def test_one_decider_only():
    banned = {("tool_fleet", "decide"), ("tool_fleet", "plan_queue"), ("device", "decide")}
    for rel in ("services/cases/intake.py", "services/actions/decisions.py", "services/actions/modeler_sim.py"):
        tree = ast.parse((APP / rel).read_text(encoding="utf-8"))
        hits = [
            f"{rel}:{n.lineno} {n.value.id}.{n.attr}"
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and (n.value.id, n.attr) in banned
        ]
        assert not hits, hits
