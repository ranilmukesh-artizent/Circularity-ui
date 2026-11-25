"""Plan 9, P9-3.9 (story TF-06): wear index and remaining life per component of a tool. Computed, not written by a model.

`tool_life.evaluate` (pure) is A 1.5: `k_i = 1 + alpha_i * s_hi`, `U_i = max(0, h - h0_i) * k_i + sum(n_e * p_e)`,
`c_i = min(1, U_i / L_i)`, `RUL_i = round(100 * (1 - c_i))`, `WTI = round(100 * sum(w_i * c_i))`, `RUL_tool` the least
`RUL_i` of the critical components. The worked example is the combihammer CMH-48213 (820 h, 30% high load, piston kit
replaced at 500 h). No model step: no explanation is written here, so no `AgentLoop` and no model tests belong to it.

The pinned clock is 2026-10-07 09:00 UTC. The sample world (the prototype's returns) has no life inputs: it keeps its numbers.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from di.core import golden
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.cases import intake
from di.services.cases.decide import decide_case
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import tool_fleet, tool_life
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "tool-fleet-a"
NOW = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
PARAMS = load_pack("tool_fleet").valuer.params["life"]
HELD = {"release", "redeploy"}
SERIALS = ("CMH-48213", "CMH-48777")


def _inputs(**over) -> tool_life.LifeInputs:
    base = {
        "cls": "CMH", "hours": 820.0, "high_load_share": 0.30, "events": {}, "months_on_contract": None,
        "coverage_pct": 95.0, "telemetry_age_days": 3.0, "repair_history_complete": True,
        "components": tool_life.components("CMH", PARAMS, replacements={"Piston and seal kit": 500.0}),
    }  # fmt: skip
    return tool_life.LifeInputs(**(base | over))


# ------------------------------------------------------------------ the pure computation
def test_tf_06_worked_example():
    r = tool_life.evaluate(_inputs(), PARAMS)
    assert r.wti == 65
    assert [c.rul_pct for c in r.per_component] == [21, 37, 59, 39]
    assert (r.rul_tool, r.weakest, r.rul_tool_hours) == (21, "Motor armature", 223.5)
    assert r.confidence == "High" and r.range is None
    assert r.rule_version == "tf-life-1" and r.table_version == PARAMS["table_version"]
    assert [c.source for c in r.per_component] == ["pack"] * 4


def test_tf_06_low_confidence_range():
    r = tool_life.evaluate(
        _inputs(hours=None, high_load_share=None, months_on_contract=41, coverage_pct=None, telemetry_age_days=None,
                components=tool_life.components("CMH", PARAMS)),
        PARAMS,
    )  # fmt: skip
    assert r.inputs["hours"] == 820 and r.rul_tool == 21
    assert r.range == (0, 53) and r.confidence == "Low"


def test_tf_06_medium_on_coverage_gap():
    assert tool_life.evaluate(_inputs(coverage_pct=80.0), PARAMS).confidence == "Medium"
    assert tool_life.evaluate(_inputs(repair_history_complete=False), PARAMS).confidence == "Medium"
    assert tool_life.evaluate(_inputs(telemetry_age_days=7.0), PARAMS).confidence == "Low"  # GR-13 failed


def test_tf_06_rerun_same_numbers():
    a, b = tool_life.evaluate(_inputs(), PARAMS), tool_life.evaluate(_inputs(), PARAMS)
    assert a == b
    assert a.inputs["hours"] == 820 and a.inputs["high_load_share"] == 0.3 and a.inputs["components"][0]["rated_hours"] == 1200
    assert a.table_version and a.rule_version


def test_tf_06_events_add_equivalent_hours():
    base = tool_life.evaluate(_inputs(), PARAMS)
    worn = tool_life.evaluate(_inputs(events={"overheat": 2}), PARAMS)
    assert worn.per_component[2].used_hours == base.per_component[2].used_hours + 2 * PARAMS["events"]["overheat"]
    assert worn.wti > base.wti


def test_tf_06_plm_rating_wins_over_pack():
    plm = [{"name": "Motor armature", "rated_life_hours": 1300.0, "weight": 0.4, "critical": True}]
    comps = tool_life.components("CMH", PARAMS, plm=plm, replacements={"Piston and seal kit": 500.0})
    assert [(c.name, c.rated_hours, c.source) for c in comps][:2] == [
        ("Motor armature", 1300.0, "plm"),
        ("Gearbox", 1500.0, "pack"),
    ]
    r = tool_life.evaluate(_inputs(components=comps), PARAMS)
    assert r.per_component[0].source == "plm" and r.per_component[0].rul_pct == 27  # 943 h of 1,300


def test_tf_06_repair_log_names_map_to_components():
    got = tool_life.replacements_for("CMH", {"Piston seal": 500, "Chuck": 100, "Gearbox": 300}, PARAMS)
    assert got == {"Piston and seal kit": 500.0, "Gearbox": 300.0}


def test_tf_06_low_confidence_never_auto_reissues():
    """The sample world has returns whose best path is re-issue or pool: with a Low life confidence the same case is valued as
    before, but the recommendation is another route (or none)."""
    pack = load_pack("tool_fleet")
    queue = tool_fleet.sample_live_cases()
    want = [w for w in golden.load("po/equip_decisions")["decisions"] if w["best"]["k"] in HELD]
    assert want
    by_id = {c["id"]: c for c in tool_fleet.sample_queue()}
    for w in want:
        case = dict(by_id[w["id"]])
        base = decide_case(dict(case), pack, FlowVersion(None, 0, ()), NOW, queue=queue)
        assert base.recommendation["id"] == w["best"]["k"]
        low = decide_case(case | {"life": {"confidence": "Low"}}, pack, FlowVersion(None, 0, ()), NOW, queue=queue)
        assert low.recommendation is None or low.recommendation["id"] not in HELD, w["id"]
        assert {r["id"]: r["net"] for r in low.routes if r["id"] in HELD} == {
            r["id"]: r["net"] for r in base.routes if r["id"] in HELD
        }


# ------------------------------------------------------------------ cases opened from data
def _clean() -> None:
    with engine.begin() as conn:
        for m in ("contract_line", "contract", "condition", "repair_event"):
            keys = [*SERIALS, "FC-TEST", "DR-LIFE-1"]
            conn.execute(text("DELETE FROM provenance WHERE model = :m AND key = ANY(:k)"), {"m": m, "k": keys})
            conn.execute(text("DELETE FROM canonical WHERE model = :m AND key = ANY(:k)"), {"m": m, "k": keys})


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    yield
    starting.reset()
    _clean()


def _telematics(serial: str, hours: float, seen: str, coverage: float = 95) -> None:
    facts = [
        canonical.Fact("condition", serial, "run_hours", hours, resource="tools"),
        canonical.Fact("condition", serial, "high_load_share", 0.3, resource="tools"),
        canonical.Fact("condition", serial, "event_counts", {"overheat": 0, "drop": 0, "overload": 0}, resource="tools"),
        canonical.Fact("condition", serial, "telemetry_coverage_pct", coverage, resource="tools"),
    ]
    with SessionLocal() as s:
        canonical.apply(s, "fleet", facts)
        s.commit()


def _piston_replaced(serial: str, hours: int) -> None:
    comps = [{"name": "Piston seal", "replaced": True, "runHoursAtReplacement": hours}]
    facts = [
        canonical.Fact("repair_event", "DR-LIFE-1", "serial", serial, resource="orders"),
        canonical.Fact("repair_event", "DR-LIFE-1", "kind", "repair_order", resource="orders"),
        canonical.Fact("repair_event", "DR-LIFE-1", "status", "closed", resource="orders"),
        canonical.Fact("repair_event", "DR-LIFE-1", "components", comps, resource="orders"),
    ]
    with SessionLocal() as s:
        canonical.apply(s, "fleet", facts)
        s.commit()


def _open(serial: str, seen: str | None, **line) -> dict:
    facts = tool_case_facts(
        serial, {"tool_class": serial.split("-")[0], "site": "Houston", "grade": "B", "rul": 62}, seen=seen, line=line
    )
    with SessionLocal() as s:
        c = intake.open_case(
            s,
            {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": serial, "reason": "contract_end", "facts": facts},
            "system",
        )
        s.commit()
    return c


def test_tf_06_case_opened_from_telematics_gets_the_worked_example():
    tool_case_facts_seen = "2026-10-04T08:15:00+00:00"
    _telematics("CMH-48213", 820, tool_case_facts_seen)
    _piston_replaced("CMH-48213", 500)
    c = _open("CMH-48213", tool_case_facts_seen)
    assert c["life"]["wti"] == 65 and c["life"]["confidence"] == "High"
    assert c["rul"] == 21 and c["partRul"] == [21, 37, 59, 39]
    r = client.get(f"/api/screens/toolfleet/{c['id']}", headers=h("admin"))
    assert r.status_code == 200, r.text
    life = r.json()["life"]
    assert (life["wti"], life["rul_tool"], life["weakest"], life["rul_tool_hours"]) == (65, 21, "Motor armature", 223.5)
    assert [x["rul_pct"] for x in life["per_component"]] == [21, 37, 59, 39] and life["confidence"] == "High"
    assert life["table_version"] and life["rule_version"] == "tf-life-1"


def test_tf_06_no_telematics_is_low_with_a_range_and_never_reissues():
    c = _open("CMH-48777", None, months_on_contract=41)
    assert c["life"]["confidence"] == "Low" and c["life"]["range"] == [0, 53] and c["rul"] == 21
    assert c["recommendation"] is None or c["recommendation"]["id"] not in HELD


def test_tf_06_case_with_no_evidence_keeps_its_inputs():
    c = _open("CMH-48213", "2026-10-04T08:15:00+00:00")
    assert c.get("life") is None and c["rul"] == 62
    r = client.get(f"/api/screens/toolfleet/{c['id']}", headers=h("admin"))
    assert r.json()["life"] is None
