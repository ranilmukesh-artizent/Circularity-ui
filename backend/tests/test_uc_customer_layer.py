"""Plan 9, P9-9.14 (stories UC-14 to UC-17): the used-car customer layer: diversions, the audited skip refusal and the locked
guardrails.

A customer's diversions are overlay operations on the used-car pack (`apply_overlay`, the overlay approval of P9-1.3), applied by
`decide_case` after the gates (R20). `DV-UC-EV` adds the step `battery_assessment` for an EV under 80 percent battery health: the
case is held, an instruction goes to the inspection app, no channel is valued until `condition.battery_assessment_result` is on
file, and the hold releases itself when it arrives. `DV-UC-MILES` sends a car over 120,000 miles to the wholesale auction only;
the title, odometer and recall gates still run. `DV-UC-SKIP` (skip the title check) is refused and audited. The three locked
guardrails
(G-VEH-TITLE, G-VEH-ODO, G-VEH-RECALL) accept an extra approver and nothing else: any other change is `locked_guardrail`.
Fixed deviations from the spec text (the operation vocabulary is the registry's, I-4): the shortcut's target is `to`, an EV step
carries `owner_role`, and the conditions use `lte 79.99` and `gte 120000` (the operators are eq, ne, in, gte, lte, exists).
Legal note: the refusal and guardrail wording is product text; Kinective's Legal team reviews it before it is relied on.
"""

from typing import Any

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories.live_rules import live_pack
from di.services.cases import battery_wait, gate_hold
from di.services.instructions import writers
from di.services.modeler.pack import load_pack
from tests import ucfixtures as uc
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

ORG = uc.ORG
PACK = "used_cars"
EV = {"id": "op-1", "op": "add_step", "stage": "condition", "step": "battery_assessment", "owner_role": "inspection_lead",
      "when": [{"fact": "asset.powertrain", "op": "eq", "value": "ev"},
               {"fact": "condition.battery_soh", "op": "lte", "value": 79.99}]}  # fmt: skip
MILES = {"id": "op-2", "op": "shortcut", "stage": "value", "to": "auction",
         "when": [{"fact": "asset.mileage_at_return", "op": "gte", "value": 120000}]}  # fmt: skip
SKIP = {"id": "op-3", "op": "shortcut", "stage": "receive", "to": "condition",
        "when": [{"fact": "asset.return_kind", "op": "eq", "value": "trade_in"}]}  # fmt: skip
REF = {"pack_key": PACK, "org_unit_id": ORG}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    uc.start()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM domain_event WHERE type = 'overlay.blocked'"))
        conn.execute(text("DELETE FROM instruction WHERE kind = 'battery_assessment'"))
    monkeypatch.setattr(battery_wait, "enabled", lambda: True)  # the suite sends nothing; the queued row is what these tests read
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM domain_event WHERE type = 'overlay.blocked'"))
        conn.execute(text("DELETE FROM instruction WHERE kind = 'battery_assessment'"))
    uc.finish()


def _save(*ops: dict[str, Any], user: str = "planner-a") -> dict[str, Any]:
    return call("overlay.save", {**REF, "ops": list(ops)}, user)


def _publish(*ops: dict[str, Any]) -> None:
    assert _save(*ops)["ok"]
    assert call("overlay.submit", REF, "planner-a")["ok"]
    assert call("overlay.approve", REF, "approver")["ok"]


def _instructions(cid: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        q = text("SELECT kind, system, idem_key, status FROM instruction WHERE case_id = :c AND kind = 'battery_assessment'")
        return [dict(r) for r in s.execute(q, {"c": cid}).mappings()]


def _assessed(n: int, soh: int = 74) -> None:
    """The inspection app's completed assessment of sample UC-S<n>, as its adapter writes it."""
    row = {"assessmentId": "BA-0001", "vin": uc.vin(n), "status": "complete", "batterySoh": soh,
           "result": "fit_for_retail" if soh >= 80 else "pack_replacement_needed", "org_unit_id": ORG}  # fmt: skip
    uc.write("uc_insp", "battery_assessments", row)


def _recheck(n: int) -> list[str]:
    """What the worker's `case.gateRecheck` job does once the assessment's fact lands."""
    from di.services.canonical.schema import vin_key

    with SessionLocal() as s:
        out = gate_hold.recheck(s, vin_key(ORG, uc.vin(n)))
        s.commit()
    return out


def _queued_rechecks() -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM job WHERE kind = 'case.gateRecheck'")).scalar_one()


# ---------------------------------------------------------------- UC-14
def test_uc_14_ev_diversion_waits_for_assessment():
    _publish(EV)
    c = uc.open_car(6)  # UC-S6: an EV at 74 percent battery health
    assert c["requiredSteps"] == [
        {"gate": "op-1", "step": "battery_assessment", "owner": "inspection_lead", "stage": "condition", "kind": "diversion"}
    ]
    assert c["recommendation"] is None and c["stage"] == "none" and c["gateHold"]["gates"] == ["battery_assessment"]
    assert c["routes"] and all(r["excluded"] for r in c["routes"])  # no route is valued
    assert any("battery assessment" in r["failReason"] for r in c["routes"])
    (ins,) = _instructions(c["id"])
    assert (ins["kind"], ins["system"], ins["idem_key"]) == ("battery_assessment", "uc_insp", f"BATTERY.{c['id']}.{uc.vin(6)}")

    _assessed(6)  # the result arrives: the hold releases itself
    assert _queued_rechecks() >= 1  # the fact that lands queues the recheck of the held car
    assert _recheck(6) == [c["id"]]
    c = uc.get(c["id"])
    assert c.get("gateHold") is None and c["recommendation"] is not None and c["stage"] == "awaiting_approval"
    assert any(not r["excluded"] for r in c["routes"])
    assert len(_instructions(c["id"])) == 1  # a second look sends no second request


def test_uc_14_other_cars_are_not_diverted():
    _publish(EV)
    c = uc.open_car(1)  # a petrol car: the diversion does not match
    assert "requiredSteps" not in c and c.get("gateHold") is None and c["recommendation"] is not None
    assert _instructions(c["id"]) == []
    healthy = uc.open_car(16, like=6, battery=88)  # an EV at 88 percent: over the 80 percent line
    assert healthy.get("gateHold") is None and _instructions(healthy["id"]) == []


def test_uc_14_template_unchanged():
    _publish(EV)
    assert [d.step for d in load_pack(PACK).diversions] == []  # the pack file never holds a customer's diversion
    with SessionLocal() as s:
        pack = live_pack(s, {"template": PACK, "owner": ORG})
    assert [d.step for d in pack.diversions] == ["battery_assessment"]
    assert all("battery_assessment" not in str(g) for g in load_pack(PACK).guardrails)


def test_uc_14_writer_posts_the_vin_with_the_instruction_key(monkeypatch):
    sent: list[dict[str, Any]] = []

    class Reply:
        def json(self) -> dict[str, Any]:
            return {"assessmentId": "BA-0007", "status": "scheduled"}

    class Client:
        def request(self, method: str, path: str, **kw: Any) -> Reply:
            sent.append({"method": method, "path": path, **kw})
            return Reply()

        def close(self) -> None:
            pass

    monkeypatch.setattr(writers, "client", lambda s, source: Client())
    case = {"id": "RT-9", "assetId": f"{ORG}:{uc.vin(6)}", "vehicle": {"vin": uc.vin(6)}}
    got = writers.WRITERS["battery_assessment"](None, {"idem_key": "BATTERY.RT-9.X"}, case, {})  # type: ignore[arg-type]
    assert sent == [{"method": "POST", "path": "/battery-assessments", "json": {"vin": uc.vin(6)},
                     "headers": {"Idempotency-Key": "BATTERY.RT-9.X"}}]  # fmt: skip
    assert (got.doc_ref, got.detail["vin"]) == ("BA-0007", uc.vin(6))
    with pytest.raises(writers.NotApplicable):
        writers.WRITERS["battery_assessment"](None, {"idem_key": "k"}, {"id": "RT-9"}, {})  # type: ignore[arg-type]


def test_uc_14_writer_turns_a_4xx_into_a_refusal(monkeypatch):
    from di.connectors.http import SourceError

    class Client:
        def request(self, *a: Any, **k: Any) -> Any:
            raise SourceError("client", "The car has no traction battery to assess.")

        def close(self) -> None:
            pass

    monkeypatch.setattr(writers, "client", lambda s, source: Client())
    with pytest.raises(writers.Refused):
        writers.WRITERS["battery_assessment"](None, {"idem_key": "k"}, {"id": "RT-9", "vehicle": {"vin": "V"}}, {})  # type: ignore[arg-type]


# ---------------------------------------------------------------- UC-15
def test_uc_15_high_mileage_shortcut_keeps_gates():
    _publish(MILES)
    c = uc.open_car(5)  # UC-S5: 133,000 miles
    assert [r["id"] for r in c["routes"] if not r["excluded"]] == ["auction"]  # only the auction is valued
    others = [r for r in c["routes"] if r["id"] != "auction"]
    assert others and any("op-2" in r["failReason"] for r in others)  # the channels it left out say why
    assert c["recommendation"]["id"] == "auction"
    gates = {g["id"]: g["passed"] for g in c["gates"]}
    three = ("G-VEH-TITLE", "G-VEH-ODO", "G-VEH-RECALL")  # stages 2 and 3 still ran
    assert set(three) <= set(gates) and all(gates[g] for g in three)
    under = uc.open_car(1)  # 38,000 miles: every channel is valued
    assert len([r for r in under["routes"] if not r["excluded"]]) > 1


def test_uc_15_shortcut_cannot_revive_a_blocked_channel():
    _publish(MILES)
    c = uc.open_car(15, like=5, lien=True)  # a lien: the title gate blocks every channel, the shortcut brings none back
    assert all(r["excluded"] for r in c["routes"]) and c["recommendation"] is None


# ---------------------------------------------------------------- UC-16
def test_uc_16_title_skip_blocked_and_audited():
    r = _save(SKIP)
    assert r["ok"] is False and r["error"]["overlay_code"] == "skips_compliance" and r["error"]["op_id"] == "op-3"
    assert r["error"]["message"] == (
        "Blocked: this skips the compliance guardrail Clear title and no open finance before any sale channel "
        "at Match and verify."
    )
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT payload FROM domain_event WHERE type = 'overlay.blocked'")).all()
    assert len(rows) == 1
    p = rows[0].payload
    assert (p["guardrail"], p["by"], p["pack_key"], p["org_unit_id"]) == ("G-VEH-TITLE", "planner-a", PACK, ORG)
    assert p["op"]["id"] == "op-3" and p["op"]["when"] == SKIP["when"]  # who, what and the text of the attempt
    assert call("overlay.submit", REF, "planner-a")["ok"] is False  # nothing was saved


# ---------------------------------------------------------------- UC-17
@pytest.mark.parametrize("target", ["G-VEH-RECALL", "G-VEH-TITLE", "G-VEH-ODO"])
def test_uc_17_locked_guardrail_tighten_only(target):
    tighten = {"id": "op-1", "op": "tighten", "target": target, "field": "max_age_days", "value": 30, "seen": 90}
    r = _save(tighten)
    assert r["ok"] is False and r["error"]["code"] == "locked_guardrail" and r["error"]["op_id"] == "op-1"
    assert "locked by the pack" in r["error"]["message"]
    param = {"id": "op-1", "op": "set_param", "path": f"{target}.max_age_days", "value": 30, "seen": 90}
    r = _save(param)
    assert r["ok"] is False and r["error"]["code"] == "locked_guardrail" and r["error"]["op_id"] == "op-1"
    approver = {"id": "op-1", "op": "add_approver", "target": target, "role": "used_car_manager"}
    assert _save(approver)["ok"]  # an extra approver is accepted
    assert call("overlay.submit", REF, "planner-a")["ok"]
    with SessionLocal() as s:
        q = text("SELECT status FROM customer_overlay WHERE pack_key = :p AND org_unit_id = :o")
        row = s.execute(q, {"p": PACK, "o": ORG}).one()
    assert row.status == "review"  # pending approval
    assert call("overlay.approve", REF, "approver")["ok"]
    with SessionLocal() as s:
        g = next(x for x in live_pack(s, {"template": PACK, "owner": ORG}).guardrails if x.id == target)
    assert g.approvers == ["used_car_manager"] and g.locked and g.type == "Compliance"  # stricter, and still locked


def test_uc_17_a_customer_only_tightens_the_unlocked_ones():
    bad = {"id": "op-1", "op": "tighten", "target": "G-VEH-BRAND", "field": "threshold", "value": 1, "seen": 0}
    r = _save(bad)
    assert r["ok"] is False and r["error"]["code"] != "locked_guardrail"  # the brand check is not locked: it just has no field
    recon = {"id": "op-1", "op": "tighten", "target": "AP-UC-RECON", "field": "condition.recon_estimate",
             "value": 2000, "seen": 2500}  # fmt: skip
    assert _save(recon)["ok"]
