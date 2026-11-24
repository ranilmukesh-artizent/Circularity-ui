"""The plan-8 audit's findings (docs/agents/audits/2026-11-24-plan-08/README.md), each reproduced, then fixed.

    F1  a tool-fleet case opened from data leaves the tool-fleet Modeler (screen, simulate, propose) working
    F2  battery and IT lots: the hazardous-waste exclusion comes before the business rules, so the waiver sees it
    F3a the person an agent acted for does not accept that agent's proposal; another person does
    F3b everyone who edited a draft is its maker: none of them approves or publishes it
    F4  an agent-prepared call never runs an action no agent may run, whatever the headers say
    F6  a template case is ranked by its template's valuer, as the simulation ranks it
    F7  the org pack drops any setting whose name says it is a key, not only secret/password/token
    F8  the pilot report is refused for an org unit outside the reader's tenants
Every test ends with the starting state.
"""

import dataclasses
from typing import Any

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.actions import decisions
from di.services.actions.pipeline import SYSTEM, CallContext
from di.services.cases import intake, store
from di.services.engine.gates import HAZARDOUS
from di.services.modeler.compile import compile_flow
from di.services.modeler.flow import default_flow
from di.services.modeler.templates import load_template
from di.services.modeler.valuers import device
from tests import flowkit, starting
from tests.flowkit import ok, with_rule
from tests.helpers import call, client, h


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()
    yield
    starting.reset()
    flowkit.reset_flows()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()


def _open(user: str, **body: Any) -> dict:
    return call("case.open", {"org_unit_id": "Customer A", "reason": "contract_end"} | body, user)


TOOL = {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 62}
# a lot whose lowest channel scores more than 15% below its best (so the device valuer's "prefer" does not move it)
LOT = {"brand": "Apple", "model": "iPhone 14", "band": "0-24m", "grade": "A", "ref": 315, "qty": 1, "doh": 200}


# ---------------------------------------------------------------- F1
def test_f1_tool_fleet_modeler_works_with_an_opened_case():
    assert _open("admin", template_key="tool_fleet", asset_key="T-CMH-F1", facts=TOOL)["ok"]
    r = client.get("/api/screens/modeler", params={"template": "tool_fleet"}, headers=h("admin"))
    assert r.status_code == 200, r.text
    fid = flowkit.flow_id("tool_fleet", "workspace")
    g = default_flow(load_template("tool_fleet"))
    out = ok(call("flow.simulate", {"flow_id": fid, "graph": g}, "admin"))
    assert out["n"] >= 1
    assert call("flow.propose", {"flow_id": fid, "text": "never resell grade D"}, "admin")["ok"]


# ---------------------------------------------------------------- F2
def test_f2_hazard_exclusion_comes_before_business_rules():
    with SessionLocal() as s:
        cid = next(c["id"] for c in store.all_cases(s) if c["cls"] == "batch" and c["owner"] == "Customer A")
    flowkit.fork_and_publish("Customer A", [("IR-90", "require", "material", {})])
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        decisions._rebuild(CallContext(actor=SYSTEM, session=s), c, lambda: 0.05)  # every draw 0.05: hazard (< 0.12)
        s.rollback()
    m = next(r for r in c["routes"] if r["id"] == "material")
    assert m["excluded"] and m["failReason"] == HAZARDOUS
    assert c["recommendation"] is not None, "the require rule is waived: material is not eligible"
    assert not c.get("rulesWaived") and not c.get("rulesApplied")  # require on a route already excluded does nothing


# ---------------------------------------------------------------- F3a
AGENT = {"id": "ext-audit", "name": "Audit proposer", "tools": ["request_missing_evidence"], "autonomy": "propose"}


def _held(user: str) -> int:
    assert call("agent.register", AGENT, "admin")["ok"]
    hdr = h(user) | {"X-Circularity-Preparer": AGENT["id"]}
    r = client.post("/api/actions/evidence.request", json={"case_id": "RT-1051"}, headers=hdr).json()
    assert r["ok"] and "held" in r["output"], r
    return int(r["output"]["held"])


def test_f3a_requester_does_not_accept_own_agents_proposal():
    pid = _held("planner-a")
    r = call("proposal.accept", {"id": pid}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "conflict", r
    assert call("proposal.accept", {"id": pid}, "admin")["ok"] is True


# ---------------------------------------------------------------- F3b
def test_f3b_every_editor_is_a_maker():
    fid = ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer A"}, "planner-a"))["flow_id"]
    g = default_flow(load_template("industrial"))
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "planner-a"))
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": with_rule(g, "IR-91", "exclude", "exit", {})}, "admin"))
    ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    r = call("flow.approve", {"flow_id": fid}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "conflict", r
    ok(call("flow.approve", {"flow_id": fid}, "approver"))


# ---------------------------------------------------------------- F4
def test_f4_agent_prepared_forbidden_action_refused():
    assert call("agent.register", AGENT | {"id": "ext-act", "autonomy": "act"}, "admin")["ok"]
    hdr = h("admin") | {"X-Circularity-Preparer": "ext-act", "X-Circularity-Confirmed": "true"}
    r = client.post("/api/actions/org.setPilot", json={"org_unit_id": "Customer A", "on": True}, headers=hdr).json()
    assert r["ok"] is False and r["error"]["code"] == "approval_required", r
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM action_journal WHERE action = 'org.setPilot'")).scalar_one() == 0


# ---------------------------------------------------------------- F6
def test_f6_device_case_ranked_like_the_simulation():
    lot = intake.device_lot("x", LOT)
    worst = min((device.score(dict(lot), k) for k in device.DCH), key=lambda v: v["score"])
    fid = flowkit.flow_id("device", "workspace")
    g = with_rule(default_flow(load_template("device")), "DR-90", "prefer", worst["k"], {})
    flowkit.publish(fid, g, maker="admin")
    rules = [dataclasses.asdict(r) for r in compile_flow(load_template("device"), g)]
    want = device.decide(dict(lot), rules)["best"]
    assert want is not None and want["k"] != worst["k"]  # the preferred channel is more than 15% below the best
    r = _open("admin", template_key="device", asset_key="T-LOT-F6", facts=LOT)
    with SessionLocal() as s:
        c = store.get(s, r["output"]["case_id"])
    assert c is not None and c["recommendation"]["id"] == want["k"]


# ---------------------------------------------------------------- F7
def test_f7_pack_drops_key_named_settings():
    from di.services.actions.org_pack import _no_secrets

    got = _no_secrets({"api_key": "k", "apiKey": "k", "private_key": "k", "client_secret": "k", "url": "u"})
    assert got == {"url": "u"}


# ---------------------------------------------------------------- F8
def test_f8_pilot_report_needs_the_tenant(monkeypatch):
    from di.core import policy

    real = policy.can
    monkeypatch.setattr(policy, "can", lambda a, p, ctx=None: True if p == "approve.flows" else real(a, p, ctx))
    r = call("org.pilotReport", {"org_unit_id": "Customer B"}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", r
    assert call("org.pilotReport", {"org_unit_id": "Customer A"}, "planner-a")["ok"] is True


# ---------------------------------------------------------------- F10
def test_f10_text_guards_in_the_prototypes_order():
    from di.services.modeler.guard import text_breaks

    t = load_template("tool_fleet")  # prototype textGuard (line 2435): GR-03, GR-04, GR-05, then GR-02
    assert text_breaks(t, "Lower the threshold for refurb to stock") == "GR-03"
    assert text_breaks(t, "refurb to stock without approval") == "GR-05"
    assert text_breaks(t, "refurb straight to stock") == "GR-02"
