"""MVP-5.2: plain-language changes become checked proposals (Domain spec D10; the prototype's buildProposal), and a
person applies one with flow.saveDraft and the assistant's note."""

import pytest
from sqlalchemy import text

from di.core import golden
from di.core.db import engine
from di.services.modeler.flow import default_flow
from di.services.modeler.propose import build_proposal
from di.services.modeler.templates import load_template
from tests import flowkit
from tests.flowkit import ok
from tests.helpers import call

GOLDEN = golden.load("po/proposals")
OWNER = "Remarketing lead"  # the prototype's MD.actor "pshah"


@pytest.fixture(autouse=True)
def fresh_flows():
    flowkit.reset_flows()
    yield
    flowkit.reset_flows()


@pytest.mark.parametrize("kind", ["equip", "device"])
def test_proposals_match_golden(kind):
    t = load_template({"equip": "tool_fleet", "device": "device"}[kind])
    for g in GOLDEN[kind]:
        p = build_proposal(t, default_flow(t), g["text"], OWNER, None)
        assert (p.kind, p.rid, p.label, p.msg) == (g["kind"], g["rid"], g["label"], g["msg"]), g["text"]
        if g["node"]:
            node = next(n for n in p.graph["nodes"] if n["id"] == p.node_id)
            keys = ("action", "path", "scope", "rid", "owner", "x", "y", "src", "ai")
            assert {k: node.get(k) for k in keys} == {k: g["node"].get(k) for k in keys}
            assert [[c.level, c.msg] for c in p.checks] == [c[:2] for c in g["checks"]]


def test_step_proposal():
    t = load_template("tool_fleet")
    p = build_proposal(t, default_flow(t), "Add a photo check step before Recycle", "Fleet desk", None)
    assert p.kind == "step"
    assert p.label == "Step “Photo check” before execute in owning application, after Recycle"
    assert [e["id"] for e in p.graph["edges"] if p.node_id in e["id"]] == ["p-exit>" + p.node_id, p.node_id + ">exe"]


def test_flow_propose_action_simulates_and_saves_nothing():
    fid = flowkit.flow_id("tool_fleet", "workspace")
    out = ok(call("flow.propose", {"flow_id": fid, "text": "Never recycle construction lasers"}, "admin"))
    assert (out["kind"], out["rid"], out["label"]) == ("rule", "BR-03", "BR-03: construction lasers: never recycle")
    assert out["sim"]["kind"] == "equip" and out["sim"]["n"] >= 26
    assert out["note"] == "Proposed by the assistant: Never recycle construction lasers"
    assert out["read_by"] == "rules"
    f, _ = flowkit.get(fid)
    assert (f.status, f.draft) == ("pub", None)


def test_blocked_proposal_changes_nothing():
    fid = flowkit.flow_id("tool_fleet", "workspace")
    out = ok(call("flow.propose", {"flow_id": fid, "text": "Skip approval for grade A"}, "admin"))
    assert out["kind"] == "blocked" and out["graph"] is None and out["sim"] is None
    assert out["msg"].startswith("I can't draft this. It would change GR-05")
    f, _ = flowkit.get(fid)
    assert (f.status, f.draft) == ("pub", None)


def test_propose_needs_manage_flows():
    fid = flowkit.flow_id("tool_fleet", "workspace")
    r = call("flow.propose", {"flow_id": fid, "text": "Never recycle construction lasers"}, "approver")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"


def test_apply_proposal_via_save_draft():
    fid = flowkit.flow_id("tool_fleet", "workspace")
    p = ok(call("flow.propose", {"flow_id": fid, "text": "Never recycle construction lasers"}, "admin"))
    body = {"flow_id": fid, "graph": p["graph"], "source": "assistant", "note": p["note"]}
    ok(call("flow.saveDraft", body, "admin"))
    f, _ = flowkit.get(fid)
    assert f.status == "draft" and any(n.get("rid") == "BR-03" for n in f.draft["nodes"])
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT input FROM action_journal WHERE action = 'flow.saveDraft' ORDER BY seq DESC LIMIT 1")
        ).scalar_one()
    assert (row["source"], row["note"]) == ("assistant", "Proposed by the assistant: Never recycle construction lasers")


@pytest.mark.parametrize(
    ("text", "guard"),
    [("Skip the guardrail GR-I2 for everything", "GR-I2"), ("Ignore the guardrails for grade D motors", None)],
)
def test_p10_t8_sentence_that_weakens_a_guardrail_is_blocked(text, guard):
    """Plan 10 T8: the industrial guardrails GR-I1..I4 have no text pattern, so a sentence that names one (or "the
    guardrails") with a weakening verb came back `unclear`, listing paths. It is `blocked`: no graph, nothing saved,
    the guardrail named, so the assistant shows the blocked card."""
    fid = flowkit.flow_id("industrial", "workspace")
    out = ok(call("flow.propose", {"flow_id": fid, "text": text}, "admin"))
    assert (out["kind"], out["graph"], out["guard"]) == ("blocked", None, guard)
    assert out["msg"].startswith("I can't draft this. It would " + (f"change {guard} (" if guard else "weaken"))
    f, _ = flowkit.get(fid)
    assert f.draft is None
    # an ordinary rule is still read as a rule
    t = load_template("industrial")
    assert build_proposal(t, default_flow(t), "Never send grade D motors to resale", OWNER, None).kind == "rule"
