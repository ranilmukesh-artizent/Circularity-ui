"""P9-8.17 (G C8, C12; R21): the composition object, one approvable thing made of the description's change set, the mapping
rows and the stage-agent settings, with maker-checker. The pure core (`di.services.modeler.compose`) and the actions
(`di.services.actions.compose`) through the pipeline. Every model is absent here (the deterministic path, R16)."""

import json

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.agents import runtime
from di.services.agents.forbidden import forbidden
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.modeler import compose as core
from di.services.modeler.overlay import parse_ops
from di.services.modeler.pack import load_pack
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

MAKER_CHECKER = "Maker-checker: you composed this, so you cannot approve it."
SID = "insp"
ROW = ["audit_data.status", "", "condition.inspection_status", "", "upper"]
ORG = "Customer A"


def _reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM composition_version"))
        conn.execute(text("DELETE FROM composition"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM field_mapping WHERE source_id = :s"), {"s": SID})
        conn.execute(text("DELETE FROM agent_proposal WHERE requested_by IN ('planner-a', 'admin')"))
        mine = "SELECT seq FROM action_journal WHERE action LIKE 'compose.%' OR action LIKE 'overlay.%'"
        conn.execute(text(f"DELETE FROM domain_event WHERE seq IN ({mine})"))  # noqa: S608 - a fixed string
        conn.execute(text(f"DELETE FROM action_journal WHERE seq IN ({mine})"))  # noqa: S608


@pytest.fixture(autouse=True)
def fresh():
    _reset()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path
    yield
    runtime.set_loop(None)
    _reset()


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def _prompt() -> str:
    return load_pack("tool_fleet").prompts[0]


def _start(user: str = "planner-a", org: str = ORG) -> dict:
    return call("compose.start", {"org_unit_id": org, "text": _prompt(), "pack_key": "tool_fleet"}, user)


def _row(cid: int) -> dict:
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT * FROM composition WHERE id = :i"), {"i": cid}).mappings().one())


def _set_steps(cid: int, extra: dict) -> None:
    """Stands in for the page work of P9-8.18/8.20 that fills the mapping rows and the stage settings."""
    with engine.begin() as conn:
        for step, body in extra.items():
            conn.execute(
                text("UPDATE composition SET steps = jsonb_set(steps, ARRAY[:k], steps->:k || CAST(:b AS jsonb)) WHERE id = :i"),
                {"k": step, "b": json.dumps(body), "i": cid},
            )


def _ready(user: str = "planner-a", org: str = ORG, submit: bool = True) -> int:
    """A composition with the question answered and the three steps done; submitted by `user` when asked."""
    out = ok(_start(user, org))
    cid = out["id"]
    qid = out["change_set"]["question"]["options"][0]["id"]
    ok(call("compose.answer", {"id": cid, "answer": qid}, user))
    _set_steps(cid, {
        "mapping": {"fields": [{"source_id": SID, "row": ROW, "state": "accepted"}]},
        "agents": {"settings": [{"stage": "condition", "autonomy": "limits", "threshold": 0.7}]},
    })  # fmt: skip
    for step in ("describe", "mapping", "agents"):
        ok(call("compose.markStep", {"id": cid, "step": step}, user))
    if submit:
        ok(call("compose.submit", {"id": cid}, user))
    return cid


# ---------------------------------------------------------------- the pure core
def test_c8_blocking_names_what_is_left():
    pack = load_pack("tool_fleet")
    steps = core.new_steps()
    assert core.blocking(steps, [], pack) == [
        "Step describe is not done.", "Step mapping is not done.", "Step agents is not done."
    ]  # fmt: skip
    for s in ("describe", "mapping", "agents"):
        steps[s]["state"] = "done"
    assert core.blocking(steps, [], pack) == []
    steps["mapping"]["fields"] = [{"source_id": SID, "row": ROW, "state": "asked_owner"}]
    assert core.blocking(steps, [], pack) == [f"A mapping field ({ROW[0]} of {SID}) is still waiting for its owner."]
    steps["mapping"]["fields"] = []
    steps["agents"]["settings"] = [{"stage": "condition", "autonomy": "alone", "threshold": 0.9}]
    assert core.blocking(steps, [], pack) == ["The condition confidence threshold 0.9 is outside 0.65 to 0.85."]


def test_c8_blocking_refuses_a_weaker_overlay():
    pack = load_pack("device")
    weak = parse_ops([{"id": "op-1", "op": "tighten", "target": "GR-D2", "field": "floor", "value": 0.10, "seen": 0.55}])
    steps = core.new_steps()
    for s in ("describe", "mapping", "agents"):
        steps[s]["state"] = "done"
    left = core.blocking(steps, weak, pack)
    assert len(left) == 1 and left[0].startswith("The changes do not validate")


# ---------------------------------------------------------------- the actions
def test_composition_start_drafts_change_set():
    out = ok(_start())
    cs = out["change_set"]
    assert out["status"] == "draft" and cs["pack"] == "tool_fleet"
    assert cs["question"] is not None and len(cs["question"]["options"]) == 2
    row = _row(out["id"])
    assert row["reading"]["word_count"] > 0 and row["status"] == "draft" and row["created_by"] == "planner-a"
    assert row["pack_key"] == "tool_fleet" and row["org_unit_id"] == ORG
    assert {k: v["state"] for k, v in row["steps"].items()} == dict.fromkeys(core.STEPS, "todo")
    assert ok(call("compose.get", {"id": out["id"]}, "approver"))["id"] == out["id"]
    assert [c["id"] for c in ok(call("compose.list", {"org_unit_id": ORG}, "planner-a"))["compositions"]] == [out["id"]]


def test_composition_answer_redrafts_without_a_second_question():
    out = ok(_start())
    qid = out["change_set"]["question"]["options"][0]["id"]
    again = ok(call("compose.answer", {"id": out["id"], "answer": qid}, "planner-a"))
    assert again["change_set"]["question"] is None and again["change_set"]["answer"] == qid


def test_composition_submit_blocked_until_steps_done():
    cid = ok(_start())["id"]
    ok(call("compose.markStep", {"id": cid, "step": "describe"}, "planner-a"))
    r = call("compose.submit", {"id": cid}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "conflict"
    assert r["error"]["blocking"] == ["Step mapping is not done.", "Step agents is not done."]
    assert _row(cid)["status"] == "draft"


def test_composition_submit_snapshots_and_sets_the_submitter():
    cid = _ready()
    row = _row(cid)
    assert row["status"] == "submitted" and row["submitted_by"] == "planner-a" and row["version"] == 2
    with SessionLocal() as s:
        snap = s.execute(text("SELECT status, snapshot FROM composition_version WHERE composition_id = :i"), {"i": cid}).one()
    assert snap.status == "submitted" and snap.snapshot["change_set"]["pack"] == "tool_fleet"


def test_composition_send_back_pins_step():
    cid = _ready()
    short = call("compose.sendBack", {"id": cid, "step": "agents", "reason": "too short"}, "approver")
    assert short["error"]["code"] == "validation_error"
    ok(call("compose.sendBack", {"id": cid, "step": "agents", "node_id": "stage:condition",
                                 "reason": "The condition threshold is too low for this unit."}, "approver"))  # fmt: skip
    row = _row(cid)
    assert row["status"] == "sent_back" and row["steps"]["agents"]["state"] == "sent_back"
    note = row["steps"]["agents"]["note"]
    assert note["node_id"] == "stage:condition" and note["by"] == "approver" and "threshold" in note["reason"]
    assert "approver" not in row["editors"]
    blocked = call("compose.submit", {"id": cid}, "planner-a")  # the sent-back step must be marked done again
    assert blocked["error"]["blocking"] == ["Step agents is not done."]


def test_composition_maker_cannot_approve():
    # the creator is also the checker's account (Admin holds both permissions)
    c1 = _ready("admin")
    r = call("compose.approve", {"id": c1}, "admin")
    assert r == {"ok": False, "error": {"code": "conflict", "message": MAKER_CHECKER}}
    # the submitter
    c2 = _ready("planner-a", submit=False)
    ok(call("compose.submit", {"id": c2}, "admin"))
    assert call("compose.approve", {"id": c2}, "admin")["error"]["message"] == MAKER_CHECKER
    # an editor
    c3 = _ready("planner-a", submit=False)
    ok(call("compose.editChangeSet", {"id": c3, "ops": _row(c3)["change_set"]["ops"]}, "admin"))
    ok(call("compose.submit", {"id": c3}, "planner-a"))
    assert call("compose.approve", {"id": c3}, "admin")["error"]["message"] == MAKER_CHECKER
    assert all(_row(c)["status"] == "submitted" for c in (c1, c2, c3))
    # a person who made none of it
    out = ok(call("compose.approve", {"id": c3}, "approver"))
    assert out["status"] == "approved"
    row = _row(c3)
    assert row["status"] == "approved" and row["approved_by"] == "approver"
    with SessionLocal() as s:
        ov = s.execute(text("SELECT status, checker, maker, published FROM customer_overlay WHERE pack_key = 'tool_fleet'")).one()
        ver = s.execute(text("SELECT count(*) FROM field_mapping WHERE source_id = :s"), {"s": SID}).scalar_one()
        snap = s.execute(
            text("SELECT snapshot FROM composition_version WHERE composition_id = :i AND status = 'approved'"), {"i": c3}
        ).scalar_one()
    assert (ov.status, ov.checker, ov.maker) == ("pub", "approver", "planner-a") and ov.published
    assert ver >= 1
    assert snap["steps"]["agents"]["settings"] == [{"stage": "condition", "autonomy": "limits", "threshold": 0.7}]


def test_composition_agent_cannot_approve():
    assert forbidden("compose.sendBack") and forbidden("compose.approve") and forbidden("compose.publish")
    cid = _ready()
    for action, body in (("compose.sendBack", {"id": cid, "step": "agents", "reason": "Not for this quarter, sorry."}),
                         ("compose.approve", {"id": cid})):  # fmt: skip
        for extra in ({}, {"X-Circularity-Confirmed": "true"}):
            hdr = h("approver") | {"X-Circularity-Preparer": "coordinator"} | extra
            r = client.post(f"/api/actions/{action}", json=body, headers=hdr)
            assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required", (action, r.json())
    assert _row(cid)["status"] == "submitted"
    hdr = h("planner-a") | {"X-Circularity-Preparer": "coordinator"}
    started = client.post("/api/actions/compose.start", json={"org_unit_id": ORG, "text": _prompt()}, headers=hdr).json()
    assert started["ok"] is True  # a draft: allowed (an agent at a lower autonomy is held as a proposal)


def test_composition_tenant_boundary():
    r = _start("planner-a", "Customer B")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    assert r["error"]["message"] == "Customer B is a tenant you cannot see. Request tenant access first."
    cid = _ready("admin", "Customer B")
    for action, body in (("compose.get", {"id": cid}), ("compose.markStep", {"id": cid, "step": "describe"})):
        assert call(action, body, "planner-a")["error"]["code"] == "tenant_boundary", action
    assert ok(call("compose.approve", {"id": cid}, "approver"))["status"] == "approved"


def test_composition_approve_is_atomic(monkeypatch):
    from di.services.actions import compose as actions

    def boom(*_a, **_k):
        raise ValueError("Row 1: the save failed.")

    monkeypatch.setattr(actions.mapping, "save_version", boom)
    cid = _ready()
    r = call("compose.approve", {"id": cid}, "approver")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM customer_overlay WHERE status = 'pub'")).scalar_one() == 0
    row = _row(cid)
    assert row["status"] == "submitted" and row["approved_by"] is None


# ---------------------------------------------------------------- P9-8.18: the systems of a composition
def _systems(cid: int, user: str = "planner-a") -> dict[str, dict]:
    return {s["name"]: s for s in ok(call("compose.systems", {"id": cid}, user))["systems"]}


def _repair_log(systems: dict[str, dict]) -> dict:
    return next(s for n, s in systems.items() if "repair log" in n.lower())


def _clean_connections() -> None:
    with engine.begin() as c:
        made = list(c.execute(text("SELECT source_id FROM source_connection WHERE registry_id IS NOT NULL")).scalars())
        for t in ("sync_run", "fetch_log", "raw_record", "sync_cursor", "source_connection", "source_secret", "field_mapping"):
            c.execute(text(f"DELETE FROM {t} WHERE source_id = ANY(:i)"), {"i": made})  # noqa: S608 - fixed names
        c.execute(text("DELETE FROM source_system WHERE id = ANY(:i)"), {"i": made})
        c.execute(text("DELETE FROM connection_approval"))
        c.execute(text("DELETE FROM work_item WHERE type LIKE 'connection_approval%'"))
        c.execute(text("DELETE FROM adapter_registry"))
        c.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))


@pytest.fixture
def connections():
    _clean_connections()
    yield
    _clean_connections()


def test_composition_systems_status(connections):
    cid = ok(_start())["id"]
    systems = _systems(cid)
    log = _repair_log(systems)
    assert (log["status"], log["source_id"]) == ("needs_adapter", None)
    assert set(log["mapping"]) == {"fields", "pre_ticked", "check", "none", "asked_owner"}
    entry = {"id": "depot-log", "kind": "from_spec", "system_type": "repairlog", "vendor_family": "Depot", "org_unit_id": ORG}
    ok(call("registry.saveEntry", {"entry": entry}, "developer"))
    assert _repair_log(_systems(cid))["registry"] == ["depot-log"]  # the org's draft is offered
    body = {"registry_id": "depot-log", "version": 1, "name": "Depot repair log test", "org_unit_id": ORG,
            "system_owner": "approver", "test_base_url": "https://depot.example.test/api"}  # fmt: skip
    sid = ok(call("connection.create", body, "developer"))["source_id"]
    log = _repair_log(_systems(cid))
    assert (log["status"], log["source_id"]) == ("test_connection", sid)
    ok(call("connection.requestOwner", {"source_id": sid, "environment": "production", "access": "read"}, "developer"))
    assert _repair_log(_systems(cid))["status"] == "awaiting_owner"


def test_composition_systems_reach_and_role():
    cid = _ready("admin", "Customer B", submit=False)
    assert call("compose.systems", {"id": cid}, "planner-a")["error"]["code"] == "tenant_boundary"
    assert call("compose.systems", {"id": cid}, "exec")["error"]["code"] == "out_of_scope"
    assert call("compose.systems", {"id": 99999}, "admin")["error"]["code"] == "not_found"


def test_composition_prompts_are_the_packs_own():
    out = ok(call("compose.prompts", {"pack_key": "tool_fleet"}, "planner-a"))
    assert out["prompts"] == load_pack("tool_fleet").prompts and len(out["prompts"]) == 3
    assert call("compose.prompts", {"pack_key": "nope"}, "planner-a")["error"]["code"] == "not_found"
