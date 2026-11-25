"""P9-1.3 (I-4, story X-04; R21): the overlay actions (di.services.actions.overlays): save, submit, approve, return and
rebase, maker-checker, the audited compliance refusal, the three security tests of a new approvable object, and the live
pack a case is decided with."""

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories.live_rules import live_pack
from di.repositories.overlays import get as get_overlay
from di.services.agents.forbidden import forbidden
from di.services.modeler.pack import load_pack
from tests.helpers import call, client, h

MAKER_CHECKER = "Maker-checker: you made these changes, so you cannot approve them."
RECALL = Path(__file__).resolve().parent / "fixtures" / "packs" / "recall_test.json"
TIGHTEN = {"id": "op-1", "op": "tighten", "target": "GR-D2", "field": "floor", "value": 0.60, "seen": 0.55}
SKIP = {"id": "op-1", "op": "shortcut", "stage": "receive", "to": "condition",
        "when": [{"fact": "age", "op": "lte", "value": 3}]}  # fmt: skip


def _reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM domain_event WHERE type = 'overlay.blocked' OR type LIKE 'action.overlay.%'"))
        conn.execute(text("DELETE FROM action_journal WHERE action LIKE 'overlay.%'"))


@pytest.fixture(autouse=True)
def fresh():
    _reset()
    yield
    _reset()


def _body(org: str = "Customer A", pack: str = "device", *ops: dict) -> dict:
    return {"pack_key": pack, "org_unit_id": org, "ops": list(ops or [TIGHTEN])}


def _ref(org: str = "Customer A", pack: str = "device") -> dict:
    return {"pack_key": pack, "org_unit_id": org}


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def _row(org: str = "Customer A", pack: str = "device"):
    with SessionLocal() as s:
        return get_overlay(s, pack, org)


def _publish(org: str = "Customer A", pack: str = "device", *ops: dict) -> None:
    ok(call("overlay.save", _body(org, pack, *ops), "planner-a" if org == "Customer A" else "admin"))
    ok(call("overlay.submit", _ref(org, pack), "planner-a" if org == "Customer A" else "admin"))
    ok(call("overlay.approve", _ref(org, pack), "approver"))


def test_x_04_lifecycle_save_submit_approve():
    out = ok(call("overlay.save", _body(), "planner-a"))
    assert out["status"] == "draft"
    row = _row()
    assert (row.status, row.maker, row.ver, row.published) == ("draft", "planner-a", 0, [])
    assert row.draft == [TIGHTEN | {"by": "planner-a", "note": ""}] and row.draft_base_version == "2.7.0"
    assert ok(call("overlay.submit", _ref(), "planner-a"))["status"] == "review"
    assert ok(call("overlay.approve", _ref(), "approver"))["status"] == "pub"
    row = _row()
    assert (row.status, row.ver, row.draft, row.base_version) == ("pub", 1, None, "2.7.0")
    assert row.published[0]["value"] == 0.60 and row.checker == "approver"


def test_x_04_save_refuses_weakening_with_the_ops_id():
    weak = TIGHTEN | {"value": 0.50}
    r = call("overlay.save", _body("Customer A", "device", weak), "planner-a")
    assert r["ok"] is False
    assert r["error"] == {
        "code": "validation_error", "message": "GR-D2 can only be tightened: floor 0.55 → 0.5 weakens it.",
        "op_id": "op-1", "overlay_code": "weakens",
    }  # fmt: skip
    assert _row() is None  # nothing was saved


def test_x_04_compliance_skip_audited(monkeypatch):
    monkeypatch.setattr("di.services.actions.overlays.load_pack", lambda key: _recall_pack())
    r = call("overlay.save", _body("Customer A", "tool_fleet", SKIP), "planner-a")
    assert r["error"]["code"] == "validation_error" and r["error"]["overlay_code"] == "skips_compliance"
    assert r["error"]["message"] == "Blocked: this skips the compliance guardrail Safety recall check at Match and verify."
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT payload FROM domain_event WHERE type = 'overlay.blocked'")).all()
    assert len(rows) == 1
    p = rows[0].payload
    assert (p["guardrail"], p["by"], p["pack_key"], p["org_unit_id"]) == ("G-TOOL-REC", "planner-a", "tool_fleet", "Customer A")
    assert p["op"]["id"] == "op-1" and _row("Customer A", "tool_fleet") is None  # the draft is unchanged


def _recall_pack():
    from di.services.modeler.pack import parse_pack

    return parse_pack(json.loads(RECALL.read_text(encoding="utf-8")))


def test_overlay_maker_cannot_approve():
    ok(call("overlay.save", _body(), "admin"))
    ok(call("overlay.submit", _ref(), "admin"))
    r = call("overlay.approve", _ref(), "admin")
    assert r == {"ok": False, "error": {"code": "conflict", "message": MAKER_CHECKER}}
    assert _row().status == "review"
    assert ok(call("overlay.approve", _ref(), "approver"))["status"] == "pub"


def test_overlay_maker_who_only_submitted_cannot_approve():
    ok(call("overlay.save", _body(), "planner-a"))
    ok(call("overlay.submit", _ref(), "admin"))  # admin submitted planner-a's draft
    assert call("overlay.approve", _ref(), "admin")["error"]["message"] == MAKER_CHECKER
    assert call("overlay.approve", _ref(), "approver")["ok"]


def test_overlay_agent_cannot_approve():
    assert forbidden("overlay.approve") and forbidden("overlay.reject")
    ok(call("overlay.save", _body(), "planner-a"))
    ok(call("overlay.submit", _ref(), "planner-a"))
    for action, body in (("overlay.approve", _ref()), ("overlay.reject", _ref() | {"reason": "Not for this quarter, sorry."})):
        for extra in ({}, {"X-Circularity-Confirmed": "true"}):
            hdr = h("approver") | {"X-Circularity-Preparer": "coordinator"} | extra
            r = client.post(f"/api/actions/{action}", json=body, headers=hdr)
            assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required", (action, r.json())
    assert _row().status == "review"


def test_overlay_tenant_boundary():
    r = call("overlay.save", _body("Customer B"), "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    assert r["error"]["message"] == "Customer B is a tenant you cannot see. Request tenant access first."
    ok(call("overlay.save", _body("Customer B"), "admin"))
    for action in ("overlay.submit", "overlay.rebase"):
        assert call(action, _ref("Customer B"), "planner-a")["error"]["code"] == "tenant_boundary", action
    ok(call("overlay.submit", _ref("Customer B"), "admin"))
    assert call("overlay.reject", _ref("Customer B") | {"reason": "A reason long enough."}, "planner-a")["ok"] is False
    assert _row("Customer B").status == "review"


def test_x_04_return_goes_back_to_the_maker_with_the_reason():
    ok(call("overlay.save", _body(), "planner-a"))
    ok(call("overlay.submit", _ref(), "planner-a"))
    short = call("overlay.reject", _ref() | {"reason": "no"}, "approver")
    assert short["error"]["code"] == "validation_error"
    ok(call("overlay.reject", _ref() | {"reason": "Floor too high for this quarter."}, "approver"))
    row = _row()
    assert row.status == "draft" and row.notes == ["Returned by approver: Floor too high for this quarter."]
    assert call("overlay.approve", _ref(), "approver")["error"]["code"] == "conflict"  # not in review any more


def test_x_04_save_after_publish_starts_a_new_draft_and_keeps_the_published_ops():
    _publish()
    ok(call("overlay.save", _body("Customer A", "device", TIGHTEN | {"value": 0.65}), "planner-a"))
    row = _row()
    assert (row.status, row.ver) == ("draft", 1)
    assert row.published[0]["value"] == 0.60 and row.draft[0]["value"] == 0.65


def test_x_04_rebase_needs_a_newer_pack_and_makes_a_draft(monkeypatch):
    _publish()
    assert call("overlay.rebase", _ref(), "planner-a")["error"] == {"code": "conflict", "message": "Already on 2.7.0."}
    newer = load_pack("device")
    gs = [
        g.model_copy(update={"param": g.param.model_copy(update={"value": 0.65})}) if g.id == "GR-D2" and g.param else g
        for g in newer.guardrails
    ]
    newer = newer.model_copy(update={"guardrails": gs, "version": "2.8.0"})
    monkeypatch.setattr("di.services.actions.overlays.load_pack", lambda key: newer)
    out = ok(call("overlay.rebase", _ref(), "planner-a"))
    assert out["notes"] == ["GR-D2: the pack is now stricter (0.65); your change is no longer needed."]
    row = _row()
    assert (row.status, row.draft, row.draft_base_version, row.maker) == ("draft", [], "2.8.0", "planner-a")
    assert row.published[0]["value"] == 0.60  # what runs does not change until the draft is approved


def test_x_04_unresolved_conflicts_block_submit(monkeypatch):
    _publish()
    base = load_pack("device")
    newer = base.model_copy(update={"guardrails": [g for g in base.guardrails if g.id != "GR-D2"], "version": "2.8.0"})
    monkeypatch.setattr("di.services.actions.overlays.load_pack", lambda key: newer)
    out = ok(call("overlay.rebase", _ref(), "planner-a"))
    assert [c["kind"] for c in out["conflicts"]] == ["target_gone"]
    r = call("overlay.submit", _ref(), "planner-a")
    assert r["error"] == {"code": "conflict", "message": "Resolve the conflicts before submitting."}
    ok(call("overlay.save", _body("Customer A", "device") | {"ops": [], "resolved": ["op-1"]}, "planner-a"))
    assert _row().conflicts == [] and ok(call("overlay.submit", _ref(), "planner-a"))["status"] == "review"


def test_x_04_permissions():
    assert call("overlay.save", _body(), "approver")["error"]["code"] == "out_of_scope"
    ok(call("overlay.save", _body(), "planner-a"))
    ok(call("overlay.submit", _ref(), "planner-a"))
    assert call("overlay.approve", _ref(), "planner-a")["error"]["code"] == "out_of_scope"


def _floor(pack) -> float:
    return next(g.param.value for g in pack.guardrails if g.id == "GR-D2" and g.param)


def test_live_pack_applies_published_overlay():
    _publish()
    with SessionLocal() as s:
        a = live_pack(s, {"template": "device", "owner": "Customer A"})
        b = live_pack(s, {"template": "device", "owner": "Customer B"})
    assert (_floor(a), _floor(b)) == (0.60, 0.55)
    assert _floor(load_pack("device")) == 0.55  # the pack itself is never changed


def test_live_pack_walks_up_to_the_nearest_published_overlay():
    ok(call("overlay.save", _body("workspace", "device", TIGHTEN | {"value": 0.70}), "admin"))
    ok(call("overlay.submit", _ref("workspace"), "admin"))
    ok(call("overlay.approve", _ref("workspace"), "approver"))
    with SessionLocal() as s:
        assert _floor(live_pack(s, {"template": "device", "owner": "Customer B"})) == 0.70
    _publish()
    with SessionLocal() as s:
        assert _floor(live_pack(s, {"template": "device", "owner": "Customer A"})) == 0.60  # the nearest wins


def test_x_04_modeler_screen_carries_the_orgs_overlay():
    url = "/api/screens/modeler"
    none = client.get(url, params={"template": "device", "org": "Customer A"}, headers=h("planner-a")).json()["overlay"]
    assert (none["status"], none["ops"], none["can"], none["in_force"], none["stale"]) == (
        "none", [], {"edit": True, "approve": False}, None, False,
    )  # fmt: skip
    assert none["pack_version"] == "2.7.0"
    g = next(x for x in none["guardrails"] if x["id"] == "GR-D2")
    assert g["param"] == {"field": "floor", "value": 0.55, "stricter": "higher", "min": 0.3, "max": 0.9}
    _publish()
    got = client.get(url, params={"template": "device", "org": "Customer A"}, headers=h("approver")).json()["overlay"]
    assert (got["status"], got["ver"], got["in_force"], got["can"]) == (
        "pub", 1, {"org_unit_id": "Customer A", "ver": 1}, {"edit": False, "approve": True},
    )  # fmt: skip
    assert got["ops"][0]["value"] == 0.60 and got["ops"][0]["by"] == "planner-a"
