"""B14: the Home and utility-page reads give what the facade (apps/web/src/api/home.ts) gives today, for all 11 accounts.

Golden data: fixtures/golden/screens/home.json (apps/web/scripts/golden/home_command.mjs), from the starting state.
Numbers went through the golden script's plain(): floats rounded to 1e-6; the comparison rounds the server's answer the
same way. Booleans compare strictly (tests/starting.py).

Two golden values are synthetic in the demo and are not compared, by design (see di/screens/home.py):
- a failing workflow alert's `s` ends with " · <age of the last run>", drawn at random when the demo seeds its
  workflows; the server answers the failure note alone, so the age is cut from the expected text;
- Home's activity includes the demo's seeded workflow runs (random times and record counts): the server has none, so
  the expected activity is the demo's own frActivity with those runs removed (`activity_without_workflow_runs`).

Plan 6 B4 (decision-log D-Fabric): the Developer's Connection Fabric KPI tiles are real; their numbers are asserted to
equal the Monitor and the Source Map at the same moment instead of the demo's (test_kpis). The same holds for the
alerts' sources and conflicts and the Developer's briefing lines on them (plan 6 follow-up): they are asserted against
the source list and the conflict queue at the same moment (test_alerts, test_briefing); every other field is the
demo's. No golden file was edited.
"""

import os
import re

import pytest
from sqlalchemy import text

from di import golden
from di.db import engine
from di.engine.jsmath import js_round
from di.reads.common import to_fixed
from tests import starting
from tests.helpers import client, h

HOME = golden.load("screens/home")
ACCOUNTS = sorted(HOME)


def setup_module():
    if os.environ.get("B14_PARALLEL") != "1":
        starting.reset()


def get(path: str, user: str, **params):
    r = client.get("/api/screens/home" + path, params=params, headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def plain(x):
    """The golden script's rounding, applied to the server's answer, with strict booleans."""
    if isinstance(x, bool):
        return x
    if isinstance(x, float):
        return js_round(x * 1e6) / 1e6
    if isinstance(x, dict):
        return {k: plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [plain(v) for v in x]
    return x


def same(got, expected) -> None:
    assert starting.strict(plain(got)) == starting.strict(expected)


def test_every_account_is_in_the_golden_file():
    assert len(ACCOUNTS) == 11


REAL_ALERTS = ("src", "conf")  # the alert kinds that come from the live Connection Fabric (docstring)


def with_fabric(read, acct: str):
    """`read()` together with the Connection Fabric at the same moment: the sources as the Source Map shows them, the
    open conflicts (the Conflict Queue's count) and those that hold up a decision of the account (the menu badge's
    rule). The reads are repeated when a sync lands between them (the worker keeps syncing while the tests run)."""

    def fabric():
        hd = h("developer")
        srcs = client.get("/api/screens/integration/sources", headers=hd).json()["sources"]
        n = client.get("/api/screens/integration/conflicts", params={"limit": 1}, headers=hd).json()["counts"]["open"]
        held = client.get("/api/screens/nav", headers=h(acct)).json()["badges"]["sections"]["conf"]
        return srcs, n, held

    for _ in range(5):
        before, got, after = fabric(), read(), fabric()
        if before == after:
            return got, before
    raise AssertionError("the Connection Fabric kept changing")


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_briefing(acct):
    """Every account's briefing is the demo's, but the Developer's Connection Fabric lines (decision-log D-Fabric):
    the stale or unconnected sources and the open conflicts are the live fabric's (the source list and the conflict
    queue at the same moment; the conflicts line also says how many hold up a decision, the menu badge's rule), and
    the failed workflows are the stored workflows whose last run failed (the seeded state: the demo's one). An Admin's
    briefing stops at six lines, before these."""
    if acct != "developer":
        same(get("/briefing", acct), HOME[acct]["briefing"])
        return
    got, (srcs, n, held) = with_fabric(lambda: get("/briefing", acct), acct)
    want = HOME[acct]["briefing"]
    st = [s for s in srcs if s["status"] in ("stale", "unavailable")]
    names = (": " + ", ".join(s["name"] for s in st)) if st else ""
    assert got[0] == {"text": f"{len(st)} source{'' if len(st) == 1 else 's'} stale or not connected{names}.",
                      "go": "integration/map", "n": len(st)}  # fmt: skip
    assert got[1] == want[1]  # the seeded failed workflow
    line = plural(n, "open source conflict", "open source conflicts") + "; " + plural(held, "holds", "hold") + " up a decision."
    assert got[2] == {"text": line, "go": "integration/conflicts", "n": n}
    same(got[3:], want[3:])


def test_the_developer_briefing_lists_a_workflow_whose_real_run_failed():
    from di import state
    from di.db import SessionLocal

    with SessionLocal() as s:
        w = state.get(s, "workflows", "WF-101")
        w["last"] = {"ts": w["last"]["ts"], "state": "failed", "dur": 1, "rows": 0, "note": "Salesforce failed"}
        state.put(s, "workflows", "WF-101", w)
        s.commit()
    try:
        line = next(x for x in get("/briefing", "developer") if x["go"] == "integration/studio")
        names = "Ingest · Salesforce Sales Cloud, Ingest · Oracle Depot Repair"
        assert line["text"] == f"2 workflows failed on the last run: {names}."
        assert line["n"] == 2
        wf = [a for a in get("/alerts", "developer") if a["kind"] == "wf"]
        seeded = HOME["developer"]["alerts"][0]["s"].split(" · ")[0]  # WF-116's seeded failure note
        assert [(a["id"], a["s"]) for a in wf] == [("wf:WF-101", "Salesforce failed"), ("wf:WF-116", seeded)]
    finally:
        state.reset(["workflows"])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_tasks(acct):
    same(get("/tasks", acct), HOME[acct]["tasks"])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_alerts(acct):
    """The demo's alerts, but the stale or failing sources (one alert each, from source_system as the Connection Fabric
    shows it) and the open conflicts (one alert for the whole queue: how many are open and how many hold up a
    decision), which are the live fabric's (decision-log D-Fabric). Every other alert, and every field of the others, is
    the demo's."""
    expected = [
        {**a, "s": re.sub(r" · [^·]* ago$", "", a["s"])} if a["kind"] == "wf" else a  # the run's random age (docstring)
        for a in HOME[acct]["alerts"]
    ]
    got, (srcs, n, held) = with_fabric(lambda: get("/alerts", acct), acct)
    same([a for a in got if a["kind"] not in REAL_ALERTS], [a for a in expected if a["kind"] not in REAL_ALERTS])
    sees_src = any(a["kind"] in ("src", "cred") for a in expected)  # the accounts that see the Connection Fabric
    st = [s for s in srcs if s["status"] in ("stale", "unavailable")] if sees_src else []
    assert sorted(a["id"] for a in got if a["kind"] == "src") == sorted("src:" + s["id"] for s in st)
    for a in (a for a in got if a["kind"] == "src"):
        s = next(x for x in st if "src:" + x["id"] == a["id"])
        assert a["t"].startswith(s["name"] + " · ") and a["s"].startswith(s["vendor"]) and a["go"] == "integration/map"
    conf = [a for a in got if a["kind"] == "conf"]
    if any(a["kind"] == "conf" for a in expected) and n:
        t = plural(n, "open source conflict", "open source conflicts")
        assert conf == [{"id": "cf:open", "kind": "conf", "ic": "conflict", "h": "dec", "t": t,
                         "s": plural(held, "holds", "hold") + " up a decision", "sev": 1, "go": "integration/conflicts",
                         "ack": False}]  # fmt: skip
    else:
        assert not conf


def test_a_failing_or_expired_source_raises_one_alert():
    """A source a sync left failing or with an expired credential shows as stale on the Source Map: one alert each."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE source_system SET status = 'auth_expired' WHERE id = 'crm'"))
        conn.execute(text("UPDATE source_system SET status = 'failing' WHERE id = 'lease'"))
    try:
        got = {a["id"]: a for a in get("/alerts", "developer") if a["kind"] == "src"}
        assert got["src:crm"]["t"].endswith(" · credential expired") and got["src:crm"]["sev"] == 2
        assert got["src:lease"]["t"].endswith(" · sync failing") and got["src:lease"]["sev"] == 2
    finally:
        starting.reset()


FABRIC_TILES = ("wffail", "stale", "mapx", "conf", "health")  # the Developer's Connection Fabric tiles


def fabric_now(read):
    """`read()` together with the Monitor, the Source Map and the sources as they are at the same moment: the reads
    are repeated when a sync lands between them (the worker keeps syncing while the tests run)."""

    def fabric():
        hd = h("developer")
        return [
            client.get(f"/api/screens/integration/{x}", params={"limit": 2000}, headers=hd).json()
            for x in ("monitor", "map", "sources")
        ]

    for _ in range(5):
        before, got, after = fabric(), read(), fabric()
        if before == after:
            return got, before
    raise AssertionError("the Connection Fabric kept changing")


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_kpis(acct):
    """Plan 6 B4: the Developer's Connection Fabric tiles are real (decision-log D-Fabric). They no longer replay the
    demo's hash-generated health buckets or its fixed sources and conflicts: each equals what the Monitor and the Source
    Map show for the same moment (failing workflows, stale or unconnected sources, exceptions, open conflicts, the
    24 hours' success share and its hourly line). Their label, icon and link stay the demo's; every other tile and
    every other account is compared with the demo exactly."""
    got, (mon, smap, srcs) = fabric_now(lambda: get("/kpis", acct))
    want = HOME[acct]["kpis"]
    real = {k["k"]: k for k in got if k["k"] in FABRIC_TILES}
    if acct != "developer":
        assert not real
        same(got, want)
        return

    def labels(tiles):
        return [{k: v for k, v in t.items() if k not in ("v", "n", "sp")} for t in tiles]

    same(labels(got), labels(want))
    stale = sum(1 for s in srcs["sources"] if s["status"] in ("stale", "unavailable"))
    pct = to_fixed(mon["totals"]["pct"], 1)
    expect = {
        "wffail": mon["kpis"]["failing_workflows"],
        "stale": stale,
        "mapx": smap["kpis"]["exceptions"],
        "conf": smap["open_conflicts"],
    }
    for k, n in expect.items():
        assert (real[k]["v"], real[k]["n"]) == (n, n), k
    assert real["health"]["v"] == pct + "%" and real["health"]["n"] == float(pct)
    assert real["health"]["sp"] == [b["ok"] / ((b["ok"] + b["warn"] + b["bad"]) or 1) for b in mon["hourly"]]


@pytest.mark.parametrize("win", ["live", "today", "week"])
@pytest.mark.parametrize("acct", ACCOUNTS)
def test_activity(acct, win):
    same(get("/activity", acct, win=win), HOME[acct]["activity_without_workflow_runs"][win])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_activity_matches_the_facade_where_there_are_no_workflow_runs(acct):
    """Accounts that cannot open the Workflow Studio or the Source Map never see workflow runs: the facade's own output."""
    g = HOME[acct]
    for win in ("live", "today", "week"):
        if not any(r["ic"] == "workflow" for r in g["activity"][win]):
            same(get("/activity", acct, win=win), g["activity"][win])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_middle_panel(acct):
    same(get("/middle", acct), HOME[acct]["middle"])


@pytest.mark.parametrize("per", ["30", "90", "365"])
@pytest.mark.parametrize("acct", ACCOUNTS)
def test_figures(acct, per):
    same(get("/figures", acct, per=per), HOME[acct]["figures"][per])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_reports(acct):
    same(get("/reports", acct), HOME[acct]["reports"])


REPORT_CASES = [
    pytest.param(acct, rid, key, id=f"{acct}-{rid}-{key}")
    for acct in ACCOUNTS
    for rid, by in HOME[acct]["report_rows"].items()
    for key in by
]


@pytest.mark.parametrize(("acct", "rid", "key"), REPORT_CASES)
def test_report_rows(acct, rid, key):
    tenant, period = key.split("|")
    same(get(f"/reports/{rid}", acct, tenant=tenant, period=period), HOME[acct]["report_rows"][rid][key])


def test_every_listed_report_but_the_audit_extract_is_covered():
    for acct in ACCOUNTS:
        listed = {r["id"] for r in HOME[acct]["reports"]} - {"audit"}
        assert set(HOME[acct]["report_rows"]) == listed


def test_the_audit_extract_is_the_audit_area_s():
    r = client.get("/api/screens/home/reports/audit", headers=h("admin"))
    assert r.status_code == 404


def test_a_report_the_account_cannot_open_is_not_found():
    r = client.get("/api/screens/home/reports/health", headers=h("planner-a"))
    assert r.status_code == 404


def test_a_tenant_outside_the_account_is_refused():
    r = client.get("/api/screens/home/reports/pva", params={"tenant": "Customer B"}, headers=h("planner-a"))
    assert r.status_code == 403


def test_signed_out_is_refused():
    assert client.get("/api/screens/home/briefing").status_code == 401
