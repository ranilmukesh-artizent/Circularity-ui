"""P9-12.7 (stories NS-BAT-01, NS-BAT-02, NS-BAT-03): the battery pack's link to the used-car case, its passport step from a date,
and the dangerous-goods lane. `BP-044` is the pack of the car with VIN `SYNUC000000000044`; the records are the ones the mock
`bat_bms` serves (source-sim/sim/vendors/battery_bms, built here as literals) read through the real adapter's `map()`. The
decisions on the pure cases run the one decider (`decide_case`, R19) with no session. Compliance wording (battery passport,
dangerous-goods transport) is product text; Kinective's Legal team reviews it before it is relied on. The passport date
(18 Feb 2027) is indicative.
"""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.canonical.schema import serial_key, vin_key
from di.services.cases import intake
from di.services.cases import store as cases
from di.services.cases.decide import decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.gate_checks.battery import case_view
from di.services.modeler.pack import load_pack
from tests import flowkit
from tests import ucfixtures as uc
from tests.helpers import call

ORG = uc.ORG
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "battery.json"
PASSPORT_DAY = datetime(2027, 2, 18, tzinfo=UTC)
BEFORE = datetime(2026, 11, 25, tzinfo=UTC)
NOT_YET = "Battery passport not yet required (from 18 Feb 2027, indicative)"
FITNESS = {"type": "repurpose_fitness", "source": "manual", "at": "2026-11-10T00:00:00+00:00", "result": "pass", "value": {}}
PERMIT = {"type": "recycler_permit", "source": "manual", "at": "2026-11-10T00:00:00+00:00", "result": "pass",
          "value": {"permit_ref": "RP-7", "chemistries": ["NMC", "LFP"]}}  # fmt: skip


def _pack_row(**over: Any) -> dict[str, Any]:
    row = {"packId": "BP-044", "vinRef": uc.vin(44), "chemistry": "NMC", "sohPct": 74, "expectedLifeYears": 4,
           "readAt": "2026-11-10", "thermalEvent": False, "damaged": False, "safetyClass": "9", "market": "EU",
           "org_unit_id": ORG}  # fmt: skip
    return row | over


def _case(market: str = "US", **over: Any) -> dict[str, Any]:
    """A pure pack case: the `battery` view (what intake keeps on a case) and the records its gates read."""
    facts = {"packId": "BP-1", "chemistry": "NMC", "soh_pct": 86, "expected_life_years": 7, "read_at": "2026-11-10",
             "market": market} | over  # fmt: skip
    return {"id": "BAT-T", "cls": "ev_pack", "battery": case_view(facts), "evidenceRecords": [PERMIT]}


def _decide(c: dict[str, Any], as_of: datetime = BEFORE, rules: tuple = ()):
    return decide_case(c, load_pack("battery"), FlowVersion(None, 0, rules), as_of)


def _gates(d) -> dict[str, Any]:
    return {g.gate_id: g for g in d.gates}


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture
def world():
    uc.start()
    flowkit.reset_flows()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.4"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        extra.register(s, "bat_bms", ORG)
        s.commit()
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:BP-%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:BP-%"})
    uc.finish()
    flowkit.reset_flows()


def _write_pack(row: dict[str, Any]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, "bat_bms", ADAPTERS["bat_bms"].map(Record("packs", row["packId"], row)))
        s.commit()


def test_ns_bat_01_ev_assessment_opens_battery_case(world):
    """The car's assessment says `pack_replacement_needed`: one `battery` case for BP-044, linked both ways. A second look
    (the car valued again) opens no second case."""
    car = uc.open_car(44, like=6)  # an EV
    _write_pack(_pack_row())
    done = {"assessmentId": "BA-0044", "vin": uc.vin(44), "status": "complete", "batterySoh": 74,
            "result": "pack_replacement_needed", "org_unit_id": ORG}  # fmt: skip
    uc.write("uc_insp", "battery_assessments", done)
    for _ in range(2):
        with SessionLocal() as s:
            c = cases.get(s, car["id"], for_update=True)
            assert c is not None
            intake.revalue(s, c)
            cases.save(s, c)
            s.commit()
    car = uc.get(car["id"])
    with SessionLocal() as s:
        rows = s.execute(text("SELECT id FROM case_record WHERE data ->> 'template' = 'battery'")).scalars().all()
        assert len(rows) == 1
        bat = cases.get(s, rows[0])
    assert bat is not None
    assert bat["assetId"] == serial_key(ORG, "BP-044") and bat["linked_case"] == car["id"]
    assert [x["case"] for x in car["linked"]] == [bat["id"]] and car["linked"][0]["template"] == "battery"
    assert (bat["battery"]["soh_pct"], bat["battery"]["chemistry"], bat["battery"]["market"]) == (74, "NMC", "EU")
    assert vin_key(ORG, uc.vin(44)) == car["assetId"]  # the car case is the one keyed by the VIN


def test_ns_bat_01_a_replacement_needed_without_a_pack_on_file_opens_nothing(world):
    car = uc.open_car(44, like=6)
    uc.write("uc_insp", "battery_assessments", {"assessmentId": "BA-0044", "vin": uc.vin(44), "status": "complete",
                                                  "batterySoh": 74, "result": "pack_replacement_needed", "org_unit_id": ORG})  # fmt: skip
    with SessionLocal() as s:
        c = cases.get(s, car["id"], for_update=True)
        assert c is not None
        intake.revalue(s, c)
        cases.save(s, c)
        n = s.execute(text("SELECT count(*) FROM case_record WHERE data ->> 'template' = 'battery'")).scalar_one()
        s.commit()
    assert n == 0 and not uc.get(car["id"]).get("linked")


def test_ns_bat_02_passport_step_from_date():
    """From 2027-02-18 a repurpose for the EU requires the step `battery_passport`; before it the gate says so and requires
    nothing. A US pack never needs one."""
    c = _case(market="EU", read_at="2027-02-10")
    after = _decide(c, PASSPORT_DAY)
    g = _gates(after)["G-BAT-3"]
    assert not g.passed and g.effect.kind == "require_step" and g.effect.step == "battery_passport"
    assert set(g.effect.routes) == {"repurpose", "remanufacture"} and g.evidence_missing == ("battery_passport",)
    assert [x["step"] for x in after.required_steps if x["gate"] == "G-BAT-3"] == ["battery_passport"]
    before = _decide(c, BEFORE)
    g = _gates(before)["G-BAT-3"]
    assert g.passed and g.reason == NOT_YET and g.effect.routes == ()
    assert not [x for x in before.required_steps if x["gate"] == "G-BAT-3"]
    us = _decide(_case(market="US"), PASSPORT_DAY)
    assert "G-BAT-3" not in _gates(us)
    held = {"type": "battery_passport", "source": "manual", "at": "2027-02-17T00:00:00+00:00", "result": "pass", "value": {}}
    done = _decide({**c, "evidenceRecords": [*c["evidenceRecords"], held]}, PASSPORT_DAY)
    assert _gates(done)["G-BAT-3"].passed


def test_ns_bat_03_damaged_never_standard_lane():
    """A damaged pack takes only `recycle`, through the dangerous-goods lane; reuse, remanufacture and repurpose are refused
    with the gate's reason. A thermal event alone does the same."""
    for over in ({"damaged": True}, {"thermal_event": True}):
        d = _decide(_case(**over))
        g = _gates(d)["G-BAT-4"]
        assert not g.passed and g.effect.kind == "block" and g.effect.step == "dg_lane"
        assert set(g.effect.routes) == {"reuse", "remanufacture", "repurpose"}
        by = {r["id"]: r for r in d.routes}
        assert all(by[i]["excluded"] for i in g.effect.routes)  # repurpose may fail first on its fitness gate
        assert all("Damaged battery transport" in by[i]["failReason"] for i in ("reuse", "remanufacture"))
        assert not by["recycle"]["excluded"] and d.route == "recycle"
        assert [x["step"] for x in d.required_steps if x["gate"] == "G-BAT-4"] == ["dg_lane"]
    rule = (CompiledRule("BR-1", {}, "prefer", "reuse", "x"),)
    assert _decide(_case(damaged=True), rules=rule).route == "recycle"  # a business rule never revives a refused route


def test_battery_soh_read_gates_everything_but_recycle():
    """G-BAT-1: without a reading of state of health and expected life, with its date, only recycle is left."""
    d = _decide(_case(soh_pct=None, read_at=None))
    g = _gates(d)["G-BAT-1"]
    assert not g.passed and g.evidence_missing == ("battery_soh",) and set(g.effect.routes) == {"reuse", "remanufacture", "repurpose"}
    assert d.route == "recycle"
    ok = _gates(_decide(_case()))["G-BAT-1"]
    assert ok.passed


def test_battery_repurpose_needs_fitness_and_recycle_needs_a_permit_for_the_chemistry():
    d = _decide(_case(soh_pct=62))
    assert not _gates(d)["G-BAT-2"].passed and next(r for r in d.routes if r["id"] == "repurpose")["excluded"]
    with_fit = {**_case(soh_pct=62), "evidenceRecords": [PERMIT, FITNESS]}
    assert _gates(_decide(with_fit))["G-BAT-2"].passed
    wrong = {**_case(), "evidenceRecords": [{**PERMIT, "value": {"permit_ref": "RP-8", "chemistries": ["LFP"]}}]}
    g = _gates(_decide(wrong))["G-BAT-5"]
    assert not g.passed and "NMC" in g.reason and next(r for r in _decide(wrong).routes if r["id"] == "recycle")["excluded"]
    none = {**_case(), "evidenceRecords": []}
    assert _gates(_decide(none))["G-BAT-5"].evidence_missing == ("recycler_permit",)
