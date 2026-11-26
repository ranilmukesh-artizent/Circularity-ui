"""Plan 9, P9-3.11 (story TF-11): the telematics and the workbench grade disagree, so a person looks.

`tool_life.disagreement(grade, life, damage_code)` (pure) is computed from the wear index and the workbench grade: grade A or B
with WTI >= 60, or grade D with WTI <= 20 and no damage code. An estimated grade never triggers it. The case then keeps
`disagreement`, opens the exception `grade_wear_disagreement` for Quality through the case process layer and does not choose
re-issue or pool. No model step is added here: the text is computed from numbers on file; the item's draft for a person is the
exception assistant's (P9-2.10, P9-2.19, tested in test_exception_assistant), and the model cannot resolve it (`work.resolve` is
forbidden to agents).
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.cases import decide, intake, replan
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import tool_inputs, tool_life
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "tool-fleet-a"
SERIAL = "CMH-48213"
SEEN = "2026-10-04T08:15:00+00:00"
PARAMS = load_pack("tool_fleet").valuer.params["life"]
EXAMPLE = {"Motor armature": 79, "Gearbox": 63, "Piston and seal kit": 61}


def _grade(g: str, source: str = "workbench") -> tool_inputs.GradeView:
    return tool_inputs.GradeView(g, source, "DR-50412", "2026-10-07T03:00:00+00:00", 6.0)  # type: ignore[arg-type]


def _life(hours: float = 820.0, replaced: float | None = 500.0) -> tool_life.LifeResult:
    comps = tool_life.components("CMH", PARAMS, replacements={"Piston and seal kit": replaced} if replaced else None)
    inp = tool_life.LifeInputs("CMH", hours, 0.30, {}, None, 95.0, 3.0, True, comps)
    return tool_life.evaluate(inp, PARAMS)


# ------------------------------------------------------------------ the pure part
def test_tf_11_grade_a_high_wear_flags():
    life = _life()
    d = tool_life.disagreement(_grade("A"), life, False)
    assert life.wti == 65 and d is not None
    assert d.components == list(EXAMPLE)
    assert d.text == (
        "Telematics and inspection disagree: grade A, WTI 65 (Motor armature 79%, Gearbox 63%, Piston and seal kit 61%)"
    )
    assert tool_life.disagreement(_grade("B"), life, False) is not None


def test_tf_11_grade_d_low_wear_flags():
    life = _life(hours=60, replaced=None)
    assert life.wti <= 20
    d = tool_life.disagreement(_grade("D"), life, False)
    assert d is not None and d.text.startswith("Telematics and inspection disagree: grade D, WTI ")
    assert d.components and all(c.consumed_pct <= 20 for c in life.per_component if c.name in d.components)
    assert tool_life.disagreement(_grade("D"), life, True) is None  # a damage code explains a poor grade on a low-wear tool


def test_tf_11_no_flag_on_estimate_or_agreement():
    assert tool_life.disagreement(_grade("A", "estimate"), _life(), False) is None  # an estimated grade never triggers it
    low = _life(hours=330, replaced=None)
    assert low.wti < 60 and tool_life.disagreement(_grade("B"), low, False) is None
    assert tool_life.disagreement(_grade("C"), _life(), False) is None  # only A, B (worn) and D (fresh) disagree
    assert tool_life.disagreement(_grade("D"), _life(), False) is None


def test_tf_11_life_round_trips_through_the_case():
    import dataclasses

    life = _life()
    d = dataclasses.asdict(life) | {"range": None}
    assert tool_life.life_from_dict(d) == life


def test_tf_11_the_disagreement_leaves_reissue_and_pool_to_a_person():
    routes = [
        {"id": "release", "excluded": False, "rank": 1},
        {"id": "redeploy", "excluded": False, "rank": 2},
        {"id": "repair", "excluded": False, "rank": 3},
    ]
    held = decide._not_held_for_person(routes[0], routes, [], {"confidence": "High"}, {"text": "x", "components": []})
    assert held is not None and held["id"] == "repair"
    assert decide._not_held_for_person(routes[0], routes, [], {"confidence": "High"}, None) is routes[0]


def test_tf_11_no_agent_resolves_the_item():
    assert forbidden("work.resolve") and forbidden("work.assign")


def test_tf_11_pack_names_the_exception_for_quality():
    kind = next(t for t in load_pack("tool_fleet").runtime.exception_types if t.id == "grade_wear_disagreement")
    assert kind.owner_role == "Quality" and kind.label == "Telematics and inspection disagree"


# ------------------------------------------------------------------ the case
def _clean() -> None:
    with engine.begin() as conn:
        for m in ("contract_line", "contract", "condition", "repair_event"):
            keys = [SERIAL, "FC-TEST", "DR-LIFE-1"]
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


def _write(source: str, facts: list[canonical.Fact]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, facts)
        s.commit()


def _world(grade: str | None, hours: float = 820, damage: str | None = None) -> None:
    _write("fleet", [
        canonical.Fact("condition", SERIAL, "run_hours", hours, resource="tools"),
        canonical.Fact("condition", SERIAL, "high_load_share", 0.3, resource="tools"),
        canonical.Fact("condition", SERIAL, "event_counts", {"overheat": 0, "drop": 0, "overload": 0}, resource="tools"),
        canonical.Fact("condition", SERIAL, "telemetry_coverage_pct", 95, resource="tools"),
    ])  # fmt: skip
    _write("fleet", [
        canonical.Fact("repair_event", "DR-LIFE-1", "serial", SERIAL, resource="orders"),
        canonical.Fact("repair_event", "DR-LIFE-1", "kind", "repair_order", resource="orders"),
        canonical.Fact("repair_event", "DR-LIFE-1", "status", "closed", resource="orders"),
        canonical.Fact("repair_event", "DR-LIFE-1", "components", [
            {"name": "Piston seal", "replaced": True, "runHoursAtReplacement": 500}], resource="orders"),
    ])  # fmt: skip
    if grade:
        f = {"grade": grade, "test_result": "pass", "inspection_ref": "DR-50412", "graded_at": "2026-10-07T03:00:00Z"}
        f |= {"damage_code": damage} if damage else {}
        _write("repairlog", [canonical.Fact("condition", SERIAL, k, v, resource="orders") for k, v in f.items()])


def _open() -> dict:
    facts = tool_case_facts(SERIAL, {"tool_class": "CMH", "site": "Houston", "grade": "B", "rul": 62}, seen=SEEN)
    with SessionLocal() as s:
        c = intake.open_case(
            s, {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": SERIAL, "reason": "contract_end", "facts": facts},
            "system",
        )  # fmt: skip
        s.commit()
    return c


def _items(case_id: str) -> list[tuple]:
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT owner_role, status, kind, cause FROM work_item WHERE case_id = :c AND type = 'grade_wear_disagreement'"),
            {"c": case_id},
        )
        return [tuple(r) for r in rows]


def test_tf_11_case_grade_a_high_wear_opens_the_exception_for_quality():
    _world("A")
    c = _open()
    assert c["life"]["wti"] == 65
    assert c["disagreement"]["components"] == list(EXAMPLE)
    assert c["disagreement"]["text"].startswith("Telematics and inspection disagree: grade A, WTI 65 (Motor armature 79%")
    items = _items(c["id"])
    # Quality is an Approver of the programme (the pack's roles table)
    assert len(items) == 1 and items[0][:3] == ("Approver", "open", "exception")
    assert items[0][3] == c["disagreement"]["text"]
    assert not c["recommendation"] or c["recommendation"]["id"] not in {"release", "redeploy"}  # waits for a person
    v = client.get(f"/api/screens/toolfleet/{c['id']}", headers=h("admin")).json()
    assert v["disagreement"] == c["disagreement"]


def test_tf_11_case_estimate_grade_is_never_flagged():
    _world(None)
    c = _open()
    assert c["life"]["wti"] == 65 and c.get("disagreement") is None and _items(c["id"]) == []
    assert client.get(f"/api/screens/toolfleet/{c['id']}", headers=h("admin")).json()["disagreement"] is None


def test_tf_11_case_grade_d_low_wear_flags_unless_damage_coded():
    _world("D", hours=60)
    c = _open()
    assert c["disagreement"]["text"].startswith("Telematics and inspection disagree: grade D, WTI ")
    assert len(_items(c["id"])) == 1


def test_tf_11_case_damage_code_explains_the_poor_grade():
    _world("D", hours=60, damage="DMG-12")
    c = _open()
    assert c.get("disagreement") is None and _items(c["id"]) == []


def test_tf_11_agreeing_again_closes_the_item():
    _world("A")
    c = _open()
    assert [i[1] for i in _items(c["id"])] == ["open"]
    _write("repairlog", [canonical.Fact("condition", SERIAL, "grade", "D", resource="orders")])
    _write("fleet", [canonical.Fact("condition", SERIAL, "run_hours", 600, resource="tools")])
    with SessionLocal() as s:
        assert replan.on_graded(s, c["id"])
        s.commit()
    assert [i[1] for i in _items(c["id"])] == ["done"]
