"""Plan 11, D1: the headline of the tool fleet and device packs in Analytics (`GET /api/screens/analytics/pack-headline`).

The arithmetic (rates, medians, the carbon estimate, the route and grade tables) is tested on typed rows with no database.
The endpoint is tested on cases the test inserts itself (ids `RT-HL-*`, removed by the reset around it): which packs an account
sees, the tenant boundary, the period and the figures it states with their counts.
"""

import statistics
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from di.core import clock
from di.core.db import SessionLocal
from di.services.cases import store
from di.services.questions import HEADLINES
from di.services.questions.headline import carbon_estimate, grade_table, headline, median_days, route_table, share
from tests import starting
from tests.helpers import client, h

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
CLASSES = {"offers": ["sale"], "auction": ["sale"], "buynow": ["sale"], "parts": ["parts"]}
NAMES = {"offers": "Offers", "auction": "Auction", "buynow": "Buy Now", "parts": "Parts"}


def _case(cid: str, stage: str, route: str | None, net: float = 0.0, co2: float | None = None, grade: str = "A") -> dict:
    r = {"id": route, "net": net, "co2": co2, "co2Prov": {"set": "cfs-2026.2"} if co2 is not None else None} if route else None
    return {"id": cid, "stage": stage, "grade": grade, "chosen": r if stage in ("approved", "executing", "closed") else None,
            "recommendation": r if stage == "awaiting_approval" else None}  # fmt: skip


def _spans(**days: float | None) -> dict[str, tuple[datetime, datetime | None]]:
    return {k: (T0, None if v is None else T0 + timedelta(days=v)) for k, v in days.items()}


# ---------------------------------------------------------------- the arithmetic


def test_share_and_median_of_nothing_and_of_one():
    assert share(0, 0) is None
    assert share(1, 4) == 25.0
    assert median_days([]) is None
    assert median_days([(T0, T0 + timedelta(days=3))]) == 3.0
    assert median_days([(T0, T0 + timedelta(days=1)), (T0, T0 + timedelta(days=5)), (T0, T0 + timedelta(days=2))]) == 2.0
    assert median_days([(T0, T0 + timedelta(days=1)), (T0, T0 + timedelta(days=4))]) == 2.5
    assert median_days([(T0, T0 - timedelta(days=1))]) == 0.0  # a close before the open counts no days


def test_carbon_estimate_sums_only_what_has_a_factor():
    assert carbon_estimate([]) == (None, 0, [])
    no_factor = _case("a", "closed", "offers", 10)
    assert carbon_estimate([no_factor]) == (None, 0, [])  # no factor behind it: no figure
    kg, n, sets = carbon_estimate(
        [no_factor, _case("b", "closed", "offers", 10, co2=12.5), _case("c", "closed", "auction", 5, co2=7.5)]
    )
    assert (kg, n, sets) == (20.0, 2, ["cfs-2026.2"])


def test_route_and_grade_tables():
    cs = [
        _case("a", "closed", "offers", 100, grade="A"),
        _case("b", "closed", "offers", 50, grade="B"),
        _case("c", "awaiting_approval", "parts", 20, grade="B"),
        _case("d", "none", None, grade="C"),  # no route survived: in neither table
    ]
    rows = route_table(cs, NAMES)
    assert [(r["id"], r["n"], r["closed"], r["net"]) for r in rows] == [("offers", 2, 2, 150.0), ("parts", 1, 0, 20.0)]
    g = grade_table(cs, ["A", "B", "C", "D"], NAMES)
    assert [r["grade"] for r in g["rows"]] == ["A", "B"]
    assert g["rows"][1]["cells"] == {"offers": 1, "parts": 1} and g["rows"][1]["total"] == 2
    assert route_table([], NAMES) == [] and grade_table([], ["A"], NAMES)["rows"] == []


def _device(cases: list[dict], spans: dict[str, tuple[datetime, datetime | None]], since: datetime = T0) -> dict:
    return headline(HEADLINES["device"], "Device recommerce", cases, CLASSES, NAMES, ["A", "B", "C", "D"], spans, since,
                    T0 + timedelta(days=30), 90)  # fmt: skip


def test_device_headline_figures_and_their_counts():
    cs = [
        _case("d1", "closed", "offers", 100, 20),
        _case("d2", "closed", "auction", 50, 10, "B"),
        _case("d3", "approved", "buynow"),
        _case("d4", "awaiting_approval", "parts", 9, grade="C"),
        _case("d5", "none", None, grade="C"),
    ]
    out = _device(cs, _spans(d1=2, d2=4, d3=None, d4=None, d5=None))
    f = {x["id"]: x for x in out["figures"]}
    assert out["cases"] == 5 and out["closed"] == 2
    assert (f["net"]["value"], f["net"]["n"], f["net"]["of"], f["net"]["basis"]) == (150.0, 2, 2, "modelled")
    assert (f["sell_through"]["value"], f["sell_through"]["n"], f["sell_through"]["of"]) == (pytest.approx(200 / 3), 2, 3)
    assert (f["days"]["value"], f["days"]["n"]) == (3.0, 2)
    assert (f["listed"]["value"], f["listed"]["n"], f["listed"]["of"]) == (1.0, 1, 3)
    assert (f["carbon"]["value"], f["carbon"]["basis"]) == (30.0, "estimated")
    assert "cfs-2026.2" in f["carbon"]["note"] and out["carbon_sets"] == ["cfs-2026.2"]
    assert [r["id"] for r in out["routes"]] == ["offers", "auction", "parts", "buynow"]  # one case each: the larger net first


def test_a_case_opened_before_the_period_is_left_out_and_one_case_is_enough():
    old = {"d1": (T0 - timedelta(days=200), T0 - timedelta(days=198))}
    out = _device([_case("d1", "closed", "offers", 100, 20)], old)
    assert out["cases"] == 0
    assert all(x["value"] is None for x in out["figures"] if x["id"] != "listed")  # nothing to say, each says what it needs
    assert all(x["needs"] for x in out["figures"])
    one = _device([_case("d1", "closed", "offers", 40, 6)], _spans(d1=1.5))
    f = {x["id"]: x for x in one["figures"]}
    assert (f["net"]["value"], f["sell_through"]["value"], f["days"]["value"], f["carbon"]["value"]) == (40.0, 100.0, 1.5, 6.0)


def test_empty_data_has_no_figure_and_no_division_by_zero():
    out = _device([], {})
    assert out["cases"] == 0 and out["routes"] == [] and out["grades"]["rows"] == []
    assert [x["value"] for x in out["figures"]] == [None] * 5


def test_tool_fleet_reuse_rate_is_the_share_routed_to_keep_the_tool_in_use():
    classes = {"redeploy": ["reuse"], "release": ["release"], "exit": ["recycle", "exit"]}
    cs = [_case("t1", "closed", "redeploy", 30, 5), _case("t2", "awaiting_approval", "exit", 4), _case("t3", "none", None)]
    out = headline(HEADLINES["tool_fleet"], "Tool fleet", cs, classes, {}, ["A"], _spans(t1=1, t2=None, t3=None), T0, T0, 90)
    f = {x["id"]: x for x in out["figures"]}
    assert (f["reuse_rate"]["value"], f["reuse_rate"]["n"], f["reuse_rate"]["of"]) == (50.0, 1, 2)
    assert (f["open"]["value"], f["open"]["of"]) == (2.0, 3)  # still open: every case not closed
    assert f["days"]["label"] == "Median days to close" and out["route_word"] == "route"


# ---------------------------------------------------------------- the endpoint


@pytest.fixture(scope="module", autouse=True)
def _cases():
    starting.reset()
    now = clock.now().astimezone(UTC)
    rows = [  # id, owner, template, stage, route, net, co2, grade, opened days ago, days to close
        ("RT-HL-1", "Customer A", "device", "closed", "offers", 100.0, 20.0, "A", 10, 2),
        ("RT-HL-2", "Customer A", "device", "closed", "auction", 50.0, 10.0, "B", 12, 4),
        ("RT-HL-3", "Customer A", "device", "approved", "buynow", 30.0, 5.0, "A", 5, None),
        ("RT-HL-4", "Customer A", "device", "awaiting_approval", "parts", 9.0, None, "C", 4, None),
        ("RT-HL-5", "Customer A", "device", "none", None, 0.0, None, "C", 3, None),
        ("RT-HL-6", "Customer A", "device", "closed", "offers", 999.0, 99.0, "A", 200, 2),  # before the 90 days
        ("RT-HL-7", "Customer B", "device", "closed", "offers", 70.0, None, "A", 8, 6),
        ("RT-HL-8", "Customer A", "tool_fleet", "closed", "redeploy", 30.0, 5.0, "B", 3, 1),
    ]
    with SessionLocal() as s:
        for cid, owner, tpl, stage, route, net, co2, grade, ago, took in rows:
            r = None
            if route:
                r = {"id": route, "net": net, "co2": co2, "co2Prov": {"set": "cfs-2026.2"} if co2 is not None else None}
            c = {"id": cid, "owner": owner, "location": "Repair centre", "stage": stage, "template": tpl, "grade": grade,
                 "routes": [r] if r else [], "recommendation": r if stage == "awaiting_approval" else None,
                 "chosen": r if stage in ("approved", "closed") else None}  # fmt: skip
            opened = now - timedelta(days=ago)
            if cid == "RT-HL-1":  # received 5 days before the case opened: the days count from receipt
                c["received"] = (opened - timedelta(days=5)).isoformat().replace("+00:00", "Z")
            store.insert_new(s, c)
            s.execute(text("UPDATE case_record SET created_at = :t WHERE id = :i"), {"t": opened, "i": cid})
            s.execute(
                text("DELETE FROM case_stage_log WHERE case_id = :i AND to_stage = 'closed'"), {"i": cid}
            )  # intake logged now
            if took is not None:
                s.execute(
                    text("INSERT INTO case_stage_log (case_id, from_stage, to_stage, reason, actor, at) "
                         "VALUES (:i, 'executing', 'closed', 'Outcome reported', 'system', :t)"),
                    {"i": cid, "t": opened + timedelta(days=took)},
                )  # fmt: skip
        s.commit()
    yield
    starting.reset()


def _get(user: str, **q: object):
    return client.get("/api/screens/analytics/pack-headline", params=q, headers=h(user))


def _packs(user: str, **q: object) -> dict[str, dict]:
    r = _get(user, **q)
    assert r.status_code == 200, r.text
    return {p["pack"]: p for p in r.json()["packs"]}


def test_a_group_account_sees_both_packs_over_every_tenant():
    out = _packs("admin")
    assert set(out) == {"device", "tool_fleet"}
    d = out["device"]
    f = {x["id"]: x for x in d["figures"]}
    assert d["period"]["days"] == 90 and d["cases"] == 6 and d["closed"] == 3  # RT-HL-6 opened 200 days ago
    assert f["net"]["value"] == 220.0 and f["net"]["n"] == 3
    assert f["sell_through"]["value"] == 75.0 and (f["sell_through"]["n"], f["sell_through"]["of"]) == (3, 4)
    assert f["days"]["value"] == pytest.approx(6.0)  # 7 (received 5 days before it opened), 4 and 6 days
    assert f["days"]["note"] == "Median days from received to closed, 3 cases"
    assert (f["listed"]["value"], f["listed"]["of"]) == (1.0, 4)
    assert f["carbon"]["value"] == 30.0 and f["carbon"]["n"] == 2  # RT-HL-7 has no factor: not counted, not guessed
    assert {r["id"]: (r["n"], r["closed"]) for r in d["routes"]} == {
        "offers": (2, 2),
        "auction": (1, 1),
        "buynow": (1, 0),
        "parts": (1, 0),
    }
    rows = {r["grade"]: r for r in d["grades"]["rows"]}
    assert rows["A"]["cells"]["offers"] == 2 and rows["A"]["cells"]["buynow"] == 1 and rows["C"]["total"] == 1
    t = {x["id"]: x for x in out["tool_fleet"]["figures"]}
    assert t["net"]["value"] == 30.0 and t["reuse_rate"]["value"] == 100.0


def test_the_median_days_tile_is_the_median_of_the_rows_days_column():
    tile = {x["id"]: x for x in _packs("admin")["device"]["figures"]}["days"]
    q = {"source": "cases", "chart": "pack", "key": "pack:device|state:closed", "days": 90, "limit": 200}
    r = client.get("/api/screens/analytics/rows", params=q, headers=h("admin"))
    assert r.status_code == 200, r.text
    days = [x["days"] for x in r.json()["rows"]]
    assert len(days) == tile["n"] == 3 and sorted(days) == [4.0, 6.0, 7.0]
    assert statistics.median(days) == pytest.approx(tile["value"], abs=0.05)  # the rows show one decimal


def test_a_role_without_the_waterfall_section_gets_neither_the_headline_nor_the_pack_rows():
    assert _get("engineer").status_code == 403
    rows_q = {"source": "cases", "chart": "pack", "key": "pack:device"}
    assert client.get("/api/screens/analytics/rows", params=rows_q, headers=h("engineer")).status_code == 403
    assert client.get("/api/screens/analytics/rows.csv", params=rows_q, headers=h("engineer")).status_code == 403
    for user in ("admin", "planner.a"):
        assert _get(user).status_code == 200
        assert client.get("/api/screens/analytics/rows", params=rows_q, headers=h(user)).status_code == 200
    mine = client.get("/api/screens/analytics/rows", params=rows_q, headers=h("planner.a")).json()
    assert mine["tenants"] == ["Customer A"]  # the tenant boundary is unchanged


def test_a_tenant_account_sees_only_its_own_cases():
    a, b = _packs("planner.a"), _packs("planner.b")
    assert a["device"]["cases"] == 5 and a["device"]["closed"] == 2
    assert {x["id"]: x for x in a["device"]["figures"]}["net"]["value"] == 150.0
    assert set(b) == {"device"} and b["device"]["cases"] == 1  # Customer B has no tool fleet case: that pack is not shown
    assert {x["id"]: x for x in b["device"]["figures"]}["net"]["value"] == 70.0
    assert set(_packs("planner.c")) == set()  # no case of that pack in sight: nothing is shown


def test_the_period_narrows_the_cases_and_a_page_the_account_lacks_is_refused():
    assert _packs("admin", days=7)["device"]["cases"] == 3  # RT-HL-3, 4 and 5
    assert _packs("admin", days=365)["device"]["cases"] == 7
    assert _get("admin", days=0).status_code == 422
    assert _get("developer").status_code == 403
    assert client.get("/api/screens/analytics/pack-headline").status_code == 401
