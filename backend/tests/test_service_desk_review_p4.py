"""Plan 9, the phase 4 review (findings F1-F4, F7): what a service ticket may never be decided as.

F1 GR-12 blocks the service-desk options (fix, swap, upgrade) of a recalled tool, with repair history or not.
F2 A ticket with no priced option is held (GR-S1), never valued as a tool-fleet return.
F3 GR-S3: a table approved after the estimate holds the case on every decision and refuses the approval until the case is
   decided again; the cited versions are never edited by hand.
F4 `serviceDesk.postFault` takes a fault only on a draft line of a case no one has approved.
F7 R20 (a recalled line is never valued; a rule cannot open a swap GR-S2 refuses) and R19 (a single ticket: intake,
   `case.reevaluate` and the decider agree).
No model step (R16). It starts and ends with the demo reset.
"""

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import market_tables
from di.repositories.live_rules import live_pack
from di.services.canonical import store as canonical
from di.services.cases import decide, intake, store
from di.services.modeler.compile import CompiledRule, FlowVersion
from tests.helpers import call
from tests.test_service_desk_options import ORG, _line, _open, _stock, _ticket, fresh  # noqa: F401 - `fresh` is the fixture

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
SD_ROUTES = {"fix", "swap", "upgrade", "split", "all_fix", "all_upgrade"}
RECALL = {"recall_id": "RC-2026-099", "tool_class": "CRH", "serial_from": "CRH-46000", "serial_to": "CRH-46999",
          "remedy": "repair", "affected_parts": ["Motor"], "status": "active"}  # fmt: skip


def _history(cls: str = "CRH", n: int = 60) -> None:
    rows = [{"id": f"RH-{cls}-{i}", "closed": date(2023, 10, 7) + timedelta(days=i * 5)} for i in range(n)]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO repair_history (id, org_unit_id, serial, model_class, age_months, fault_code, market, parts, "
                "labour_hours, test_fee, turnaround_days, actual_cost, currency, closed_on, source) VALUES (:id, :org, NULL, "
                ":cls, 18, 'MOT', 'US', CAST(:parts AS jsonb), 2.0, false, 5, 0, 'USD', :closed, 'rephist')"
            ),
            [{"org": ORG, "cls": cls, "parts": json.dumps([{"PART_NUMBER": f"{cls}-0", "QUANTITY": 1}]), **r} for r in rows],
        )


def _recall() -> None:
    with SessionLocal() as s:
        canonical.apply(
            s, "recall", [canonical.Fact("recall", RECALL["recall_id"], k, v, resource="notices") for k, v in RECALL.items()]
        )
        s.commit()


def _case(case_id: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, case_id)
    assert c is not None
    return c


def _holds(c: dict) -> list[str]:
    return [x["id"] for x in c.get("approvalHolds") or []]


def _opts(c: dict, line: int = 0) -> dict[str, dict]:
    return {o["k"]: o for o in c["serviceDesk"]["lines"][line]["options"]}


# ---------------------------------------------------------------- F1: GR-12 blocks the service-desk options
def test_sd_01_f1_a_recalled_tool_with_repair_history_gets_no_option():
    _history()
    _stock(2)
    _recall()
    _ticket("CS0010042", [_line()])  # CRH-46042 is in the notice's range, and the class has 60 closed repairs
    c = _open("CS0010042")
    assert c["serviceDesk"]["lines"][0]["estimate"]["n"] >= 50  # the line is priced: only GR-12 stops it
    o = _opts(c)
    assert not any(x["eligible"] for x in o.values())
    assert all("RC-2026-099" in x["why"] and "GR-12" in x["why"] for x in o.values())
    assert c["recommendation"] is None and {r["id"] for r in c["routes"]} <= SD_ROUTES
    assert all(r["excluded"] for r in c["routes"])


def test_sd_01_f1_in_a_batch_the_recalled_line_blocks_the_split_and_the_clean_line_stays_open():
    _history()
    _stock(2)
    _recall()
    _ticket("CS0010043", [_line("CRH-46042"), _line("CRH-47001")])  # the second is outside the notice's range
    with engine.begin() as conn:
        conn.execute(text("UPDATE service_ticket SET batch_id = 'B-1' WHERE number = 'CS0010043'"))
    c = _open("CS0010043")
    assert not any(o["eligible"] for o in _opts(c, 0).values()) and any(o["eligible"] for o in _opts(c, 1).values())
    assert c["recommendation"] is None
    assert all(r["excluded"] for r in c["routes"])


# ---------------------------------------------------------------- F2: an unpriced ticket is held, never a return
def _assert_held_not_a_return(c: dict, routes: set[str]) -> None:
    assert {r["id"] for r in c["routes"]} <= routes, [r["id"] for r in c["routes"]]
    assert c["recommendation"] is None
    assert _holds(c) == ["GR-S1"], c.get("approvalHolds")


def test_sd_01_f2_an_unknown_fault_is_held_and_never_valued_as_a_return():
    _history()
    _ticket("CS0010042", [{**_line(), "fault_code": None}])
    _assert_held_not_a_return(_open("CS0010042"), {"fix", "swap", "upgrade"})


def test_sd_01_f2_a_market_without_tables_is_held_and_never_valued_as_a_return():
    _ticket("CS0010042", [_line()])
    with engine.begin() as conn:
        conn.execute(text("UPDATE service_ticket SET market = 'ZZ' WHERE number = 'CS0010042'"))
    _assert_held_not_a_return(_open("CS0010042"), {"fix", "swap", "upgrade"})


def test_sd_01_f2_one_draft_line_in_a_batch_holds_the_whole_case():
    _history()
    _stock(2)
    _ticket("CS0010042", [_line("CRH-46042"), {**_line("CRH-46043"), "fault_code": None}])
    with engine.begin() as conn:
        conn.execute(text("UPDATE service_ticket SET batch_id = 'B-2' WHERE number = 'CS0010042'"))
    _assert_held_not_a_return(_open("CS0010042"), {"split", "all_fix", "all_upgrade"})


# ---------------------------------------------------------------- F3: GR-S3 fires when the tables move
def _new_labour_version(valid_from: str) -> None:
    """Finance drafts and submits a labour change for the US, the Approver approves it (maker-checker)."""
    with SessionLocal() as s:
        row = market_tables.effective(s, None, "tool_fleet", "service_desk", "US", "labour", date.fromisoformat(valid_from))
        assert row is not None
        body = {**row.body, "values": {**row.body["values"], "per_hour": row.body["values"]["per_hour"] + 4}}
        currency = row.currency
    out = call("marketTable.save", {"pack": "tool_fleet", "flow": "service_desk", "market": "US", "name": "labour",
                                    "kind": "rate_card", "valid_from": valid_from, "currency": currency, "body": body},
               "finance")  # fmt: skip
    assert out["ok"], out
    tid = out["output"]["id"]
    assert call("marketTable.submit", {"id": tid}, "finance")["ok"]
    assert call("marketTable.approve", {"id": tid}, "approver")["ok"]


def _open_early(number: str = "CS0010042") -> dict:
    """A ticket opened on 1 Oct (its estimate cites the tables of that day); the demo's clock stands on 7 Oct."""
    _history()
    _ticket(number, [_line()])
    with engine.begin() as conn:
        conn.execute(text("UPDATE service_ticket SET opened_at = '2026-10-01T09:00:00+00:00' WHERE number = :n"), {"n": number})
    return _open(number)


def test_sd_04_f3_gr_s3_a_table_approved_after_the_estimate_holds_the_case_on_the_next_decision():
    c = _open_early()
    assert "GR-S3" not in _holds(c)
    _new_labour_version("2026-10-07")  # in force on the decision date, after the estimate's 1 Oct
    with SessionLocal() as s:
        case = store.get(s, c["id"])
        intake.revalue(s, case)  # the same path as `case.reevaluate`; no cite is edited
        store.save(s, case)
        s.commit()
        holds = case.get("approvalHolds") or []
    assert "GR-S3" in [x["id"] for x in holds]
    assert next(x for x in holds if x["id"] == "GR-S3")["reason"] == (
        "Prices must come from the market's current approved table (GR-S3)"
    )


def test_sd_04_f3_the_approval_is_refused_when_a_table_changed_after_the_decision():
    c = _open_early()
    r = call("decision.submit", {"case_id": c["id"]}, "admin")
    assert r["ok"], r
    _new_labour_version("2026-10-07")
    rec = c["recommendation"]
    body = {"case_id": c["id"], "reviewed": True, "route": rec["plan"], "rationale": "Checked against the evidence"}
    r = call("decision.approve", body, "approver")
    assert r["ok"] is False and r["error"]["code"] == "conflict" and "GR-S3" in r["error"]["message"], r
    assert _case(c["id"])["stage"] == "awaiting_approval"


# ---------------------------------------------------------------- F4: postFault only before approval, on a draft line
def _approve(c: dict) -> None:
    r = call("decision.submit", {"case_id": c["id"]}, "admin")
    assert r["ok"], r
    plan = c["recommendation"]["plan"]
    body = {"case_id": c["id"], "reviewed": True, "route": plan, "rationale": "Checked against the evidence"}
    r = call("decision.approve", body, "approver")
    assert r["ok"], r


def test_sd_06_f4_a_fault_is_refused_on_an_approved_case_and_nothing_changes():
    _history()
    _ticket("CS0010042", [_line(age=10, cover="none")])
    c = _open("CS0010042")
    _approve(c)
    before = _case(c["id"])
    r = call("serviceDesk.postFault", {"case_id": c["id"], "line": 1, "fault_code": "GBX"}, "engineer")
    assert r["ok"] is False and r["error"]["code"] == "conflict", r
    assert "draft" not in r["error"]["message"]  # it is the stage that refuses, not the line
    after = _case(c["id"])
    assert after["serviceDesk"]["lines"][0]["fault_code"] == "MOT"
    keep = ("routes", "recommendation", "stage")
    assert [after[k] for k in keep] == [before[k] for k in keep]


def test_sd_06_f4_a_fault_is_refused_on_a_line_that_is_not_a_draft():
    _history()
    _ticket("CS0010042", [_line()])
    c = _open("CS0010042")
    assert c["serviceDesk"]["lines"][0]["estimate"]["auto"] is True
    r = call("serviceDesk.postFault", {"case_id": c["id"], "line": 1, "fault_code": "GBX"}, "engineer")
    assert r["ok"] is False and r["error"]["code"] == "conflict" and "draft" in r["error"]["message"], r
    assert _case(c["id"])["serviceDesk"]["lines"][0]["fault_code"] == "MOT"


# ---------------------------------------------------------------- F7: R20 order and R19 paths
def test_order_invariant_service_desk_a_recalled_line_is_never_valued():
    _history()
    _recall()
    _ticket("CS0010042", [_line()])
    c = _open("CS0010042")
    with SessionLocal() as s:
        d = decide.decide_case(c, live_pack(s, c), FlowVersion(None, 3, ()), session=s)
    assert d.trace[0] == "gates" and d.recommendation is None and d.ticket is not None
    assert not any(o["eligible"] for o in d.ticket["options"])  # the gate came first: valuation found nothing open


def test_order_invariant_service_desk_a_rule_cannot_open_a_swap_gr_s2_refuses():
    _history("CMH")
    _stock(2, "CMH")
    _ticket("CS0010042", [_line("CMH-46043", "CMH")])  # fleet cover on a CMH: repaired, never swapped
    c = _open("CS0010042")
    assert not _opts(c)["swap"]["eligible"] and "Covered swap is not allowed" in _opts(c)["swap"]["why"]
    prefer = CompiledRule("R-1", {}, "prefer", "swap", "prefer the swap")
    require = CompiledRule("R-2", {}, "require", "swap", "always swap")
    with SessionLocal() as s:
        d = decide.decide_case(c, live_pack(s, c), FlowVersion(None, 3, (prefer, require)), session=s)
    swap = next(r for r in d.routes if r["id"] == "swap")
    assert swap["excluded"] and d.route != "swap" and d.preferred is None


def test_paths_agree_tool_fleet_service_desk_single_ticket():
    """R19: opening the case, `case.reevaluate` and the decider on the stored case give the same option and margin."""
    _history()
    _stock(1)
    _ticket("CS0010042", [_line("CRH-46077", age=33, cover="none")])  # 92% of life: an upgrade is offered
    c = _open("CS0010042")
    best = c["serviceDesk"]["lines"][0]["best"]
    want = (c["recommendation"]["id"], best, _opts(c)[best]["margin"])
    for action, body, who in (
        ("decision.submit", {}, "admin"),
        ("decision.decline", {"reason": "Check again."}, "approver"),
        ("case.reevaluate", {}, "admin"),
    ):
        assert call(action, {"case_id": c["id"], **body}, who)["ok"]
    again = _case(c["id"])
    k = again["serviceDesk"]["lines"][0]["best"]
    assert (again["recommendation"]["id"], k, _opts(again)[k]["margin"]) == want
    with SessionLocal() as s:
        dec = decide.decide_case(again, intake._pack(s, again), intake.flow_version(s, again), session=s)
    assert dec.ticket is not None and (dec.route, dec.ticket["lines"][0]["best"]) == want[:2]
    assert next(o for o in dec.ticket["lines"][0]["options"] if o["k"] == k)["margin"] == want[2]
