"""B14: the Connection Fabric's reads, for every account (fixtures/golden/screens/integration.json).

Most of the Connection Fabric is real here: the sources' status, freshness, records and runs come from the synced
source_system, sync_run, raw_record and fetch_log tables, and the conflicts from the conflict table. Those are tested
for shape, scope and invariants (every source listed once with its status and freshness, every conflict names its
authority and that authority's value, counts add up). What is still the demo's reference is compared with the demo
exactly: each source's descriptive fields, field mappings, canonical models and examples, table models, the
catalogue, the event stream (with which cases this account may open), and what is derived from them (tables, fields,
models, channels, category and workflows per source).

The event log is a workspace collection that actions append to: the golden events are compared with the oldest
events of the log (all of it after `starting.reset()`). Since plan 6 B4 Event Streams also lists real messages (sync
runs, instructions, webhook deliveries; ids SYNC-, INS-, WH-), merged newest first; the golden comparison takes the
log's EV- events only, and test_events_include_real_messages checks the real ones (decision-log D-Fabric).
"""

import os
import re
from collections.abc import Mapping

import pytest
from sqlalchemy import text

from di.core import golden
from di.core.db import engine
from di.repositories.fabric import SCREEN_STATUS
from tests import starting
from tests.helpers import client, h

G = golden.load("screens/integration")
ACCOUNTS = list(G["accounts"])
REF = {s["id"]: s for s in G["sources"]}
REF_FIELDS = (
    "name", "short", "cat", "ver", "env", "url", "mode", "auth", "rw", "inputs", "read", "write", "step", "authority", "method",
    "cfg", "cfgVer", "credAt", "credDays", "audit",
)  # fmt: skip
# the section(s) of the Connection Fabric each endpoint needs (any of them)
NEEDS = {
    "sources": ("overview", "map", "tables", "models", "monitor"),
    "overview": ("overview",),
    "map": ("map",),
    "tables": ("tables",),
    "models": ("models",),
    "events": ("events",),
    "conflicts": ("conflicts",),
    "monitor": ("monitor",),
}
STATUSES = {"live", "stale", "manual", "unavailable", "paused", "disconnected"}


def setup_module():
    if os.environ.get("B14_PARALLEL") != "1":
        starting.reset()


def allowed(acct: str, path: str) -> bool:
    secs = G["accounts"][acct]["pages"]["integration"] or []
    return any(s in secs for s in NEEDS[path])


def get(acct: str, path: str, **params):
    """The answer, or None when the account may not see it (checked to be a 403 out_of_scope)."""
    r = client.get(f"/api/screens/integration/{path}", params=params, headers=h(acct))
    if not allowed(acct, path.split("/")[0]):
        assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope", r.text
        return None
    assert r.status_code == 200, r.text
    return r.json()


def db(sql: str, **args):
    with engine.connect() as c:
        return c.execute(text(sql), args).all()


class _LiveSources(Mapping):
    """source_system as it is when a test reads it. Other test files sync and change the sources after this module is
    imported, so a snapshot taken at import time would be stale by the time these tests run."""

    def _rows(self) -> dict:
        return {r[0]: r for r in db("SELECT id, status, last_success_at FROM source_system")}

    def __getitem__(self, k):
        return self._rows()[k]

    def __iter__(self):
        return iter(self._rows())

    def __len__(self):
        return len(self._rows())


DB_SOURCES = _LiveSources()


# ---------------------------------------------------------------- sources
@pytest.mark.parametrize("acct", ACCOUNTS)
def test_sources(acct):
    got = get(acct, "sources")
    if got is None:
        return
    rows = got["sources"]
    assert sorted(s["id"] for s in rows) == sorted(DB_SOURCES)  # every synced source, once
    assert [s["id"] for s in rows if s["id"] in REF] == [s["id"] for s in G["sources"] if s["id"] in DB_SOURCES]  # demo order
    for s in rows:
        st, last = DB_SOURCES[s["id"]][1], DB_SOURCES[s["id"]][2]
        assert s["connectorStatus"] == st and s["status"] == SCREEN_STATUS.get(st, st) and s["status"] in STATUSES
        assert (s["lastSync"] is None) == (last is None) == (s["freshMin"] is None)
        assert s["freshMin"] is None or (s["freshMin"] >= 0 and s["fresh"] != "—")
        assert isinstance(s["records"], int) and s["records"] >= 0
        assert s["runs"] == sorted(s["runs"], key=lambda r: -int(r["id"][5:]))
        # the demo's reference, as the demo has it
        if s["id"] in REF:
            assert {k: s.get(k) for k in REF_FIELDS} == {k: REF[s["id"]].get(k) for k in REF_FIELDS}
            d, hl = G["derived"][s["id"]], s["health"]
            assert (hl["tables"], hl["fields"], hl["channels"], hl["category"]) == (
                d["tables"],
                d["fields"],
                d["channels"],
                d["category"],
            )
            assert hl["workflows"] == d["workflows"]
        hl = s["health"]
        assert hl["success"] is None or 0 <= hl["success"] <= 100
        assert hl["in_sla"] == (s["freshMin"] is not None and s["freshMin"] <= hl["sla"])
        assert hl["needs_attention"] == (
            s["status"] in ("stale", "unavailable")
            or hl["failing"]
            or (s["status"] == "live" and hl["cred_days"] is not None and hl["cred_days"] <= 14)
        )
    assert sum(v for k, v in got["counts"].items() if k != "total") == got["counts"]["total"] == len(rows)


def test_source_filters():
    hd = h("developer")
    live = client.get("/api/screens/integration/sources", params={"status": "live"}, headers=hd).json()["sources"]
    assert live and all(s["status"] == "live" for s in live)
    erp = client.get("/api/screens/integration/sources", params={"q": "s/4hana"}, headers=hd).json()["sources"]
    assert [s["id"] for s in erp] == ["erp"]
    cat = client.get("/api/screens/integration/sources", params={"cat": "EAM"}, headers=hd).json()["sources"]
    assert cat and all(s["health"]["category"] == "EAM" for s in cat)


@pytest.mark.parametrize("sid", sorted(DB_SOURCES))
def test_source_detail(sid):
    got = client.get(f"/api/screens/integration/sources/{sid}", params={"days": 14}, headers=h("engineer")).json()
    s = got["source"]
    assert s["id"] == sid and len(got["series"]) == 14 and all(n >= 0 for n in got["series"])
    assert got["failed"] >= 0
    assert [x["ts"] for x in got["sync_history"]] == [r["ts"] for r in s["runs"][:12]]
    assert all(x["ok"] == (r["result"] == "success") for x, r in zip(got["sync_history"], s["runs"], strict=False))
    if sid in REF:
        assert got["mappings"] == G["mappings"].get(sid, [])
        assert got["models"] == G["derived"][sid]["models"]
        assert got["table_model"] == G["table_models"].get(sid)
    assert isinstance(got["comments"], list)


def test_source_detail_refusals():
    assert client.get("/api/screens/integration/sources/nope", headers=h("admin")).status_code == 404
    r = client.get("/api/screens/integration/sources/erp", headers=h("approver"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope"
    assert client.get("/api/screens/integration/sources").status_code == 401


# ---------------------------------------------------------------- overview and map
@pytest.mark.parametrize("acct", ACCOUNTS)
def test_overview(acct):
    got = get(acct, "overview")
    if got is None:
        return
    connected_catalog = {c["id"] for c in G["catalog"] if c["id"] in DB_SOURCES}
    assert got["catalog"] == [c | {"connected": c["id"] in connected_catalog} for c in G["catalog"]]
    assert got["available"] == [c["id"] for c in G["catalog"] if c["id"] not in connected_catalog]
    ints = got["integrations"]
    assert [i["src"] for i in ints if i["src"]] == [i["src"] for i in ints[: len(DB_SOURCES)]]
    assert len(ints) == len(DB_SOURCES) + len(got["available"])
    assert [i for i in ints if i["catalog"]] == [i for i in G["integrations"] if i["catalog"]]  # catalogue rows: demo reference
    assert set(got["attention"]) <= set(DB_SOURCES) and set(got["connected"]) <= set(DB_SOURCES)
    for i in ints:
        if i["src"]:
            assert i["status"] in ("connected", "attention", "unavailable", "paused", "disconnected", "manual")
            assert (i["status"] in ("attention", "unavailable")) == (
                i["src"] in got["attention"] and DB_SOURCES[i["src"]][1] not in ("paused", "disconnected")
            )
    recs = got["recommendations"]
    assert len(recs) <= 4
    for r in recs:
        assert (r["source"] in DB_SOURCES) if r["source"] else (r["catalog"] in got["available"])
    # catalogue suggestions fill the slots the live sources leave free, in the demo's order; the demo's list can be
    # shorter than what a live database needs, so only the overlap is compared
    cat_recs, golden_cat_recs = [r for r in recs if r["catalog"]], [r for r in G["recommendations"] if r["catalog"]]
    n = min(len(cat_recs), len(golden_cat_recs))
    assert cat_recs[:n] == golden_cat_recs[:n] and len({r["catalog"] for r in cat_recs}) == len(cat_recs)
    assert sum(n for _, n in got["categories"]) == len(ints)


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_map(acct):
    got = get(acct, "map", limit=2000)
    if got is None:
        return
    k = got["kpis"]
    assert k["connected"] == sum(1 for r in DB_SOURCES.values() if r[1] != "unavailable")
    assert k["tables"] == sum(G["derived"][i]["tables"] for i in DB_SOURCES if i in REF)
    assert k["fields"] == sum(len(v) for v in G["mappings"].values())
    assert k["workflows_published"] == sum(1 for w in golden.load("screens/workflows")["starting"] if w["status"] == "published")
    n_open = db("SELECT count(*) FROM conflict WHERE status IN ('open', 'escalated')")[0][0]
    assert k["exceptions"] == len(got["exceptions"]) and got["open_conflicts"] == n_open
    assert sum(1 for e in got["exceptions"] if e["sev"] == "Medium") == n_open
    assert len(got["hourly"]) == 24 and [b["ts"] for b in got["hourly"]] == sorted(b["ts"] for b in got["hourly"])
    t = got["totals"]
    assert (t["ok"], t["warn"], t["bad"]) == tuple(sum(b[x] for b in got["hourly"]) for x in ("ok", "warn", "bad"))
    assert 0 <= t["pct"] <= 100 and k["health_pct"] == t["pct"]
    assert all(a["id"] in DB_SOURCES and a["kind"] in ("ok", "warn") for a in got["activity"]) and len(got["activity"]) <= 6
    deps = {i for i, r in DB_SOURCES.items() if SCREEN_STATUS.get(r[1], r[1]) in ("unavailable", "stale", "manual")}
    assert set(got["dependencies"]) == deps
    assert got["mappings"] == {k: v for k, v in G["mappings"].items() if k in DB_SOURCES}
    assert got["source_models"] == {i: G["derived"][i]["models"] for i in DB_SOURCES if i in REF}
    assert got["table_models"] == {k: m for k, m in G["table_models"].items() if k in DB_SOURCES}


# ---------------------------------------------------------------- tables, models
@pytest.mark.parametrize("acct", ACCOUNTS)
def test_tables(acct):
    got = get(acct, "tables")
    if got is None:
        return
    want = {k: m for k, m in G["table_models"].items() if k in DB_SOURCES}
    assert got["models"] == want
    assert got["counts"] == {
        "tables": sum(len(m["t"]) for m in want.values()),
        "links": sum(len(m["fk"]) for m in want.values()),
        "systems": sum(1 for m in want.values() if m["t"]),
    }
    one = get(acct, "tables", source="erp")
    assert one["models"] == {"erp": G["table_models"]["erp"]}


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_models(acct):
    got = get(acct, "models")
    if got is None:
        return
    assert [{k: v for k, v in m.items() if k != "records"} for m in got["canon"]] == G["canon"]
    assert got["examples"] == G["canon_examples"] and got["prefix"] == G["canon_pfx"]
    assert got["mappings"] == {k: v for k, v in G["mappings"].items() if k in DB_SOURCES}
    assert got["source_models"] == {i: G["derived"][i]["models"] for i in DB_SOURCES if i in REF}
    counts = dict(db("SELECT model, count(*) FROM canonical GROUP BY model"))
    for m in got["canon"]:
        assert m["records"] == counts.get(G["canon_pfx"][m["n"]], 0)
    assert got["counts"]["models"] == len(G["canon"])


# ---------------------------------------------------------------- events, conflicts
@pytest.mark.parametrize("acct", ACCOUNTS)
def test_events(acct):
    got = get(acct, "events")
    if got is None:
        return
    ev, want = got["events"], G["events"]
    log = [e for e in ev if e["id"].startswith("EV-")]  # the workspace log; the rest are real messages (below)
    assert len(log) >= len(want)
    if os.environ.get("B14_PARALLEL") != "1":
        assert len(log) == len(want)
    tail = log[len(log) - len(want) :]
    expected = [e | {"openable": ok} for e, ok in zip(want, G["accounts"][acct]["events_openable"], strict=True)]
    assert starting.strict(tail) == starting.strict(expected)
    assert all(re.fullmatch(r"(EV|SYNC|INS|WH)-.+", e["id"]) for e in ev)
    c = got["counts"]
    assert c["total"] == len(ev) == c["inbound"] + c["outbound"]
    assert c["errors"] == sum(1 for e in ev if re.search("error|fail|duplicate|escalat", e["ack"] or "", re.I))
    out = get(acct, "events", dir="out", issues=True)["events"]
    assert out == [e for e in ev if e["dir"] == "out" and e["ack"] != "acknowledged"]
    q = get(acct, "events", q="rt-1009", limit=5)["events"]
    assert len(q) <= 5 and all(
        "rt-1009" in ((e["caseId"] or "") + (e["decisionId"] or "") + e["type"] + e["dest"]).lower() for e in q
    )


def test_events_include_real_messages():
    """Plan 6 B4: Event Streams lists the workspace log (the demo's seeded messages and what actions add) plus the
    backend's real messages: sync runs that read or failed records (sync_run), instructions that went out or failed
    (instruction), and webhook deliveries (webhook_event, when that table exists), newest first by when they were
    recorded. The real rows have the page's row shape, so its filters, search and drawer work on them unchanged.
    This replaces the demo's fixed stream for those rows (decision-log D-Fabric)."""
    with engine.begin() as c:
        ins = c.execute(
            text(
                "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, status, attempts, last_error) "
                "VALUES ('RT-9999', 'B4-TEST', 0, 'order', 'oms', 'b4-test-idem', 'failed', 3, 'HTTP 503 from oms') "
                "RETURNING id"
            )
        ).scalar_one()
    with engine.begin() as c:
        bad = c.execute(
            text(
                "INSERT INTO sync_run (source_id, trigger, status, started_at, finished_at, error) "
                "VALUES ('erp', 'manual', 'failed', now(), now(), 'connect timeout (b4 test)') RETURNING id"
            )
        ).scalar_one()
    with engine.begin() as c:
        ok = c.execute(
            text(
                "INSERT INTO sync_run (source_id, trigger, status, started_at, finished_at, records_read, facts_written) "
                "VALUES ('wms', 'webhook', 'ok', now(), now(), 7, 21) RETURNING id"
            )
        ).scalar_one()
    try:
        ev = get("admin", "events")["events"]
        ids = [e["id"] for e in ev]
        i_ok, i_bad, i_ins = ids.index(f"SYNC-{ok}"), ids.index(f"SYNC-{bad}"), ids.index(f"INS-{ins}")
        assert i_ok < i_bad < i_ins < ids.index(next(i for i in ids if i.startswith("EV-")))  # newest first
        e = ev[i_ok]
        assert e["dir"] == "in" and e["type"] == "sync.completed" and e["ack"] == "acknowledged"
        assert e["caseId"] is None and e["decisionId"] is None and e["approval"] is None and e["ver"] is None
        assert e["key"] == f"sync-{ok}" and "7 records" in e["note"] and e["openable"] is False
        assert isinstance(e["dest"], str) and e["dest"] and isinstance(e["ts"], str)
        e = ev[i_bad]
        assert e["type"] == "sync.failed" and e["ack"].startswith("failed") and "connect timeout (b4 test)" in e["ack"]
        e = ev[i_ins]
        assert e["dir"] == "out" and e["type"] == "instruction.failed" and e["caseId"] == "RT-9999"
        assert e["approval"] == "B4-TEST" and e["key"] == "b4-test-idem" and e["retries"] == 2
        assert e["ack"] == "failed · HTTP 503 from oms"
        # counts, filters and search see them
        got = get("admin", "events")
        assert got["counts"]["total"] == len(ev) and got["counts"]["inbound"] == sum(1 for x in ev if x["dir"] == "in")
        issues = get("admin", "events", issues=True)["events"]
        assert {f"SYNC-{bad}", f"INS-{ins}"} <= {x["id"] for x in issues} and f"SYNC-{ok}" not in {x["id"] for x in issues}
        assert [x["id"] for x in get("admin", "events", q="b4-test")["events"]] == []  # search: case, decision, type, dest
        assert f"INS-{ins}" in [x["id"] for x in get("admin", "events", q="rt-9999")["events"]]
        assert f"INS-{ins}" in [x["id"] for x in get("admin", "events", dir="out")["events"]]
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM sync_run WHERE id IN (:a, :b)"), {"a": ok, "b": bad})
            c.execute(text("DELETE FROM instruction WHERE id = :i"), {"i": ins})


def test_events_leave_out_syncs_that_carried_nothing():
    """A scheduled sync that read nothing and failed nothing carried no message: it is not in the stream (the Monitor
    still counts it)."""
    with engine.begin() as c:
        rid = c.execute(
            text(
                "INSERT INTO sync_run (source_id, trigger, status, started_at, finished_at) "
                "VALUES ('erp', 'schedule', 'ok', now(), now()) RETURNING id"
            )
        ).scalar_one()
    try:
        assert f"SYNC-{rid}" not in {e["id"] for e in get("admin", "events")["events"]}
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM sync_run WHERE id = :i"), {"i": rid})


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_conflicts(acct):
    got = get(acct, "conflicts", limit=5000)
    if got is None:
        return
    rows = got["conflicts"]
    n_open = db("SELECT count(*) FROM conflict WHERE status IN ('open', 'escalated')")[0][0]
    assert got["total"] == len(rows) == n_open == got["counts"]["open"]
    names = {s["id"]: s["name"] for s in G["sources"]}
    for c in rows:
        assert re.fullmatch(r"CF-\d+", c["id"]) and c["status"] == "open"
        assert c["authorityId"] and c["authority"] == names.get(c["authorityId"], c["authorityId"])  # names its authority
        assert c["a"]["src"] == c["authority"]
        vals = {v["source"]: v["val"] for v in c["values"]}
        assert c["authorityId"] in vals and c["a"]["val"] == vals[c["authorityId"]] and len(vals) >= 2
        assert c["b"]["src"] != c["a"]["src"]
    assert [int(c["id"][3:]) for c in rows] == sorted((int(c["id"][3:]) for c in rows), reverse=True)
    few = get(acct, "conflicts", limit=3, source="wms")
    assert len(few["conflicts"]) <= 3 and all("wms" in {v["source"] for v in c["values"]} for c in few["conflicts"])
    closed = get(acct, "conflicts", status="resolved")
    assert all(c["status"] == "resolved" for c in closed["conflicts"])


def test_conflicts_bad_status_is_a_validation_error():
    r = client.get("/api/screens/integration/conflicts", params={"status": "bogus"}, headers=h("admin"))
    assert r.status_code == 422
    assert client.get("/api/screens/integration/conflicts", params={"status": "all"}, headers=h("admin")).status_code == 200


# ---------------------------------------------------------------- monitor
@pytest.mark.parametrize("acct", ACCOUNTS)
def test_monitor(acct):
    got = get(acct, "monitor")
    if got is None:
        return
    assert sorted(x["id"] for x in got["sources"]) == sorted(DB_SOURCES)
    for x in got["sources"]:
        assert x["in_sla"] == (x["freshMin"] is not None and x["freshMin"] <= x["sla"])
        assert x["failed7"] >= 0 and (x["success"] is None or 0 <= x["success"] <= 100)
    k = got["kpis"]
    conn = [x for x in got["sources"] if x["status"] != "unavailable"]
    assert k["connected"] == len(conn) and k["in_sla"] == sum(1 for x in conn if x["in_sla"])
    wf = golden.load("screens/workflows")["starting"]
    assert [w["id"] for w in got["workflows"]] == [w["id"] for w in wf if w.get("runsN")]
    assert k["failing_workflows"] == sum(
        1 for w in wf if w["status"] == "published" and w.get("last") and w["last"]["state"] == "failed"
    )
    assert len(got["hourly"]) == 24
    for w in got["workflows"]:  # no real run in the window: the demo's stats, as the demo shows them
        if not w["real"]:
            assert (w["runs24"], w["ok24"], w["p95"], w["steps"]) == (w["runsN"], w["okN"], None, [])
            assert w["avg"] == (w["last"] or {}).get("dur")


# ---------------------------------------------------------------- monitor: per workflow and per step, from real runs
MON_WF = "WF-133"  # a decision workflow: quick runs, no source to read
MON_KEYS = [f"RUN-MONT{k}" for k in range(21)]


def _forget_monitor_seed() -> None:
    with engine.begin() as c:
        c.execute(text("DELETE FROM failed_record WHERE run_id LIKE 'RUN-MONT%'"))
        c.execute(text("DELETE FROM state_item WHERE collection = 'workflow_run_stats' AND id LIKE 'RUN-MONT%'"))


@pytest.fixture
def monitor_seed():
    """20 real runs of MON_WF in the last 24 hours (durations 1..20 s, runs 0, 5 and 10 failed; steps `a` 0.1..2.0 s and
    `b` 2..40 s) and one 25 hours old, with held records: 2 `required` and 1 `format` at step b in the window, one
    reprocessed (not held), one in the old run and one of a sync with the same key (neither counted)."""
    from di.core import clock
    from di.core.db import SessionLocal
    from di.repositories.common import ms
    from di.repositories.workflows import record_run_stats

    _forget_monitor_seed()
    now = ms(clock.now().isoformat())
    with SessionLocal() as s:
        for k, key in enumerate(MON_KEYS):
            old = k == 20
            record_run_stats(
                s, key, MON_WF, now - (25 * 3_600_000 if old else (20 - k) * 60_000), 99.0 if old else float(k + 1),
                "failed" if k in (0, 5, 10) or old else "success" if k % 2 else "warning",
                {"a": 50.0 if old else round((k + 1) / 10, 2), "b": 500.0 if old else float(2 * (k + 1))},
                {"a": "Read", "b": "Validate"},
            )  # fmt: skip
        s.commit()
    rows = [
        ("workflow", "RUN-MONT1", "b", "required", "held"),
        ("workflow", "RUN-MONT1", "b", "required", "held"),
        ("workflow", "RUN-MONT2", "b", "format", "held"),
        ("workflow", "RUN-MONT2", "b", "format", "reprocessed"),
        ("workflow", "RUN-MONT20", "b", "required", "held"),
        ("sync", "RUN-MONT3", "b", "required", "held"),
    ]
    with engine.begin() as c:
        for kind, rid, step, rule, st in rows:
            c.execute(
                text(
                    "INSERT INTO failed_record (run_kind, run_id, step, rule, reason, status) "
                    "VALUES (:k, :r, :s, :u, 'seeded by the monitor test', :st)"
                ),
                {"k": kind, "r": rid, "s": step, "u": rule, "st": st},
            )
    yield
    _forget_monitor_seed()


def test_monitor_per_workflow_and_step_from_real_runs(monitor_seed):
    got = get("admin", "monitor")
    w = next(x for x in got["workflows"] if x["id"] == MON_WF)
    assert w["real"] is True
    assert (w["runs24"], w["ok24"], w["success"]) == (20, 17, 85)  # the old run is outside the window
    assert w["p95"] == 19.0  # nearest rank: the 19th of 20 durations
    assert w["avg"] == 10.5
    assert w["lastState"] == "success"  # the newest run in the window (k = 19)
    a, b = w["steps"]
    assert (a["id"], a["label"], a["p95"], a["held"], a["heldN"]) == ("a", "Read", 1.9, {}, 0)
    assert (b["id"], b["label"], b["p95"], b["held"], b["heldN"]) == ("b", "Validate", 38.0, {"required": 2, "format": 1}, 3)
    # the per-workflow and per-source sections are unchanged: the demo's workflows are all still listed
    wf = golden.load("screens/workflows")["starting"]
    assert [x["id"] for x in got["workflows"]] == [x["id"] for x in wf if x.get("runsN")]


def test_monitor_counts_a_real_run(monkeypatch):
    """A run through the run job writes the stats the Monitor reads: its duration, state and per-step durations."""
    from di.core import state
    from di.services.actions import workflows as wf
    from tests.helpers import call

    for k in ("STEP_SECONDS", "QUICK_SECONDS", "BACKOFF_SECONDS"):
        monkeypatch.setattr(wf, k, 0)
    try:
        r = call("workflow.run", {"id": MON_WF}, "developer")
        assert r["ok"], r
        key = r["output"]["run"]
        with engine.begin() as c:  # the test runs the job itself (as test_workflow_engine does)
            payload = c.execute(
                text("UPDATE job SET status = 'done' WHERE kind = 'workflow.run' AND payload->>'run' = :r RETURNING payload"),
                {"r": key},
            ).scalar_one()
        out = wf.run_job(payload)
        assert out["state"] in ("success", "warning"), out
        w = next(x for x in get("admin", "monitor")["workflows"] if x["id"] == MON_WF)
        assert w["real"] is True and w["runs24"] == 1 and w["ok24"] == 1 and w["success"] == 100
        assert w["lastState"] == out["state"] and w["p95"] is not None and w["p95"] >= 0
        assert w["steps"] and all(st["p95"] is not None and st["label"] for st in w["steps"])
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM job WHERE kind = 'workflow.run'"))
        state.reset(["workflows", "workflow_runs", "workflow_run_stats", "notes"])


def test_every_account_and_endpoint_covered():
    assert len(ACCOUNTS) == 11
    for path in NEEDS:
        seen = [a for a in ACCOUNTS if allowed(a, path)]
        assert 0 < len(seen) < len(ACCOUNTS), path
