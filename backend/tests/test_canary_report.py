"""P9-7.4 (story X-06; registry entry I-17): the canary report and the automatic pause.

The pure part (`canary_stats`) is unit tested; the actions run through the API on a flow of Customer A in a canary at FR 20 %.
The arms' cases are written straight into `case_record` and `rollout_assignment` with known nets, so every figure can be
checked by hand. R16: every number and sentence in the report is code (no model output to route), and the pause is the one thing
the system does alone: it moves towards the known-good version. Widening and full are never automatic.
"""

import json
import math

import pytest
from sqlalchemy import text

from di import worker
from di.core.db import SessionLocal
from di.services.modeler.canary_stats import TOO_FEW, arm_stats, diff_band, n_needed, stop_check
from tests import flowkit, starting
from tests.flowkit import ok
from tests.helpers import call
from tests.test_rollout import ORG, replay_done, row, shadow_flow, start

RULES = {"exception_margin": 0.05, "override_margin": 0.05, "hold_margin": 0.05, "min_cases": 30}


@pytest.fixture(autouse=True)
def fresh():
    def clean() -> None:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM rollout"))
            s.execute(text("DELETE FROM replay_run"))
            s.execute(text("DELETE FROM replay_batch"))
            s.execute(text("DELETE FROM work_item WHERE case_id LIKE 'CZ-%' OR type LIKE 'canary_paused:%'"))
            s.execute(text("DELETE FROM case_record WHERE id LIKE 'CZ-%'"))
            s.commit()

    clean()
    starting.reset()
    flowkit.reset_flows()
    yield
    clean()
    flowkit.reset_flows()
    starting.reset()


def canary_flow() -> int:
    fid = shadow_flow("industrial")
    replay_done(fid, real=False)
    ok(start(fid, "FR", 20))
    return fid


def seed_arm(rid: int, arm: str, nets: list[float], *, exceptions: int = 0, overrides: int = 0, holds: int = 0) -> None:
    """One decided case per net in the arm: the first `exceptions` have an exception item, the first `overrides` an override,
    the first `holds` a gate hold."""
    with SessionLocal() as s:
        for n, net in enumerate(nets):
            cid = f"CZ-{'N' if arm == 'canary' else 'K'}{n:03d}"
            data = {"approval": {"by": "t"}, "chosen": {"net": net}, "outcome": {"net": net - 1}}
            if n < overrides:
                data["override"] = {"reason": "t"}
            if n < holds:
                data["gateHold"] = {"gates": ["G"]}
            s.execute(
                text(
                    "INSERT INTO case_record (id, owner, location, stage, data) "
                    "VALUES (:i, :o, 'Hub', 'closed', CAST(:d AS jsonb))"
                ),
                {"i": cid, "o": ORG, "d": json.dumps(data)},
            )
            s.execute(
                text("INSERT INTO rollout_assignment (rollout_id, case_id, arm, ver) VALUES (:r, :c, :a, '1')"),
                {"r": rid, "c": cid, "a": arm},
            )
            if n < exceptions:
                s.execute(
                    text(
                        "INSERT INTO work_item (kind, case_id, type, title, owner_role) "
                        "VALUES ('exception', :c, 'evidence_missing', 'x', 'Planner')"
                    ),
                    {"c": cid},
                )
        s.commit()


def assign_case(rid: int, case_id: str, arm: str = "canary") -> None:
    with SessionLocal() as s:
        s.execute(
            text("INSERT INTO rollout_assignment (rollout_id, case_id, arm, ver) VALUES (:r, :c, :a, '1')"),
            {"r": rid, "c": case_id, "a": arm},
        )
        s.commit()


def stage_of(fid: int) -> str:
    return ok(call("rollout.get", {"flow_id": fid}, "approver"))["stage"]


def journal(action: str) -> list[dict]:
    with SessionLocal() as s:
        rows = s.execute(text("SELECT actor, role FROM action_journal WHERE action = :a AND NOT undone"), {"a": action})
        return [dict(r._mapping) for r in rows]


def submit_and_watch() -> None:
    """The next decision.submit on a case in the canary, then the worker runs the job it queued."""
    ok(call("decision.submit", {"case_id": "RT-1048"}, "admin"))
    while worker.run_once():
        pass


# ---------------------------------------------------------------- the pure part
def test_x_06_arm_stats_and_band_pure():
    rows = [{"decided": True, "override": i < 2, "exception": i < 1, "hold": False, "net": 100.0 + i, "realised": 90.0}
            for i in range(10)]  # fmt: skip
    st = arm_stats(rows)
    assert st["n"] == 10 and st["override_rate"] == 0.2 and st["exception_rate"] == 0.1 and st["hold_rate"] == 0.0
    assert st["mean_net"] == pytest.approx(104.5) and st["mean_realised"] == pytest.approx(90.0)
    a, b = [10.0, 12.0, 11.0, 13.0] * 5, [9.0, 10.0, 8.0, 11.0] * 5
    band = diff_band(a, b)
    assert band == diff_band(a, b)  # the fixed seed: the same inputs, the same bands
    assert band["band95"][0] <= band["band80"][0] <= band["diff"] <= band["band80"][1] <= band["band95"][1]
    assert diff_band([], b) is None


def test_x_06_n_needed_formula():
    nets = [90.0, 110.0] * 10
    var = sum((x - 100) ** 2 for x in nets) / (len(nets) - 1)
    assert n_needed(nets) == math.ceil(16 * var / (0.05 * 100) ** 2)
    assert n_needed([5.0]) == 0 and n_needed([1.0, -1.0]) == 0


def test_x_06_stop_check_text_and_min_cases():
    c = {"n": 40, "override_rate": 0.0, "exception_rate": 0.18, "hold_rate": 0.0}
    k = {"n": 40, "override_rate": 0.0, "exception_rate": 0.09, "hold_rate": 0.0}
    assert stop_check(c, k, RULES) == "Canary exceptions 18 % exceed control 9 % by more than 5 points."
    assert stop_check(c | {"n": 29}, k, RULES) is None  # below min_cases: no verdict
    assert stop_check(c | {"exception_rate": 0.13}, k, RULES) is None  # 4 points: inside the margin
    assert stop_check(c | {"exception_rate": 0.09, "hold_rate": 0.2}, k, RULES).startswith("Canary holds 20 %")


# ---------------------------------------------------------------- the report
def test_x_06_canary_report_arms_and_band():
    fid = canary_flow()
    rid = row(fid).id
    canary = [100.0, 120.0] * 20  # 40 cases, mean 110
    control = [90.0, 110.0] * 80  # 160 cases, mean 100
    seed_arm(rid, "canary", canary, overrides=1)
    seed_arm(rid, "control", control)
    out = ok(call("rollout.report", {"flow_id": fid}, "approver"))
    assert out["canary"]["n"] == 40 and out["control"]["n"] == 160
    assert out["canary"]["mean_net"] == pytest.approx(110.0) and out["control"]["mean_net"] == pytest.approx(100.0)
    assert out["canary"]["mean_realised"] == pytest.approx(109.0)
    assert out["canary"]["override_rate"] == pytest.approx(0.025) and out["control"]["override_rate"] == 0
    band = out["band"]
    assert band["diff"] == pytest.approx(10.0)
    assert band["band80"][0] <= 10.0 <= band["band80"][1] and band["band95"][0] <= band["band80"][0]
    assert out["n_needed"] == n_needed(control)
    assert out["breach"] is None and out["paused"] is None
    # an executive reads the report too (runReplay), a planner of another tenant does not (tenant boundary)
    assert call("rollout.report", {"flow_id": fid}, "exec")["ok"]
    assert call("rollout.report", {"flow_id": fid}, "planner.b")["error"]["code"] == "tenant_boundary"


def test_x_06_min_sample_note():
    fid = canary_flow()
    rid = row(fid).id
    seed_arm(rid, "canary", [100.0] * 10, exceptions=10)  # every canary case is an exception, but only 10 cases
    seed_arm(rid, "control", [100.0] * 10)
    assert ok(call("rollout.report", {"flow_id": fid}, "approver"))["note"] == TOO_FEW
    assign_case(rid, "RT-1048")
    submit_and_watch()
    assert stage_of(fid) == "canary"  # too few cases: no pause
    assert not journal("rollout.autoPause")


# ---------------------------------------------------------------- the automatic pause
def test_x_06_stop_rule_pauses_automatically():
    fid = canary_flow()
    rid = row(fid).id
    seed_arm(rid, "canary", [100.0] * 39, exceptions=8)  # with RT-1048: 8 of 40 = 20 % exceptions
    seed_arm(rid, "control", [100.0] * 50, exceptions=4)  # 8 %
    assign_case(rid, "RT-1048")
    assert stage_of(fid) == "canary"
    submit_and_watch()
    out = ok(call("rollout.get", {"flow_id": fid}, "approver"))
    assert out["stage"] == "paused"
    (entry,) = journal("rollout.autoPause")
    assert entry["actor"] == "system"
    rep = ok(call("rollout.report", {"flow_id": fid}, "approver"))
    reason = "Canary exceptions 20 % exceed control 8 % by more than 5 points."
    assert rep["paused"]["reason"] == reason and rep["paused"]["automatic"] is True and rep["paused"]["by"] == "system"
    with SessionLocal() as s:
        sql = text("SELECT owner_role, cause, status FROM work_item WHERE type = :t")
        items = s.execute(sql, {"t": f"canary_paused:{fid}"}).all()
        events = s.execute(text("SELECT count(*) FROM domain_event WHERE type = 'rollout.paused'")).scalar_one()
    assert {r[0] for r in items} == {"Approver", "Admin"} and all(r[1] == reason and r[2] == "open" for r in items)
    assert events == 1
    # resuming (a person's rollout.widen at the same share) closes the tasks
    assert call("rollout.widen", {"flow_id": fid, "share": 20}, "approver")["ok"]
    with SessionLocal() as s:
        sql = text("SELECT count(*) FROM work_item WHERE type = :t AND status = 'open'")
        assert s.execute(sql, {"t": f"canary_paused:{fid}"}).scalar_one() == 0


def test_x_06_autopause_is_the_systems_alone():
    fid = canary_flow()
    rid = row(fid).id
    for user in ("approver", "admin", "planner.a"):
        r = call("rollout.autoPause", {"rollout_id": rid, "reason": "A person trying it."}, user)
        assert not r.get("ok"), user
    assert stage_of(fid) == "canary"


def test_x_06_widen_never_automatic():
    fid = canary_flow()
    rid = row(fid).id
    seed_arm(rid, "canary", [150.0] * 39)  # a canary doing clearly better than control
    seed_arm(rid, "control", [100.0] * 50)
    assign_case(rid, "RT-1048")
    submit_and_watch()
    assert stage_of(fid) == "canary" and row(fid).share == 20
    assert not journal("rollout.widen") and not journal("rollout.full") and not journal("rollout.autoPause")
    rep = ok(call("rollout.report", {"flow_id": fid}, "approver"))
    assert rep["band"]["band80"][0] > 0 and rep["breach"] is None
