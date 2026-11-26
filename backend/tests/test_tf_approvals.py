"""Plan 9, P9-3.15 (story TF-09): threshold approvals and the standing policy for tool returns.

Who must approve a returned tool's decision is `tool_approval.route_for_approval` (pure): a repair over $600 waits for the Fleet
manager (GR-14), a write-off of a tool under 24 months for Service operations (GR-15), a decision under the flow's 0.75
confidence (a Low life class is 0.50) or with a failed gate for a person; anything else the standing policy (I-11) may approve.
The route is kept on the case as `approvalRoute` and `approvalHolds`, which the hold policy (I-10) and the standing policy
already read; the panel's `approval` says it. No new approvable object: the policy was approved through maker-checker in P9-2.5
(`test_tf_09_policy_maker_cannot_approve` and the agent test below rerun that for this pack). No language is written here
(arithmetic on the valuer's lines), so there is no AgentLoop and no model test.
It opens tool cases in its own org unit and starts and ends with the demo reset.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from di.core import state
from di.core.db import SessionLocal, engine
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.cases import intake, process, store
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import tool_approval
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "tool-fleet-ap"
DCD, CMH = "DCD-62001", "CMH-48213"
SEEN = "2026-10-04T08:15:00+00:00"
PACK = load_pack("tool_fleet")
REPAIR = tool_approval.REPAIR_LABEL


def _best(k: str, repair: float = 0.0) -> dict:
    lines = [{"type": "v", "label": "Sales order SO-1", "basis": "", "amt": 2500.0}]
    if repair:
        lines.append({"type": "c", "label": REPAIR, "basis": "", "amt": repair})
    return {"k": k, "lines": lines}


def _gate(gid: str, passed: bool, reason: str = "") -> SimpleNamespace:
    return SimpleNamespace(gate_id=gid, passed=passed, reason=reason)


def _route(best: dict, age: float = 36, conf: float | None = 0.9, gates=()) -> tool_approval.ApprovalRoute:
    return tool_approval.route_for_approval(best, {"age": age}, conf, list(gates), PACK)


# ------------------------------------------------------------------ the pure route
def test_tf_09_thresholds_are_pack_data():
    t = tool_approval.thresholds(PACK)
    assert (t.repair_usd, t.write_off_months, t.confidence) == (600, 24, 0.75)
    assert dict(t.by_life) == {"High": 0.90, "Medium": 0.78, "Low": 0.50}
    assert tool_approval.confidence_of({"confidence": "Low"}, PACK) == 0.50
    assert tool_approval.confidence_of(None, PACK) is None


def test_tf_09_repair_over_600_waits_for_fleet_manager():
    r = _route(_best("refurb", 702.0))  # DCD grade C: 520 x 1.35
    assert (r.kind, r.role) == ("person", "Fleet manager")
    assert r.reasons == ["Repair $702 is over $600 (GR-14)"]
    assert [x["id"] for x in r.holds] == ["GR-14"]
    assert _route(_best("refurb", 600.0)).kind == "policy"  # at the limit is within it


def test_tf_09_young_write_off_waits_for_service_operations():
    r = _route(_best("exit"), age=18)
    assert (r.kind, r.role) == ("person", "Service operations")
    assert r.reasons[0].endswith("(GR-15)")
    assert _route(_best("harvest"), age=18).role == "Service operations"
    assert _route(_best("exit"), age=24).kind == "policy"  # 24 months is old enough
    assert _route(_best("resell"), age=18).kind == "policy"  # only a write-off is held


def test_tf_09_low_confidence_goes_to_person():
    r = _route(_best("release"), conf=tool_approval.confidence_of({"confidence": "Low"}, PACK))
    assert (r.kind, r.role) == ("person", "Fleet desk")
    assert r.reasons == ["Confidence 0.50 is under the flow's 0.75"]
    assert _route(_best("release"), conf=0.78).kind == "policy"  # Medium clears 0.75
    assert _route(_best("release"), conf=None).kind == "policy"  # no life reading: the valuation's own confidence


def test_tf_09_guardrail_fired_goes_to_person():
    r = _route(_best("release"), gates=[_gate("G-TOOL-TEL", False, "No telematics in 7 days"), _gate("G-CON-1", True)])
    assert r.kind == "person" and r.reasons == ["No telematics in 7 days"]
    assert r.holds[0]["id"] == "G-TOOL-TEL" and r.holds[0]["owner"]


def test_tf_09_clean_decision_goes_to_policy():
    r = _route(_best("release"), gates=[_gate("G-CON-1", True)])
    assert (r.kind, r.role, r.reasons, r.holds) == ("policy", None, [], ())


def test_tf_09_customer_can_tighten_the_limits(monkeypatch):
    guards = [
        g.model_copy(update={"param": g.param.model_copy(update={"value": 400})}) if g.id == "GR-14" and g.param else g
        for g in PACK.guardrails
    ]
    tight = PACK.model_copy(update={"guardrails": guards})
    r = tool_approval.route_for_approval(_best("refurb", 450.0), {"age": 36}, 0.9, [], tight)
    assert r.reasons == ["Repair $450 is over $400 (GR-14)"]


# ------------------------------------------------------------------ cases opened from data
DEMAND = {
    "FC-AP-R": ("fleet", {"kind": "lease", "need_by": "2026-12-01", "lease_rate": 410, "term_months": 12, "renew": True,
                          "site": "Houston", "tool_class": "CMH", "buyer": "Brightline Mechanical", "contract_ref": "FC-30117"}),
    "SO-AP-1": ("parts", {"kind": "so", "need_by": "2026-12-20", "price": 2500, "site": "Houston", "tool_class": "DCD",
                          "buyer": "Oakridge Tooling"}),
}  # fmt: skip


def _clean() -> None:
    k = {"k": [*DEMAND, DCD, CMH, "FC-TEST", "DR-AP-1"]}
    with engine.begin() as c:
        for m in ("demand", "contract_line", "contract", "condition", "repair_event"):
            for t in ("provenance", "canonical", "conflict"):
                c.execute(text(f"DELETE FROM {t} WHERE model = :m AND key = ANY(:k)"), {"m": m, **k})  # noqa: S608
        c.execute(text("DELETE FROM case_record WHERE owner = :o"), {"o": ORG})


@pytest.fixture(autouse=True)
def world():
    starting.reset()
    _clean()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet AP"}, "admin")["ok"]
    with SessionLocal() as s:
        for key, (src, row) in DEMAND.items():
            canonical.apply(s, src, [canonical.Fact("demand", key, k, v, resource="demand") for k, v in row.items()])
        s.commit()
    yield
    _clean()
    starting.reset()


def _grade(serial: str, g: str) -> None:
    f = {"grade": g, "test_result": "pass", "inspection_ref": "DR-AP-1", "graded_at": "2026-10-07T03:00:00Z"}
    with SessionLocal() as s:
        canonical.apply(s, "repairlog", [canonical.Fact("condition", serial, k, v, resource="orders") for k, v in f.items()])
        s.commit()


def _telematics(serial: str) -> None:
    facts = [
        canonical.Fact("condition", serial, "run_hours", 820.0, resource="tools"),
        canonical.Fact("condition", serial, "high_load_share", 0.3, resource="tools"),
        canonical.Fact("condition", serial, "event_counts", {"overheat": 0, "drop": 0, "overload": 0}, resource="tools"),
        canonical.Fact("condition", serial, "telemetry_coverage_pct", 95, resource="tools"),
    ]
    with SessionLocal() as s:
        canonical.apply(s, "fleet", facts)
        s.commit()


def _open(serial: str, cls: str, grade: str, seen: str | None = SEEN) -> dict:
    facts = tool_case_facts(serial, {"tool_class": cls, "site": "Houston", "grade": grade}, seen=seen)
    with SessionLocal() as s:
        c = intake.open_case(
            s, {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": serial, "reason": "contract_end", "facts": facts},
            "system",
        )  # fmt: skip
        s.commit()
        return c


def _dcd_grade_c() -> dict:
    _grade(DCD, "C")
    return _open(DCD, "DCD", "C")


def _clean_case() -> dict:
    _telematics(CMH)  # a High life class: fresh telematics, 95% coverage, no repair gap
    _grade(CMH, "A")
    c = _open(CMH, "CMH", "A")
    with SessionLocal() as s:  # the system-of-record check may have opened an exception: a person closes it
        open_ = "SELECT id FROM work_item WHERE case_id = :c AND kind = 'exception' AND status = 'open'"
        for (i,) in s.execute(text(open_), {"c": c["id"]}).all():
            process.close_item(s, i, "resolved", "admin")
        s.commit()
    return c


def _save(rules: dict) -> str:
    body = {"pack": "tool_fleet", "org_unit_id": ORG, "name": "Tool returns standing", "rules": rules, "owner": "admin"}
    out = call("standingPolicy.save", body, "admin")
    assert out["ok"], out
    return out["output"]["id"]


def _activate() -> str:
    pid = _save({"max_value": 20000, "min_confidence": 0.75})
    assert call("standingPolicy.submit", {"id": pid}, "admin")["ok"]
    assert call("standingPolicy.approve", {"id": pid}, "approver")["ok"]
    return pid


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        return c


def _view(cid: str, user: str = "admin"):
    return client.get(f"/api/screens/toolfleet/{cid}", headers=h(user))


def test_tf_09_dcd_repair_over_600_waits_for_fleet_manager():
    c = _dcd_grade_c()
    assert c["recommendation"]["id"] == "refurb"
    route = c["approvalRoute"]
    assert (route["kind"], route["role"]) == ("person", "Fleet manager")
    assert route["reasons"][0] == "Repair $702 is over $600 (GR-14)"
    assert c["approvalHolds"][0]["id"] == "GR-14"
    a = _view(c["id"]).json()["approval"]
    assert (a["kind"], a["role"], a["appRole"]) == ("person", "Fleet manager", "Approver")  # the item routes to the Approver
    assert a["text"] == "Waits for the Fleet manager: Repair $702 is over $600 (GR-14)"


def test_tf_09_policy_cannot_approve_repair_over_600():
    c = _dcd_grade_c()
    pid = _activate()
    assert call("decision.submit", {"case_id": c["id"]}, "admin")["ok"]
    after = _case(c["id"])
    assert after["stage"] == "awaiting_approval" and not after.get("approval")  # it waits in the Approver's My work
    with SessionLocal() as s:
        args = {"case_id": c["id"], "policy_id": pid, "ver": 1}
        r = invoke("decision.approveByPolicy", args, CallContext(actor=SYSTEM, session=s))
        s.commit()
    assert r["ok"] is False and r["error"]["code"] == "approval_required"
    assert not _case(c["id"]).get("approval")


def test_tf_09_clean_case_approved_by_policy():
    c = _clean_case()
    assert (c.get("life") or {}).get("confidence") == "High" and c["decisionConfidence"] == 0.9
    assert c["approvalRoute"]["kind"] == "policy" and "approvalHolds" not in c, c["approvalRoute"]
    pid = _activate()
    assert call("decision.submit", {"case_id": c["id"]}, "admin")["ok"]
    after = _case(c["id"])
    assert after["stage"] == "approved" and after["approval"]["by"] == f"policy {pid} v1"
    with SessionLocal() as s:
        notes = [e["note"] for e in state.items(s, "events") if e.get("type") == "decision.approved.policy"]
    assert notes == [f"Approved by policy {pid} v1, owner admin"]
    a = _view(c["id"]).json()["approval"]
    assert a["policy"] == {"id": pid, "ver": 1, "owner": "admin"}
    assert a["text"] == f"Approved by policy {pid} v1 (owner admin)"


def test_tf_09_no_telematics_is_low_and_goes_to_person():
    _grade(CMH, "A")
    c = _open(CMH, "CMH", "A", seen=None)
    assert c["approvalRoute"]["kind"] == "person", (c["approvalRoute"], c.get("life"))
    assert c["approvalHolds"]


# ------------------------------------------------------------------ security (R21, no new approvable object)
def test_tf_09_policy_maker_cannot_approve():
    pid = _save({"max_value": 500, "min_confidence": 0.75})
    assert call("standingPolicy.submit", {"id": pid}, "admin")["ok"]
    r = call("standingPolicy.approve", {"id": pid}, "admin")
    assert r["ok"] is False and "Maker-checker" in r["error"]["message"]


def test_tf_09_agent_cannot_approve():
    for action in ("decision.approve", "decision.approveByPolicy", "decision.override", "standingPolicy.approve"):
        assert forbidden(action), action


def test_tf_09_view_tenant_boundary():
    c = _dcd_grade_c()
    r = _view(c["id"], "planner.b")
    assert r.status_code == 403 and r.json()["error"]["code"] == "tenant_boundary", r.text
