"""Plan 11, writer G1: Analytics "View data" (GET /api/screens/analytics/rows, rows.csv, open-age; the action analytics.export).

Every figure is compared with what the page's own read returns in the same test (`GET /api/screens/analytics`: rows and
metrics), never with a number written here: the rows a chart key returns are the rows the browser counts for that bar, and
their sum is the figure. Access is the page's: a section the role lacks is a 403, a tenant account never receives another
tenant's row, and a warehouse manager's lock holds on case rows. The live cases the age and pack charts read are inserted by
the module (ids `RT-GR-*`, removed by the reset around it).
"""

import csv
import io
import statistics
from datetime import UTC, timedelta
from itertools import pairwise

import pytest
from sqlalchemy import text

from di.core import clock, policy
from di.core.auth import Principal
from di.core.db import SessionLocal, engine
from di.services.cases import store
from di.services.screens import analytics_rows as svc
from tests import starting
from tests.helpers import client, h

ROWS = "/api/screens/analytics/rows"


@pytest.fixture(scope="module", autouse=True)
def _cases():
    starting.reset()
    now = clock.now().astimezone(UTC)
    rows = [  # id, owner, location, template, stage, route, net, co2, grade, opened days ago, days to close
        ("RT-GR-1", "Customer A", "Warehouse 1", None, "awaiting_approval", "resale", 500.0, None, "A", 2, None),
        ("RT-GR-2", "Customer A", "Warehouse 2", None, "awaiting_approval", "redeploy", 300.0, None, "B", 20, None),
        ("RT-GR-3", "Customer B", "Warehouse 2", None, "awaiting_approval", "resale", 100.0, None, "B", 40, None),
        ("RT-GR-4", "Customer A", "Repair centre", "device", "closed", "offers", 100.0, 20.0, "A", 10, 2),
        ("RT-GR-5", "Customer A", "Repair centre", "device", "approved", "auction", 50.0, 10.0, "B", 5, None),
        ("RT-GR-6", "Customer B", "Repair centre", "device", "closed", "offers", 70.0, None, "A", 8, 6),
    ]
    with SessionLocal() as s:
        for cid, owner, where, tpl, stage, route, net, co2, grade, ago, took in rows:
            r = {"id": route, "net": net, "co2": co2, "co2Prov": {"set": "cfs-2026.2"} if co2 is not None else None}
            c = {"id": cid, "owner": owner, "location": where, "stage": stage, "grade": grade, "routes": [r],
                 "recommendation": r if stage == "awaiting_approval" else None,
                 "chosen": r if stage in ("approved", "closed") else None,
                 "evidence": [{"secret": "never in a row"}]}  # fmt: skip
            if tpl:
                c["template"] = tpl
            store.insert_new(s, c)
            opened = now - timedelta(days=ago)
            s.execute(text("UPDATE case_record SET created_at = :t WHERE id = :i"), {"t": opened, "i": cid})
            s.execute(text("DELETE FROM case_stage_log WHERE case_id = :i AND to_stage = 'closed'"), {"i": cid})
            if took is not None:
                s.execute(
                    text("INSERT INTO case_stage_log (case_id, from_stage, to_stage, reason, actor, at) "
                         "VALUES (:i, 'executing', 'closed', 'Outcome reported', 'system', :t)"),
                    {"i": cid, "t": opened + timedelta(days=took)},
                )  # fmt: skip
        s.commit()
    yield
    starting.reset()


def page(user: str = "admin", **q: object) -> dict:
    r = client.get("/api/screens/analytics", params=q, headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def get(user: str = "admin", **q: object):
    q = {"source": "decisions", "key": "all"} | q
    return client.get(ROWS, params=q, headers=h(user))


def rows(user: str = "admin", **q: object) -> dict:
    r = get(user, **q)
    assert r.status_code == 200, r.text
    return r.json()


def rc(page_rows: list[dict]) -> list[dict]:
    return [r for r in page_rows if r["status"] == "reconciled"]


def everything(q: dict, user: str = "admin") -> list[dict]:
    """Every row of the selection (the table pages through, so it is read in pages of 200)."""
    got: list[dict] = []
    while True:
        out = rows(user, **q, limit=200, offset=len(got))
        got += out["rows"]
        if len(got) >= out["total"] or not out["rows"]:
            return got


def figure(chart: str, key: str = "all", user: str = "admin", **q: object) -> dict:
    return rows(user, chart=chart, key=key, **q)


# ---------------------------------------------------------------- the rows are the rows the figure counts
def test_kpis_waterfall_and_pipeline_reconcile_with_the_page():
    p = page()
    m, pr = p["metrics"], p["rows"]
    k = figure("kpi")
    assert k["of"] == len(rc(pr)) and k["sum"]["value"] == m["uplift"] and k["sum"]["unit"] == "usd"
    assert k["totals"]["vs"] == m["uplift"]
    assert figure("kpi", "avoided")["sum"]["value"] == m["avoided"]
    assert figure("kpi", "pending")["total"] == m["pend"]
    assert figure("waterfall", "baseline")["sum"]["value"] == m["base"]
    assert figure("waterfall", "circularity")["sum"]["value"] == m["act"]
    assert figure("waterfall")["sum"]["value"] == m["uplift"]
    routes = {r["route"] for r in rc(pr)}
    assert routes
    for route in routes:
        w = figure("waterfall", f"route:{route}")
        mine = [r for r in rc(pr) if r["route"] == route]
        assert w["of"] == len(mine) and w["sum"]["value"] == sum(r["actual"] - r["baseline"] for r in mine)
    assert figure("pipeline")["of"] == len(pr)
    assert figure("pipeline", "carried_out")["of"] == len([r for r in pr if r["status"] in ("reconciled", "pending")])
    assert figure("pipeline", "reconciled")["of"] == len(rc(pr))


def test_mix_flow_heatmap_and_trend_reconcile_with_the_page():
    pr = page()["rows"]
    carried = [r for r in pr if r["status"] in ("reconciled", "pending")]
    mix = figure("mix", "route:redeploy|month:3")
    assert mix["of"] == len([r for r in carried if r["route"] == "redeploy" and r["mi"] == 3])
    assert figure("mix", "month:3")["of"] == len([r for r in carried if r["mi"] == 3])
    for key, pred in (
        ("cls:pump", lambda r: r["cls"] == "pump"),
        ("route:resale|status:pending", lambda r: r["route"] == "resale" and r["status"] == "pending"),
        ("cls:motor|route:redeploy", lambda r: r["cls"] == "motor" and r["route"] == "redeploy"),
        ("status:cancelled", lambda r: r["status"] == "cancelled"),
    ):
        assert figure("flow", key)["of"] == len([r for r in pr if pred(r)]), key
    assert figure("flow")["of"] == len(pr)
    cell = [r for r in rc(pr) if r["route"] == "redeploy" and r["cls"] == "motor"]
    heat = figure("heatmap", "route:redeploy|cls:motor")
    assert heat["of"] == len(cell) and heat["sum"]["label"] == "Median uplift per case"
    assert heat["sum"]["value"] == statistics.median([r["actual"] - r["baseline"] for r in cell])
    month = [r for r in rc(pr) if r["mi"] == 5]
    assert figure("trend", "month:5")["sum"]["value"] == sum(r["actual"] for r in month)
    assert figure("trend")["sum"]["value"] == sum(r["actual"] for r in rc(pr))


def test_predicted_models_overrides_eng_and_sustain_reconcile_with_the_page():
    p = page()
    pr = p["rows"]
    pts = [r for r in rc(pr) if r["route"] != "exit" and r["p50"] > 0 and (r["actual"] or 0) > 0 and not r["override"]]
    assert figure("predicted")["of"] == len(pts)
    stats = {s["v"]: s for s in p["model_stats"] if s}
    for v, s in stats.items():  # the account sees every tenant, so its rows are the table's rows
        m = figure("models", f"model:{v}")
        assert m["of"] == s["n"], v
        assert "your rows" in m["subtitle"]
    ov = [r for r in rc(pr) if r["override"]]
    o = figure("overrides")
    assert o["of"] == len(ov) and o["sum"]["value"] == sum(r["override"]["delta"] for r in ov)
    reason = ov[0]["override"]["reason"]
    one = figure("overrides", f"reason:{reason}")
    mine = [r for r in ov if r["override"]["reason"] == reason]
    assert one["of"] == len(mine) and one["sum"]["value"] == sum(r["override"]["delta"] for r in mine)
    e = next(r for r in pr if r["ero"] > 0)
    cell = [r for r in pr if r["equip"] == e["equip"] and r["comp"] == e["comp"] and r["ero"] > 0]
    eng = figure("eng", f"equip:{e['equip']}|comp:{e['comp']}")
    assert eng["of"] == len(cell) and eng["sum"]["value"] == sum(r["ero"] for r in cell)
    assert figure("sustain")["sum"]["value"] == sum(r["co2e"] for r in rc(pr))
    me = [r for r in rc(pr) if r["co2m"] is not None]
    assert figure("sustain", "measured")["sum"]["value"] == sum(r["co2m"] for r in me)
    r1 = me[0]["route"]
    by = figure("sustain", f"route:{r1}")
    assert by["of"] == len([r for r in me if r["route"] == r1])
    assert by["sum"]["value"] == sum(r["co2m"] for r in me if r["route"] == r1)


def test_the_pages_filters_narrow_the_rows_as_they_narrow_the_charts():
    q = {"cls": "pump", "route": "redeploy", "from": 2, "to": 6, "model": "v1.2"}
    pr = page(**q)["rows"]
    out = figure("kpi", **q)
    assert out["of"] == len(rc(pr)) and out["period"] == "Dec 25 to Apr 26"
    assert figure("kpi", tenant_filter="Customer A")["of"] == len(rc(page(tenant_filter="Customer A")["rows"]))


def test_a_part_of_a_chart_partitions_the_whole():
    whole = figure("flow")
    parts = [figure("flow", f"status:{s}")["of"] for s in ("reconciled", "pending", "cancelled", "expired")]
    assert sum(parts) == whole["of"]
    classes = {r["cls"] for r in page()["rows"]}
    assert sum(figure("flow", f"cls:{c}")["of"] for c in classes) == whole["of"]


# ---------------------------------------------------------------- live cases: ageing and the pack's cases
def test_open_decisions_by_age_reconcile_with_the_pages_awaiting_approval_count():
    live = page()["metrics"]["liveOpen"]
    out = client.get("/api/screens/analytics/open-age", headers=h("admin")).json()
    assert out["total"]["n"] == live and live >= 3
    assert [b["key"] for b in out["bands"]] == ["0-7", "8-14", "15-30", "30+"]
    assert sum(b["n"] for b in out["bands"]) == live
    whole = rows(source="cases", chart="age")
    assert whole["of"] == live and whole["sum"]["value"] == out["total"]["value"]
    for b in out["bands"]:
        got = rows(source="cases", chart=b["rows"]["chart"], key=b["rows"]["key"])
        assert got["of"] == b["n"] and got["sum"]["value"] == b["value"], b["key"]
        assert sum(r["n"] for r in b["routes"]) == b["n"]
        for r in b["routes"]:
            sub = rows(source="cases", chart=r["rows"]["chart"], key=r["rows"]["key"])
            assert (sub["of"], sub["sum"]["value"]) == (r["n"], r["value"])
    ages = {x["id"]: x["days"] for x in whole["rows"]}
    assert ages["RT-GR-1"] < 8 <= ages["RT-GR-2"] <= 30 < ages["RT-GR-3"]  # the three bands the module's cases fall in


def test_the_age_rows_are_the_callers_tenants_only():
    a = rows("planner.a", source="cases", chart="age")
    assert a["tenants"] == ["Customer A"] and {r["tenant"] for r in a["rows"]} == {"Customer A"}
    assert "RT-GR-3" not in {r["id"] for r in a["rows"]}  # Customer B's
    assert client.get("/api/screens/analytics/open-age", headers=h("planner.a")).json()["total"]["n"] == a["of"]
    assert rows("planner.a", source="cases", chart="age", org="Customer B")["total"] == 0


def test_the_warehouse_lock_holds_on_case_rows():
    wm = policy.account("wm-1")
    assert wm is not None and wm.warehouse
    with SessionLocal() as s:
        mine = {r["id"]: r for r in svc.age_records(s, Principal(account=wm, ctx=policy.Context()), svc.Filters())}
        every = {
            r["id"] for r in svc.age_records(s, Principal(account=policy.account("admin"), ctx=policy.Context()), svc.Filters())
        }
    assert mine and set(mine) < every
    assert "RT-GR-1" in mine and "RT-GR-2" not in mine  # Warehouse 1 and Warehouse 2
    assert client.get(ROWS, params={"source": "cases", "chart": "age"}, headers=h("warehouse1")).status_code == 403


def test_pack_cases_are_a_whitelist_and_follow_the_tenant_boundary():
    out = rows(source="cases", chart="pack", key="pack:device")
    assert [c["key"] for c in out["columns"]] == ["id", "received", "grade", "route", "status", "days", "net", "co2", "co2_set"]
    assert next(c["label"] for c in out["columns"] if c["key"] == "route") == "Channel"  # a device's route is its channel
    assert {r["id"] for r in out["rows"]} >= {"RT-GR-4", "RT-GR-5", "RT-GR-6"}
    assert all(set(r) == {c["key"] for c in out["columns"]} for r in out["rows"])  # nothing but the whitelist
    assert "never in a row" not in str(out)
    assert out["sum"]["value"] == 220.0 and out["sum"]["label"] == "Net (modelled)"
    closed = rows(source="cases", chart="pack", key="pack:device|state:closed")
    assert {r["id"] for r in closed["rows"]} == {"RT-GR-4", "RT-GR-6"}
    assert rows(source="cases", chart="pack", key="pack:device|route:offers|grade:A")["of"] == 2
    one = rows("planner.b", source="cases", chart="pack", key="pack:device")
    assert [r["id"] for r in one["rows"]] == ["RT-GR-6"] and one["tenants"] == ["Customer B"]
    assert rows(source="cases", chart="pack", key="pack:device", days=7)["of"] == 1  # RT-GR-5; the others opened earlier


def test_a_count_says_1_row_not_1_rows():
    assert [svc.row_count(n) for n in (0, 1, 2, 1277)] == ["0 rows", "1 row", "2 rows", "1,277 rows"]
    one = rows("planner.b", source="cases", chart="pack", key="pack:device")
    assert one["of"] == 1 and one["subtitle"].startswith("1 row · ")


def test_a_route_with_a_request_or_lot_in_its_id_has_its_channels_plain_name():
    assert svc.channel_of("rerent:REQ-1") == "rerent" and svc.channel_of("offers") == "offers"
    names = {"rerent": "Re-rent", "retail": "Retail lot"}
    assert svc._route_name("rerent:REQ-1", names) == "Re-rent"
    assert svc._route_name("retail:LOT-S", names) == "Retail lot"
    assert svc._route_name("nothing:X") == "nothing:X"  # an id nobody names stays as it is


# ---------------------------------------------------------------- access
def test_a_tenant_account_never_receives_another_tenants_row():
    every = figure("waterfall")
    a = figure("waterfall", user="planner.a")
    assert a["tenants"] == ["Customer A"] and 0 < a["of"] < every["of"]
    assert {r["tenant"] for r in everything({"source": "decisions", "chart": "waterfall", "key": "all"}, "planner.a")} == {
        "Customer A"
    }
    mine = {r["id"] for r in rc(page("planner.a")["rows"])}
    assert {r["id"] for r in everything({"source": "decisions", "chart": "waterfall", "key": "all"}, "planner.a")} == mine
    assert figure("waterfall", user="planner.a", org="Customer B")["total"] == 0
    assert figure("waterfall", user="planner.a", tenant="Customer B")["total"] == 0
    assert figure("waterfall", user="planner.a", org="Customer B")["can_export"] is False
    # the model table keeps its demo numbers, but the rows behind it are the caller's own
    assert figure("models", user="planner.a")["of"] < figure("models")["of"]


@pytest.mark.parametrize(
    ("user", "chart", "code"),
    [
        ("engineer", "waterfall", 403), ("engineer", "overrides", 403), ("engineer", "pipeline", 403), ("engineer", "eng", 200),
        ("engineer", "sustain", 200), ("planner.a", "eng", 403), ("planner.a", "sustain", 403), ("planner.a", "overrides", 200),
        ("developer", "kpi", 403), ("warehouse1", "kpi", 403), ("executive", "eng", 200), ("finance", "sustain", 200),
    ],
)  # fmt: skip
def test_a_role_without_the_charts_section_is_refused(user, chart, code):
    assert get(user, chart=chart).status_code == code
    assert client.get(ROWS + ".csv", params={"source": "decisions", "chart": chart}, headers=h(user)).status_code == code


def test_signed_out_is_refused():
    assert client.get(ROWS, params={"source": "decisions", "chart": "kpi"}).status_code == 401


def test_the_hidden_pool_section_has_no_chart():
    assert get(chart="pool").status_code == 422


# ---------------------------------------------------------------- what is refused, paged and sorted
@pytest.mark.parametrize(
    "q",
    [
        {"chart": "nope"}, {"chart": "kpi", "key": "nope"}, {"chart": "waterfall", "key": "route:nope"},
        {"chart": "mix", "key": "month:12"}, {"chart": "mix", "key": "route:redeploy|route:resale"},
        {"chart": "mix", "key": "cls:pump"}, {"chart": "flow", "key": "cls:"}, {"chart": "flow", "key": "cls:pump|"},
        {"chart": "overrides", "key": "reason:not a reason"},
        {"chart": "kpi", "sort": "password"}, {"chart": "kpi", "sort": "reason"}, {"chart": "kpi", "source": "bogus"},
        {"chart": "age"}, {"chart": "kpi", "source": "cases"}, {"chart": "pack", "source": "cases", "key": "all"},
        {"chart": "pack", "source": "cases", "key": "pack:nope"},
        {"chart": "pack", "source": "cases", "key": "pack:device|grade:Z"},
        {"chart": "age", "source": "cases", "key": "band:9-9"}, {"chart": "kpi", "dir": "up"}, {"chart": "kpi", "offset": -1},
        {"chart": "pack", "source": "cases", "key": "pack:device", "days": 9999},
    ],
)  # fmt: skip
def test_an_unknown_chart_key_sort_or_source_is_a_422(q):
    assert get(**q).status_code == 422, q
    assert get(**q).json()["ok"] is False


def test_a_reason_known_only_to_other_tenants_is_unknown_to_the_caller():
    other = next(r for r in page()["rows"] if r["tenant"] == "Customer B" and r["override"])
    mine = {r["override"]["reason"] for r in page("planner.a")["rows"] if r["override"]}
    if other["override"]["reason"] not in mine:  # (every seeded reason is in every tenant; this guards the rule if one is not)
        assert get("planner.a", chart="overrides", key=f"reason:{other['override']['reason']}").status_code == 422


def test_the_limit_is_capped_and_the_pages_add_up():
    big = rows(chart="waterfall", limit=100000)
    assert big["shown"] == len(big["rows"]) == 200 and big["total"] > 200 and big["truncated"] is False
    assert rows(chart="waterfall", limit=0)["shown"] == 1
    assert rows(chart="waterfall", limit=10, offset=big["total"])["rows"] == []
    seen = [r["id"] for r in everything({"source": "decisions", "chart": "waterfall", "key": "all"})]
    assert len(seen) == len(set(seen)) == big["total"]


def test_sort_is_stable_and_ties_keep_the_id_order():
    q = {"source": "decisions", "chart": "mix", "key": "all", "sort": "route"}
    for d in ("asc", "desc"):
        a = everything(q | {"dir": d})
        assert a == everything(q | {"dir": d})
        names = [r["route"] for r in a]
        assert names == sorted(names, key=str.casefold, reverse=d == "desc")
        for x, y in pairwise(a):
            if x["route"] == y["route"]:
                assert x["id"] < y["id"], (d, x["id"], y["id"])
    by_month = everything({"source": "decisions", "chart": "mix", "key": "all", "sort": "month", "dir": "asc"})
    months = [r["month"] for r in by_month]
    assert months == sorted(months, key=lambda m: svc._months().index(m))  # the month sorts as a month, not as text
    nulls = everything({"source": "decisions", "chart": "kpi", "key": "pending", "sort": "actual", "dir": "asc"})
    assert all(r["actual"] is None for r in nulls)  # pending decisions: empty values, all last, none lost


def test_the_search_box_matches_id_model_asset_and_site_and_leaves_the_figure_alone():
    pr = rc(page()["rows"])
    needle = pr[0]["assetId"].lower()
    hit = [r for r in pr if any(needle in str(r[k]).lower() for k in ("id", "model", "assetId", "site"))]
    got = rows(chart="kpi", q=needle.upper())  # not case sensitive
    assert got["total"] == len(hit) and got["totals"]["actual"] == sum(r["actual"] for r in hit)
    assert got["of"] == len(pr) and got["sum"]["n"] == len(pr)  # the figure is the selection, not the search
    assert rows(chart="kpi", q="no such text anywhere")["total"] == 0


def test_the_columns_are_plain_words_and_every_row_has_exactly_them():
    out = rows(chart="kpi", limit=5)
    assert {c["kind"] for c in out["columns"]} <= {"text", "money", "number", "date", "days", "percent"}
    assert [c["label"] for c in out["columns"]][:4] == ["Case", "Month", "Tenant", "Asset class"]
    assert all(set(r) == {c["key"] for c in out["columns"]} for r in out["rows"])
    assert all(c["unit"] for c in out["columns"] if c["kind"] == "money")
    assert out["subtitle"].startswith(f"{out['of']:,} rows · Oct 25 to Sep 26 · Customer A")
    assert out["totals"].keys() <= {c["key"] for c in out["columns"] if c["kind"] == "money"}
    # asset ids are shown in full
    assert all(r["asset"] and "*" not in r["asset"] for r in out["rows"])


def test_the_override_reason_is_cut_in_the_table_and_never_exported():
    long = "x" * 500
    cell = svc._cell(svc.DEC["reason"], {"override": {"reason": long}})
    assert len(cell) == svc.REASON_CHARS and cell.endswith("…")
    out = rows(chart="overrides", limit=3)
    assert "reason" in [c["key"] for c in out["columns"]]
    assert all(len(r["reason"]) <= svc.REASON_CHARS for r in out["rows"])
    reasons = {r["override"]["reason"] for r in page()["rows"] if r["override"]}
    r = client.get(ROWS + ".csv", params={"source": "decisions", "chart": "overrides", "key": "all"}, headers=h("admin"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert not any(reason in r.text for reason in reasons)
    header = next(csv.reader(io.StringIO(r.text)))
    assert "Override reason" not in header and header == [c.label for c in svc.CHARTS["overrides"].columns if c.export]


# ---------------------------------------------------------------- the export
def journal(chart: str) -> list[dict]:
    with engine.connect() as conn:
        found = conn.execute(
            text("SELECT input, actor, role FROM action_journal WHERE action = 'analytics.export' AND input->>'chart' = :c"),
            {"c": chart},
        ).mappings()
        return [dict(x) for x in found]


def test_the_csv_has_the_shown_columns_and_the_selection_and_is_journaled():
    q = {"source": "decisions", "chart": "waterfall", "key": "route:redeploy", "sort": "actual", "dir": "asc", "q": "CS-"}
    shown = rows(**q)
    r = client.get(ROWS + ".csv", params=q, headers=h("admin"))
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    got = list(csv.reader(io.StringIO(r.text)))
    assert got[0] == [c["label"] for c in shown["columns"]]
    assert len(got) - 1 == shown["total"]
    first = rows(**q, limit=1)["rows"][0]
    assert got[1][0] == first["id"] and got[1][got[0].index("Actual")] == str(first["actual"])
    entries = journal("waterfall")
    assert entries and entries[-1]["actor"] == "admin" and entries[-1]["input"]["key"] == "route:redeploy"
    assert entries[-1]["input"]["sort"] == "actual"


def test_the_export_is_capped(monkeypatch):
    monkeypatch.setattr(svc, "EXPORT_CAP", 7)
    out = rows(chart="waterfall")
    assert out["truncated"] is True
    r = client.get(ROWS + ".csv", params={"source": "decisions", "chart": "waterfall"}, headers=h("admin"))
    assert len(list(csv.reader(io.StringIO(r.text)))) == 8  # the header and 7 rows


def test_a_cell_that_a_spreadsheet_would_run_is_written_as_text():
    assert svc._safe("=SUM(A1)") == "'=SUM(A1)" and svc._safe("+1") == "'+1" and svc._safe("@x") == "'@x"
    assert svc._safe(-5) == -5 and svc._safe("CS-2001") == "CS-2001"


def test_an_agent_cannot_export_and_a_refused_export_writes_nothing():
    before = len(journal("kpi"))
    hdr = h("admin") | {"X-Circularity-Preparer": "coordinator"}
    r = client.post("/api/actions/analytics.export", json={"source": "decisions", "chart": "kpi"}, headers=hdr).json()
    assert r["ok"] is False and r["error"]["code"] == "approval_required"
    assert (
        client.get(ROWS + ".csv", params={"source": "decisions", "chart": "kpi", "key": "nope"}, headers=h("admin")).status_code
        == 422
    )
    assert client.get(ROWS + ".csv", params={"source": "decisions", "chart": "eng"}, headers=h("planner.a")).status_code == 403
    assert len(journal("kpi")) == before


def test_the_export_action_itself_checks_the_section_and_counts_the_rows():
    r = client.post("/api/actions/analytics.export", json={"source": "decisions", "chart": "kpi"}, headers=h("admin")).json()
    assert r["ok"] is True and r["output"]["rows"] == rows(chart="kpi")["total"] and "reason" not in r["output"]["columns"]
    bad = client.post("/api/actions/analytics.export", json={"source": "decisions", "chart": "waterfall"}, headers=h("engineer"))
    assert bad.status_code == 403 and bad.json()["error"]["code"] == "out_of_scope"
