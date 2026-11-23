"""MVP-12.3: rule suggestions from Approver overrides. The pure grouping and thresholds (di.services.modeler.suggest)
on synthetic decisions, and the read action `flow.suggestions`, which turns them into checked and simulated proposals
and never changes the flow."""

import json

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.cases import store
from di.services.modeler.flow import default_flow
from di.services.modeler.suggest import DecisionRow, override_groups, place_rule, suggest
from di.services.modeler.templates import load_template
from tests import flowkit
from tests.flowkit import ok
from tests.helpers import call

T = load_template("industrial")


def _row(i: int, to: str, frm: str = "redeploy", cls: str = "motor", grade: str = "B", site: str = "Site 1") -> DecisionRow:
    return DecisionRow(f"C-{i}", "industrial", frm, to, {"cls": cls, "grade": grade, "site": site, "owner": "Customer A"})


def _synthetic() -> list[DecisionRow]:
    """Motors: 3 overrides redeploy -> resale of 4 motor decisions (75 %). Pumps: 2 overrides to resale (below 3), at
    grade D with the motor not overridden, so grade D stays below the thresholds too.
    The overridden motors sit at different grades and sites, and Customer A also has many plain approvals."""
    rows = [_row(1, "resale", grade="A", site="Site 1"), _row(2, "resale", grade="B", site="Site 2"),
            _row(3, "resale", grade="C", site="Site 3"), _row(4, "redeploy", grade="D", site="Site 4")]  # fmt: skip
    rows += [_row(10 + k, "resale", cls="pump", grade="D", site="Site 5") for k in range(2)]
    rows += [_row(20 + k, "redeploy", cls="drill", grade="B", site="Site 6") for k in range(4)]
    return rows


def test_exactly_one_suggestion_for_a_synthetic_override_set():
    out = suggest(T, _synthetic())
    assert len(out) == 1
    s = out[0]
    assert (s.dim, s.value, s.path, s.overrides, s.decisions) == ("cls", "motor", "resale", 3, 4)
    assert s.share == pytest.approx(0.75)
    assert s.text == "industrial motors: prefer whole-asset resale"
    assert s.rule == {"action": "prefer", "path": "resale", "scope": {"cls": ["motor"]}}


def test_override_groups_by_template_and_routes():
    groups = override_groups(_synthetic())
    assert [(g.template, g.from_path, g.to_path, g.n) for g in groups] == [("industrial", "redeploy", "resale", 5)]


def test_no_suggestion_below_the_thresholds():
    rows = _synthetic()
    assert suggest(T, rows[:2] + rows[3:]) == []  # 2 motor overrides: below 3
    diluted = rows + [_row(30 + k, "redeploy") for k in range(2)]  # 3 of 6 motor decisions: 50 %
    assert suggest(T, diluted) == []
    other = [DecisionRow(r.case_id, "tool_fleet", r.from_path, r.to_path, r.values) for r in rows]
    assert suggest(T, other) == []  # another template's decisions


def test_place_rule_sits_between_the_gate_and_the_decision():
    g = default_flow(T)
    placed, node_id, rid = place_rule(T, g, {"action": "prefer", "path": "resale", "scope": {"cls": ["motor"]}}, "Planner", "x")
    assert rid == "IR-01"
    assert {(e["a"], e["b"]) for e in placed["edges"]} >= {("gate", node_id), (node_id, "dec")}
    assert ("gate", "dec") not in {(e["a"], e["b"]) for e in placed["edges"]}
    assert len(g["nodes"]) + 1 == len(placed["nodes"])  # the given graph is not changed
    again, _, rid2 = place_rule(T, placed, {"action": "exclude", "path": "exit", "scope": {}}, "Planner", "y")
    assert rid2 == "IR-02" and len(again["nodes"]) == len(placed["nodes"]) + 1


# ---------------------------------------------------------------- the action, over journaled overrides
@pytest.fixture
def overrides():
    """Synthetic journaled overrides on real cases: enough of one asset class, all to the same other route, that they
    are at least 60 % of that class's journaled decisions. Removed afterwards."""
    flowkit.reset_flows()
    with SessionLocal() as s:
        cases = [c for c in store.all_cases(s) if (c.get("template") or "industrial") == "industrial" and c.get("recommendation")]
        done = s.execute(text(
            "SELECT case_id FROM action_journal WHERE action IN ('decision.approve', 'decision.override') "
            "AND NOT undone AND case_id IS NOT NULL")).scalars().all()  # fmt: skip
    by_cls: dict[str, list[dict]] = {}
    for c in cases:
        by_cls.setdefault(c["cls"], []).append(c)
    pick = None
    for cls, cs in sorted(by_cls.items()):
        existing = sum(1 for cid in done if any(c["id"] == cid for c in cs))
        for path in T.path_ids():
            hits = [c for c in cs if c["recommendation"]["id"] != path and any(r["id"] == path for r in c["routes"])]
            need = max(3, -(-3 * existing // 2))  # k / (k + existing) >= 0.6
            if len(hits) >= need:
                pick = (cls, path, hits[:need])
                break
        if pick:
            break
    assert pick, "the demo's cases offer a class with enough cases sharing another route"
    cls, path, hits = pick
    seqs = []
    with engine.begin() as conn:
        for c in hits:
            plan = next(r["plan"] for r in c["routes"] if r["id"] == path)
            seqs.append(conn.execute(text(
                "INSERT INTO action_journal (action, input, actor, role, case_id, at) "
                "VALUES ('decision.override', CAST(:i AS jsonb), 'approver', 'Approver', :c, now()) RETURNING seq"),
                {"i": json.dumps({"case_id": c["id"], "route": plan, "rationale": "Customer commitment"}), "c": c["id"]},
            ).scalar_one())  # fmt: skip
    yield cls, path, len(hits)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM action_journal WHERE seq = ANY(:s)"), {"s": seqs})
    flowkit.reset_flows()


def test_suggestions_arrive_checked_and_simulated(overrides):
    cls, path, n = overrides
    fid = flowkit.flow_id("industrial", "workspace")
    out = ok(call("flow.suggestions", {"flow_id": fid}, "admin"))
    assert sum(g["n"] for g in out["groups"] if g["to"] == path) >= n  # grouped by the route each came from
    s = next(x for x in out["suggestions"] if (x["dim"], x["value"], x["path"]) == ("cls", cls, path))
    assert s["overrides"] >= n and s["share"] >= 0.6
    p = s["proposal"]
    assert p["kind"] == "rule" and p["rid"] == "IR-01" and p["guard"] is None
    assert p["label"] == "IR-01: " + s["text"]
    assert p["sim"]["kind"] == "equip" and p["sim"]["n"] > 0
    assert any(c["node_id"] == p["node_id"] and c["level"] == "ok" for c in p["checks"])
    f, _ = flowkit.get(fid)
    assert (f.status, f.draft) == ("pub", None)  # a suggestion is never applied by itself


def test_suggestions_need_a_flow_permission(overrides):
    fid = flowkit.flow_id("industrial", "workspace")
    r = call("flow.suggestions", {"flow_id": fid}, "warehouse1")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
