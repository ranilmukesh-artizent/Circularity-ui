"""P9-7.3 (story X-06; registry entry I-17): publish in steps, a canary by region and share, then full.

The pure part (stages, `assign`) is unit tested; the actions run through the API on a flow of Customer A approved into shadow with
a replay of its candidate done (the real replay job for the tool-fleet flow, a stored `done` run for the industrial one, whose
history format the replay does not need here). Nothing here reads or writes free text, so the model-first rule (R16) has no
output to route. Review Focus 10: only the cases of the canary's region use the candidate, both arms are journaled.
"""

import pytest
from sqlalchemy import text

from di import worker
from di.core.db import SessionLocal
from di.repositories import flows as flow_repo
from di.repositories import rollouts
from di.services.cases import store
from di.services.modeler.flow import default_flow
from di.services.modeler.rollout import Rollout, assign, can_move
from di.services.modeler.templates import load_template
from tests import flowkit, starting
from tests.flowkit import ok, with_rule
from tests.helpers import call, client, h
from tests.test_replay_run import as_csv

ORG = "Customer A"
MAKER_TEXT = "Maker-checker: you made these changes, so you cannot widen their rollout."
SCOPE_A_C = {"grade": ["C"], "owner": ["Customer A"]}


@pytest.fixture(autouse=True)
def fresh():
    def clean() -> None:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM rollout"))
            s.execute(text("DELETE FROM replay_run"))
            s.execute(text("DELETE FROM replay_batch"))
            s.commit()

    clean()
    starting.reset()
    flowkit.reset_flows()
    yield
    clean()
    flowkit.reset_flows()
    starting.reset()


def shadow_flow(template: str = "tool_fleet", maker: str = "planner-a") -> int:
    """Customer A's own flow of the template with a draft (one rule) approved into shadow; `maker` saved and submitted it."""
    fid = ok(call("flow.fork", {"template_key": template, "org_unit_id": ORG}, maker))["flow_id"]
    if template == "tool_fleet":
        g = with_rule(default_flow(load_template(template)), "TF-C", "exclude", "redeploy", {})
    else:
        g = with_rule(default_flow(load_template(template)), "IR-01", "require", "material", SCOPE_A_C)
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, maker))
    ok(call("flow.submit", {"flow_id": fid}, maker))
    ok(call("flow.approve", {"flow_id": fid}, "approver"))
    return int(fid)


def replay_done(fid: int, real: bool = True) -> None:
    """A done replay of the flow's draft: through the worker for the tool-fleet pack, else stored."""
    if real:
        bid = ok(call("replay.import", {"pack": "tool_fleet", "org_unit_id": ORG, "csv": as_csv()}, "planner.a"))["id"]
        ok(call("replay.run", {"batch_id": bid, "flow_id": fid}, "planner.a"))
        while worker.run_once():
            pass
        return
    with SessionLocal() as s:
        bid = s.execute(
            text(
                "INSERT INTO replay_batch (pack, org_unit_id, rows, held, created_by) "
                "VALUES ('industrial', :o, 0, 0, 't') RETURNING id"
            ),
            {"o": ORG},
        ).scalar_one()
        dver = flow_repo.get_flow(s, fid).dver
        s.execute(
            text(
                "INSERT INTO replay_run (batch_id, flow_id, flow_ver, dver, status, created_by) "
                "VALUES (:b, :f, 'draft', :d, 'done', 't')"
            ),
            {"b": bid, "f": fid, "d": dver},
        )
        s.commit()


def start(fid: int, region: str = "FR", share: int = 20, key: str | None = None, user: str = "approver") -> dict:
    body = {"flow_id": fid, "region": region, "share": share} | ({"region_key": key} if key else {})
    return call("rollout.startCanary", body, user)


def fix_salt(salt: str = "fixed-salt") -> None:
    with SessionLocal() as s:
        s.execute(text("UPDATE rollout SET salt = :s"), {"s": salt})
        s.commit()


def evaluate(fid: int, cases: list[dict]) -> list[tuple]:
    """(version, arm) of each case under the flow, as the decider reads it; assignments are stored."""
    with SessionLocal() as s:
        f = flow_repo.get_flow(s, fid)
        out = [rollouts.version_for(s, c, f) for c in cases]
        s.commit()
    return out


def cases(prefix: str, market: str, n: int) -> list[dict]:
    return [{"id": f"{prefix}{k:03d}", "market": market} for k in range(n)]


def row(fid: int) -> Rollout:
    with SessionLocal() as s:
        (r,) = rollouts.rollouts_of(s, fid)[:1]
    return r


# ---------------------------------------------------------------- the pure part
def test_x_06_stage_moves():
    assert can_move(None, "replay") and can_move("replay", "shadow") and can_move("shadow", "canary")
    assert can_move("canary", "full") and can_move("canary", "paused") and can_move("paused", "canary")
    assert not can_move("shadow", "full") and not can_move("paused", "full") and not can_move("full", "canary")
    assert all(can_move(s, "rolled_back") for s in ("replay", "shadow", "canary", "paused", "full"))
    assert not can_move("rolled_back", "rolled_back")


def test_x_06_assign_is_deterministic_and_region_exact():
    r = Rollout(1, "flow", "7", 2, 1, "canary", "market", "FR", 20, "s")
    assert assign("C1", "7", "s", "DE", r) == "out" and assign("C1", "7", "s", None, r) == "out"
    assert assign("C1", "7", "s", "fr", r) == "out"  # compared exactly
    arms = [assign(f"C{k}", "7", "s", "FR", r) for k in range(300)]
    assert arms == [assign(f"C{k}", "7", "s", "FR", r) for k in range(300)]
    assert 0 < arms.count("canary") < 300 and set(arms) == {"canary", "control"}
    wide = Rollout(1, "flow", "7", 2, 1, "canary", "market", "FR", 40, "s")
    for k, a in enumerate(arms):  # a higher share only adds
        assert a == "control" or assign(f"C{k}", "7", "s", "FR", wide) == "canary"


# ---------------------------------------------------------------- the actions
def test_x_06_canary_share_and_region():
    fid = shadow_flow()
    replay_done(fid)
    out = ok(start(fid))
    assert (out["stage"], out["region"], out["share"], out["candidate_ver"], out["base_ver"]) == ("canary", "FR", 20, 2, 1)
    fix_salt()
    r = row(fid)
    fr, de = cases("FR", "FR", 200), cases("DE", "DE", 50)
    got_fr, got_de = evaluate(fid, fr), evaluate(fid, de)
    assert all(g == (1, "out") for g in got_de)  # the published version, arm out
    canary = {c["id"] for c in fr if assign(c["id"], str(fid), r.salt, "FR", r) == "canary"}
    assert {c["id"] for c, g in zip(fr, got_fr, strict=True) if g == ("draft", "canary")} == canary
    assert all(g in (("draft", "canary"), (1, "control")) for g in got_fr)
    assert 25 <= len(canary) <= 55 and len(canary) < 200
    with SessionLocal() as s:
        counts = rollouts.arm_counts(s, fid)
        stored = s.execute(text("SELECT count(*) FROM rollout_assignment WHERE case_id LIKE 'FR%'")).scalar_one()
        assert not s.execute(text("SELECT 1 FROM rollout_assignment WHERE case_id LIKE 'DE%'")).first()
    assert counts == {"canary": len(canary), "control": 200 - len(canary)} and stored == 200


def test_x_06_canary_sticky_through_close():
    fid = shadow_flow("industrial")
    replay_done(fid, real=False)
    ok(start(fid, region="Customer A", share=99, key="owner"))
    fix_salt()
    r = row(fid)
    case_id = next(c for c in ("RT-1065", "RT-1079") if assign(c, str(fid), r.salt, ORG, r) == "canary")
    ok(call("decision.decline", {"case_id": case_id, "reason": "Re-check with the new policy."}, "admin"))
    ok(call("case.reevaluate", {"case_id": case_id}, "admin"))
    with SessionLocal() as s:
        c = store.get(s, case_id)
    assert (c["flowVer"], c["flowArm"]) == (2, "canary")  # decided by the candidate, the arm recorded on the case
    ok(call("rollout.pause", {"flow_id": fid, "reason": "Pausing to look at the numbers."}, "approver"))
    ok(call("decision.submit", {"case_id": case_id}, "planner-a"))
    approve = {"case_id": case_id, "rationale": "Material recovery as the rule requires; evidence reviewed.", "reviewed": True}
    r2 = call("decision.approve", approve, "approver")
    assert r2["ok"], r2
    from di.services.actions.pipeline import SYSTEM, CallContext, invoke

    for _ in range(12):
        with SessionLocal() as s:
            if (store.get(s, case_id) or {})["stage"] == "closed":
                break
            res = invoke("adapter.acknowledge", {"case_id": case_id}, CallContext(actor=SYSTEM, session=s))
            s.commit() if res["ok"] else s.rollback()
    with SessionLocal() as s:
        c = store.get(s, case_id)
        assert c["stage"] == "closed" and (c["flowVer"], c["flowArm"]) == (2, "canary")
        assert rollouts.version_for(s, {"id": case_id, "owner": ORG}, flow_repo.get_flow(s, fid)) == ("draft", "canary")


def test_x_06_raising_share_only_adds():
    fid = shadow_flow()
    replay_done(fid)
    ok(start(fid))
    fix_salt()
    fr = cases("FR", "FR", 200)
    before = evaluate(fid, fr)
    ok(call("rollout.widen", {"flow_id": fid, "share": 40}, "approver"))
    assert row(fid).share == 40
    assert evaluate(fid, fr) == before  # earlier canary cases stay canary, earlier control cases stay control
    fresh_cases = cases("NEW", "FR", 200)
    arms = [a for _, a in evaluate(fid, fresh_cases)]
    assert 55 <= arms.count("canary") <= 105  # new cases fall in at 40 %
    low = call("rollout.widen", {"flow_id": fid, "share": 30}, "approver")
    assert low["error"]["code"] == "conflict" and "only rises" in low["error"]["message"]
    ok(call("rollout.widen", {"flow_id": fid, "region": "DE", "share": 10}, "approver"))  # a new region adds a row
    with SessionLocal() as s:
        assert sorted((r.region, r.share) for r in rollouts.active_rollout(s, fid)) == [("DE", 10), ("FR", 40)]
    assert evaluate(fid, cases("D2", "DE", 100)) and any(a == "canary" for _, a in evaluate(fid, cases("D3", "DE", 100)))


def test_x_06_canary_needs_replay():
    fid = shadow_flow()
    r = start(fid)
    needs = "Run a replay of v2 before a canary (Modeler, Replay)."
    assert r["ok"] is False and r["error"] == {"code": "conflict", "message": needs}
    assert call("rollout.get", {"flow_id": fid}, "approver")["output"]["stage"] == "shadow"
    replay_done(fid)
    assert ok(start(fid, share=20))["stage"] == "canary"
    again = start(fid)
    assert again["error"]["code"] == "conflict" and "already running" in again["error"]["message"]
    bad = start(fid, share=100)
    assert bad["ok"] is False


def test_x_06_pause_returns_new_cases_to_base():
    fid = shadow_flow()
    replay_done(fid)
    ok(start(fid, share=50))
    fix_salt()
    old = evaluate(fid, cases("OLD", "FR", 40))
    assert any(a == "canary" for _, a in old)
    ok(call("rollout.pause", {"flow_id": fid, "reason": "Stop rule hit in the first week."}, "approver"))
    new = evaluate(fid, cases("NEW", "FR", 40))
    assert all(g == (1, "none") for g in new)
    assert evaluate(fid, cases("OLD", "FR", 40)) == old  # the cases already in keep theirs
    out = ok(call("rollout.get", {"flow_id": fid}, "approver"))
    assert out["stage"] == "paused" and out["can"]["full"] is not None
    ok(call("rollout.widen", {"flow_id": fid, "share": 60}, "approver"))  # widening resumes it
    assert ok(call("rollout.get", {"flow_id": fid}, "approver"))["stage"] == "canary"


def test_x_06_rollback_clears_undecided():
    fid = shadow_flow("industrial")
    replay_done(fid, real=False)
    ok(start(fid, region="Customer A", share=99, key="owner"))
    fix_salt()
    r = row(fid)
    picked = [c for c in ("RT-1065", "RT-1079", "RT-1062", "RT-1048") if assign(c, str(fid), r.salt, ORG, r) == "canary"]
    assert len(picked) >= 2
    waiting, approved = picked[0], picked[1]
    for cid in (waiting, approved):
        ok(call("decision.decline", {"case_id": cid, "reason": "Re-check with the new policy."}, "admin"))
        ok(call("case.reevaluate", {"case_id": cid}, "admin"))
    ok(call("decision.submit", {"case_id": approved}, "planner-a"))
    ap = {"case_id": approved, "rationale": "Material recovery as the rule requires; evidence reviewed.", "reviewed": True}
    assert call("decision.approve", ap, "approver")["ok"]
    out = ok(call("rollout.rollback", {"flow_id": fid, "reason": "The candidate looks worse in the first days."}, "approver"))
    assert out["stage"] == "rolled_back" and out["cleared"] >= 1
    with SessionLocal() as s:
        f = flow_repo.get_flow(s, fid)
        assert rollouts.version_for(s, {"id": waiting, "owner": ORG}, f) == (1, "none")  # back on the base version
        assert rollouts.version_for(s, {"id": approved, "owner": ORG}, f) == ("draft", "canary")  # decided: keeps its version
    # a rolled-back flow may start another canary (a new salt)
    assert ok(start(fid, region="Customer A", share=10, key="owner"))["stage"] == "canary"


def test_x_06_full_publishes():
    fid = shadow_flow()
    replay_done(fid)
    ok(start(fid))
    assert call("rollout.full", {"flow_id": fid}, "approver")["ok"]
    f, versions = flowkit.get(fid)
    assert (f.status, f.ver, f.dver, f.draft) == ("pub", 2, None, None)
    assert [v.ver for v in versions] == [1]  # the base version went to history
    assert ok(call("rollout.get", {"flow_id": fid}, "approver"))["stage"] == "full"
    with SessionLocal() as s:  # after full everyone runs the published version
        assert rollouts.version_for(s, {"id": "FR001", "market": "FR"}, flow_repo.get_flow(s, fid)) == (2, "none")
    refused = call("rollout.full", {"flow_id": fid}, "approver")
    assert refused["error"]["code"] == "conflict"


def test_x_06_full_needs_a_canary():
    fid = shadow_flow()
    replay_done(fid)
    r = call("rollout.full", {"flow_id": fid}, "approver")
    assert r["error"]["code"] == "conflict" and "Start a canary" in r["error"]["message"]
    f, _ = flowkit.get(fid)
    assert f.status == "shadow"


def test_x_06_draft_is_fixed_while_a_canary_runs():
    fid = shadow_flow()
    replay_done(fid)
    ok(start(fid))
    g = with_rule(default_flow(load_template("tool_fleet")), "TF-D", "exclude", "resell", {})
    r = call("flow.saveDraft", {"flow_id": fid, "graph": g}, "planner-a")
    assert r["error"]["code"] == "conflict" and "canary running" in r["error"]["message"]


# ---------------------------------------------------------------- R21: the publish step is a person's, a checker's
def test_rollout_maker_cannot_approve():
    fid = shadow_flow(maker="admin")  # the Admin saved and submitted it, a different person approved it
    replay_done(fid)
    r = call("rollout.startCanary", {"flow_id": fid, "region": "FR", "share": 20}, "admin")
    assert r["ok"] is False and r["error"] == {"code": "conflict", "message": MAKER_TEXT}
    with SessionLocal() as s:
        assert rollouts.active_rollout(s, fid) == []
    ok(start(fid))  # the checker may
    assert call("rollout.widen", {"flow_id": fid, "share": 30}, "admin")["error"]["message"] == MAKER_TEXT
    assert call("rollout.full", {"flow_id": fid}, "admin")["error"]["message"] == MAKER_TEXT
    pause = call("rollout.pause", {"flow_id": fid, "reason": "Pausing is towards the known-good."}, "admin")
    assert pause["ok"]  # pausing has no maker-checker


def test_rollout_agent_cannot_widen():
    fid = shadow_flow()
    replay_done(fid)
    ok(start(fid))
    from di.services.agents.forbidden import FORBIDDEN_ACTIONS

    for a in ("rollout.startCanary", "rollout.widen", "rollout.pause", "rollout.full", "rollout.rollback"):
        assert a.startswith(FORBIDDEN_ACTIONS), a
    for extra in ({}, {"X-Circularity-Confirmed": "true"}):
        hdr = h("approver") | {"X-Circularity-Preparer": "coordinator"} | extra
        r = client.post("/api/actions/rollout.widen", json={"flow_id": fid, "share": 40}, headers=hdr)
        assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required", r.json()
    assert row(fid).share == 20


def test_rollout_tenant_boundary(monkeypatch):
    fid = shadow_flow()
    replay_done(fid)
    r = call("rollout.get", {"flow_id": fid}, "planner.b")  # a planner of another tenant
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    assert call("rollout.get", {"flow_id": fid}, "exec")["error"]["code"] == "out_of_scope"
    planner = call("rollout.startCanary", {"flow_id": fid, "region": "FR", "share": 20}, "planner-a")
    assert planner["error"]["code"] == "out_of_scope"
    monkeypatch.setattr("di.services.actions.modeler._org_ok", lambda ctx, org: False)  # an approver outside the flow's org
    r = start(fid)
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    monkeypatch.undo()
    with SessionLocal() as s:
        assert rollouts.active_rollout(s, fid) == []
