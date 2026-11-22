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

The endpoints are in di.routes.screens.integration (parameters and access); this module builds what each returns,
over the live Connection Fabric (di.repositories.fabric.Fabric).

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
  changed by tables.update (di.services.actions.fabric_records: tables, links, positions);
- workspace collection "conflict_escalations": who escalated which conflict (conflict.escalate; it stays open);
- workspace collection "source_config" (di.connectors.lifecycle): what people saved about a source (its descriptive
  fields, credential, configuration version, audit trail and field mapping) over the reference above, sources created
  in the Connection Fabric, and the deleted sources (left out of every endpoint until their deletion is undone);
- workspace collection "events": the event stream's log (the demo's EVENTS and what actions add), merged with the real
  messages (sync runs that carried records, instructions sent or failed, webhook deliveries; di.repositories.fabric.stream);
- workspace collection "workflows" (di.repositories.workflows): the workflows reading a source, failing ingest workflows;
- workspace collection "workflow_run_stats" and table failed_record (plan 6 D1): the Monitor's per-workflow row over
  the last 24 hours (runs, success share, last state, p95 and mean run duration) and per step (p95 duration, records
  still held by rule), from the real runs. A workflow without a real run in the window (the demo's seeded workflows)
  shows the demo's stats as before (`real` false: runs and successes since it was made, the last run's duration), so
  the seeded screen stays the demo's.

Texts the demo computes (recommendations, exceptions, activity lines) are built the demo's way from these values.
Where the backend has no value the demo invented one: a conflict's `impact` names what the backend does (dependent
routes are held), `since` is its age; hourly health buckets are the sync runs of the 24 hours up to now (or up to the
newest run, when the clock is behind the synced data, as the test suite's pinned clock is); a source with no finished
run has `success` null; one with no HTTP calls has `latency` null.

Facade (frontend/src/api/integration.ts) → here, export by export:

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
- endpoint GET /monitor: totals, hourly, workflows and wfStat (`workflows`; the full list is GET /api/screens/workflows),
  monitorWorkflows (`workflows` with their 24-hour and per-step stats)
- another area: openDecisionCount (the open decisions, from the cases)
- reference: connMethods, srcTypes, srcCats, srcCatNote, authOpts, frCats, frDecisions, intSub, intKids, sampleCsv,
  facilities, tenantList, tableSuggestions, frSample, frAuthOptions, typeOf
- frontend-only (formatting, the ticking age, view helpers): srcAgeText, srcFresh, srcAge, methodMode, cfgDefaults,
  buildUrl, hashId, vHue, ackKind, pct, isoTime, tableHeight, vlogoHtml, stepHtml, jsonHtml, nowLabel, caseExists,
  rbPath; and moveTable, alignTables (the table layout on the canvas)
- actions (POST /api/actions/...): syncSource, reconnectSource, rotateCredentials, deleteSource, saveSource,
  resolveConflict, escalateConflict, commitImport, updateTables, addComment, undoActions, syncAllLive
- the demo's browser-only flows, now actions (di.services.actions.fabric_sources): pauseSource and resumeSource
  (source.pause, source.resume), disconnectSource (source.disconnect), reauthenticated (source.reconnect or
  credentials.rotate), testConnection (source.test, a read), connectFromCatalog (source.update, mode "catalog")
"""

import re
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.connectors import mapping
from di.core import golden
from di.core.auth import Principal
from di.repositories.constants import MAP_TARGET, MAPPINGS
from di.repositories.context import case_openable
from di.repositories.fabric import DAY, FR_CATOF, Fabric, cat_of, epoch_ms, sla_minutes, stream, type_of
from di.repositories.workflows import monitor_stats, wf_stat
from di.services.actions.decisions import comments
from di.services.engine.jsmath import js_round

CANON: list[dict] = golden.load("canonical")["models"]
_REF = golden.load("screens/integration")
CATALOG: list[dict] = _REF["catalog"]
CANON_EX: dict = _REF["canon_examples"]
CANON_PFX: dict[str, str] = _REF["canon_pfx"]
FR_CATS: list[str] = _REF["fr_cats"]


# ---------------------------------------------------------------- small ports of the demo
def src_models(s: dict, maps: dict[str, list] | None = None) -> dict[str, list]:
    """frSrcModels: the canonical models a source reaches (its mapped fields' prefixes, or its target model)."""
    pre = {v: k for k, v in CANON_PFX.items()}
    o: dict[str, list] = {}
    for r in (MAPPINGS if maps is None else maps).get(s["id"], []):
        m = pre.get(str(r[2]).split(".")[0])
        if m:
            o.setdefault(m, []).append(r)
    t = MAP_TARGET.get(s["id"]) or type_of(s["type"]).get("target")
    if t and t not in o:
        o[t] = []
    return o


def _catalog(f: Fabric) -> list[dict]:
    """CATALOG, each marked connected when a source with its id exists."""
    return [c | {"connected": c["id"] in f.by_id} for c in CATALOG]


def _integration_status(f: Fabric, s: dict) -> str:
    if s.get("disconnected"):
        return "disconnected"
    if s.get("paused"):
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


# ---------------------------------------------------------------- what each endpoint returns
def sources(session: Session, p: Principal, cat: str | None, status: str | None, method: str | None, q: str | None) -> dict:
    """GET /sources: every source (with its health) the filters keep, and the status counts."""
    f = Fabric(session, p)
    rows = [s | {"health": f.health(s)} for s in f.sources if _source_filter(s, f, cat, status, method, q)]
    return {"sources": rows, "counts": _status_counts(f)}


def source_detail(session: Session, p: Principal, source_id: str, days: int) -> dict | None:
    """GET /sources/{id}: one source in detail; None when there is no such source."""
    f = Fabric(session, p)
    s = f.by_id.get(source_id)
    if s is None:
        return None
    return {
        "source": s | {"health": f.health(s)},
        "sync_history": [
            {"ts": r["ts"], "ok": r["result"] == "success", "rows": r["rows"],
             "dur": f"{r['dur']} s" if r["dur"] is not None else "—"}
            for r in s["runs"][:12]
        ],
        "series": f.series(source_id, days),
        "failed": f.failed_in(source_id, days),
        "mappings": f.maps.get(source_id, []),
        # the saved versions of the mapping a sync applies (plan 6 A4); none: the adapter's own mapping
        "mapping": {"version": mapping.active_version(session, source_id), "versions": mapping.versions(session, source_id)},
        "models": src_models(s, f.maps),
        "table_model": f.tables.get(source_id),
        "comments": comments(session, "src:" + source_id),
    }  # fmt: skip


def overview(session: Session, p: Principal) -> dict:
    """GET /overview: the catalogue."""
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


def source_map(session: Session, p: Principal, limit: int) -> dict:
    """GET /map: the source map."""
    f = Fabric(session, p)
    hh = f.hourly()
    t = f.totals(hh)
    ex = f.exceptions()
    runs = session.execute(text("SELECT * FROM sync_run WHERE status <> 'running' ORDER BY id DESC LIMIT 6")).mappings()
    activity = [
        {"ts": epoch_ms(r["finished_at"] or r["started_at"]), "id": r["source_id"],
         "kind": "ok" if r["status"] == "ok" else "warn",
         "text": f"Sync completed · {r['records_read']:,} records" if r["status"] == "ok"
         else f"Sync failed · {r['error'] or r['status']}"}
        for r in runs
    ]  # fmt: skip
    return {
        "kpis": {
            "connected": sum(1 for s in f.sources if s["status"] != "unavailable"),
            "tables": sum(f.table_count(s["id"]) for s in f.sources),
            "fields": sum(len(v) for v in f.maps.values()),
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
        "mappings": {k: v for k, v in f.maps.items() if k in f.by_id},
        "source_models": {s["id"]: src_models(s, f.maps) for s in f.sources},
        "table_models": {k: m for k, m in f.tables.items() if k in f.by_id},
    }


def tables(session: Session, p: Principal, source: str | None) -> dict | None:
    """GET /tables: the table models (of one source, when given) and their counts; None when that source has none."""
    f = Fabric(session, p)
    models = {k: m for k, m in f.tables.items() if k in f.by_id and (source is None or k == source)}
    if source is not None and source not in models:
        return None
    return {
        "models": models,
        "counts": {
            "tables": sum(len(m["t"]) for k, m in f.tables.items() if k in f.by_id),
            "links": sum(len(m["fk"]) for k, m in f.tables.items() if k in f.by_id),
            "systems": sum(1 for k, m in f.tables.items() if k in f.by_id and m["t"]),
        },
    }


def models(session: Session, p: Principal) -> dict:
    """GET /models: the canonical models with their synced record counts, examples and mappings."""
    f = Fabric(session, p)
    records: dict[str, int] = dict(session.execute(text("SELECT model, count(*) FROM canonical GROUP BY model")).tuples().all())
    return {
        "canon": [m | {"records": records.get(CANON_PFX.get(m["n"], ""), 0)} for m in CANON],
        "examples": CANON_EX,
        "prefix": CANON_PFX,
        "mappings": {k: v for k, v in f.maps.items() if k in f.by_id},
        "source_models": {s["id"]: src_models(s, f.maps) for s in f.sources},
        "counts": {
            "models": len(CANON),
            "fields": sum(len(m["fields"]) for m in CANON),
            "sources_mapped": sum(1 for s in f.sources if f.maps.get(s["id"])),
            "records": sum(records.values()),
        },
    }


def events(session: Session, p: Principal, dir: str | None, issues: bool, q: str | None, limit: int | None) -> dict:
    """GET /events: the event stream (the workspace log and the real messages, plan 6 B4), with its counts."""
    ev = stream(session)
    ok = case_openable(session, p, {e["caseId"] for e in ev if e.get("caseId")})
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


def conflicts(session: Session, p: Principal, status: Literal["open", "resolved", "all"], source: str | None, limit: int) -> dict:
    """GET /conflicts: the conflict queue, with its counts."""
    f = Fabric(session, p)
    rows, total = f.conflicts(status, source, limit)
    n_open = f.conflicts("open", limit=1)[1]
    n_all = f.conflicts("all", limit=1)[1]
    systems = session.execute(text('SELECT count(DISTINCT k) FROM conflict, jsonb_object_keys(conflict."values") AS k')).scalar()
    return {"conflicts": rows, "total": total, "counts": {"open": n_open, "closed": n_all - n_open, "systems": systems}}


def _wf_window(w: dict, r: dict | None) -> dict:
    """The Monitor's per-workflow stats for the last 24 hours. From the workflow's real runs (monitor_stats) when it
    has any in the window; otherwise the demo's stats as the demo shows them (runs and successes since it was made,
    the last run's duration as the duration, no p95 and no steps), so a seeded workflow's row stays the demo's."""
    if r is not None:
        return {"real": True, "runs24": r["runs"], "ok24": r["ok"], "success": r["success"], "p95": r["p95"],
                "avg": r["avg"], "lastState": r["lastState"], "steps": r["steps"]}  # fmt: skip
    last = w.get("last") or {}
    runs, ok = w.get("runsN") or 0, w.get("okN") or 0
    return {"real": False, "runs24": runs, "ok24": ok, "success": js_round(ok / runs * 100) if runs else None, "p95": None,
            "avg": last.get("dur"), "lastState": last.get("state"), "steps": []}  # fmt: skip


def monitor(session: Session, p: Principal) -> dict:
    """GET /monitor: health over 24 hours, per source, per workflow."""
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
    real = monitor_stats(session, f.now - DAY)
    wfs = [
        {"id": w["id"], "name": w["name"], "runsN": w["runsN"], "okN": w["okN"], "last": w.get("last"), "stat": wf_stat(w)}
        | _wf_window(w, real.get(w["id"]))
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
