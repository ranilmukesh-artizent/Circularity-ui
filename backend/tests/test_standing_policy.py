"""P9-2.5 (story X-05; registry entry I-11; R21): a standing policy approves a submitted decision below its limits.

The policy is a new approvable object: a person owns it, a different person approves it, no agent approves or retires it, and
an org outside the actor's units is refused. A decision the policy does not cover (above its value, below its confidence, with an
open exception, a conflict, a guardrail hold or a fraud hold) waits for a person as it does without a policy. With no policy
the demo, RT-1048 included, is unchanged. The main stack's RT-1048 asset may have an open synced conflict: the tests pick a case
with none and add their own.
"""

import copy
from decimal import Decimal

import pytest
from sqlalchemy import text

from di.core import policy, state
from di.core.auth import load_context
from di.core.db import SessionLocal
from di.services.actions import standing_policy as sp
from di.services.actions.pipeline import SYSTEM, Actor, CallContext, invoke
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, forbidden
from di.services.cases import process, store
from di.services.modeler.pack import GuardParam, PackGuardrail, load_pack
from di.services.policy_standing import StandingRules, covers, parse_rules, rules_problem
from tests import starting
from tests.helpers import call

RULES = {"max_value": 500, "min_confidence": 0.75}
MAKER_CHECKER = "Maker-checker: you drafted this policy, so another person approves it."
ABOVE = "Above the policy's threshold: a person approves this decision."


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    yield
    starting.reset()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM conflict WHERE model = 'asset' AND field = 'x_05_probe'"))
        s.commit()


# ---------------------------------------------------------------- helpers
def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def pick_case() -> dict:
    """A case awaiting approval, not yet submitted, whose asset has no open conflict and which has no open exception."""
    with SessionLocal() as s:
        for (cid,) in s.execute(text("SELECT id FROM case_record WHERE stage = 'awaiting_approval' ORDER BY id")).all():
            c = store.get(s, cid)
            if not c or c.get("submitted") or c.get("approval") or c.get("recommendation") is None or c["id"] == "RT-1048":
                continue
            busy = s.execute(
                text("SELECT 1 FROM conflict WHERE key = :k AND status IN ('open','escalated')"), {"k": c.get("assetId")}
            ).first()
            if not busy:
                return c
    raise AssertionError("no case awaiting approval without a conflict")


def shape(cid: str, net: float, overlap: float = 10.0) -> None:
    """Value the case at `net` with two routes whose intervals overlap by `overlap` of 100 (confidence 1 - overlap/100)."""
    with SessionLocal() as s:
        c = store.get(s, cid, for_update=True)
        assert c is not None
        top = copy.deepcopy(c["recommendation"])
        top |= {"net": net, "p10": 0, "p90": 100, "excluded": False}
        second = copy.deepcopy(top) | {"id": "resell", "plan": "Resell " + cid, "net": net / 2, "p10": 100 - overlap, "p90": 200}
        c["routes"] = [top, second]
        c["recommendation"] = c["routes"][0]
        c.pop("chosen", None)
        store.save(s, c)
        s.commit()


def activate(
    org: str, *, rules: dict | None = None, owner: str = "admin", pack: str = "industrial", name: str = "Standing"
) -> str:
    out = ok(
        call(
            "standingPolicy.save",
            {"pack": pack, "org_unit_id": org, "name": name, "rules": rules or RULES, "owner": owner},
            "admin",
        )
    )
    pid = out["id"]
    ok(call("standingPolicy.submit", {"id": pid}, "admin"))
    ok(call("standingPolicy.approve", {"id": pid}, "approver"))
    return pid


def submit(cid: str) -> dict:
    return call("decision.submit", {"case_id": cid}, "admin")


def case_now(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        return c


def journal(action: str) -> list[dict]:
    with SessionLocal() as s:
        rows = s.execute(text("SELECT actor, role, case_id FROM action_journal WHERE action = :a AND NOT undone"), {"a": action})
        return [dict(r._mapping) for r in rows]


def policy_log() -> list[str]:
    with SessionLocal() as s:
        return [e["note"] for e in state.items(s, "events") if e.get("type") == "decision.approved.policy"]


def approve_by_policy_direct(cid: str, pid: str, ver: int) -> dict:
    """`decision.approveByPolicy` as the hook calls it (SYSTEM), so its own re-check is what refuses."""
    with SessionLocal() as s:
        r = invoke(
            "decision.approveByPolicy", {"case_id": cid, "policy_id": pid, "ver": ver}, CallContext(actor=SYSTEM, session=s)
        )
        s.commit()
        return r


def hold_stays(cid: str) -> None:
    c = case_now(cid)
    assert c["stage"] == "awaiting_approval" and c.get("submitted") and not c.get("approval"), c["stage"]


# ---------------------------------------------------------------- story X-05
def test_x_05_policy_approves_within_threshold():
    c = pick_case()
    shape(c["id"], 300, overlap=10)  # $300 at 0.9
    pid = activate(c["owner"])
    ok(submit(c["id"]))
    after = case_now(c["id"])
    assert after["stage"] == "approved" and after["approval"]["by"] == f"policy {pid} v1"
    rows = journal("decision.approveByPolicy")
    assert [(r["actor"], r["role"], r["case_id"]) for r in rows] == [("system", "System", c["id"])]
    assert policy_log() == [f"Approved by policy {pid} v1, owner admin"]


def test_x_05_policy_is_inherited_up_the_org_tree():
    c = pick_case()
    shape(c["id"], 300)
    pid = activate("workspace")
    ok(submit(c["id"]))
    assert case_now(c["id"])["approval"]["by"] == f"policy {pid} v1"


def test_x_05_policy_cannot_approve_above_threshold():
    c = pick_case()
    shape(c["id"], 700)  # above the $500 policy
    pid = activate(c["owner"])
    ok(submit(c["id"]))
    hold_stays(c["id"])
    r = approve_by_policy_direct(c["id"], pid, 1)
    assert r["ok"] is False and r["error"]["code"] == "approval_required" and r["error"]["message"] == ABOVE
    hold_stays(c["id"])
    assert journal("decision.approveByPolicy") == []


def test_x_05_policy_needs_the_confidence():
    c = pick_case()
    shape(c["id"], 300, overlap=40)  # 0.6, below the policy's 0.75
    activate(c["owner"])
    ok(submit(c["id"]))
    hold_stays(c["id"])


def test_x_05_policy_skips_holds_exceptions_and_conflicts():
    # an open exception
    c = pick_case()
    shape(c["id"], 300)
    activate(c["owner"])
    with SessionLocal() as s:
        process.open_item(s, kind="exception", case_id=c["id"], org_unit_id=c["owner"], type="x_05", title="Held", cause=None,
                          action=None, owner_role="Planner", due_hours=None, by="system")  # fmt: skip
        s.commit()
    ok(submit(c["id"]))
    hold_stays(c["id"])
    # a conflict on the asset
    d = pick_case_other(c["id"])
    shape(d["id"], 300)
    with SessionLocal() as s:
        s.execute(
            text(
                'INSERT INTO conflict (model, key, field, "values", status, opened_at) '
                "VALUES ('asset', :k, 'x_05_probe', CAST('{}' AS jsonb), 'open', now())"
            ),
            {"k": d["assetId"]},
        )
        s.commit()
    ok(submit(d["id"]))
    hold_stays(d["id"])
    # a guardrail hold (a failed gate that holds)
    e = pick_case_other(c["id"], d["id"])
    shape(e["id"], 300)
    with SessionLocal() as s:
        k = store.get(s, e["id"], for_update=True)
        assert k is not None
        k["gates"] = [{"id": "G-X", "passed": False, "hold": True}]
        store.save(s, k)
        s.commit()
    ok(submit(e["id"]))
    hold_stays(e["id"])
    # a fraud hold
    f = pick_case_other(c["id"], d["id"], e["id"])
    shape(f["id"], 300)
    with SessionLocal() as s:
        k = store.get(s, f["id"], for_update=True)
        assert k is not None
        k["fraud"] = {"status": "held", "score": 0.9}
        store.save(s, k)
        s.commit()
    ok(submit(f["id"]))
    hold_stays(f["id"])
    assert journal("decision.approveByPolicy") == []


def pick_case_other(*used: str) -> dict:
    with SessionLocal() as s:
        for (cid,) in s.execute(text("SELECT id FROM case_record WHERE stage = 'awaiting_approval' ORDER BY id")).all():
            c = store.get(s, cid)
            if not c or cid in used or cid == "RT-1048" or c.get("submitted") or c.get("recommendation") is None:
                continue
            if not s.execute(
                text("SELECT 1 FROM conflict WHERE key = :k AND status IN ('open','escalated')"), {"k": c.get("assetId")}
            ).first():
                return c
    raise AssertionError("not enough cases awaiting approval")


def test_x_05_policy_capped_by_pack_and_owner_limit(monkeypatch):
    base = load_pack("industrial")
    cap = PackGuardrail(
        id="GR-X", text="Approval by threshold", owner="Governance board", type="Approval", stage="decide", locked=False,
        param=GuardParam(field="value_limit", value=600, stricter="lower", min=0, max=1000000),
    )  # fmt: skip
    capped = base.model_copy(update={"guardrails": [*base.guardrails, cap]})
    monkeypatch.setattr(sp, "active_pack", lambda s, key, org: capped)
    r = call(
        "standingPolicy.save",
        {
            "pack": "industrial",
            "org_unit_id": "Customer A",
            "name": "Wide",
            "rules": {**RULES, "max_value": 10000},
            "owner": "admin",
        },
        "admin",
    )
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert r["error"]["message"] == "The policy cannot approve above the pack's $600 threshold."
    monkeypatch.setattr(sp, "active_pack", lambda s, key, org: base)
    # the owner's approval limit: the Planner may approve up to $250
    assert call("access.setLimit", {"role": "Planner", "amount": 250}, "admin")["ok"] is True
    r = call(
        "standingPolicy.save",
        {"pack": "industrial", "org_unit_id": "Customer A", "name": "Owner", "rules": RULES, "owner": "planner-a"},
        "admin",
    )
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert r["error"]["message"] == "The owner may approve up to $250."


def test_x_05_policy_needs_the_flow_confidence():
    r = call(
        "standingPolicy.save",
        {
            "pack": "industrial",
            "org_unit_id": "Customer A",
            "name": "Loose",
            "rules": {"max_value": 100, "min_confidence": 0.5},
            "owner": "admin",
        },
        "admin",
    )
    assert r["ok"] is False and r["error"]["message"] == "The policy needs at least the flow's 0.75 confidence."


def test_standing_policy_none_keeps_demo():
    ok(submit("RT-1048"))
    c = case_now("RT-1048")
    assert c["stage"] == "awaiting_approval" and c.get("submitted") and not c.get("approval")
    assert journal("decision.approveByPolicy") == []


def test_standing_policy_retired_approves_nothing():
    c = pick_case()
    shape(c["id"], 300)
    pid = activate(c["owner"])
    ok(call("standingPolicy.retire", {"id": pid, "reason": "No longer wanted by the board."}, "approver"))
    ok(submit(c["id"]))
    hold_stays(c["id"])


# ---------------------------------------------------------------- R21: the standing policy as an approvable object
def draft(org: str = "Customer A", user: str = "admin") -> str:
    out = ok(
        call(
            "standingPolicy.save",
            {"pack": "industrial", "org_unit_id": org, "name": "Standing", "rules": RULES, "owner": "admin"},
            user,
        )
    )
    ok(call("standingPolicy.submit", {"id": out["id"]}, user))
    return out["id"]


def test_standing_policy_maker_cannot_approve():
    pid = draft()
    r = call("standingPolicy.approve", {"id": pid}, "admin")  # Admin drafted and submitted it
    assert r["ok"] is False and r["error"]["code"] == "conflict" and r["error"]["message"] == MAKER_CHECKER
    assert ok(call("standingPolicy.approve", {"id": pid}, "approver"))["status"] == "active"


def test_standing_policy_agent_cannot_approve():
    pid = draft()
    assert forbidden("standingPolicy.approve") and forbidden("standingPolicy.retire")
    assert "standingPolicy.approve" in FORBIDDEN_ACTIONS and "standingPolicy.retire" in FORBIDDEN_ACTIONS
    for action, body in (
        ("standingPolicy.approve", {"id": pid}),
        ("standingPolicy.retire", {"id": pid, "reason": "An agent may not retire it."}),
    ):
        for confirmed in (False, True):
            with SessionLocal() as s:
                pctx = load_context(s)
                ctx = CallContext(
                    actor=Actor(account=policy.account("approver", pctx), ctx=pctx),
                    session=s,
                    preparer="coordinator",
                    confirmed=confirmed,
                )
                r = invoke(action, body, ctx)
                s.commit()
            assert r["ok"] is False and r["error"]["code"] == "approval_required", (action, confirmed, r)
    # an agent's draft is held for a person, not saved
    with SessionLocal() as s:
        pctx = load_context(s)
        ctx = CallContext(actor=Actor(account=policy.account("admin", pctx), ctx=pctx), session=s, preparer="coordinator")
        r = invoke(
            "standingPolicy.save",
            {"pack": "industrial", "org_unit_id": "Customer A", "name": "Agent", "rules": RULES, "owner": "admin"},
            ctx,
        )
        s.commit()
    assert r["ok"] is True and "held" in r["output"]
    assert (
        ok(call("standingPolicy.list", {"pack": "industrial", "org_unit_id": "Customer A"}, "admin"))["policies"][0]["status"]
        == "review"
    )


def test_standing_policy_agent_cannot_approve_by_policy_directly():
    c = pick_case()
    for ctx_kw in ({"preparer": "coordinator"}, {"preparer": "coordinator", "confirmed": True}):
        with SessionLocal() as s:
            pctx = load_context(s)
            ctx = CallContext(actor=Actor(account=policy.account("admin", pctx), ctx=pctx), session=s, **ctx_kw)
            r = invoke("decision.approveByPolicy", {"case_id": c["id"], "policy_id": "SP-1", "ver": 1}, ctx)
        assert r["ok"] is False and r["error"]["code"] in ("approval_required", "out_of_scope")
    r = call(
        "decision.approveByPolicy", {"case_id": c["id"], "policy_id": "SP-1", "ver": 1}, "admin"
    )  # a person is no system either
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"


def test_standing_policy_tenant_boundary(monkeypatch):
    pid = draft("Customer A")
    body = {"pack": "industrial", "org_unit_id": "Customer A", "name": "B", "rules": RULES, "owner": "admin"}
    # planner.b has no standing-policy permission at all ...
    for action, inp in (
        ("standingPolicy.save", body),
        ("standingPolicy.list", {"pack": "industrial", "org_unit_id": "Customer A"}),
        ("standingPolicy.approve", {"id": pid}),
    ):
        assert call(action, inp, "planner-b")["error"]["code"] == "out_of_scope", action
    # ... and were the permission granted, the org boundary refuses the org of another customer
    monkeypatch.setitem(policy.EXTRA_PERMS, "manageStandingPolicy", ("Admin", "Planner"))
    monkeypatch.setitem(policy.EXTRA_PERMS, "approve.standingPolicy", ("Admin", "Approver", "Planner"))
    for action, inp in (
        ("standingPolicy.save", body),
        ("standingPolicy.list", {"pack": "industrial", "org_unit_id": "Customer A"}),
        ("standingPolicy.submit", {"id": pid}),
        ("standingPolicy.approve", {"id": pid}),
    ):
        r = call(action, inp, "planner-b")
        assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", (action, r)
        assert r["error"]["message"] == "Customer A is a tenant you cannot see. Request tenant access first."


def test_standing_policy_one_active_per_pack_and_org():
    activate("Customer A")
    pid = draft("Customer A")
    r = call("standingPolicy.approve", {"id": pid}, "approver")
    assert r["ok"] is False and r["error"]["code"] == "conflict" and "retire it first" in r["error"]["message"]


def test_standing_policy_active_cannot_be_edited():
    pid = activate("Customer A")
    r = call(
        "standingPolicy.save",
        {"pack": "industrial", "org_unit_id": "Customer A", "name": "Edit", "rules": RULES, "owner": "admin", "id": pid},
        "admin",
    )
    assert r["ok"] is False and r["error"]["code"] == "conflict"


# ---------------------------------------------------------------- the pure core
def test_standing_rules_covers_and_problems():
    pack = load_pack("industrial")
    rules = parse_rules({"max_value": 500, "min_confidence": 0.75, "routes": ["redeploy"], "classes": None, "markets": ["US"]})
    assert isinstance(rules, StandingRules) and rules.routes == ("redeploy",)
    base: dict = dict(  # noqa: C408
        value=Decimal(300),
        confidence=0.9,
        route="redeploy",
        cls="motor",
        market="US",
        holds=[],
        open_exception=False,
        conflict=False,
        fraud_hold=False,
    )
    assert covers(rules, **base)
    for change in (
        {"value": Decimal(501)},
        {"confidence": 0.7},
        {"confidence": None},
        {"route": "recycle"},
        {"market": None},
        {"open_exception": True},
        {"conflict": True},
        {"fraud_hold": True},
    ):
        assert not covers(rules, **{**base, **change}), change
    assert rules_problem(rules, pack, Decimal("inf")) is None
    assert rules_problem(rules, pack, Decimal(250)) == "The owner may approve up to $250."
    assert isinstance(parse_rules({"max_value": -1, "min_confidence": 0.8}), str)
    assert isinstance(parse_rules({"max_value": 5, "min_confidence": 2}), str)
