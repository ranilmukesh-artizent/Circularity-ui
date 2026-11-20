"""Connection Fabric (#/integration): sources, catalogue, source map, tables, canonical models, event stream, conflicts
and monitor (B14).

    GET /api/screens/integration/sources?cat=&status=&method=&q=   every source (with its health), status counts
    GET /api/screens/integration/sources/{id}?days=30             one source: health, runs, sync history, daily
                                                                  records, mappings, models, table model, comments
    GET /api/screens/integration/overview                         the catalogue: integrations, recommendations,
                                                                  available systems, categories
    GET /api/screens/integration/map?limit=                       source map tiles, exceptions, sync activity,
                                                                  dependencies, health by hour, and the mappings,
                                                                  source models and table models the map draws
    GET /api/screens/integration/tables?source=                   table models, with their counts
    GET /api/screens/integration/models                           canonical models (with synced record counts),
                                                                  examples, field mappings per source
    GET /api/screens/integration/events?dir=&issues=&q=&limit=    the event stream, with its counts
    GET /api/screens/integration/conflicts?status=&source=&limit= the conflict queue, with its counts
    GET /api/screens/integration/monitor                          health over 24 hours, per source, per workflow

Access: each endpoint needs a section of the Connection Fabric (sources and overview: overview or map; map; tables;
models; events; conflicts; monitor), as policy.json gives them (Admin and Developer all; Engineer map, tables,
models, overview, monitor; Finance map, overview, monitor; Approver events, conflicts). Others get 403 `out_of_scope`.

Real backend data and demo reference. The demo simulated the Connection Fabric; the backend syncs it. A source here is
the demo's record (fixtures/golden/sources.json) overlaid with what the backend knows. Real backend data:
- table source_system: status, vendor, type, interval, owner, note, compl (completeness), conf (confidence),
  updatedAt; lastSync (the last successful sync), freshMin and fresh (minutes since then, on the workspace clock,
  never negative);
- table raw_record: records (records landed from the source);
- table sync_run: runs (latest 20), sync history (latest 12), success rate, failed records, daily records (series),
  the hourly health and the sync activity;
- table fetch_log: latency (mean HTTP call time);
- table conflict: the conflicts, all of them (model, key, field, every source's value, the authority);
- table canonical: record counts per canonical model;
- di.connectors.registry: connector (a connector adapter exists for the source).
Still the demo's reference:
- sources.json: name, short, cat, ver, env, url, mode, auth, rw, inputs, read, write, step, authority (field labels),
  method, cfg, cfgVer, credAt, credDays, audit, and the source types;
- canonical.json and screens/integration.json: field mappings (MAPPINGS), canonical models (CANON) and their examples,
  the catalogue (CATALOG; an entry is connected when a source with its id exists), categories;
- workspace collection "table_models": the table models (TBL_MODELS, laid out by tgLayout), seeded from the demo
  (tables.update has no handler yet);
- workspace collection "events": the event stream (the demo's EVENTS and what actions add);
- workspace collection "workflows" (di.screens.workflows): the workflows reading a source, failing ingest workflows.

Texts the demo computes (recommendations, exceptions, activity lines) are built the demo's way from these values.
Where the backend has no value the demo invented one: a conflict's `impact` names what the backend does (dependent
routes are held), `since` is its age; hourly health buckets are the sync runs of the 24 hours up to now (or up to the
newest run, when the clock is behind the synced data, as the test suite's pinned clock is); a source with no finished
run has `success` null; one with no HTTP calls has `latency` null.

Facade (apps/web/src/api/integration.ts) → here, export by export:

- endpoint GET /sources: sources, source, needsAttention, srcFailing, credDays, successRate, latency, slaMinutes,
  tableCount, fieldCount, wfUsing, srcChannels, catOf (each in `health`), connected (status not unavailable)
- endpoint GET /sources/{id}: syncHistory (`sync_history`), series, failedRecords (`failed`, and `health.failed7`),
  srcModels (`models`), tableModel for one source (`table_model`), commentsOf('src:<id>') (`comments`)
- endpoint GET /overview: integrations, recommendations, available, catalog
- endpoint GET /map: exceptions, smLog (`activity`), totals and hourly, and for accounts without Tables or Models
  mappings, allMappings, srcModels (`source_models`), tableModel and tableModelIds (`table_models`)
- endpoint GET /tables: tableModel, tableModelIds
- endpoint GET /models: canon, canonExample (`examples`), canonPrefix (`prefix`), mappings, allMappings
- endpoint GET /events: events
- endpoint GET /conflicts: conflicts
- endpoint GET /monitor: totals, hourly, workflows and wfStat (`workflows`; the full list is GET /api/screens/workflows)
- another area: openDecisionCount (the open decisions, from the cases)
- reference: connMethods, srcTypes, srcCats, srcCatNote, authOpts, frCats, frDecisions, intSub, intKids, sampleCsv,
  facilities, tenantList, tableSuggestions, frSample, frAuthOptions, typeOf
- frontend-only (formatting, the ticking age, view helpers): srcAgeText, srcFresh, srcAge, methodMode, cfgDefaults,
  buildUrl, hashId, vHue, ackKind, pct, isoTime, tableHeight, vlogoHtml, stepHtml, jsonHtml, nowLabel, caseExists,
  rbPath; and moveTable, alignTables (the table layout on the canvas)
- actions (POST /api/actions/...): syncSource, reconnectSource, rotateCredentials, deleteSource, saveSource,
  resolveConflict, escalateConflict, commitImport, updateTables, addComment, undoActions, syncAllLive
- browser-only flows in the demo, need actions before B17: togglePause, disconnectSource, reauthenticated,
  recordTest, finishConnect
"""

import json
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import clock, golden, policy, state
from di.actions.decisions import comments
from di.auth import Principal, principal
from di.connectors.registry import ADAPTERS
from di.db import get_session
from di.engine.jsmath import js_round
from di.reads.common import STARTING_MAPPINGS, ms
from di.screens.mcp import case_openable
from di.screens.workflows import all_workflows, wf_stat, wf_using

router = APIRouter(prefix="/api/screens/integration", tags=["screens: integration"])

_SRC = golden.load("sources")
REF_SOURCES: list[dict] = _SRC["sources"]  # the demo's SOURCES, in its order
REF_BY_ID = {s["id"]: s for s in REF_SOURCES}

# The connectors know two states the screens do not: `failing` (the system did not answer) and `auth_expired` (its
# credentials were refused, like the demo's expired Ritchie Bros. token). The screens show both as `stale`, as the
# demo does: the data is there but not current. `connectorStatus` keeps the connector's own word.
SCREEN_STATUS = {"failing": "stale", "auth_expired": "stale"}
SRC_TYPES: dict[str, dict] = _SRC["types"]
CANON: list[dict] = golden.load("canonical")["models"]
MAPPINGS: dict[str, list] = STARTING_MAPPINGS
_REF = golden.load("screens/integration")
CATALOG: list[dict] = _REF["catalog"]
CANON_EX: dict = _REF["canon_examples"]
CANON_PFX: dict[str, str] = _REF["canon_pfx"]
MAP_TARGET: dict[str, str] = _REF["map_target"]
FR_CATOF: dict[str, str] = _REF["fr_catof"]
FR_CATS: list[str] = _REF["fr_cats"]
FR_XTYPES: dict[str, dict] = _REF["fr_xtypes"]
state.register("table_models", lambda: [(k, m | {"source": k}) for k, m in _REF["table_models"].items()])

DAY = 86_400_000
HOUR = 3_600_000
SECTIONS_SOURCES = ("overview", "map")


def _require_any(p: Principal, *sections: str) -> None:
    if not any(policy.can_page(p.account, "integration", s) for s in sections):
        p.require_page("integration", sections[0])


# ---------------------------------------------------------------- small ports of the demo
def src_age(m: float) -> str:
    """srcAge: "just now", "4 min", "19 h", "3 days"."""
    if m < 1:
        return "just now"
    if m < 60:
        return f"{js_round(m)} min"
    if m < 2880:
        return f"{js_round(m / 60)} h"
    return f"{js_round(m / 1440)} days"


def type_of(t: str) -> dict:
    """frTypeOf."""
    return SRC_TYPES.get(t) or FR_XTYPES.get(t) or {"label": t, "short": t, "cat": "internal", "target": "Asset & component"}


def cat_of(s: dict) -> str:
    """frCatOf."""
    return FR_CATOF.get(s["type"], "Custom")


def channels(s: dict) -> list[str]:
    """srcCh: api, event and file, from the source's mode and auth."""
    m = f"{s.get('mode', '')} {s.get('auth', '')}".lower()
    out = []
    if re.search("api|poll", m):
        out.append("api")
    if re.search("event|webhook", m):
        out.append("event")
    if re.search("csv|sftp", m):
        out.append("file")
    return out


def sla_minutes(s: dict) -> int:
    """frSla: twice the polling interval, 15 min for events, two days for a manual import, else an hour."""
    if s.get("interval"):
        return s["interval"] * 2
    if re.search("event|webhook", s.get("mode") or "", re.I):
        return 15
    return 2880 if s["status"] == "manual" else 60


def cred_days(s: dict, now: int) -> int | None:
    """frCredDays: days until the credential expires."""
    if not s.get("credAt"):
        return None
    return js_round((s["credAt"] + s["credDays"] * DAY - now) / DAY)


def src_models(s: dict) -> dict[str, list]:
    """frSrcModels: the canonical models a source reaches (its mapped fields' prefixes, or its target model)."""
    pre = {v: k for k, v in CANON_PFX.items()}
    o: dict[str, list] = {}
    for r in MAPPINGS.get(s["id"], []):
        m = pre.get(str(r[2]).split(".")[0])
        if m:
            o.setdefault(m, []).append(r)
    t = MAP_TARGET.get(s["id"]) or type_of(s["type"]).get("target")
    if t and t not in o:
        o[t] = []
    return o


# ---------------------------------------------------------------- the backend's data
def _now() -> int:
    return ms(clock.now().isoformat())


def _ts(v: datetime | None) -> int | None:
    return ms(v.astimezone(UTC).isoformat()) if v else None


def _run_view(r) -> dict:
    """A sync run in the demo's SyncRun shape."""
    dur = round((r["finished_at"] - r["started_at"]).total_seconds(), 1) if r["finished_at"] else None
    result = {"ok": "success"}.get(r["status"], r["status"])
    return {
        "id": f"SYNC-{r['id']}",
        "ts": _ts(r["started_at"]),
        "trigger": r["trigger"].capitalize(),
        "rows": r["records_read"],
        "facts": r["facts_written"],
        "failed": r["records_failed"],
        "dur": dur,
        "result": result,
        "note": r["error"] or "",
    }


class Fabric:
    """Everything the Connection Fabric screens read, loaded once per request."""

    def __init__(self, s: Session, p: Principal):
        self.s, self.p = s, p
        self.now = _now()
        rows = s.execute(
            text(
                "SELECT s.*, (SELECT count(*) FROM raw_record r WHERE r.source_id = s.id) AS records, "
                "(SELECT count(*) FROM conflict c WHERE c.status <> 'resolved' AND c.authority = s.id) AS open_conflicts "
                "FROM source_system s ORDER BY s.id"
            )
        ).mappings()
        self.rows = {r["id"]: r for r in rows}
        runs = s.execute(
            text(
                "SELECT * FROM (SELECT r.*, row_number() OVER (PARTITION BY source_id ORDER BY id DESC) AS n "
                "FROM sync_run r) x WHERE n <= 20 ORDER BY id DESC"
            )
        ).mappings()
        self.runs: dict[str, list] = {}
        for r in runs:
            self.runs.setdefault(r["source_id"], []).append(r)
        newest = s.execute(text("SELECT max(started_at) FROM sync_run")).scalar()
        # the end of every window: now, or the newest run when the clock is behind the synced data (pinned test clock)
        self.ref = max(self.now, _ts(newest) or 0)
        since7 = datetime.fromtimestamp((self.ref - 7 * DAY) / 1000, UTC)
        self.agg = {
            r["source_id"]: r
            for r in s.execute(
                text(
                    "SELECT source_id, count(*) FILTER (WHERE finished_at IS NOT NULL) AS fin, "
                    "count(*) FILTER (WHERE status = 'ok') AS ok, "
                    "coalesce(sum(records_failed) FILTER (WHERE started_at >= :s), 0) AS failed7, "
                    "count(*) FILTER (WHERE status = 'running') AS running FROM sync_run GROUP BY source_id"
                ),
                {"s": since7},
            ).mappings()
        }
        self.latency = {
            r[0]: js_round(float(r[1]))
            for r in s.execute(text("SELECT source_id, avg(duration_ms) FROM fetch_log WHERE duration_ms IS NOT NULL GROUP BY 1"))
        }
        self.workflows = all_workflows(s)
        self.tables = dict((k, m) for k, m in _table_models(s))
        ids = [x["id"] for x in REF_SOURCES if x["id"] in self.rows] + sorted(i for i in self.rows if i not in REF_BY_ID)
        self.sources = [self._source(i) for i in ids]
        self.by_id = {x["id"]: x for x in self.sources}

    # ---- a source in the facade's Source shape
    def _source(self, sid: str) -> dict:
        row = self.rows[sid]
        ref = REF_BY_ID.get(sid)
        t = type_of(row["type"])
        base = dict(ref) if ref else {
            "id": sid, "cat": t.get("cat", "internal"), "name": t["label"], "short": t["short"], "ver": "", "env": "Production",
            "url": "", "mode": "", "auth": "", "rw": "Read", "inputs": "", "read": [], "write": [], "step": [], "authority": [],
            "cfgVer": "1.0", "method": "api", "cfg": {}, "credAt": None, "credDays": None, "audit": [],
        }  # fmt: skip
        last = _ts(row["last_success_at"])
        fm = max(0, js_round((self.now - last) / 60000)) if last is not None else None
        base.update(
            vendor=row["vendor"],
            type=row["type"],
            status=SCREEN_STATUS.get(row["status"], row["status"]),
            connectorStatus=row["status"],
            interval=row["interval_min"],
            owner=row["owner"] or base.get("owner", ""),
            compl=float(row["completeness"]) if row["completeness"] is not None else 0,
            conf=float(row["confidence"]) if row["confidence"] is not None else 0,
            lastSync=last,
            freshMin=fm,
            fresh=src_age(fm) if fm is not None else "—",
            records=row["records"],
            runs=[_run_view(r) for r in self.runs.get(sid, [])],
            updatedAt=_ts(row["updated_at"]),
            connector=sid in ADAPTERS,
            openConflicts=row["open_conflicts"],
        )
        base.pop("note", None)
        if row["note"]:
            base["note"] = row["note"]
        for k in ("c0", "k0", "updatedBy"):  # the demo's starting copies of completeness and confidence
            base.pop(k, None)
        return base

    # ---- derived per source
    def failing(self, s: dict) -> bool:
        """frSrcFailing: its ingest workflow is failing."""
        return any(w.get("src") == s["id"] and w["cat"] == "Ingest" and wf_stat(w) == "failing" for w in self.workflows)

    def needs_attention(self, s: dict) -> bool:
        """frNeedsAttn: stale, unavailable, failing, or a live source whose credential expires within 14 days."""
        cd = cred_days(s, self.now)
        return (
            s["status"] in ("stale", "unavailable") or self.failing(s) or (s["status"] == "live" and cd is not None and cd <= 14)
        )

    def success(self, sid: str) -> float | None:
        a = self.agg.get(sid)
        return round(100 * a["ok"] / a["fin"], 1) if a and a["fin"] else None

    def table_count(self, sid: str) -> int:
        m = self.tables.get(sid)
        return len(m["t"]) if m else 0

    def field_count(self, sid: str) -> int:
        """frFldN: columns across the source's tables, or its mapped fields when it has no table model."""
        m = self.tables.get(sid)
        return sum(len(t["cols"]) for t in m["t"]) if m else len(MAPPINGS.get(sid, []))

    def health(self, s: dict) -> dict:
        sla = sla_minutes(s)
        return {
            "needs_attention": self.needs_attention(s),
            "failing": self.failing(s),
            "cred_days": cred_days(s, self.now),
            "success": self.success(s["id"]),
            "failed7": int((self.agg.get(s["id"]) or {}).get("failed7") or 0),
            "latency": self.latency.get(s["id"]),
            "sla": sla,
            "in_sla": s["freshMin"] is not None and s["freshMin"] <= sla,
            "tables": self.table_count(s["id"]),
            "fields": self.field_count(s["id"]),
            "mapped": len(MAPPINGS.get(s["id"], [])),
            "workflows": wf_using(self.workflows, s["id"]),
            "channels": channels(s),
            "category": cat_of(s),
            "comments": len(comments(self.s, "src:" + s["id"])),
        }

    def series(self, sid: str, days: int) -> list[int]:
        """Records read per day over the last `days` days (oldest first), from the source's sync runs."""
        end = self.ref // DAY
        rows = self.s.execute(
            text(
                "SELECT floor(extract(epoch FROM started_at) * 1000 / :d)::bigint AS day, sum(records_read) "
                "FROM sync_run WHERE source_id = :i GROUP BY 1"
            ),
            {"i": sid, "d": DAY},
        ).all()
        by_day = {int(d): int(n or 0) for d, n in rows}
        return [by_day.get(end - days + 1 + k, 0) for k in range(days)]

    def failed_in(self, sid: str, days: int) -> int:
        since = datetime.fromtimestamp((self.ref - days * DAY) / 1000, UTC)
        q = text("SELECT coalesce(sum(records_failed), 0) FROM sync_run WHERE source_id = :i AND started_at >= :s")
        return int(self.s.execute(q, {"i": sid, "s": since}).scalar())

    # ---- across sources
    def hourly(self) -> list[dict]:
        """Sync runs per hour over the 24 hours up to `ref`: successful, with failed records (warn), failed."""
        start = (self.ref // HOUR - 23) * HOUR
        b = [{"ts": start + i * HOUR, "ok": 0, "warn": 0, "bad": 0} for i in range(24)]
        rows = self.s.execute(
            text("SELECT started_at, status, records_failed FROM sync_run WHERE started_at >= :s"),
            {"s": datetime.fromtimestamp(start / 1000, UTC)},
        ).mappings()
        for r in rows:
            i = (_ts(r["started_at"]) - start) // HOUR
            if 0 <= i < 24 and r["status"] != "running":
                k = "bad" if r["status"] != "ok" else "warn" if r["records_failed"] else "ok"
                b[i][k] += 1
        return b

    def totals(self, hourly: list[dict]) -> dict:
        """hhTotals: the 24 hours' runs, what is running now (syncs and workflows), the success share."""
        t = {k: sum(x[k] for x in hourly) for k in ("ok", "warn", "bad")}
        t["run"] = sum(int(a["running"]) for a in self.agg.values()) + sum(1 for w in self.workflows if w.get("running"))
        n = t["ok"] + t["warn"] + t["bad"]
        t["pct"] = t["ok"] / n * 100 if n else 100
        return t

    def conflicts(self, status: str = "open", source: str | None = None, limit: int | None = None) -> tuple[list[dict], int]:
        where = {"open": "status IN ('open', 'escalated')", "resolved": "status = 'resolved'", "all": "true"}[status]
        args = {"src": source}
        cond = f'{where} AND (CAST(:src AS text) IS NULL OR authority = :src OR "values" ? :src)'
        total = self.s.execute(text(f"SELECT count(*) FROM conflict WHERE {cond}"), args).scalar()
        q = f"SELECT * FROM conflict WHERE {cond} ORDER BY id DESC" + (" LIMIT :n" if limit else "")
        rows = self.s.execute(text(q), args | ({"n": limit} if limit else {})).mappings()
        return [self._conflict(r) for r in rows], total

    def _name(self, sid: str) -> str:
        s = self.by_id.get(sid) or REF_BY_ID.get(sid)
        return s["name"] if s else sid

    def _conflict(self, r) -> dict:
        """A conflict in the facade's Conflict shape: `a` is the authority's value, `b` the first other source's."""
        vals: dict = r["values"] or {}
        auth = r["authority"]
        others = sorted(k for k in vals if k != auth)
        b = others[0] if others else auth

        def val(v):
            return v if isinstance(v, str) else json.dumps(v)

        age = max(0, (self.ref - _ts(r["opened_at"])) / 60000)
        out = {
            "id": f"CF-{r['id']}",
            "kind": r["field"].replace("_", " ").capitalize(),
            "asset": r["key"],
            "a": {"src": self._name(auth), "val": val(vals.get(auth))},
            "b": {"src": self._name(b), "val": val(vals.get(b))},
            "authority": self._name(auth),
            "authorityId": auth,
            "model": r["model"],
            "field": r["field"],
            "values": [{"source": k, "src": self._name(k), "val": val(v)} for k, v in sorted(vals.items())],
            "impact": f"Routes that use {r['model']}.{r['field']} for {r['key']} are held until it is resolved",
            "status": "resolved" if r["status"] == "resolved" else "open",
            "since": src_age(age),
            "openedAt": _ts(r["opened_at"]),
        }
        if r["status"] == "escalated":
            out["escalated"] = {"by": r["closed_by"], "at": datetime.isoformat(r["closed_at"]) if r["closed_at"] else None}
        if r["status"] == "resolved":
            out["resolved"] = {"by": r["closed_by"], "at": datetime.isoformat(r["closed_at"]) if r["closed_at"] else None}
        return out

    def exceptions(self) -> list[dict]:
        """smExceptions: unconnected, expired and unmapped sources, manual imports, then every open conflict."""
        o = []
        for s in self.sources:
            if s["status"] == "unavailable":
                o.append({"src": s["name"], "obj": s["vendor"], "issue": "Not connected: no feed", "sev": "High", "st": "Open"})
            elif s["status"] == "stale":
                o.append({"src": s["name"], "obj": s["vendor"], "issue": "Feed token expired", "sev": "High", "st": "Open"})
            if s["status"] != "unavailable" and not MAPPINGS.get(s["id"]):
                o.append({"src": s["name"], "obj": s["vendor"], "issue": "No field mapping defined", "sev": "High", "st": "Open"})
            elif s["status"] == "manual":
                issue = "Manual import only, no live feed"
                o.append({"src": s["name"], "obj": s["vendor"], "issue": issue, "sev": "Low", "st": "In Progress"})
        for c in self.conflicts("open")[0]:
            o.append(
                {
                    "src": c["a"]["src"],
                    "obj": c["asset"],
                    "issue": f"{c['kind']} differs from {c['b']['src']}",
                    "sev": "Medium",
                    "st": "Open",
                }
            )
        return o


def _table_models(s: Session) -> list[tuple[str, dict]]:
    """The table models (the demo's tgModel for every source in TBL_MODELS), keyed by source."""
    return [(m["source"], {k: v for k, v in m.items() if k != "source"}) for m in state.items(s, "table_models")]


def _catalog(f: Fabric) -> list[dict]:
    """CATALOG, each marked connected when a source with its id exists."""
    return [c | {"connected": c["id"] in f.by_id} for c in CATALOG]


def _integration_status(f: Fabric, s: dict) -> str:
    if s["status"] == "disconnected":
        return "disconnected"
    if s["status"] == "paused":
        return "paused"
    if f.needs_attention(s):
        return "unavailable" if s["status"] == "unavailable" else "attention"
    return "manual" if s["status"] == "manual" else "connected"


def _recommendations(f: Fabric, available: list[dict]) -> list[dict]:
    """frRecs: stale feeds, failing ingest workflows, unconnected sources, then catalogue systems worth connecting."""
    r = []
    for s in f.sources:
        if s["status"] == "stale":
            r.append({
                "source": s["id"], "catalog": None, "v": s["vendor"], "t": s["name"],
                "line": s["name"] + " feed is stale. " + (s.get("note") or "Pricing falls back to the last fresh data."),
                "why": f"{s['vendor']} has not delivered fresh data for {s['fresh']}. Every prediction that uses "
                f"{s['name'].lower()} says it fell back to older data until the feed is refreshed.",
                "btn": "Manage", "act": "frOpenSrc", "arg": s["id"], "st": "attention",
            })  # fmt: skip
    for s in f.sources:
        if f.failing(s):
            w = next(x for x in f.workflows if x.get("src") == s["id"] and wf_stat(x) == "failing")
            r.append({
                "source": s["id"], "catalog": None, "v": s["vendor"], "t": s["name"],
                "line": f"{w['name']} is failing: {w['last'].get('note') or 'last run failed'}.",
                "why": f"The ingest workflow for {s['vendor']} failed its last run, so {type_of(s['type'])['target']} evidence "
                "from it is not current.",
                "btn": "Investigate", "act": "frInvestigate", "arg": w["id"], "st": "failing",
            })  # fmt: skip
    for s in f.sources:
        if s["status"] == "unavailable":
            note = s.get("note") or ""
            r.append({
                "source": s["id"], "catalog": None, "v": s["vendor"], "t": s["name"],
                "line": f"{s['vendor']} is not connected yet. {note}",
                "why": (note or s["vendor"] + " is not connected.")
                + " Connecting it replaces estimated factors with measured data.",
                "btn": "Connect", "act": "frOpenSrc", "arg": s["id"], "st": "unavailable",
            })  # fmt: skip
    for c in available:
        if c.get("why"):
            r.append({
                "source": None, "catalog": c["id"], "v": c["vendor"], "t": type_of(c["type"])["label"], "line": c["desc"],
                "why": c["why"], "btn": "Connect", "act": "frConnectStart", "arg": c["id"], "st": "available",
            })  # fmt: skip
    return r[:4]


def _source_filter(s: dict, f: Fabric, cat: str | None, status: str | None, method: str | None, q: str | None) -> bool:
    """smFilter and frSmList: category (the source's or the catalogue's), status (or attention), method, search."""
    if cat and cat not in (s["cat"], cat_of(s)):
        return False
    if status and (not f.needs_attention(s) if status == "attention" else s["status"] != status):
        return False
    if method and s.get("method") != method:
        return False
    if q:
        hay = " ".join(str(s.get(k) or "") for k in ("name", "vendor", "owner", "mode", "id")).lower()
        return q.strip().lower() in hay
    return True


def _status_counts(f: Fabric) -> dict:
    c = {"total": len(f.sources)}
    for s in f.sources:
        c[s["status"]] = c.get(s["status"], 0) + 1
    return c


# ---------------------------------------------------------------- endpoints
@router.get("/sources")
def sources(
    cat: str | None = None,
    status: str | None = None,
    method: str | None = None,
    q: str | None = None,
    p: Principal = Depends(principal),
    session: Session = Depends(get_session),
):
    _require_any(p, *SECTIONS_SOURCES, "tables", "models", "monitor")
    f = Fabric(session, p)
    rows = [s | {"health": f.health(s)} for s in f.sources if _source_filter(s, f, cat, status, method, q)]
    return {"sources": rows, "counts": _status_counts(f)}


@router.get("/sources/{source_id}")
def source_detail(
    source_id: str,
    days: int = Query(30, ge=1, le=180),
    p: Principal = Depends(principal),
    session: Session = Depends(get_session),
):
    _require_any(p, *SECTIONS_SOURCES, "tables", "models", "monitor")
    f = Fabric(session, p)
    s = f.by_id.get(source_id)
    if s is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No source {source_id}."})
    return {
        "source": s | {"health": f.health(s)},
        "sync_history": [
            {"ts": r["ts"], "ok": r["result"] == "success", "rows": r["rows"],
             "dur": f"{r['dur']} s" if r["dur"] is not None else "—"}
            for r in s["runs"][:12]
        ],
        "series": f.series(source_id, days),
        "failed": f.failed_in(source_id, days),
        "mappings": MAPPINGS.get(source_id, []),
        "models": src_models(s),
        "table_model": f.tables.get(source_id),
        "comments": comments(session, "src:" + source_id),
    }  # fmt: skip


@router.get("/overview")
def overview(p: Principal = Depends(principal), session: Session = Depends(get_session)):
    _require_any(p, "overview")
    f = Fabric(session, p)
    catalog = _catalog(f)
    available = [c for c in catalog if not c["connected"]]
    integrations = [
        {"id": s["id"], "src": s["id"], "catalog": None, "vendor": s["vendor"], "name": s["name"], "cat": cat_of(s),
         "type": s["name"], "status": _integration_status(f, s), "last": s["lastSync"], "owner": s["owner"]}
        for s in f.sources
    ] + [
        {"id": "cat:" + c["id"], "src": None, "catalog": c["id"], "vendor": c["vendor"], "name": type_of(c["type"])["label"],
         "cat": FR_CATOF.get(c["type"]), "type": type_of(c["type"])["label"], "status": "available", "last": None, "owner": "—"}
        for c in available
    ]  # fmt: skip
    return {
        "integrations": integrations,
        "recommendations": _recommendations(f, available),
        "catalog": catalog,
        "available": [c["id"] for c in available],
        "connected": [s["id"] for s in f.sources if s["status"] != "unavailable"],
        "attention": [s["id"] for s in f.sources if f.needs_attention(s)],
        "categories": [[c, n] for c in FR_CATS if (n := sum(1 for x in integrations if x["cat"] == c))],
    }


@router.get("/map")
def source_map(
    limit: int = Query(100, ge=1, le=2000), p: Principal = Depends(principal), session: Session = Depends(get_session)
):
    _require_any(p, "map")
    f = Fabric(session, p)
    hh = f.hourly()
    t = f.totals(hh)
    ex = f.exceptions()
    runs = session.execute(text("SELECT * FROM sync_run WHERE status <> 'running' ORDER BY id DESC LIMIT 6")).mappings()
    activity = [
        {"ts": _ts(r["finished_at"] or r["started_at"]), "id": r["source_id"], "kind": "ok" if r["status"] == "ok" else "warn",
         "text": f"Sync completed · {r['records_read']:,} records" if r["status"] == "ok"
         else f"Sync failed · {r['error'] or r['status']}"}
        for r in runs
    ]  # fmt: skip
    return {
        "kpis": {
            "connected": sum(1 for s in f.sources if s["status"] != "unavailable"),
            "tables": sum(f.table_count(s["id"]) for s in f.sources),
            "fields": sum(len(v) for v in MAPPINGS.values()),
            "workflows_published": sum(1 for w in f.workflows if w["status"] == "published"),
            "exceptions": len(ex),
            "health_pct": t["pct"],
        },
        "counts": _status_counts(f),
        "exceptions": ex[:limit],
        "activity": activity,
        "dependencies": [s["id"] for s in f.sources if s["status"] in ("unavailable", "stale", "manual")],
        "open_conflicts": f.conflicts("open", limit=1)[1],
        "hourly": hh,
        "totals": t,
        # what the map draws (tree, graph, matrix): accounts with the map but without Tables or Models read them here
        "mappings": {k: v for k, v in MAPPINGS.items() if k in f.by_id},
        "source_models": {s["id"]: src_models(s) for s in f.sources},
        "table_models": {k: m for k, m in f.tables.items() if k in f.by_id},
    }


@router.get("/tables")
def tables(source: str | None = None, p: Principal = Depends(principal), session: Session = Depends(get_session)):
    _require_any(p, "tables")
    f = Fabric(session, p)
    models = {k: m for k, m in f.tables.items() if k in f.by_id and (source is None or k == source)}
    if source is not None and source not in models:
        raise HTTPException(404, {"code": "not_found", "message": f"No table model for {source}."})
    return {
        "models": models,
        "counts": {
            "tables": sum(len(m["t"]) for k, m in f.tables.items() if k in f.by_id),
            "links": sum(len(m["fk"]) for k, m in f.tables.items() if k in f.by_id),
            "systems": sum(1 for k, m in f.tables.items() if k in f.by_id and m["t"]),
        },
    }


@router.get("/models")
def models(p: Principal = Depends(principal), session: Session = Depends(get_session)):
    _require_any(p, "models")
    f = Fabric(session, p)
    records = dict(session.execute(text("SELECT model, count(*) FROM canonical GROUP BY model")).all())
    return {
        "canon": [m | {"records": records.get(CANON_PFX.get(m["n"], ""), 0)} for m in CANON],
        "examples": CANON_EX,
        "prefix": CANON_PFX,
        "mappings": {k: v for k, v in MAPPINGS.items() if k in f.by_id},
        "source_models": {s["id"]: src_models(s) for s in f.sources},
        "counts": {
            "models": len(CANON),
            "fields": sum(len(m["fields"]) for m in CANON),
            "sources_mapped": sum(1 for s in f.sources if MAPPINGS.get(s["id"])),
            "records": sum(records.values()),
        },
    }


@router.get("/events")
def events(
    dir: str | None = Query(None, pattern="^(in|out)$"),
    issues: bool = False,
    q: str | None = None,
    limit: int | None = Query(None, ge=1, le=5000),
    p: Principal = Depends(principal),
    session: Session = Depends(get_session),
):
    _require_any(p, "events")
    ev = state.items(session, "events", newest_first=True)
    ok = case_openable(session, p, {e.get("caseId") for e in ev if e.get("caseId")})
    qq = (q or "").lower()

    def keep(e: dict) -> bool:
        hay = ((e.get("caseId") or "") + (e.get("decisionId") or "") + e["type"] + e["dest"]).lower()
        return (not dir or e["dir"] == dir) and (not issues or e["ack"] != "acknowledged") and (not qq or qq in hay)

    rows = [e | {"openable": ok.get(e.get("caseId") or "", False)} for e in ev if keep(e)]
    acks = [e.get("ack") or "" for e in ev]
    return {
        "events": rows[:limit] if limit else rows,
        "counts": {
            "total": len(ev),
            "inbound": sum(1 for e in ev if e["dir"] == "in"),
            "outbound": sum(1 for e in ev if e["dir"] != "in"),
            "errors": sum(1 for a in acks if re.search("error|fail|duplicate|escalat", a, re.I)),
            "acknowledged": sum(1 for a in acks if a == "acknowledged"),
            "duplicates": sum(1 for a in acks if "duplicate" in a),
            "retries": sum(1 for a in acks if "retry" in a),
            "late": sum(1 for a in acks if re.search("late|out of order", a)),
        },
    }


@router.get("/conflicts")
def conflicts(
    status: str = Query("open", pattern="^(open|resolved|all)$"),
    source: str | None = None,
    limit: int = Query(200, ge=1, le=5000),
    p: Principal = Depends(principal),
    session: Session = Depends(get_session),
):
    _require_any(p, "conflicts")
    f = Fabric(session, p)
    rows, total = f.conflicts(status, source, limit)
    n_open = f.conflicts("open", limit=1)[1]
    n_all = f.conflicts("all", limit=1)[1]
    systems = session.execute(text('SELECT count(DISTINCT k) FROM conflict, jsonb_object_keys(conflict."values") AS k')).scalar()
    return {"conflicts": rows, "total": total, "counts": {"open": n_open, "closed": n_all - n_open, "systems": systems}}


@router.get("/monitor")
def monitor(p: Principal = Depends(principal), session: Session = Depends(get_session)):
    _require_any(p, "monitor")
    f = Fabric(session, p)
    hh = f.hourly()
    t = f.totals(hh)
    conn = [s for s in f.sources if s["status"] != "unavailable"]
    per = [
        {"id": s["id"], "vendor": s["vendor"], "name": s["name"], "status": s["status"], "freshMin": s["freshMin"],
         "fresh": s["fresh"], "sla": sla_minutes(s), "in_sla": s["freshMin"] is not None and s["freshMin"] <= sla_minutes(s),
         "success": f.success(s["id"]), "failed7": f.failed_in(s["id"], 7), "latency": f.latency.get(s["id"])}
        for s in f.sources
    ]  # fmt: skip
    lat = [x["latency"] for x in per if x["status"] != "unavailable" and x["latency"] is not None]
    wfs = [
        {"id": w["id"], "name": w["name"], "runsN": w["runsN"], "okN": w["okN"], "last": w.get("last"), "stat": wf_stat(w)}
        for w in f.workflows
        if w.get("runsN")
    ]
    return {
        "kpis": {
            "success_pct": t["pct"],
            "latency": js_round(sum(lat) / len(lat)) if lat else None,
            "failed7": sum(x["failed7"] for x in per if x["status"] != "unavailable"),
            "in_sla": sum(1 for x in per if x["status"] != "unavailable" and x["in_sla"]),
            "connected": len(conn),
            "failing_workflows": sum(1 for w in f.workflows if wf_stat(w) == "failing"),
        },
        "hourly": hh,
        "totals": t,
        "sources": per,
        "workflows": wfs,
    }
