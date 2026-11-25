"""Plan 9, P9-3.5 (story TF-03): the workbench grade on the tool fleet case panel.

The grade of a tool is the depot's: the repair log's `condition` record for the serial (grade, test result, inspection
reference, time). Until a graded record with a test result is in, the valuer reads its own estimate and the panel labels
it so. A late grade re-evaluates the open case (job `case.reevaluate`). No model step: the grade is read, never computed.

The pure part runs without a database; the rest opens a tool case in its own org unit (a `company`: the case page is
refused for a unit that is not a tenant) and writes canonical facts as the repair log would.
It starts and ends with the demo reset.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from di import worker
from di.core import clock
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.cases import intake
from di.services.modeler.evidence import Evidence
from di.services.modeler.valuers import tool_inputs
from di.services.modeler.valuers.tool_inputs import GradeView
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "tool-fleet-a"
SERIAL = "CMH-48213"
GRADED = datetime(2026, 10, 7, 3, 0, tzinfo=UTC)
BASE = {"id": "RT-X", "cls": "CMH", "grade": "C", "estGrade": "C", "serial": SERIAL}


def _evidence(grade="B", test="pass") -> dict[str, Evidence | None]:
    value = {"grade": grade, "test_result": test, "inspection_ref": "DR-50412", "graded_at": GRADED.isoformat()}
    return {"workbench_grade": Evidence("workbench_grade", "repairlog", GRADED, "pass" if test == "pass" else "fail", value)}


def _facts(**over):
    f = {"grade": "B", "test_result": "pass", "inspection_ref": "DR-50412", "graded_at": "2026-10-07T03:00:00Z"} | over
    return [canonical.Fact("condition", SERIAL, k, v, resource="orders") for k, v in f.items() if v is not None]


def _jobs() -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(text("SELECT payload FROM job WHERE kind = 'case.reevaluate' AND status = 'queued' ORDER BY id"))
        return list(rows.scalars())


def _clear_jobs() -> None:
    with engine.begin() as c:
        c.execute(text("DELETE FROM job WHERE kind = 'case.reevaluate'"))


# ------------------------------------------------------------------ the pure part
def test_tf_03_grade_from_workbench():
    g = tool_inputs.grade_of(_evidence(), "C", now=clock.now())
    assert (g.grade, g.source, g.ref, g.age_hours) == ("B", "workbench", "DR-50412", 6.0)
    assert g == GradeView("B", "workbench", "DR-50412", g.at, 6.0) and g.at.startswith("2026-10-07T03:00")
    vc = tool_inputs.valuer_case(BASE, _evidence())
    assert vc["grade"] == "B" and vc["estGrade"] == "C"
    assert BASE["grade"] == "C"  # the base is never changed


def test_tf_03_estimate_labelled_when_late():
    g = tool_inputs.grade_of({}, "C", now=clock.now())
    assert (g.grade, g.source, g.ref, g.at, g.age_hours) == ("C", "estimate", None, None, None)
    vc = tool_inputs.valuer_case(BASE, {})
    assert vc["grade"] is None and vc["estGrade"] == "C"
    assert tool_inputs.valuer_case(BASE, {"workbench_grade": None})["grade"] is None


def test_tf_03_grade_without_test_result_is_in_progress():
    """A grade with no test result yet is not the workbench grade (A 1.5)."""
    ev = _evidence(test=None)
    assert tool_inputs.grade_of(ev, "C", now=clock.now()).source == "estimate"
    assert tool_inputs.valuer_case(BASE, ev)["grade"] is None
    ev = _evidence()
    ev["workbench_grade"] = Evidence("workbench_grade", "repairlog", GRADED, "pass", {"test_result": "pass"})
    assert tool_inputs.grade_of(ev, "C", now=clock.now()).source == "estimate"  # a test result and no grade


# ------------------------------------------------------------------ the screen and the late grade
def _clear_canonical() -> None:
    """Remove the `condition` records this module writes through the `repairlog` source (`starting.reset()` keeps them)."""
    keys = {"k": [SERIAL, "LSR-00001"]}
    with engine.begin() as c:
        c.execute(text("DELETE FROM provenance WHERE model = 'condition' AND source_id = 'repairlog' AND key = ANY(:k)"), keys)
        c.execute(text("DELETE FROM canonical WHERE model = 'condition' AND key = ANY(:k)"), keys)
        c.execute(text("DELETE FROM conflict WHERE model = 'condition' AND key = ANY(:k)"), keys)


@pytest.fixture(scope="module")
def opened():
    starting.reset()
    _clear_canonical()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    with SessionLocal() as s:
        c = intake.open_case(
            s, {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": SERIAL, "reason": "contract_end",
                "facts": tool_case_facts(SERIAL, {"tool_class": "CMH", "site": "Houston"})}, "system")  # fmt: skip
        s.commit()
    yield c["id"]
    _clear_jobs()
    starting.reset()
    _clear_canonical()


def _view(case_id: str, user: str = "admin"):
    return client.get(f"/api/screens/toolfleet/{case_id}", headers=h(user))


def test_tf_03_view_shows_the_estimate(opened):
    _clear_jobs()
    r = _view(opened)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["case_id"] == opened and v["pack_version"] and v["flow"] == "returns"
    assert v["grade"]["source"] == "estimate" and v["grade"]["grade"] == "C" and v["grade"]["ref"] is None
    # the recall check (P9-3.7) and the contract right (P9-3.6)
    assert [(g["id"], g["passed"]) for g in v["gates"]] == [("G-TOOL-REC", True), ("G-CON-2", True)]
    assert (v["life"], v["paths"], v["plan"], v["approval"], v["followThrough"]) == (None, [], None, None, None)


def test_tf_03_late_grade_reevaluates(opened):
    _clear_jobs()
    with SessionLocal() as s:
        canonical.apply(s, "repairlog", _facts())
        s.commit()
    assert _jobs() == [{"case_id": opened}]  # one job for the open case, however many facts landed
    with SessionLocal() as s:  # the same grade again: still one job (deduped)
        canonical.apply(s, "repairlog", _facts())
        s.commit()
    assert _jobs() == [{"case_id": opened}]
    worker.HANDLERS["case.reevaluate"]({"case_id": opened})
    g = _view(opened).json()["grade"]
    assert (g["grade"], g["source"], g["ref"]) == ("B", "workbench", "DR-50412")
    assert g["age_hours"] == 6.0
    with engine.connect() as c:
        log = c.execute(text("SELECT reason, actor FROM case_stage_log WHERE case_id = :c ORDER BY id DESC LIMIT 1"),
                        {"c": opened}).one()  # fmt: skip
    assert "DR-50412" in log.reason and log.actor == "system"


def test_tf_03_no_job_without_an_open_case_or_a_grade(opened):
    _clear_jobs()
    with SessionLocal() as s:
        canonical.apply(s, "repairlog", [canonical.Fact("condition", "LSR-00001", "grade", "A", resource="orders")])
        canonical.apply(s, "repairlog", [canonical.Fact("condition", SERIAL, "inspector", "Joe", resource="orders")])
        s.commit()
    assert _jobs() == []


def test_tf_03_view_tenant_boundary(opened):
    r = _view(opened, "planner.b")
    assert r.status_code == 403 and r.json()["error"]["code"] == "tenant_boundary", r.text
    assert _view("RT-9999999").status_code == 404
