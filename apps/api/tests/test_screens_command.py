"""B14: the Command Center reads give what the facade (apps/web/src/api/command.ts) gives today, for all 11 accounts,
with the page's filters (tenant, site, class, route, time horizon; the table's view, due window, reason and search) and
view settings (Admin's senior view, the widened operational scope).

Golden data: fixtures/golden/screens/command.json (apps/web/scripts/golden/home_command.mjs), from the starting state.
Floats were rounded to 1e-6 and an unlimited approval limit written as "Infinity" by the golden script; the server's
answer is rounded the same way and sends null for no limit. Booleans compare strictly.

One value is not compared, by design (di/screens/command.py): kpis.counts.workflows. The demo counts its workflows only
once a page has opened them (S.wf is created lazily, so the count depends on what the session visited first); the server
always counts the catalogue. It is checked against the demo's catalogue size instead.

Plan 6 B4 (decision-log D-Fabric): the Connection Fabric figures are real, so they are not compared with the demo's
hash-generated buckets and fixed sources: the kpis' health strip and fabric tiles and the whole /health detail are
asserted to equal the Monitor, the Source Map, the sources and Event Streams at the same moment.
"""

import os

import pytest

from di import golden
from di.engine.jsmath import js_round
from di.reads.common import fmt_n, to_fixed
from tests import starting
from tests.helpers import client, h

CMD = golden.load("screens/command")
ACCOUNTS = sorted(CMD)


def setup_module():
    if os.environ.get("B14_PARALLEL") != "1":
        starting.reset()


def get(path: str, user: str, **params):
    r = client.get("/api/screens/command" + path, params=params, headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def plain(x):
    if isinstance(x, bool):
        return x
    if isinstance(x, float):
        return js_round(x * 1e6) / 1e6
    if isinstance(x, dict):
        return {k: plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [plain(v) for v in x]
    return x


def expected(x):
    """The golden value, with "Infinity" (no approval limit) read as the server's null."""
    if x == "Infinity":
        return None
    if isinstance(x, dict):
        return {k: expected(v) for k, v in x.items()}
    if isinstance(x, list):
        return [expected(v) for v in x]
    return x


def same(got, want) -> None:
    assert starting.strict(plain(got)) == starting.strict(expected(want))


def case_params(kind: str):
    return [
        pytest.param(acct, i, id=f"{acct}-{i}-{'-'.join(f'{k}={v}' for k, v in x['filters'].items()) or 'none'}")
        for acct in ACCOUNTS
        for i, x in enumerate(CMD[acct][kind])
    ]


def test_every_account_is_in_the_golden_file():
    assert len(ACCOUNTS) == 11


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_layout(acct):
    for mode, want in CMD[acct]["layout"].items():
        same(get("/layout", acct, mode=mode), want)


KPI_CASES = [
    pytest.param(acct, mode, i, id=f"{acct}-{mode}-{i}")
    for acct in ACCOUNTS
    for mode, xs in CMD[acct]["kpis"].items()
    for i in range(len(xs))
]


FABRIC_TILES = ("ihealth", "srcattn", "wffail", "conf")


def fabric_now(read):
    """`read()` with the Monitor, the Source Map, the sources and the event stream at the same moment (repeated when a
    sync lands between the reads: the worker keeps syncing while the tests run)."""

    def fabric():
        hd = h("developer")
        return [
            client.get(f"/api/screens/integration/{x}", params={"limit": 2000}, headers=hd).json()
            for x in ("monitor", "map", "sources", "events")
        ]

    for _ in range(5):
        before, got, after = fabric(), read(), fabric()
        if before == after:
            return got, before
    raise AssertionError("the Connection Fabric kept changing")


def check_fabric_tiles(tiles: list[dict], mon: dict, smap: dict, srcs: dict) -> None:
    """The Connection Fabric tiles equal the Monitor and the Source Map (plan 6 B4)."""
    stale = [s for s in srcs["sources"] if s["status"] in ("stale", "unavailable")]
    pct = mon["totals"]["pct"]
    n_wf, n_cf = mon["kpis"]["failing_workflows"], smap["open_conflicts"]
    expect = {
        "ihealth": ("ok" if pct >= 95 else "bad", to_fixed(pct, 1) + "%", "successful syncs and events · 24 h"),
        "srcattn": ("bad" if stale else "ok", fmt_n(len(stale)), ", ".join(s["name"] for s in stale) or "all sources fresh"),
        "wffail": ("bad" if n_wf else "ok", fmt_n(n_wf), "published, last run failed"),
        "conf": ("bad" if n_cf else "ok", fmt_n(n_cf), "systems that disagree"),
    }
    for t in tiles:
        if t["key"] in expect:
            assert (t["cls"], t["val"], t["sub"]) == expect[t["key"]], t["key"]


@pytest.mark.parametrize(("acct", "mode", "i"), KPI_CASES)
def test_key_figures(acct, mode, i):
    """Plan 6 B4: the health strip and the Connection Fabric tiles (integration health, sources needing attention,
    failing workflows, open conflicts) are real (decision-log D-Fabric): they equal the Monitor, the Source Map and the
    sources for the same moment, not the demo's hash-generated buckets and fixed sources. Their label, icon, link and
    tip stay the demo's; everything else is compared with the demo exactly."""
    want = CMD[acct]["kpis"][mode][i]
    got, (mon, smap, srcs, _) = fabric_now(lambda: get("/kpis", acct, mode=mode, **want["filters"]))
    assert got["counts"].pop("workflows") == 35  # the demo's catalogue (docstring)
    want = {k: v for k, v in want.items() if k != "filters"}
    want["counts"] = {k: v for k, v in want["counts"].items() if k != "workflows"}
    health = got.pop("health")
    want.pop("health")
    st = {"live": 0, "stale": 0, "manual": 0, "unavailable": 0}
    for s in srcs["sources"]:
        st[s["status"]] = st.get(s["status"], 0) + 1
    assert health == {"pct": mon["totals"]["pct"], **st}
    check_fabric_tiles(got["tiles"], mon, smap, srcs)

    def cut(tiles):
        return [{k: v for k, v in t.items() if k not in ("cls", "val", "sub")} if t["key"] in FABRIC_TILES else t for t in tiles]

    got["tiles"], want["tiles"] = cut(got["tiles"]), cut(want["tiles"])
    same(got, want)


@pytest.mark.parametrize(("acct", "i"), case_params("charts"))
def test_charts(acct, i):
    want = CMD[acct]["charts"][i]
    same(get("/charts", acct, **want["filters"]), {k: v for k, v in want.items() if k != "filters"})


@pytest.mark.parametrize(("acct", "i"), case_params("exceptions"))
def test_exceptions(acct, i):
    want = CMD[acct]["exceptions"][i]
    same(get("/exceptions", acct, **want["filters"]), {k: v for k, v in want.items() if k != "filters"})


@pytest.mark.parametrize(("acct", "i"), case_params("actions"))
def test_actions_to_prioritise(acct, i):
    want = CMD[acct]["actions"][i]
    got = get("/actions", acct, **want["filters"])
    assert got["total"] == len(want["rows"])
    same(got["rows"], want["rows"])


@pytest.mark.parametrize("widen", [False, True])
@pytest.mark.parametrize("acct", ACCOUNTS)
def test_actions_on_me_and_handed_off(acct, widen):
    want = CMD[acct]["op_scopes"]["all" if widen else "default"]
    aome = get("/aome", acct, all=str(widen).lower())
    same(aome, {"items": want["aome"], "scope": want["scope"]})
    same(
        get("/handed", acct, all=str(widen).lower()),
        {"handed": want["handed"], "awaiting": want["awaiting"], "scope": want["scope"]},
    )


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_outcomes_to_confirm(acct):
    same(get("/outcomes", acct), CMD[acct]["outcomes"])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_approvals_inbox(acct):
    same(get("/inbox", acct), CMD[acct]["inbox"])


TENANT_CASES = [pytest.param(acct, t, id=f"{acct}-{t}") for acct in ACCOUNTS for t in CMD[acct]["in_tenant"]]


@pytest.mark.parametrize(("acct", "tenant"), TENANT_CASES)
def test_the_tenant_menu_narrows_the_queues(acct, tenant):
    want = CMD[acct]["in_tenant"][tenant]
    same(get("/aome", acct, tenant=tenant), {"items": want["aome"], "scope": want["scope"]})
    same(get("/handed", acct, tenant=tenant), {"handed": want["handed"], "awaiting": want["awaiting"], "scope": want["scope"]})
    same(get("/outcomes", acct, tenant=tenant), want["outcomes"])
    got = get("/inbox", acct, tenant=tenant)
    same(
        {"decisions_awaiting": got["decisions_awaiting"], "cards": got["cards"]},
        {k: want[k] for k in ("decisions_awaiting", "cards")},
    )


def test_pre_approval_checks(session):
    """Nothing is submitted at the start, so the approval cards are empty; their checks (the demo's afRisks) are compared
    for every case with a recommendation instead."""
    from di import policy
    from di.actions.pipeline import Actor, CallContext
    from di.cases import store
    from di.reads import cases as case_reads
    from di.reads.workspace import af_risks

    want = CMD["admin"]["risks"]
    ctx = CallContext(actor=Actor(account=policy.account("admin")), session=session)
    got = {}
    for c in store.all_cases(session):
        if c["id"] in want:
            rt = case_reads.case_routes({"case_id": c["id"]}, ctx)
            ev = case_reads.case_evidence({"case_id": c["id"]}, ctx)
            got[c["id"]] = af_risks(c, rt, ev)
    assert len(got) == len(want) > 0
    same(got, want)


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_integration_health(acct):
    """Plan 6 B4: the integration health detail is real (decision-log D-Fabric): its totals and hourly buckets are the
    Monitor's, its exceptions the Source Map's and its events the head of Event Streams, for the same moment. The demo's
    hash-generated buckets are gone. The golden file still fixes its shape."""
    got, (mon, smap, _, ev) = fabric_now(lambda: get("/health", acct))
    assert set(got) == set(CMD[acct]["health"])
    t = mon["totals"]
    assert {k: got[k] for k in ("ok", "warn", "bad", "run", "pct")} == {k: t[k] for k in ("ok", "warn", "bad", "run", "pct")}
    assert got["hours"] == mon["hourly"]
    assert got["exceptions"] == smap["exceptions"][:6] and got["exceptionCount"] == smap["kpis"]["exceptions"]
    assert [(e["id"], e["ts"], e["dest"], e["type"], e["ack"]) for e in got["events"]] == [
        (e["id"], e["ts"], e["dest"], e["type"], e["ack"]) for e in ev["events"][:6]
    ]
    assert all(e["kind"] == "ok" for e in got["events"] if e["ack"] == "acknowledged")


def test_signed_out_is_refused():
    assert client.get("/api/screens/command/kpis").status_code == 401
