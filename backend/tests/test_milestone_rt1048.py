"""B13b milestone: RT-1048 runs from approval to *Reconcile and learn* against the mocked systems, driven only by their
events and the simulated clock (docs/backend-steps.md, B13b).

People act over HTTP (Planner submits, Approver approves, Finance confirms). After the approval the test only drives
time: advance source-sim's simulated clock, run the worker's due jobs in-process (as di/worker.py does), and deliver
source-sim's events to the webhook receiver.

Delivery is deterministic: the test reads source-sim's outbox (`/_sim/outbox`) and posts each new event, signed with
di's webhook secret as source-sim signs it, to the receiver in this process (TestClient). The live api's subscription
is removed for the duration, so the running `api` container cannot acknowledge the same events concurrently, and the
simulated clock is paused (speed 0), so time moves only when the test advances it. Both are restored afterwards
(the subscription as the worker makes it at start-up). Needs source-sim running; stop the worker during the run.
"""

import hashlib
import hmac
import json
import re
import time

import httpx
import pytest
from sqlalchemy import text

from di import worker
from di.connectors.sync import ensure_sources
from di.connectors.webhook import ensure_subscription
from di.core import clock, golden, state
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.cases import lifecycle, store
from di.services.execution import line_actuals
from di.services.instructions import send as instruction_send
from tests.helpers import call, client

SETTINGS = get_settings()
SIM = SETTINGS.source_sim_url.rstrip("/")
CASE = "RT-1048"
REF = "APR-2026-10-3161"
# which event acknowledged which step (filled as events are delivered)
ACKED_BY: dict[str, str] = {}
SEEN: set[int] = set()
EXPECTED_EVENTS = {
    "order": "sterling.order.allocated",
    "repair": "oracle.apps.csd.repair.complete",
    "transport": "otm.shipment.tenderAccepted",
    "move": "manhattan.order.shipped",
    "pod": "sterling.order.fulfilled",
    "finance": "sap.s4.beh.journalentry.v1.JournalEntry.Created.v1",
}


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def post_event(ev: dict) -> dict:
    """Post one CloudEvent to the receiver, signed as source-sim signs it."""
    body = json.dumps({k: v for k, v in ev.items() if k != "delivered_at"}, separators=(",", ":")).encode()
    sig = "sha256=" + hmac.new(SETTINGS.webhook_secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
    r = client.post(
        "/api/webhooks/source-sim", content=body, headers={"x-sim-signature": sig, "content-type": "application/cloudevents+json"}
    )
    assert r.status_code == 202, r.text
    return r.json()


def outbox() -> list[dict]:
    return sorted(sim("GET", "/_sim/outbox", params={"limit": 500}).json(), key=lambda e: int(e["id"]))


def deliver() -> int:
    """Deliver every event not delivered yet, oldest first."""
    n = 0
    for ev in outbox():
        if int(ev["id"]) in SEEN:
            continue
        SEEN.add(int(ev["id"]))
        out = post_event(ev)
        ins = out.get("instruction") or {}
        if ins.get("acknowledged"):
            ACKED_BY[ins["kind"]] = ev["type"]
        n += 1
    return n


def run_jobs() -> None:
    """The worker's loop, in-process: every job that is due."""
    while worker.run_once():
        pass


def advance(hours: float) -> None:
    sim("POST", "/_sim/clock/advance", json={"hours": hours})  # also runs the mocks' scheduled work that fell due
    clock.invalidate()


def instructions() -> list[dict]:
    with SessionLocal() as s:
        return [
            dict(r) for r in s.execute(text("SELECT * FROM instruction WHERE case_id = :c ORDER BY step"), {"c": CASE}).mappings()
        ]


def the_case() -> dict:
    with SessionLocal() as s:
        return store.get(s, CASE)


def reset_di() -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE delegation SET enabled = true"))
        conn.execute(text("DELETE FROM tenant_grant"))
        conn.execute(text("DELETE FROM domain_event"))
        conn.execute(text("DELETE FROM case_stage_log WHERE seq IS NOT NULL"))
        conn.execute(text("DELETE FROM action_journal"))
        conn.execute(text("DELETE FROM instruction"))
        conn.execute(text("DELETE FROM job"))
        conn.execute(text("DELETE FROM sync_cursor"))
        conn.execute(text("DELETE FROM provenance WHERE model = 'outcome'"))
        conn.execute(text("DELETE FROM canonical WHERE model = 'outcome'"))
    store.reset()
    state.reset()


@pytest.fixture(scope="module", autouse=True)
def real_loop():
    saved = (SETTINGS.clock, SETTINGS.instructions)
    # the live api must not receive (and acknowledge) the same events: remove its subscription for the run
    for sub in sim("GET", "/_sim/webhooks").json():
        if sub["url"] == SETTINGS.webhook_url:
            sim("DELETE", f"/_sim/webhooks/{sub['id']}")
    sim("DELETE", "/_sim/faults")
    sim("POST", "/_sim/reset")  # every mock from its seed, the clock back to the as-of time
    sim("POST", "/_sim/clock/speed", json={"speed": 0})  # time moves only when the test advances it
    reset_di()
    with SessionLocal() as s:
        ensure_sources(s)
    SETTINGS.clock, SETTINGS.instructions = "sim", True
    clock.invalidate()
    yield
    SETTINGS.clock, SETTINGS.instructions = saved
    clock.invalidate()
    sim("DELETE", "/_sim/faults")
    sim("POST", "/_sim/reset")
    reset_di()
    ensure_subscription()


@pytest.fixture(autouse=True)
def clean_jobs():
    """Overrides conftest's: the loop's jobs carry over from one test of this module to the next."""
    return


# ---------------------------------------------------------------- the milestone
def test_rt1048_runs_from_approval_to_reconciled_on_events_and_the_clock():
    journey = golden.load("actions")["steps"]
    approve = next(s for s in journey if s["action"] == "decision.approve" and s["result"].get("ok"))
    assert call("decision.submit", {"case_id": CASE}, "planner-a")["ok"]
    ok = call("decision.approve", approve["input"], "approver")
    assert ok["ok"] and ok["output"]["ref"] == REF, ok
    assert the_case()["stage"] == "approved"
    (first,) = instructions()
    assert (first["kind"], first["system"], first["status"]) == ("order", "oms", "queued")

    # 1. Sterling allocates the unit to the order line; its event acknowledges the step and queues the repair
    run_jobs()
    deliver()
    assert the_case()["stage"] == "executing"
    # 2. Depot Repair is down when the work order goes out: the send fails, is retried with backoff, then succeeds
    sim("POST", "/_sim/faults", json={"system": "repair", "kind": "unavailable"})
    run_jobs()
    rep = instructions()[1]
    assert rep["kind"] == "repair" and rep["status"] == "queued" and rep["attempts"] == 1 and "503" in rep["last_error"]
    sim("DELETE", "/_sim/faults", params={"system": "repair"})
    deadline = time.monotonic() + 30
    while instructions()[1]["status"] == "queued" and time.monotonic() < deadline:
        run_jobs()  # the retry waits out its backoff (2 s)
        time.sleep(0.5)
    rep = instructions()[1]
    assert rep["status"] == "sent" and rep["attempts"] == 2 and rep["last_error"] is None and rep["doc_ref"] == "WO-47349"

    # 3. from here on, only time moves
    for _ in range(40):
        run_jobs()
        deliver()
        run_jobs()
        instruction_send.tick()
        if the_case()["stage"] == "closed":
            break
        advance(3)
    c = the_case()
    assert c["stage"] == "closed", [(i["kind"], i["status"], i["waiting_for"], i["last_error"]) for i in instructions()]
    run_jobs()  # the syncs the last events queued (S/4's journal entry among them)

    rows = instructions()
    assert [(i["kind"], i["system"], i["status"], i["simulated"]) for i in rows] == [
        ("order", "oms", "acknowledged", False),
        ("repair", "repair", "acknowledged", False),
        ("transport", "tms", "acknowledged", False),
        ("move", "wms", "acknowledged", False),
        ("pod", "oms", "acknowledged", False),
        ("finance", "erp", "acknowledged", False),
    ]
    refs = {i["kind"]: i["doc_ref"] for i in rows}
    load = rows[2]["detail"]["shipmentXid"]
    assert refs["order"] == "SO-48102"  # the order line Sterling allocated
    assert refs["repair"] == "WO-47349"  # the work order number Depot Repair kept (our P_REPAIR_NUMBER)
    assert re.fullmatch(r"LD-5\d{4}", refs["transport"]) and refs["transport"] == load  # the load OTM planned
    assert refs["move"] == "TR-47362"  # Manhattan's order (our OrderId)
    assert refs["pod"] == "POD-" + load[3:]  # the carrier's proof of delivery, confirmed in Sterling
    assert re.fullmatch(r"\d{10}", refs["finance"])  # S/4's accounting document
    # each step was acknowledged from its own system's event, with that system's reference
    assert ACKED_BY == EXPECTED_EVENTS
    steps = c["exec"]["steps"]
    assert [s["ack"]["ref"] for s in steps] == [refs[k] for k in EXPECTED_EVENTS]
    assert all(s["state"] == "done" and s["ack"]["sim"] is False for s in steps)
    with SessionLocal() as s:
        acks = s.execute(text("SELECT actor, input FROM action_journal WHERE action = 'adapter.acknowledge' ORDER BY seq")).all()
        moves = [h["to_stage"] for h in lifecycle.history(s, CASE)]
    assert [(a.actor, a.input["ref"]) for a in acks] == [("system", refs[k]) for k in EXPECTED_EVENTS]
    assert moves[-3:] == ["approved", "executing", "closed"]  # the stage machine: approved -> executing -> closed

    # the mocks hold what was sent: the allocation, the repair order, the load, the shipped order, the journal entry
    assert mock_count_repair_orders("WO-47349") == 1
    items = journal_items(REF)
    assert {i["AccountingDocument"] for i in items} == {refs["finance"]}
    lines = line_actuals(c, c["chosen"])
    assert len(items) == len([ln for ln in lines if ln["act"]]) + 1  # one item per cost line and the clearing item

    # Finance confirms the outcome with the actuals (the demo's result)
    out = call("outcome.confirm", {"case_id": CASE}, "finance")
    assert out["ok"], out
    actual = sum(ln["act"] for ln in lines)
    assert out["output"]["actual"] == actual and out["output"]["predicted"] == c["chosen"]["net"]

    # the run is at its last stage, complete
    trace = call("case.trace", {"case_id": CASE}, "planner-a")["output"]
    assert trace["done"] is True and trace["stage"] == 11
    assert trace["stages"][9]["state"] == "done"

    # the canonical store holds the outcome lines read back from S/4 (with provenance)
    with SessionLocal() as s:
        rec = canonical.get(s, "outcome", REF)
    assert rec is not None and rec["data"]["accounting_document"] == refs["finance"]
    assert {k.removeprefix("line."): v["act"] for k, v in rec["data"].items() if k.startswith("line.")} == {
        ln["kind"]: ln["act"] for ln in lines if ln["act"]
    }
    prov = rec["provenance"]["line.prep"][0]
    assert prov["source_id"] == "erp" and prov["source_field"] == "ACDOCA-WSL" and prov["authority"] is True


def test_resend_and_redelivered_events_create_nothing_twice():
    rows = instructions()
    assert len(rows) == 6 and all(i["status"] == "acknowledged" for i in rows)
    before = len(outbox())
    for ins in rows:  # every step again, under its key: each system answers with what it already has
        assert instruction_send.send(ins["id"], resend=True) == "sent"
    assert len(outbox()) == before  # no system wrote anything (every write emits an event)
    assert mock_count_repair_orders("WO-47349") == 1
    assert {i["AccountingDocument"] for i in journal_items(REF)} == {rows[5]["doc_ref"]}
    assert [i["doc_ref"] for i in instructions()] == [i["doc_ref"] for i in rows]

    # the completion events again: matched to their steps, nothing acknowledged twice
    with SessionLocal() as s:
        acks = s.execute(text("SELECT count(*) FROM action_journal WHERE action = 'adapter.acknowledge'")).scalar_one()
    again = [e for e in outbox() if e["type"] in EXPECTED_EVENTS.values()]
    matched = [post_event(ev).get("instruction") for ev in again]
    assert len([m for m in matched if m]) == 6 and all(m["acknowledged"] is False for m in matched if m)
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM action_journal WHERE action = 'adapter.acknowledge'")).scalar_one() == acks
    assert the_case()["stage"] == "closed"


def test_steps_without_a_mock_write_are_acknowledged_by_the_simulated_adapter_on_the_clock():
    """RT-1049 resells the unit (reserve, sale, ship, fulfil, receipt): no mock has these writes, so each step is
    acknowledged by the simulated adapter `simulated_ack_hours` (2) simulated hours after it was sent."""
    approve = golden.load("writes")["exec_other_routes"]["calls"][1]
    assert approve["input"]["case_id"] == "RT-1049"
    assert call("decision.submit", {"case_id": "RT-1049"}, "planner-a")["ok"]
    assert call("decision.approve", approve["input"], "approver")["ok"]
    for n in range(5):
        run_jobs()
        assert instruction_send.tick() == 0  # not due yet
        advance(2)
        assert instruction_send.tick() == 1, n
    with SessionLocal() as s:
        c = store.get(s, "RT-1049")
        rows = s.execute(text("SELECT kind, status, simulated FROM instruction WHERE case_id = 'RT-1049' ORDER BY step")).all()
        notes = [e["note"] for e in state.items(s, "events") if e.get("caseId") == "RT-1049" and e["dir"] == "in"]
    assert c["stage"] == "closed"
    assert [tuple(r) for r in rows] == [(k, "acknowledged", True) for k in ("reserve", "sale", "ship", "fulfil", "receipt")]
    assert all(s["ack"]["sim"] is True for s in c["exec"]["steps"])  # the demo's references, marked simulated
    assert len(notes) == 5 and all("simulated acknowledgement" in n for n in notes)


# ---------------------------------------------------------------- reading the mocks
def mock_count_repair_orders(number: str) -> int:
    r = sim(
        "GET",
        "/depot-repair/webservices/rest/xxcsdroquery/get_repair_orders/",
        params={"P_REPAIR_NUMBER": number},
        auth=("DI_CONNECTOR", "repair-demo-password"),
    )
    return len(r.json()["OutputParameters"]["X_REPAIR_ORDERS"]["X_REPAIR_ORDERS_ITEM"])


def journal_items(ref: str) -> list[dict]:
    r = sim(
        "GET",
        "/sap/opu/odata/sap/API_JOURNALENTRYITEMBASIC_SRV/A_JournalEntryItemBasic",
        params={"$filter": f"DocumentReferenceID eq '{ref}'", "$format": "json"},
        auth=("DI_CONNECTOR", "Circularity-demo-1"),
    )
    return r.json()["d"]["results"]
