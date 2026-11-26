"""Plan 9, P9-3.16 (story TF-12): a key account's return waits for the account manager.

The fleet contract's `key_account` flag (P9-3.1) reaches the case in its `contract_line` evidence (`keyAccount`, `customer`).
`tool_approval.route_for_approval` (pure, I-10/I-11 read its holds) adds the pack's key-account hold (`TF-KEY`, role Account
manager, mapped to Approver in the pack's `roles`) after the gates' holds: the first hold names the role, so a gate that
failed shows first, and the route ranking never changes. No new approvable object (the approval is the case's own, through
`decision.approve`), no language written by a model: arithmetic and a template reason, so no AgentLoop.
The tests seed their own contracts (FC-TFKEY-1 a key account named "Westmark Supply", FC-TFKEY-2 not) so they hold on a stack
whose fleet mock has synced (FC-30140 is the mock's key account), and they delete them.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.cases import intake, process
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import tool_approval, tool_inputs
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "tool-fleet-ka"
CMH = "CMH-48213"
KEY, PLAIN = "FC-TFKEY-1", "FC-TFKEY-2"
CUSTOMER = "Westmark Supply"
SEEN = "2026-10-04T08:15:00+00:00"
PACK = load_pack("tool_fleet")
REASON = f"Key account {CUSTOMER}: the account manager reviews the return"


def _case(key: bool | None, customer: str = CUSTOMER) -> dict:
    """A case as the decider reads it: only the contract line evidence carries the flag."""
    value = {"lineId": "FL-1", "serial": CMH, "status": "active", "customer": customer}
    if key is not None:
        value["keyAccount"] = key
    rec = {"type": "contract_line", "source": "fleet", "at": "2026-10-01T00:00:00+00:00", "result": "pass", "value": value}
    return {"age": 36, "evidenceRecords": [rec]}


def _best() -> dict:
    return {"k": "release", "lines": [{"type": "v", "label": "Sales order SO-1", "basis": "", "amt": 2500.0}]}


def _route(case: dict, gates=(), conf: float | None = 0.9) -> tool_approval.ApprovalRoute:
    return tool_approval.route_for_approval(_best(), case, conf, list(gates), PACK)


# ------------------------------------------------------------------ the pure route
def test_tf_12_key_account_waits_for_account_manager_pure():
    r = _route(_case(True))
    assert (r.kind, r.role) == ("person", "Account manager")
    assert r.reasons == [REASON]
    assert [(x["id"], x["owner"]) for x in r.holds] == [("TF-KEY", "Account manager")]
    assert PACK.roles["Account manager"] == "Approver"  # the item routes to the Approver


def test_tf_12_non_key_account_unchanged_pure():
    for case in (_case(False), _case(None), {"age": 36}):
        r = _route(case)
        assert (r.kind, r.role, r.holds) == ("policy", None, ()), case


def test_tf_12_diversion_runs_after_gates_pure():
    gate = SimpleNamespace(gate_id="G-CON-2", passed=False, reason="Damage charge CHG-1 is open")
    r = _route(_case(True), gates=[gate])
    assert r.reasons[0] == "Damage charge CHG-1 is open" and r.role != "Account manager"  # the gate shows first
    assert [x["id"] for x in r.holds] == ["G-CON-2", "TF-KEY"]  # the review is added, never replaces


def test_tf_12_key_account_fact_reads_the_contract_evidence():
    assert tool_inputs.key_account(_case(True)) == (True, CUSTOMER)
    assert tool_inputs.key_account(_case(False)) == (False, CUSTOMER)
    assert tool_inputs.key_account({}) == (False, None)


def test_tf_12_pack_names_the_dimension_and_the_hold():
    assert "keyAccount" in {d.key for d in PACK.dims}
    assert PACK.valuer.params["approval"]["key_account"] == {"id": "TF-KEY", "role": "Account manager"}


# ------------------------------------------------------------------ cases opened from data
def _clean() -> None:
    k = {"k": [KEY, PLAIN, CMH]}
    with engine.begin() as c:
        for m in ("contract", "contract_line", "condition"):
            for t in ("provenance", "canonical", "conflict"):
                c.execute(text(f"DELETE FROM {t} WHERE model = :m AND key = ANY(:k)"), {"m": m, **k})  # noqa: S608
        c.execute(text("DELETE FROM case_record WHERE owner = :o"), {"o": ORG})


@pytest.fixture(autouse=True)
def world():
    starting.reset()
    _clean()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet KA"}, "admin")["ok"]
    yield
    _clean()
    starting.reset()


def _open(contract: str, key: bool, line: dict | None = None) -> dict:
    given = {"tool_class": "CMH", "site": "Houston", "grade": "A"}
    facts = tool_case_facts(CMH, given, line={"contract_id": contract, **(line or {})}, seen=SEEN)
    more = [
        canonical.Fact("contract", contract, "customer", CUSTOMER, resource="contracts"),
        canonical.Fact("contract", contract, "key_account", key, resource="contracts"),
        canonical.Fact("condition", CMH, "run_hours", 820.0, resource="tools"),
        canonical.Fact("condition", CMH, "high_load_share", 0.3, resource="tools"),
        canonical.Fact("condition", CMH, "event_counts", {"overheat": 0, "drop": 0, "overload": 0}, resource="tools"),
        canonical.Fact("condition", CMH, "telemetry_coverage_pct", 95, resource="tools"),
    ]
    grade = {"grade": "A", "test_result": "pass", "inspection_ref": "DR-KA-1", "graded_at": "2026-10-07T03:00:00Z"}
    more += [canonical.Fact("condition", CMH, k, v, resource="orders") for k, v in grade.items()]
    with SessionLocal() as s:
        canonical.apply(s, "fleet", more[:6])
        canonical.apply(s, "repairlog", more[6:])
        s.commit()
        opening = {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": CMH, "reason": "contract_end", "facts": facts}
        c = intake.open_case(s, opening, "system")
        s.commit()
        for (i,) in s.execute(
            text("SELECT id FROM work_item WHERE case_id = :c AND kind = 'exception' AND status = 'open'"), {"c": c["id"]}
        ).all():
            process.close_item(s, i, "resolved", "admin")  # an open exception would hold any case: not what this is about
        s.commit()
        return c


def test_tf_12_key_account_waits_for_account_manager():
    c = _open(KEY, True)
    assert c["recommendation"] is not None
    assert (c["approvalRoute"]["kind"], c["approvalRoute"]["role"]) == ("person", "Account manager"), c["approvalRoute"]
    assert c["approvalRoute"]["reasons"][0] == REASON
    assert c["approvalHolds"][-1]["id"] == "TF-KEY"
    a = client.get(f"/api/screens/toolfleet/{c['id']}", headers=h("admin")).json()["approval"]
    assert (a["kind"], a["role"], a["appRole"]) == ("person", "Account manager", "Approver")
    assert a["text"] == f"Waits for the Account manager: {REASON}"


def test_tf_12_non_key_account_unchanged():
    c = _open(PLAIN, False)
    assert c["approvalRoute"]["kind"] == "policy" and "approvalHolds" not in c, c["approvalRoute"]


def test_tf_12_diversion_runs_after_gates():
    c = _open(KEY, True, line={"damage_charge_open": True, "charge_ref": "CHG-4412"})
    assert c["recommendation"] is None and c["gateHold"]["gates"] == ["G-CON-2"]
    assert not any(x.get("id") == "TF-KEY" for x in c.get("approvalHolds") or [])  # the gate shows, not the review


# ------------------------------------------------------------------ security (R21): nothing new to approve, nothing agents may
def test_tf_12_agent_cannot_approve_the_review():
    for action in ("decision.approve", "decision.approveByPolicy", "decision.override"):
        assert forbidden(action), action
