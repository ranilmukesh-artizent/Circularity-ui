"""Plan 9, P9-11.15 (story MR-17): `SR-MR-SVCWEEK` picks the service week of lowest regional demand within the due window, and
adopting it books the service through `service.book` as the person. Literal records, no source-sim."""

from datetime import date
from typing import Any

from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.cases import mr_service_planning as planning
from tests.helpers import call
from tests.test_mr_service_gates import _case, _get, _ok, _write, fresh, tag  # noqa: F401 - `fresh` is the autouse fixture

TODAY = date(2026, 11, 26)
WEEKS = [("2026-11-23", 14), ("2026-11-30", 11), ("2026-12-07", 4), ("2026-12-14", 9), ("2026-12-21", 2)]


def _forecast(n: int) -> None:
    """The depot's forecast on the pump's demand record (the real adapter's mapping)."""
    _write("mr_rental", "demand", {
        "tag": tag(n), "depot": {"latitude": 40.0, "longitude": -75.0}, "requests": [], "org_unit_id": "Customer A",
        "forecast": [{"region": "EAST", "weekStart": w, "requests": r} for w, r in WEEKS],
    })  # fmt: skip


def _east_pump(n: int = 2, **service: Any) -> dict:
    c = _case(n, **service)
    _forecast(n)
    return c


def _suggest(**kw: Any) -> list[dict]:
    with SessionLocal() as s:
        return [x.as_dict() for x in planning.suggestions(s, TODAY, **kw)]


def test_mr_17_service_in_lowest_demand_week():
    c = _east_pump(pmDue="2026-12-20")
    (sug,) = _suggest()
    assert sug["week"] == "2026-12-07" and sug["kind"] == "pm" and sug["region"] == "EAST"
    assert sug["text"] == f"Service {tag(2)} in the week of 7 Dec 2026 (lowest demand in EAST)"
    assert sug["rule"] == "SR-MR-SVCWEEK" and sug["case_id"] == c["id"]
    assert sug["book"] == {
        "action": "service.book",
        "input": {"case_id": c["id"], "asset_tag": tag(2), "kind": "pm", "due_by": "2026-12-07"},
    }


def test_mr_17_window_limits_the_weeks():
    _east_pump(pmDue="2026-12-02")  # only the weeks starting 23 and 30 Nov are before the due date
    assert _suggest()[0]["week"] == "2026-11-30"


def test_mr_17_outside_the_next_rental_gives_nothing():
    _east_pump(pmDue="2027-02-15", certificationExpiry="2027-03-31")
    assert _suggest() == []
    assert _suggest(window_days=100)[0]["kind"] == "pm"  # the BR-MR-SVC scope can widen it


def test_mr_17_adopt_books_service():
    c = _east_pump(pmDue="2026-12-20")
    with SessionLocal() as s:
        planning.open_items(s, TODAY)
        planning.open_items(s, TODAY)  # once per case and week
        s.commit()
        q = text("SELECT count(*) FROM work_item WHERE type = 'SR-MR-SVCWEEK' AND case_id = :c AND status = 'open'")
        n = s.execute(q, {"c": c["id"]}).scalar()
    assert n == 1
    book = _suggest()[0]["book"]
    _ok(call("service.book", book["input"], "planner-a"))
    orders = _get(c["id"])["serviceOrders"]
    assert [(o["asset_tag"], o["kind"], o["due_by"]) for o in orders] == [(tag(2), "pm", "2026-12-07")]
    assert _suggest() == []  # booked: no longer suggested
