"""Plan 9, P9-11.16 (stories MR-18, MR-21): the turnaround alert and the two worked questions of the rental pack.

The tests write the rental system's records through the adapter's own `map` (literal records, no source-sim), then ask
`device.question` (the DV-13 action) and `mr_turnaround.alerts_for`. Questions live in code (`di.services.questions.medical_rental`).
"""

# ruff: noqa: E501 - long sentence and SQL lines

import pytest
from sqlalchemy import text

from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.cases import mr_turnaround as mt
from di.services.device import analytics
from di.services.modeler.pack import load_pack
from di.services.questions import medical_rental as qmr
from tests import starting
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG = "Customer A"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model = 'asset' AND key LIKE '%MRA-%'"))
        conn.execute(text("DELETE FROM canonical WHERE model = 'asset' AND key LIKE '%MRA-%'"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    _clean()
    starting.reset()


def _write(resource: str, payload: dict) -> None:
    with SessionLocal() as s:
        canonical.apply(s, "mr_rental", ADAPTERS["mr_rental"].map(Record(resource, "x", payload | {"org_unit_id": ORG})))
        s.commit()


def _depot(depot: str, tags: list[str], avg: float, lines: int, prior: int, day0: int = 4) -> None:
    """`tags` returned in the last 14 days (the latest on 17 Nov), `prior` returns before; every row waits `avg` days."""
    split = (round(avg * 0.6, 1), round(avg * 0.2, 1))
    rows = [
        {"returnId": f"R-{t}", "tag": t, "depot": depot, "checkedInAt": f"2026-11-{day0 + k % 14:02d}T06:00:00+00:00",
         "totalDays": avg, "waitingDays": {"decon_queue": split[0] + k / 10, "service": split[1], "transport": round(avg - sum(split), 1)}}
        for k, t in enumerate(tags)
    ]  # fmt: skip
    for r in rows:
        _write(
            "returns",
            {"tag": r["tag"], "depot": depot, "checkedInAt": r["checkedInAt"], "hospitalId": "HOSP-A", "wardType": "general"},
        )
        _write("turnaround", {"tag": r["tag"], "depot": depot, "days": 14, "own": r, "rows": rows, "decon_lines": lines})
    for k in range(prior):  # returned 15 to 28 days before the latest, no turnaround row of their own
        _write("returns", {"tag": f"MRA-{depot[0]}-P{k}", "depot": depot, "checkedInAt": f"2026-11-0{1 + k % 2}T06:00:00+00:00",
                           "hospitalId": "HOSP-A", "wardType": "general"})  # fmt: skip


def _seed() -> None:
    _depot("EAST", [f"MRA-E-{k:02d}" for k in range(13)], 3.4, 1, 10)
    _depot("WEST", [f"MRA-W-{k:02d}" for k in range(6)], 1.6, 2, 6)
    _depot("NORTH", [f"MRA-N-{k:02d}" for k in range(5)], 1.6, 2, 5)


def test_mr_18_turnaround_alert_east():
    _seed()
    with SessionLocal() as s:
        out = mt.alerts_for(s, [ORG], load_pack("medical_rental"))
    assert [(a.id, a.to_role, a.text, a.action) for a in out] == [
        ("AL-MR-TURNAROUND", "Planner", "Turnaround slipping at East depot", "Move decontamination capacity from a quieter depot")
    ]
    assert out[0].avg_days == 3.4


def test_mr_18_east_depot_answer():
    _seed()
    r = call("device.question", {"question_id": "turnaround_by_cause"}, "planner-a")
    assert r["ok"], r
    a = r["output"]
    assert a["sentence"] == (
        "East has 1 decontamination line against 2 elsewhere, after returns rose 30%: most waiting is in the decontamination queue."
    )
    points = a["chart"]["series"][0]["points"]
    assert points[0]["x"] == "decon_queue" and points[0]["y"] == 2.6 and points[0]["y"] > points[1]["y"]
    assert len(a["examples"]) == 3 and {e["depot"] for e in a["examples"]} == {"EAST"}
    assert a["examples"][0]["waiting_days"]["decon_queue"] >= a["examples"][1]["waiting_days"]["decon_queue"]


def test_mr_18_answer_never_reads_another_tenants_rows():
    _seed()
    other = call("device.question", {"question_id": "turnaround_by_cause"}, "planner-b")
    assert other["ok"] and other["output"]["sentence"] == "No turnaround records yet." and other["output"]["examples"] == []
    with SessionLocal() as s:
        assert mt.read(s, ["Customer B"]) == ([], [])


def test_mr_18_sentence_numbers_are_checked():
    _seed()
    with SessionLocal() as s:
        ans = analytics.answer(s, "turnaround_by_cause", None, __import__("datetime").date(2026, 11, 18))
    assert analytics.sentence_problems("East has 1 line against 2, after returns rose 30%", ans) == []
    assert analytics.sentence_problems("East has 9 lines", ans)
    assert analytics.word(ans, None).by_model is False


def test_mr_21_models_retired_earliest():
    r = call("device.question", {"question_id": "retired_earliest"}, "planner-a")
    assert r["ok"], r
    a = r["output"]
    ys = [p["y"] for p in a["chart"]["series"][0]["points"]]
    assert ys and ys == sorted(ys)
    first = a["chart"]["series"][0]["points"][0]["x"]
    assert a["sentence"].startswith(first.replace("_", " ").capitalize())
    assert 0 < len(a["examples"]) <= 3 and {e["class"] for e in a["examples"]} == {first}
    assert a["examples"] == sorted(a["examples"], key=lambda e: (e["age_years"], e["item_id"]))
    assert qmr.retired_earliest([]).examples == []
