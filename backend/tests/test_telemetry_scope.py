"""MVP-7.1: telemetry facts as rule scope. The industrial template's `alarm` dim is "yes" when the asset's latest
telemetry is at an alarm threshold of the condition-monitoring kit (vibration 7.1 mm/s, bearing 90 °C), "no" below
them; with no telemetry the case has no `alarm`, so a rule scoped on it does not match (edge case 11).

The end-to-end test connects iot (not provisioned in the demo's starting state) and puts that state back afterwards, as
tests/test_adapter_aws_iot.py does: iot unavailable, none of its facts, runs or jobs left, and the mock reset.
"""

import json

import pytest
from sqlalchemy import text

from di.connectors.sync import ensure_sources, run_sync
from di.core import state
from di.core.db import SessionLocal, engine
from di.services.cases import store
from di.services.modeler.facts import case_scope_facts
from di.services.modeler.scope import in_scope
from di.services.modeler.templates import load_template
from tests import flowkit
from tests.flowkit import ok
from tests.helpers import call, client, h
from tests.test_adapter_aws_iot import SID, STARTING, aws, counts, drop_iot_jobs, restore, sim

IND = load_template("industrial")
ALARMED = ("RT-1065", "MTR-2430")  # Customer A, grade C: redeploy is eligible; its kit is made to report an alarm
QUIET = "RT-1048"  # Customer A, MTR-2041: 2.8 mm/s, 66.0 °C


def test_alarm_yes_from_vibration():
    case = {"id": "RT-1", "grade": "C"}
    assert case_scope_facts(case, {"vibration_mm_s": 7.1, "bearing_temp_c": 66.0})["alarm"] == "yes"
    assert case_scope_facts(case, {"vibration_mm_s": 2.8, "bearing_temp_c": 90})["alarm"] == "yes"
    got = case_scope_facts(case, {"vibration_mm_s": 7.09, "bearing_temp_c": 89.9})
    assert got == {"id": "RT-1", "grade": "C", "alarm": "no"}
    assert case == {"id": "RT-1", "grade": "C"}  # the case itself is not changed
    assert in_scope(got | {"alarm": "yes"}, {"alarm": ["yes"]}, IND.dims)
    assert not in_scope(got, {"alarm": ["yes"]}, IND.dims)


def test_no_telemetry_no_alarm_key():
    case = {"id": "RT-1", "alarm": "yes"}  # an earlier evaluation's fact goes when the telemetry does
    for t in (None, {}, {"grade": "B", "inspection_ref": "X"}):
        got = case_scope_facts(case, t)
        assert "alarm" not in got and got["id"] == "RT-1"
        assert not in_scope(got, {"alarm": ["yes"]}, IND.dims) and not in_scope(got, {"alarm": ["no"]}, IND.dims)
        assert in_scope(got, {"alarm": []}, IND.dims)


def test_alarm_is_an_industrial_dim():
    d = next(d for d in IND.dims if d.key == "alarm")
    assert (d.kind, d.values) == ("set", ("yes", "no"))


# ---------------------------------------------------------------- end to end, with iot connected
def _reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE delegation SET enabled = true"))
        conn.execute(text("DELETE FROM tenant_grant"))
        conn.execute(text("DELETE FROM domain_event"))
        conn.execute(text("DELETE FROM case_stage_log WHERE seq IS NOT NULL"))
        conn.execute(text("DELETE FROM action_journal"))
    store.reset()
    state.reset()
    flowkit.reset_flows()


def _iot_back() -> None:
    sim("DELETE", "/_sim/faults", params={"system": SID})
    restore()
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    drop_iot_jobs()


@pytest.fixture
def iot():
    _reset()
    sim("POST", "/_sim/reset", params={"system": SID})
    with SessionLocal() as s:
        ensure_sources(s)
    restore()
    yield
    _iot_back()
    _reset()
    assert counts() == STARTING


def _case(case_id: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, case_id)
    assert c is not None
    return c


def _reevaluate(case_id: str) -> None:
    ok(call("decision.decline", {"case_id": case_id, "reason": "Re-check with the telemetry."}, "admin"))
    ok(call("case.reevaluate", {"case_id": case_id}, "admin"))


def _route(c: dict, rid: str) -> dict:
    return next(r for r in c["routes"] if r["id"] == rid)


def test_rule_never_redeploy_on_alarm(iot):
    case_id, asset = ALARMED
    r = client.post(f"/api/sources/{SID}/connect", headers=h("developer"))
    assert r.status_code == 200 and r.json()["status"] == "live", r.text
    drop_iot_jobs()  # the test runs the sync itself
    # the returned asset's kit had reported an alarm before it was unplugged
    rep = {"operatingHours": 9000.0, "dutyCyclePct": 60.0, "vibrationMmS": 7.6, "bearingTempC": 81.0, "running": False}
    shadow = {"state": {"reported": rep | {"sampleAt": 1790000000000}}}
    aws("POST", "data", f"/things/cm-{asset.lower()}/shadow", {"name": "condition"}, json.dumps(shadow).encode())
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok", out
    flowkit.fork_and_publish("Customer A", [("IR-01", "exclude", "redeploy", {"alarm": ["yes"]})])
    _reevaluate(case_id)
    _reevaluate(QUIET)
    c, q = _case(case_id), _case(QUIET)
    rd = _route(c, "redeploy")
    assert (rd["excluded"], rd["failGate"]) == (True, 2)
    assert rd["failReason"] == "Excluded by business rule IR-01: with a telemetry alarm: never redeploy"
    assert (c["alarm"], c["rulesApplied"]) == ("yes", ["IR-01"])
    assert not _route(q, "redeploy")["excluded"] and q["recommendation"]["id"] == "redeploy"
    assert q["alarm"] == "no" and "rulesApplied" not in q
