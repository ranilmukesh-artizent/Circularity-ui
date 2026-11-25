"""Plan 9, P9-9.7 (stories UC-05, UC-09): one case per car, with the inspection read.

A lease return or a trade-in opens a `used_cars` case keyed by the VIN (`vin_key`). Its facts keep their source and age; a
second event for the same car joins the open case. The grade is the inspection's read through the pack's grade mapping,
never computed; a missing or scheduled inspection makes it an estimate (confidence 0.70), which holds the decision for
`confidence`. The canonical facts are written by the real adapters' mapping on literal records (no source-sim needed).
"""

import copy
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.actions import hold
from di.services.actions.registry import ACTIONS, ActionError
from di.services.agents import chain
from di.services.agents.stages import condition
from di.services.canonical import store as canonical
from di.services.canonical.schema import vin_key
from di.services.cases import intake
from di.services.cases import store as cases
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import call

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "used_cars.json"


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


LEASE = {
    "leaseId": "LS-0001", "vin": vin(1), "lesseeRef": "L-0001", "leaseEnd": "2026-10-03", "residualValue": 14000,
    "contractMileage": 36000, "odometerAtReturn": 38000, "odometerLastService": 31000, "odometerStatementRef": "OS-0001",
    "odometerNotActual": False, "modelYear": 2021, "segment": "suv", "powertrain": "petrol", "returnCenter": "RC-East",
    "sellerFleetSize": 0, "status": "returned", "updatedAt": "2026-10-07T08:04:00+00:00", "org_unit_id": ORG,
}  # fmt: skip
INSPECTION = {
    "inspectionId": "INS-0001", "vin": vin(1), "status": "complete", "conditionScore": 4, "odometerPhotoReading": 38010,
    "photos": [], "damage": [], "hailDamage": False, "tyres": "ok", "brakes": "ok", "reconEstimate": 1200,
    "reconLines": [{"label": "Tyres", "amount": 1200, "excessWear": False}], "batterySoh": None, "pairedDevices": False,
    "completedAt": "2026-10-05T10:00:00+00:00", "updatedAt": "2026-10-07T08:04:00+00:00", "org_unit_id": ORG,
}  # fmt: skip
TRADE = {
    "tradeId": "TI-061", "vin": vin(61), "tradeAllowance": 9000, "mileage": 52000, "modelYear": 2019, "segment": "sedan",
    "powertrain": "petrol", "payoffConfirmed": True, "org_unit_id": ORG,
}  # fmt: skip
LATE = LEASE | {"leaseId": "LS-0090", "vin": vin(90), "odometerAtReturn": 45000}
LATE_INSPECTION = INSPECTION | {
    "inspectionId": "INS-0090", "vin": vin(90), "status": "scheduled", "conditionScore": None, "odometerPhotoReading": None,
    "reconEstimate": None, "reconLines": [], "completedAt": None,
}  # fmt: skip


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SYNUC%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYNUC%"})


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.1"  # the shipped pack, imported and published as the org's
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        for sid in ("uc_lease", "uc_insp", "uc_dms"):
            extra.register(s, sid, ORG)
        s.commit()
    yield
    _clean()
    starting.reset()


def _write(source: str, resource: str, payload: dict[str, Any]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, ADAPTERS[source].map(Record(resource, "x", payload)))
        s.commit()


def _open(n: int, reason: str, facts: dict[str, Any], **over: Any) -> dict:
    body = {"org_unit_id": ORG, "template_key": "used_cars", "asset_key": vin_key(ORG, vin(n)), "reason": reason,
            "facts": facts} | over  # fmt: skip
    return call("case.open", body, "planner-a")


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _facts(c: dict, source: str | None = None) -> dict[str, Any]:
    """The case's vehicle facts by name (the newest of each, or the newest from `source`)."""
    return {f["fact"]: f for f in c["vehicle"]["facts"] if source in (None, f["source"])}


def _count() -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM case_record WHERE data ->> 'template' = 'used_cars'")).scalar_one())


def test_uc_05_one_case_per_vin():
    _write("uc_lease", "lease_returns", LEASE)
    r = _ok(_open(1, "lease_end", {"vin": vin(1), "mileage": 38000, "return_date": "2026-10-03"}))
    c = _case(r["case_id"])
    facts = _facts(c)
    assert (c["template"], c["assetId"], c["intake"]["reason"]) == ("used_cars", vin_key(ORG, vin(1)), "lease_end")
    assert {n: facts[n]["value"] for n in ("vin", "mileage", "return_date", "source")} == {
        "vin": vin(1), "mileage": 38000, "return_date": "2026-10-03", "source": "uc_lease",
    }  # fmt: skip
    assert all(f["source"] == "uc_lease" and isinstance(f["ageDays"], float) and f["at"] for f in facts.values())
    assert facts["mileage"]["at"] and facts["vin"]["source"] == "uc_lease"
    # a dealer event for the same car joins the open case: one case, two sources
    _write("uc_dms", "trade_ins", TRADE | {"vin": vin(1), "mileage": 38100})
    j = _ok(_open(1, "trade_in", {"vin": vin(1), "mileage": 38100, "return_date": "2026-10-06"}))
    assert j["case_id"] == r["case_id"] and _count() == 1
    joined = _case(r["case_id"])
    assert {f["source"] for f in joined["vehicle"]["facts"]} == {"uc_lease", "uc_dms"}  # one case, two sources
    assert _facts(joined, "uc_lease")["mileage"]["value"] == 38000 and _facts(joined, "uc_dms")["mileage"]["value"] == 38100
    assert all(f["ageDays"] >= 0 for f in joined["vehicle"]["facts"])
    assert [x["reason"] for x in joined["intake"]["joined"]] == ["trade_in"]
    again = _open(1, "trade_in", {"vin": vin(1)})  # a replay of the joined event is refused
    assert again["ok"] is False and "already open" in json.dumps(again)
    with engine.connect() as conn:
        log = conn.execute(text("SELECT reason FROM case_stage_log WHERE case_id = :c ORDER BY id"), {"c": r["case_id"]}).all()
    assert [x[0] for x in log] == ["Case opened from lease_end", "Joined by trade_in from uc_dms"]


def test_uc_05_two_events_in_one_sync_make_one_case():
    def event(reason: str, miles: int) -> dict[str, Any]:
        facts = {"vin": vin(5), "mileage": miles, "return_date": "2026-10-03"}
        return {"org_unit_id": ORG, "template_key": "used_cars", "asset_key": vin_key(ORG, vin(5)), "reason": reason,
                "facts": facts}  # fmt: skip

    with SessionLocal() as s:
        a = intake.open_case(s, event("lease_end", 1), "system")
        b = intake.open_case(s, event("trade_in", 2), "system")
        s.commit()
    assert a["id"] == b["id"] and _count() == 1


def test_uc_05_trade_in_opens_case():
    _write("uc_dms", "trade_ins", TRADE)
    r = _ok(_open(61, "trade_in", {"vin": vin(61), "mileage": 52000, "return_date": "2026-10-06"}))
    c = _case(r["case_id"])
    assert c["intake"]["reason"] == "trade_in" and c["assetId"] == vin_key(ORG, vin(61))
    assert _facts(c)["vin"]["source"] == "uc_dms"
    with SessionLocal() as s:
        assert (canonical.get(s, "asset", vin_key(ORG, vin(61))) or {})["data"]["return_kind"] == "trade_in"


def test_uc_09_inspection_read_not_computed():
    _write("uc_lease", "lease_returns", LEASE)
    _write("uc_insp", "inspections", INSPECTION)
    c = _case(_ok(_open(1, "lease_end", {"vin": vin(1), "mileage": 38000, "return_date": "2026-10-03"}))["case_id"])
    insp = c["vehicle"]["inspection"]
    assert (insp["grade"], insp["score"], insp["estimate"], insp["source"]) == ("B", 4, False, "uc_insp")
    assert insp["at"].startswith("2026-10-05") and isinstance(insp["ageDays"], float) and c["grade"] == "B"
    assert condition.confidence({}, c) == 1.0
    out = condition.output({}, c)
    assert (out["grade"], out["grade_source"], out["estimate"]) == ("B", "uc_insp", False)
    assert condition.sources({}, c)[0]["at"].startswith("2026-10-05")


def test_uc_09_late_inspection_is_estimate():
    _write("uc_lease", "lease_returns", LATE)
    _write("uc_insp", "inspections", LATE_INSPECTION)
    c = _case(_ok(_open(90, "lease_end", {"vin": vin(90), "mileage": 45000, "return_date": "2026-10-03"}))["case_id"])
    insp = c["vehicle"]["inspection"]
    assert (insp["estimate"], insp["source"], insp["status"], insp["grade"]) == (True, "estimate", "scheduled", "C")
    assert condition.confidence({}, c) == 0.70 and condition.output({}, c)["estimate"] is True
    pack = load_pack("used_cars")
    defn = next(d for d in chain.stage_defs(pack) if d.id == "condition")
    assert (defn.autonomy, defn.threshold) == ("limits", 0.75)
    held = hold.evaluate_hold(
        action=ACTIONS["decision.submit"], autonomy=defn.autonomy, confidence=condition.confidence({}, c), value=Decimal(300),
        bulk=1, open_exception=False, conflict=False, guardrail_holds=[], taint=False,
        policy=hold.HoldPolicy(Decimal(600), 100, defn.threshold),
    )  # fmt: skip
    assert [h.reason for h in held] == ["confidence"]


def test_uc_09_no_inspection_at_all_is_an_estimate():
    _write("uc_lease", "lease_returns", LEASE)
    c = _case(_ok(_open(1, "lease_end", {"vin": vin(1), "mileage": 38000, "return_date": "2026-10-03"}))["case_id"])
    assert c["vehicle"]["inspection"]["estimate"] and c["vehicle"]["inspection"]["status"] == "none"
    assert condition.confidence({}, c) == 0.70
    # the inspection arrives: the case valued again reads it
    _write("uc_insp", "inspections", INSPECTION)
    with SessionLocal() as s:
        cur = cases.get(s, c["id"])
        assert cur is not None
        intake.revalue(s, cur)
    assert cur["vehicle"]["inspection"]["grade"] == "B" and not cur["vehicle"]["inspection"]["estimate"]
    assert len([e for e in cur["evidenceRecords"] if e["type"] == "grade"]) == 1


def test_uc_09_read_grade_is_pure():
    t = datetime(2026, 11, 1, tzinfo=UTC)
    m = load_pack("used_cars").grades.map_from
    done = {"status": "complete", "score": 2, "at": "2026-10-01T00:00:00+00:00", "source": "uc_insp"}
    assert condition.read_grade(m, done, 1, t)["value"] == {"grade": "D", "estimate": False, "score": 2.0}
    assert condition.read_grade(m, done | {"score": 9}, 20000, t)["value"]["estimate"] is True  # not on the scale
    assert condition.read_grade(m, None, 20000, t)["value"]["grade"] == "B"
    assert condition.read_grade(m, None, 70000, t)["value"]["grade"] == "D"
    assert condition.read_grade(m, None, None, t)["value"]["grade"] == "C"


def test_uc_05_a_car_needs_its_key():
    with SessionLocal() as s, pytest.raises(ActionError):
        intake.open_case(s, {"org_unit_id": ORG, "template_key": "used_cars", "asset_key": " ", "reason": "lease_end"}, "x")
