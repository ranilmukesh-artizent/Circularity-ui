"""Plan 9, P9-3.13 (story TF-08): the live queue plan for open tool returns.

An org's open tool returns are planned together (di.services.cases.tool_queue, the planner of I-5, never a language model:
no model step here): a named renewal is filled once, refurbishment stays within the repair center's slots, a return that
arrives or is decided plans the others again, and the case's own decision equals its place in the plan. The panel reads
the plan as `plan` of the tool fleet screen. It opens cases in its own org unit and starts and ends with the demo reset.
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.cases import intake, store, tool_queue
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

pytestmark = pytest.mark.usefixtures("no_synced_demand")

ORG = "tool-fleet-q"
RENEWAL = "FC-30117-R"
SLOTS_MSG = "No repair center slot in the next two weeks: the queue plan gives the slots to refurbishments that add more"
LEASE = {"kind": "lease", "id": RENEWAL, "renew": True, "who": "Brightline Mechanical", "site": "Houston", "need": 9, "rate": 900,
         "term": 24, "what": "Fleet contract FC-30117 renews", "when": "renewal confirmed"}  # fmt: skip


def _sale(i: int) -> dict:
    return {"kind": "so", "id": f"SO-Q{i}", "who": f"Buyer {i}", "site": "Houston", "need": 20, "price": 30000,
            "what": f"Sales order SO-Q{i}", "when": "order booked"}  # fmt: skip


def _clear() -> None:
    with engine.begin() as c:
        c.execute(text("DELETE FROM case_record WHERE owner = :o"), {"o": ORG})


@pytest.fixture(scope="module", autouse=True)
def world():
    starting.reset()
    _clear()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet Q"}, "admin")["ok"]
    yield
    _clear()
    starting.reset()


@pytest.fixture(autouse=True)
def clean():
    _clear()
    yield
    _clear()


def _open(serial: str, grade: str = "A", dem: dict | None = None) -> str:
    facts = {"cls": "CMH", "grade": grade, "ft": "Repair center", "site": "Houston", "rul": 62, "dem": dem or {"lease": [LEASE]}}
    with SessionLocal() as s:
        c = intake.open_case(
            s, {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": serial, "reason": "manual",
                "facts": tool_case_facts(serial, facts)}, "system")  # fmt: skip
        s.commit()
        return c["id"]


def _replan() -> tool_queue.Plan:
    with SessionLocal() as s:
        plan = tool_queue.replan(s, ORG)
        s.commit()
    return plan


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _best(cid: str) -> str | None:
    return (_case(cid)["recommendation"] or {}).get("id")


def _dest(cid: str) -> str | None:
    return ((_case(cid)["recommendation"] or {}).get("dest") or {}).get("id")


def _route(cid: str, k: str) -> dict:
    return next(r for r in _case(cid)["routes"] if r["id"] == k)


def test_tf_08_live_queue_fills_renewal_once():
    a, b = _open("TQ-1"), _open("TQ-2")
    _replan()
    holders = [i for i in (a, b) if _best(i) == "release" and _dest(i) == RENEWAL]
    assert len(holders) == 1, {i: (_best(i), _dest(i)) for i in (a, b)}
    loser = a if holders[0] == b else b
    assert _best(loser) not in (None, "release")
    why = _route(loser, "release")["failReason"]
    assert why == f"{RENEWAL} (Brightline Mechanical) is planned for {holders[0]}, where it adds more across the queue"


def test_tf_08_refurb_within_slots():
    ids = [_open(f"TQ-B{i}", "B", {"so": [_sale(i)]}) for i in range(9)]
    plan = _replan()
    refurb = [i for i in ids if _best(i) == "refurb"]
    assert plan["slots"] == 8 and len(refurb) == 8 == plan["refurb_n"], {i: _best(i) for i in ids}
    cut = [i for i in ids if _best(i) != "refurb"]
    assert len(cut) == 1 and _route(cut[0], "refurb")["failReason"] == SLOTS_MSG


def test_tf_08_replan_on_arrival():
    first = _open("TQ-3", "B")
    assert _dest(first) == RENEWAL
    second = _open("TQ-4", "A")
    _replan()
    assert _dest(second) == RENEWAL and _dest(first) != RENEWAL
    with SessionLocal() as s:
        rows = s.execute(text("SELECT reason, actor FROM case_stage_log WHERE case_id = :c ORDER BY id"), {"c": first}).all()
    assert any(r[0].startswith("Re-planned: ") and r[1] == "system" for r in rows), rows


def test_tf_08_paths_agree_with_plan():
    ids = [_open("TQ-5", "A"), _open("TQ-6", "A"), _open("TQ-7", "B")]
    plan = _replan()
    with SessionLocal() as s:
        queue = tool_queue.open_queue(s, ORG)
    assert sorted(c["id"] for c in queue) == sorted(ids)
    assert all(RENEWAL in [d["id"] for d in c["dem"]["lease"]] for c in queue)
    for i in ids:
        assert _best(i) == plan["res"][i]["best"]["k"], i


def test_tf_08_screen_plan_names_order_loser_and_gain():
    a, b = _open("TQ-8"), _open("TQ-9")
    _replan()
    holder = next(i for i in (a, b) if _dest(i) == RENEWAL)
    loser = a if holder == b else b
    p = client.get(f"/api/screens/toolfleet/{holder}", headers=h("admin")).json()["plan"]
    assert p["holds"] == RENEWAL and p["contested"] == [RENEWAL] and p["lost"] == []
    assert p["headline"] == f"This return takes {RENEWAL}"
    assert p["gain"] == pytest.approx(p["total"] - p["fcfs"], abs=0.01) and p["gain"] >= 0
    q = client.get(f"/api/screens/toolfleet/{loser}", headers=h("admin")).json()["plan"]
    assert q["holds"] is None and [x["order"] for x in q["lost"]] == [RENEWAL]
    assert q["lost"][0]["to"] == holder
    assert q["headline"] == f"{RENEWAL} (Brightline Mechanical) is planned for {holder}, where it adds more across the queue"
    assert q["kinds"][RENEWAL] == "lease renewal"
