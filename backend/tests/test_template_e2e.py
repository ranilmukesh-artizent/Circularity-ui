"""The two non-industrial templates end to end on the API (plan-8 audit, agent A): a tool-fleet return and a device
recommerce lot, each taken by real accounts through the actions and screens as people would.

    1. Admin opens a case for Customer A (case.open).
    2. planner-a reads its case screen (the template's path ids as routes) and the Modeler, whose queue lists it.
    3. planner-a forks the template's flow for Customer A and adds a rule excluding the case's recommendation; the
       approver approves and publishes it (planner-a, the maker, may not).
    4. The decision is submitted and declined; planner-a re-evaluates: the rule excludes the path with its reason, the
       recommendation moves, and `rulesApplied` holds the rule.
    5. The new decision is submitted and approved: the execution plan is the path's STEP_TPL, the case is approved,
       and the first step's instruction is queued (held: Customer A is in pilot mode, so nothing reaches a mock).
    6. The pilot report counts the case.
Every test ends with the starting state.
"""

from typing import Any

import pytest
from sqlalchemy import text

from di.core.config import get_settings
from di.core.db import SessionLocal
from di.services.cases import store
from di.services.execution.steps import STEP_TPL, ex_kinds
from di.services.instructions import send as instruction_send
from di.services.modeler.flow import default_flow
from di.services.modeler.templates import load_template
from tests import flowkit, starting
from tests.flowkit import ok, with_rule
from tests.helpers import call, client, h

FACTS = {
    "tool_fleet": {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 62},
    "device": {"brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B", "ref": 315, "qty": 40, "doh": 12},
}
ORG = "Customer A"


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    yield
    starting.reset()
    flowkit.reset_flows()


@pytest.fixture
def sending(monkeypatch):
    """Instructions on for the test (the suite turns them off), so an approval queues its first step."""
    monkeypatch.setattr(get_settings(), "instructions", True)


def _case(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _paths(t: str) -> list[str]:
    return list(load_template(t).path_ids())


@pytest.mark.parametrize("template", list(FACTS))
def test_template_case_end_to_end(template, sending):
    ok(call("org.setPilot", {"org_unit_id": ORG, "on": True}, "admin"))
    before = ok(call("org.pilotReport", {"org_unit_id": ORG}, "admin"))

    # 1. Admin opens the case
    opened = ok(call("case.open", {"org_unit_id": ORG, "template_key": template, "asset_key": f"T-E2E-{template}",
                                   "reason": "contract_end", "facts": FACTS[template]}, "admin"))  # fmt: skip
    cid, first = opened["case_id"], opened["recommendation"]
    assert opened["template"] == template and opened["stage"] == "awaiting_approval" and first in _paths(template)

    # 2. planner-a sees the case with the template's paths, and the Modeler's queue lists it
    page = client.get(f"/api/screens/case/{cid}", headers=h("planner-a"))
    assert page.status_code == 200, page.text
    assert [r["id"] for r in page.json()["case"]["routes"]] == _paths(template)
    mod = client.get("/api/screens/modeler", params={"template": template, "org": ORG}, headers=h("planner-a"))
    assert mod.status_code == 200, mod.text
    row = next((q for q in mod.json()["queue"] if q["id"] == cid), None)
    assert row is not None and row["best"] == first, mod.json()["queue"]

    # 3. planner-a forks the flow for Customer A and excludes the recommendation; the approver approves and publishes
    fid = ok(call("flow.fork", {"template_key": template, "org_unit_id": ORG}, "planner-a"))["flow_id"]
    g = with_rule(default_flow(load_template(template)), "XR-1", "exclude", first, {})
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "planner-a"))
    ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    mine = call("flow.approve", {"flow_id": fid}, "planner-a")
    assert mine["ok"] is False, mine  # maker-checker: the maker never approves
    ok(call("flow.approve", {"flow_id": fid}, "approver"))
    ok(call("flow.publish", {"flow_id": fid}, "approver"))
    assert _case(cid)["recommendation"]["id"] == first  # publishing never touches a case

    # 4. submitted, declined, re-evaluated under the new flow
    ok(call("decision.submit", {"case_id": cid}, "planner-a"))
    ok(call("decision.decline", {"case_id": cid, "reason": "Re-check under the new flow."}, "approver"))
    assert _case(cid)["stage"] == "reeval"
    re = ok(call("case.reevaluate", {"case_id": cid}, "planner-a"))
    c = _case(cid)
    assert [r["id"] for r in c["routes"]] == _paths(template)
    gone = next(r for r in c["routes"] if r["id"] == first)
    assert gone["excluded"] and gone["failReason"].startswith("Excluded by business rule XR-1"), gone
    now = c["recommendation"]["id"]
    assert (re["was"], re["now"]) == (c["routes"][_paths(template).index(first)]["plan"], c["recommendation"]["plan"])
    assert now != first and now in _paths(template)
    assert c["rulesApplied"] == ["XR-1"] and c["stage"] == "awaiting_approval"
    assert c["flowVer"] >= 1

    # 5. submitted and approved: the path's execution plan, the case approved, the first step queued (and held)
    ok(call("decision.submit", {"case_id": cid}, "planner-a"))
    ap = ok(call("decision.approve", {"case_id": cid, "reviewed": True, "rationale": "Template end to end."}, "approver"))
    c = _case(cid)
    assert ap["route"] == c["recommendation"]["plan"] and c["stage"] == "approved"
    kinds = [st["k"] for st in c["exec"]["steps"]]
    assert kinds == ex_kinds(c["recommendation"]) == STEP_TPL[now]
    with SessionLocal() as s:
        rows = s.execute(text("SELECT id, step, kind, status FROM instruction WHERE case_id = :c"), {"c": cid}).all()
    assert [(r.step, r.kind, r.status) for r in rows] == [(0, kinds[0], "queued")]
    assert instruction_send.send(rows[0].id) == "held"
    for url in (f"/api/screens/case/{cid}", f"/api/screens/case/{cid}/analysis"):  # the approved case still renders
        r = client.get(url, headers=h("planner-a"))
        assert r.status_code == 200, (url, r.text)

    # 6. the pilot report counts it
    after = ok(call("org.pilotReport", {"org_unit_id": ORG}, "admin"))
    assert after["cases_opened"] == before["cases_opened"] + 1
    assert after["decisions_submitted"] == before["decisions_submitted"] + 1
    assert after["decisions_approved"] == before["decisions_approved"] + 1
    assert after["rules_applied_count"] == before["rules_applied_count"] + 1
    assert after["instructions_held"] == before["instructions_held"] + 1
    assert after["by_route"].get(now, 0) == before["by_route"].get(now, 0) + 1


# ---------------------------------------------------------------- manual import (plan 8 MVP-8.4, audit 8.4)
# A CSV row as the page sends it: the import's own columns, then the template's facts (strings, as a CSV holds them).
COMMON = {"qty": "1", "location": "Warehouse 1", "owner": ORG, "received": "2026-10-08"}
ROWS = {
    "tool_fleet": [COMMON | {"asset_id": "T-CMH-9911", "cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston",
                             "rul": "62"},
                   COMMON | {"asset_id": "T-CMH-9912", "grade": "B"}],  # no tool class
    "device": [COMMON | {"asset_id": "LOT-9911", "brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B",
                         "ref": "315", "qty": "40", "doh": "12"},
               COMMON | {"asset_id": "LOT-9912", "grade": "B", "ref": "315"}],  # no age band
}  # fmt: skip
TYPED = {"rul": 62, "ref": 315, "qty": 40, "doh": 12}  # the numbers the valuer reads


@pytest.fixture
def imports():
    from di.connectors import manual

    made: list[str] = []
    yield made
    with SessionLocal() as s:
        for imp in made:
            manual.remove(s, imp)
        s.commit()


def _import(template: str, tag: str) -> dict[str, Any]:
    spec = {"template": template, "reason": "lease_end", "org_unit_id": "", "asset_field": "asset_id"}
    body = {"ok": 2, "err": 0, "hash": f"e2e-{template}-{tag}", "rows": ROWS[template], "open_cases": spec}
    return ok(call("import.commit", body, "developer"))


@pytest.mark.parametrize("template", list(FACTS))
def test_import_rows_open_template_cases(template, imports):
    from di.services.cases import intake

    out = _import(template, "1")
    imports.append(out["id"])
    good, bad = ROWS[template]
    assert (out["cases_opened"], out["cases_skipped"], out["cases_failed"]) == (1, 0, 1), out
    # the row without a required fact fails with the intake's reason (it is not "already open")
    make = intake.tool_fleet_case if template == "tool_fleet" else intake.device_lot
    with pytest.raises(intake.ActionError) as e:
        make("x", {k: TYPED.get(k, v) for k, v in bad.items() if k in FACTS[template]})
    assert out["case_failures"] == [{"asset_id": bad["asset_id"], "code": e.value.code, "reason": e.value.message}]
    (cid,) = out["case_ids"]
    c = _case(cid)
    assert (c["template"], c["owner"], c["assetId"], c["stage"]) == (template, ORG, good["asset_id"], "awaiting_approval")
    assert [r["id"] for r in c["routes"]] == _paths(template)
    facts = {k: TYPED.get(k, good[k]) for k in FACTS[template]}
    want = intake.tool_fleet_case(cid, facts) if template == "tool_fleet" else intake.device_lot(cid, facts)
    assert c["valuer"] == want  # the row's columns are the valuer's facts, numbers as numbers
    again = _import(template, "2")  # the same rows in another file: the opened one is skipped, the bad one fails again
    imports.append(again["id"])
    assert (again["cases_opened"], again["cases_skipped"], again["cases_failed"]) == (0, 1, 1), again


@pytest.mark.parametrize("bad", [{"ft": "Nowhere"}, {"site": "Mars"}, {"rul": "long"}, {"grade": "Z"}])
def test_tool_fleet_facts_are_checked(bad):
    """A fact the valuer cannot read is refused at intake (an import row then fails), never a server error."""
    body = {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": "T-BAD-1", "reason": "manual",
            "facts": FACTS["tool_fleet"] | bad}  # fmt: skip
    r = call("case.open", body, "admin")
    assert r["ok"] is False and r["error"]["code"] == "validation_error", r


def test_template_rows_need_an_asset_id(imports):
    rows = [ROWS["device"][0] | {"asset_id": ""}, ROWS["device"][1]]
    spec = {"template": "device", "reason": "lease_end", "org_unit_id": "", "asset_field": "asset_id"}
    r = call("import.commit", {"ok": 2, "err": 0, "hash": "e2e-noid", "rows": rows, "open_cases": spec}, "developer")
    assert r["ok"] is False and r["error"]["code"] == "validation_error", r


# ---------------------------------------------------------------- shadow (MVP-3.5) for a template case
@pytest.mark.parametrize("template", list(FACTS))
def test_template_reevaluation_records_a_shadow_decision(template):
    first = ok(call("case.open", {"org_unit_id": ORG, "template_key": template, "asset_key": f"T-SH-{template}",
                                  "reason": "contract_end", "facts": FACTS[template]}, "admin"))  # fmt: skip
    cid, rec = first["case_id"], first["recommendation"]
    fid = ok(call("flow.fork", {"template_key": template, "org_unit_id": ORG}, "planner-a"))["flow_id"]
    g = with_rule(default_flow(load_template(template)), "XR-2", "exclude", rec, {})
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "planner-a"))
    ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    ok(call("flow.approve", {"flow_id": fid}, "approver"))  # into shadow, not published
    ok(call("decision.decline", {"case_id": cid, "reason": "Re-check with the shadow flow."}, "approver"))
    ok(call("case.reevaluate", {"case_id": cid}, "planner-a"))
    c = _case(cid)
    live = c["recommendation"]
    assert live["id"] == rec and "rulesApplied" not in c  # the live decision used the published graph only
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT flow_id, dver, live_route, shadow_route, live_net, shadow_net FROM shadow_decision WHERE case_id = :c"),
            {"c": cid},
        ).all()
    assert len(rows) == 1, rows
    (row,) = rows
    assert (row.flow_id, row.dver, row.live_route) == (fid, 2, rec)
    assert row.shadow_route not in (None, rec)
    shadow = next(r for r in c["routes"] if r["id"] == row.shadow_route)
    assert (float(row.live_net), float(row.shadow_net)) == pytest.approx((live["net"], shadow["net"]))  # numeric column
