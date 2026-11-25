"""P9-1.7 (I-20; enabler for X-08, X-05, TF-09): the case process layer. Items with an owner role and a due time, the SLA
timer (`work.sla`, escalation by the pack's `runtime.escalate_to`), "needs info" questions and the gate hold's exception
item. Tests call `process.on_sla` directly: the database clock does not move with the pinned one. Every test ends with the
starting state."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di import worker
from di.core import clock, policy
from di.core.auth import load_context
from di.core.db import SessionLocal
from di.services.actions.pipeline import Actor, CallContext
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key
from di.services.canonical.store import Fact
from di.services.cases import gate_hold, intake, process, store
from di.services.modeler.pack import Pack, load_pack, parse_pack
from tests import starting
from tests.helpers import call, client, h

A_CASE = "RT-1051"  # Customer A
EVIDENCE_PACK = Path(__file__).resolve().parent / "fixtures" / "packs" / "evidence_test.json"
LOT = {"brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B", "ref": 315, "qty": 40, "doh": 12, "batch": "B-9"}


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM work_item"))
        s.execute(text("DELETE FROM provenance WHERE model = 'compliance'"))
        s.execute(text("DELETE FROM canonical WHERE model = 'compliance'"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    _clean()
    starting.reset()
    yield
    _clean()
    starting.reset()


def _open(**kw: Any) -> int:
    base: dict[str, Any] = {
        "kind": "exception", "case_id": A_CASE, "org_unit_id": "Customer A", "type": "evidence_missing",
        "title": "Wipe certificate missing", "cause": "No certificate", "action": "Chase the source",
        "owner_role": "Planner", "due_hours": None, "by": "system",
    }  # fmt: skip
    with SessionLocal() as s:
        item = process.open_item(s, **(base | kw))
        s.commit()
    return item


def _row(item_id: int) -> dict[str, Any]:
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT * FROM work_item WHERE id = :i"), {"i": item_id}).mappings().one())


def _ctx(s, account_id: str) -> CallContext:
    pctx = load_context(s)
    return CallContext(actor=Actor(account=policy.account(account_id, pctx), ctx=pctx), session=s)


def _journal(action: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        return [
            dict(r)
            for r in s.execute(text("SELECT * FROM action_journal WHERE action = :a ORDER BY seq"), {"a": action}).mappings()
        ]


def test_sla_timer_escalates_overdue():
    due = _open(due_hours=-1)  # due an hour ago
    later = _open(title="Not yet due", due_hours=5)
    with SessionLocal() as s:
        assert process.on_sla(s, due) == "escalated"
        assert process.on_sla(s, later) == "not_due"
        s.commit()
    r = _row(due)
    assert r["priority"] == 50 and r["owner_role"] == "Approver" and r["escalated_at"] is not None and r["status"] == "open"
    j = _journal("work.escalate")
    assert len(j) == 1 and j[0]["actor"] == "system" and j[0]["case_id"] == A_CASE
    assert j[0]["input"]["log"].startswith("Escalated: Wipe certificate missing, due ")
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM domain_event WHERE type = 'work.escalated'")).scalar_one() == 1
    n = _row(later)
    assert n["priority"] == 100 and n["owner_role"] == "Planner" and n["escalated_at"] is None


def test_open_item_with_due_hours_queues_one_sla_job():
    item = _open(due_hours=24)
    r = _row(item)
    assert r["due_at"] == clock.now() + timedelta(hours=24)
    with SessionLocal() as s:
        rows = s.execute(text("SELECT payload, dedupe_key, run_after FROM job WHERE kind = 'work.sla'")).all()
    assert [(p, k) for p, k, _ in rows] == [({"item_id": item}, f"work.sla:{item}")]
    assert rows[0][2] > r["due_at"]  # run_after is on the database clock (R-fix: the pinned workspace clock is in the past)
    assert "work.sla" in worker.HANDLERS
    worker.HANDLERS["work.sla"]({"item_id": item})  # not due yet at the pinned clock: nothing changes
    assert _row(item)["priority"] == 100
    no_timer = _open(title="No timer")
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM job WHERE dedupe_key = :k"), {"k": f"work.sla:{no_timer}"}).scalar_one() == 0


def test_r13_sla_job_waits_on_database_clock_and_escalates_once_due(monkeypatch):
    item = _open(due_hours=24)
    with SessionLocal() as s:
        db_now = s.execute(text("SELECT now()")).scalar_one()
        run_after = s.execute(text("SELECT run_after FROM job WHERE dedupe_key = :k"), {"k": f"work.sla:{item}"}).scalar_one()
    assert run_after >= db_now + timedelta(hours=23)  # the job does not run at once
    with SessionLocal() as s:
        assert process.on_sla(s, item) == "not_due"
        s.commit()
    assert _row(item)["escalated_at"] is None
    with SessionLocal() as s:  # a fresh job waits for the due time, on the database clock again
        later = (
            s.execute(
                text("SELECT run_after FROM job WHERE kind = 'work.sla' AND status = 'queued' AND dedupe_key <> :k"),
                {"k": f"work.sla:{item}"},
            )
            .scalars()
            .all()
        )
    assert len(later) == 1 and later[0] >= db_now + timedelta(hours=23)
    start = clock.now()
    monkeypatch.setattr(clock, "now", lambda: start + timedelta(hours=25))
    with SessionLocal() as s:
        assert process.on_sla(s, item) == "escalated"
        s.commit()
    assert _row(item)["escalated_at"] is not None


def test_sla_on_closed_item_is_closed():
    item = _open(due_hours=-1)
    with SessionLocal() as s:
        process.close_item(s, item, "released", "admin")
        assert process.on_sla(s, item) == "closed"
        s.commit()
    r = _row(item)
    assert r["status"] == "done" and r["outcome"] == "released" and r["closed_by"] == "admin" and r["priority"] == 100


def test_escalation_never_approves():
    before = _case_view()
    item = _open(due_hours=-1)
    with SessionLocal() as s:
        assert process.on_sla(s, item) == "escalated"
        s.commit()
    assert _case_view() == before
    assert _journal("decision.approve") == []


def _case_view() -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, A_CASE)
    assert c is not None
    return {"stage": c["stage"], "approval": c.get("approval"), "submitted": c.get("submitted"), "decision": c.get("decision")}


def test_needs_info_round_trip():
    r = call("case.needInfo", {"case_id": A_CASE, "question": "Which site holds the unit?", "to_role": "Engineer"}, "planner-a")
    assert r["ok"] is True, r
    item = int(r["output"]["id"])
    row = _row(item)
    assert (
        row["kind"] == "needs_info" and row["owner_role"] == "Engineer" and row["case_id"] == A_CASE and row["status"] == "open"
    )
    assert row["org_unit_id"] == "Customer A" and row["due_at"] is not None  # the pack's needs_info SLA (48 h)
    assert row["due_at"] == clock.now() + timedelta(hours=48)
    other = call("work.resolve", {"item_id": item, "outcome": "answered", "note": "x"}, "planner-a")
    assert other["ok"] is False and other["error"]["message"] == "This item is for Engineer."
    done = call("work.resolve", {"item_id": item, "outcome": "answered", "note": "Warehouse 1"}, "engineer")
    assert done["ok"] is True, done
    row = _row(item)
    assert row["status"] == "done" and row["outcome"] == "answered" and row["closed_by"] == "engineer"
    with SessionLocal() as s:
        c = store.get(s, A_CASE)
    assert c is not None
    assert [n["text"] for n in c["caseNotes"]] == ["Answer to 'Which site holds the unit?': Warehouse 1"]
    again = call("work.resolve", {"item_id": item, "outcome": "answered"}, "engineer")
    assert again["ok"] is False and again["error"]["code"] == "conflict"


def test_needs_info_is_case_scoped_and_checks_the_role():
    bad_role = call("case.needInfo", {"case_id": A_CASE, "question": "Why is the lot held?", "to_role": "Wizard"}, "planner-a")
    assert bad_role["ok"] is False and bad_role["error"]["code"] == "validation_error"
    b_case = _case_of("Customer B")
    other_tenant = call(
        "case.needInfo", {"case_id": b_case, "question": "Why is the lot held?", "to_role": "Engineer"}, "planner-a"
    )
    assert other_tenant["ok"] is False and other_tenant["error"]["code"] == "tenant_boundary"


def _case_of(owner: str) -> str:
    with SessionLocal() as s:
        return str(next(c["id"] for c in store.all_cases(s) if c["owner"] == owner))


def test_work_assign_by_owner_or_admin():
    item = _open(owner_role="Planner")
    refused = call("work.assign", {"item_id": item, "account": "planner-a"}, "approver")
    assert refused["ok"] is False and refused["error"]["message"] == "This item is for Planner."
    ok = call("work.assign", {"item_id": item, "account": "planner-a"}, "planner-a")
    assert ok["ok"] is True, ok
    assert _row(item)["owner_account"] == "planner-a"
    admin = call("work.assign", {"item_id": item, "account": "planner-c"}, "admin")
    assert admin["ok"] is True and _row(item)["owner_account"] == "planner-c"
    nobody = call("work.assign", {"item_id": item, "account": "nobody"}, "admin")
    assert nobody["ok"] is False and nobody["error"]["code"] == "not_found"


def test_items_routed_by_role_and_tenant():
    b_case = _case_of("Customer B")
    a = _open(title="A planner item")
    _open(title="B planner item", case_id=b_case, org_unit_id="Customer B")
    appr = _open(title="Approver item", owner_role="Approver")
    mine = _open(title="Assigned to the engineer", owner_role="Approver", owner_account="engineer")
    with SessionLocal() as s:
        planner = {w.id for w in process.items_for(s, _ctx(s, "planner-a")) if w.kind == "exception"}
        approver = {w.id for w in process.items_for(s, _ctx(s, "approver")) if w.kind == "exception"}
        engineer = {w.id for w in process.items_for(s, _ctx(s, "engineer")) if w.kind == "exception"}
        wm = [w for w in process.items_for(s, _ctx(s, "wm-1")) if w.kind == "exception"]
    assert planner == {f"w:{a}"}  # Customer A only
    assert approver == {f"w:{appr}", f"w:{mine}"}
    assert engineer == {f"w:{mine}"}  # assigned to them whatever the role
    assert wm == []  # no Planner items for a Warehouse Manager


def test_work_resolve_forbidden_to_agents():
    assert forbidden("work.resolve") and forbidden("work.assign")
    item = _open()
    agent = {"id": "ext-work", "name": "Work helper", "tools": ["request_missing_evidence"], "autonomy": "act"}
    assert call("agent.register", agent, "admin")["ok"] is True
    hdr = h("planner-a") | {"X-Circularity-Preparer": "ext-work"}
    for action, body in (
        ("work.resolve", {"item_id": item, "outcome": "done"}),
        ("work.assign", {"item_id": item, "account": "planner-a"}),
    ):
        r = client.post(f"/api/actions/{action}", json=body, headers=hdr).json()
        assert r["ok"] is False and r["error"]["code"] == "approval_required", r
    assert _row(item)["status"] == "open"
    ok = client.post(
        "/api/actions/case.needInfo",
        json={"case_id": A_CASE, "question": "Why is the lot held?", "to_role": "Engineer"},
        headers=hdr,
    ).json()
    assert ok["ok"] is True  # an agent may ask a question: it only opens an item


def test_gate_hold_opens_exception_item():
    pack: Pack = parse_pack(json.loads(EVIDENCE_PACK.read_text(encoding="utf-8")))
    real = gate_hold.default_pack_of
    gate_hold.default_pack_of = lambda case: pack if case.get("template") == "device" else load_pack(case["template"])  # type: ignore[assignment]
    try:
        with SessionLocal() as s:
            asset = {"org_unit_id": "Customer A", "template_key": "device", "asset_key": "LOT-9"}
            asset |= {"reason": "manual", "facts": LOT}
            c = intake.open_case(s, asset, "admin")
            s.commit()
        cid = str(c["id"])
        with SessionLocal() as s:
            items = [dict(r) for r in s.execute(text("SELECT * FROM work_item WHERE case_id = :c"), {"c": cid}).mappings()]
        assert len(items) == 1 and items[0]["kind"] == "exception" and items[0]["type"] == "evidence_missing"
        assert items[0]["status"] == "open" and items[0]["action"].startswith("Wait for ")
        key = compliance_key("LOT-9", "data_wipe")
        row = {"asset_key": "LOT-9", "type": "data_wipe", "result": "pass", "method": "purge", "tool": "wipe 4.2", "ref": "WC-9",
               "at": "2026-10-01T08:00:00Z", "operator": "bench-3", "value": {"imei": "35-9"}}  # fmt: skip
        with SessionLocal() as s:
            canonical.apply(s, "manual", [Fact("compliance", key, f, v) for f, v in row.items()])
            s.commit()
        with SessionLocal() as s:
            jobs = (
                s.execute(text("SELECT payload FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).scalars().all()
            )
        for payload in jobs:
            worker.HANDLERS["case.gateRecheck"](payload)
        with SessionLocal() as s:
            after = [dict(r) for r in s.execute(text("SELECT * FROM work_item WHERE case_id = :c"), {"c": cid}).mappings()]
        assert len(after) == 1 and after[0]["status"] == "done" and after[0]["outcome"] == "released"
    finally:
        gate_hold.default_pack_of = real  # type: ignore[assignment]
