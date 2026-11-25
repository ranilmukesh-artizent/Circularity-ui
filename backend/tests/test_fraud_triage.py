"""P9-2.11 (story X-15; registry entries I-1, I-3, I-10, I-20; R16, R20, R21): fraud triage on intake with a person release.

`triage` (di.services.modeler.fraud) is the pure computed score of the pack's fraud rules; the chain's intake stage runs it and,
when the score reaches the threshold, calls `fraud.hold` and waits. Only a person releases or rejects (`fraud.release`,
`fraud.reject` are in FORBIDDEN_ACTIONS). The rules, the weights and the threshold are pack data: a device pack version carries
them here and a customer overlay moves the threshold (`set_param`). The model's review of fraud is P9-2.19, not here.
Every test ends with the starting state.
"""

import copy
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text

from di.core import policy
from di.core.db import SessionLocal, engine
from di.repositories.fraud_history import repeat_counts
from di.services.agents import chain, runtime
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, forbidden
from di.services.cases import store
from di.services.modeler.fraud import FraudRules, triage
from di.services.modeler.pack import PACKS_DIR, PackError, load_pack, parse_pack
from tests import starting
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

LOT = {"brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B", "ref": 315, "qty": 40, "doh": 12}
AT = "2026-11-20T10:00:00+00:00"
BLACKLIST = {"type": "blacklist", "source": "Blacklist register", "at": AT, "result": "fail", "value": {"hit": True}}
QUOTE = {
    "type": "quote_check", "source": "Receiving inspection", "at": AT, "result": "fail",
    "value": {"declared": {"model": "Pixel 8", "capacity": "128GB"}, "received": {"model": "Pixel 8", "capacity": "256GB"}},
}  # fmt: skip
RULES = {
    "version": "v1",
    "threshold": 0.6,
    "rules": [
        {"id": "F-BL", "signal": "blacklisted", "weight": 0.5, "params": {}, "source": "Blacklist register"},
        {"id": "F-QM", "signal": "quote_mismatch", "weight": 0.3, "params": {}, "source": "Receiving inspection"},
        {"id": "F-RR", "signal": "repeat_returns", "weight": 0.7, "params": {"n": 3, "days": 90}, "source": "Case history"},
    ],
}  # fmt: skip
RANGE = {"value": 0.6, "min": 0.3, "max": 0.95}
CASE = (
    "RT-1048"  # awaiting approval, Customer A: the hold and the person's release or reject on a case with a decision to decline
)


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    _clean()
    starting.reset()


# ---------------------------------------------------------------- helpers
def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def device_doc(version: str = "2.7.1", rules: dict[str, Any] | None = RULES) -> dict[str, Any]:
    """The shipped device pack at `version` with a fraud part and the published range of the threshold parameter."""
    d = json.loads((PACKS_DIR / "device.json").read_text(encoding="utf-8"))
    d["version"] = version
    if rules is not None:
        d["fraud"] = copy.deepcopy(rules)
        d["customer_layer"]["params"] = {"fraud.threshold": RANGE}
    return d


def publish(doc: dict[str, Any]) -> None:
    pid = ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    ok(call("pack.submit", {"id": pid}, "admin"))
    ok(call("pack.approve", {"id": pid}, "approver"))


def open_case(asset: str, *records: dict[str, Any], reason: str = "manual") -> str:
    body = {"org_unit_id": "Customer A", "template_key": "device", "asset_key": asset, "reason": reason, "facts": LOT}
    cid = ok(call("case.open", body, "planner-a"))["case_id"]
    with SessionLocal() as s:
        c = store.get(s, cid, for_update=True)
        assert c is not None
        c["evidenceRecords"] = [*(c.get("evidenceRecords") or []), *copy.deepcopy(records)]
        store.save(s, c)
        s.commit()
    return cid


def case_now(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def intake(cid: str) -> tuple[str, chain.StageRecord]:
    """Play the worker over the intake stage of a chain run; the run's status and the stage's record."""
    with SessionLocal() as s:
        run_id = runtime.start(s, "recover-chain", "stage_chain", cid, account="planner-a")
        s.commit()
        runtime.run_until_blocked(s, run_id, max_steps=6)
    with SessionLocal() as s:
        recs = {r.stage: r for r in chain.records_of(s, run_id)}
    return run_id, recs["intake"]


def prepared(action: str, body: dict, user: str = "approver", agent: str = "coordinator") -> dict:
    return client.post(f"/api/actions/{action}", json=body, headers=h(user) | {"X-Circularity-Preparer": agent}).json()


def hold_input(cid: str = CASE) -> dict[str, Any]:
    sig = {"id": "F-BL", "fired": True, "value": True, "source": "Blacklist register", "at": AT}
    return {"case_id": cid, "score": 0.8, "signals": [sig], "rule_version": "v1", "threshold": 0.6}


def held_case() -> str:
    ok(call("fraud.hold", hold_input(), "planner-a"))
    return CASE


def journal(action: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        q = text("SELECT actor, role, input FROM action_journal WHERE action = :a AND NOT undone")
        return [dict(r._mapping) for r in s.execute(q, {"a": action})]


def items(cid: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        q = text(
            "SELECT kind, type, title, owner_role, status, outcome FROM work_item WHERE case_id = :c AND type = 'fraud_hold'"
        )
        return [dict(r._mapping) for r in s.execute(q, {"c": cid})]


# ---------------------------------------------------------------- the pure triage (I-1, I-3)
def test_x_15_pack_without_fraud_rules_never_holds():
    pack = load_pack("device")
    assert pack.fraud is None
    r = triage({"evidenceRecords": [BLACKLIST]}, pack, {})
    assert (r.score, r.held, r.signals) == (0.0, False, [])


def test_x_15_triage_sums_the_weights_of_the_signals_that_fired():
    pack = parse_pack(device_doc())
    r = triage({"evidenceRecords": [BLACKLIST, QUOTE]}, pack, {})
    assert r.score == 0.8 and r.held and r.rule_version == "v1" and r.threshold == 0.6
    fired = {s.id: s for s in r.fired()}
    assert set(fired) == {"F-BL", "F-QM"}
    assert fired["F-BL"].source == "Blacklist register" and fired["F-BL"].at == datetime(2026, 11, 20, 10, tzinfo=UTC)
    assert fired["F-QM"].value == ["capacity"]  # the declared and received capacity differ, the model does not


def test_x_15_signals_read_evidence_types():
    rules = {
        "version": "v2", "threshold": 0.1,
        "rules": [
            {"id": "R", "signal": "refund_before_receipt", "weight": 0.2, "params": {}, "source": "Finance"},
            {"id": "S", "signal": "serial_not_on_contract", "weight": 0.2, "params": {}, "source": "Contracts"},
        ],
    }  # fmt: skip
    pack = parse_pack(device_doc(rules=rules))
    refund = {"type": "refund_record", "source": "Finance", "at": AT, "result": "fail",
              "value": {"refunded_at": "2026-11-01T00:00:00Z", "received_at": "2026-11-05T00:00:00Z"}}  # fmt: skip
    clause = {"type": "contract_clause", "source": "Contracts", "at": AT, "result": "fail", "value": {"serial_listed": False}}
    assert triage({"evidenceRecords": [refund, clause]}, pack, {}).score == 0.4
    ok_clause = clause | {"value": {"serial_listed": True}}
    late = refund | {"value": {"refunded_at": "2026-11-06T00:00:00Z", "received_at": "2026-11-05T00:00:00Z"}}
    assert triage({"evidenceRecords": [late, ok_clause]}, pack, {}).score == 0.0


def test_x_15_bad_rules_are_refused_when_the_pack_loads():
    for bad in (
        {**RULES, "rules": [{**RULES["rules"][0], "weight": 0}]},
        {**RULES, "rules": [RULES["rules"][0], RULES["rules"][0]]},
        {**RULES, "rules": [{**RULES["rules"][2], "params": {"n": 3}}]},
        {**RULES, "rules": [{**RULES["rules"][0], "signal": "vibes"}]},
    ):
        with pytest.raises(PackError):
            parse_pack(device_doc(rules=bad))
    assert FraudRules.model_validate(RULES).threshold == 0.6


# ---------------------------------------------------------------- the stage, the hold and the person
def test_x_15_signals_source_and_rule_version_on_hold():
    publish(device_doc())
    cid = open_case("SN-F-1", BLACKLIST, QUOTE)  # 0.5 + 0.3 against 0.6
    run_id, rec = intake(cid)
    assert rec.status == "held" and rec.output["fraud"] == {"score": 0.8, "threshold": 0.6, "rule_version": "v1", "held": True}
    f = case_now(cid)["fraud"]
    assert (f["status"], f["score"], f["rule_version"]) == ("held", 0.8, "v1")
    assert {s["id"]: (s["source"], s["at"]) for s in f["signals"]} == {
        "F-BL": ("Blacklist register", AT),
        "F-QM": ("Receiving inspection", AT),
    }
    assert f["held_at"] and f["by"] == "stage-intake"
    with SessionLocal() as s:
        assert s.execute(text("SELECT state->>'waiting' FROM agent_run WHERE id = :i"), {"i": run_id}).scalar_one() == "fraud"
    [item] = items(cid)
    assert item["kind"] == "exception" and item["owner_role"] == "Approver" and item["status"] == "open"
    assert item["title"].startswith("Fraud and compliance")


def test_x_15_below_threshold_continues():
    publish(device_doc())
    cid = open_case("SN-F-2", QUOTE)  # 0.3 against 0.6
    _, rec = intake(cid)
    assert rec.status == "done" and rec.output["fraud"]["held"] is False and rec.output["fraud"]["score"] == 0.3
    assert case_now(cid).get("fraud") is None and items(cid) == []


def test_x_15_only_person_releases():
    cid = held_case()
    r = prepared("fraud.release", {"case_id": cid, "reason": "Checked with the customer; the serial is genuine."})
    assert r["ok"] is False and r["error"]["code"] == "approval_required"
    assert case_now(cid)["fraud"]["status"] == "held" and journal("fraud.release") == []
    why = "Checked with the customer; the serial is genuine."
    out = ok(call("fraud.release", {"case_id": cid, "reason": why}, "approver"))
    assert out["status"] == "released"
    f = case_now(cid)["fraud"]
    assert (f["status"], f["resolved_by"], f["reason"]) == ("released", "approver", why) and f["signals"]  # the record is kept
    [row] = journal("fraud.release")
    assert row["actor"] == "approver" and row["input"]["reason"] == why
    assert [i["status"] for i in items(cid)] == ["done"]
    assert (
        call("fraud.release", {"case_id": cid, "reason": why}, "approver")["error"]["code"] == "conflict"
    )  # nothing left to release


def test_x_15_release_lets_the_run_go_on():
    publish(device_doc())
    cid = open_case("SN-F-3", BLACKLIST, QUOTE)
    run_id, rec = intake(cid)
    assert rec.status == "held"
    ok(call("fraud.release", {"case_id": cid, "reason": "Verified against the blacklist owner."}, "approver"))
    with SessionLocal() as s:
        runtime.run_until_blocked(s, run_id, max_steps=3)
        recs = {r.stage: r for r in chain.records_of(s, run_id)}
    assert recs["intake"].status == "done"


def test_x_15_no_automatic_decline():
    cid = held_case()
    before = case_now(cid)["stage"]
    r = prepared("fraud.reject", {"case_id": cid, "reason": "The serial is on the blacklist."})
    assert r["ok"] is False and r["error"]["code"] == "approval_required"
    assert case_now(cid)["stage"] == before and journal("decision.decline") == [] and journal("fraud.reject") == []
    # the person declines it through the existing decline path
    out = ok(call("fraud.reject", {"case_id": cid, "reason": "The serial is on the blacklist."}, "approver"))
    assert out["status"] == "rejected"
    c = case_now(cid)
    assert c["stage"] == "reeval" and c["fraud"]["status"] == "rejected" and c["fraud"]["resolved_by"] == "approver"
    assert [row["actor"] for row in journal("decision.decline")] == ["approver"]
    assert [i["status"] for i in items(cid)] == ["done"]


def test_fraud_release_and_reject_are_forbidden_to_agents():
    assert forbidden("fraud.release") and forbidden("fraud.reject")
    assert {"fraud.release", "fraud.reject"} <= set(FORBIDDEN_ACTIONS)
    assert not forbidden("fraud.hold") and not forbidden("fraud.simulate")


def test_fraud_release_tenant_boundary(monkeypatch):
    cid = held_case()
    body = {"case_id": cid, "reason": "Trying to release another customer's hold."}
    assert call("fraud.release", body, "planner-b")["error"]["code"] == "out_of_scope"  # no approval rights at all
    monkeypatch.setattr(policy, "limit_for", lambda *a, **k: 1000.0)  # were the right granted, the tenant boundary refuses
    for action in ("fraud.release", "fraud.reject"):
        r = call(action, body, "planner-b")
        assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", (action, r)
    assert case_now(cid)["fraud"]["status"] == "held"


def test_fraud_hold_by_an_agent_runs_and_is_one_per_rule_version():
    r = prepared("fraud.hold", hold_input(), user="planner-a")
    assert r["ok"] is True, r
    assert case_now(CASE)["fraud"]["by"] == "coordinator"
    again = call("fraud.hold", hold_input(), "planner-a")
    assert again["ok"] is False and again["error"]["code"] in ("duplicate", "conflict")


# ---------------------------------------------------------------- the rules are pack data
def test_x_15_rules_are_pack_data():
    publish(device_doc())
    assert intake(open_case("SN-F-4", BLACKLIST, QUOTE))[1].status == "held"
    op = {"id": "op-1", "op": "set_param", "path": "fraud.threshold", "value": 0.9, "seen": 0.6}
    ref = {"pack_key": "device", "org_unit_id": "Customer A"}
    ok(call("overlay.save", ref | {"ops": [op]}, "planner-a"))
    ok(call("overlay.submit", ref, "planner-a"))
    ok(call("overlay.approve", ref, "approver"))
    _, rec = intake(open_case("SN-F-5", BLACKLIST, QUOTE))  # the same evidence, the next intake: 0.8 against 0.9
    assert rec.status == "done" and rec.output["fraud"] == {"score": 0.8, "threshold": 0.9, "rule_version": "v1", "held": False}


def test_x_15_simulated_first():
    publish(device_doc())
    open_case("SN-S-1", QUOTE)  # 0.3
    open_case("SN-S-2", BLACKLIST)  # 0.5
    open_case("SN-S-3", BLACKLIST, QUOTE)  # 0.8
    ask = {"pack": "device", "org_unit_id": "Customer A"}
    low = ok(call("fraud.simulate", ask | {"threshold": 0.5}, "admin"))
    high = ok(call("fraud.simulate", ask | {"threshold": 0.9}, "admin"))
    assert (low["cases"], low["held"], high["held"], low["held_now"]) == (3, 2, 0, 1)
    assert low["by_signal"] == {"F-BL": 2, "F-QM": 2}
    assert [c["case_id"] for c in low["would_change"] if c["now"]] and [c["now"] for c in high["would_change"]] == [False]
    assert case_now("RT-1048").get("fraud") is None  # a simulation changes nothing
    assert call("fraud.simulate", ask, "approver")["error"]["code"] == "out_of_scope"  # manageFlows only
    assert call("fraud.simulate", ask | {"org_unit_id": "Customer B"}, "planner-a")["error"]["code"] == "tenant_boundary"


def test_x_15_repeat_returns_window():
    cids = [open_case("SN-R-1", reason=r) for r in ("rma", "trade_in", "manual")]
    with SessionLocal() as s:
        assert repeat_counts(s, case_now(cids[0]), [90, 365]) == {"90": 3, "365": 3}
        s.execute(text("UPDATE case_record SET created_at = now() - interval '120 days' WHERE id = :i"), {"i": cids[0]})
        assert repeat_counts(s, case_now(cids[0]), [90, 365]) == {"90": 2, "365": 3}  # 120 days ago is outside 90
        assert repeat_counts(s, {"assetId": None}, [90]) == {}
    pack = parse_pack(device_doc())
    rr = list(triage({}, pack, {"90": 3}).fired())
    assert [s.id for s in rr] == ["F-RR"] and triage({}, pack, {"90": 2}).fired() == []
    assert triage({}, pack, {"90": 3}).held  # 0.7 against 0.6
