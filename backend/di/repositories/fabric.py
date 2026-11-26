"""The live Connection Fabric: the object every Connection Fabric screen reads (`Fabric`, loaded once per request),
and the Fabric's health as Home and the Command Center read it: the starting workflow catalogue without its random run
data (wfSeed, wfStat), the live fabric (the same object the Connection Fabric screens read, so the tiles equal the
Monitor and the Source Map), and the event stream.

`Fabric` overlays the demo's source records (fixtures/golden/sources.json, REF_SOURCES) with what the backend knows
(source_system, raw_record, sync_run, fetch_log, conflict, source_secret, the stored workflows and table models, and
what people saved in di.connectors.lifecycle); di.services.screens.integration shapes it per endpoint. This module also
registers the workspace collection "table_models" (seeded from the demo's TBL_MODELS), so the collection is known
wherever the fabric is read (the api and the worker).

Plan 6 B4: the integration health is real. The demo drew its hourly buckets from a hash (hhInit); they are gone. Home's
and the Command Center's health figures, hourly line, exceptions, stale sources, open conflicts and failing workflows come
from `live(s)` (`Fabric`: source_system, sync_run, conflict, the stored workflows), and the event stream is the
workspace log plus the backend's real messages (`stream`). Home's alerts and the Developer briefing list the sources,
conflicts and failed workflows of the live fabric too (`stale_now`, `open_conflicts_now`, `failing_now`), not the demo's
three stale sources and starting conflicts."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal, overload

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.connectors import discover, lifecycle
from di.connectors.registry import ADAPTERS
from di.core import clock, golden, state
from di.core.auth import Principal
from di.repositories import workspace as ws
from di.repositories.common import SOURCES, iso, ms
from di.repositories.constants import MAPPINGS, SRC_TYPES
from di.repositories.reference import channels
from di.repositories.workflows import all_workflows, wf_using
from di.repositories.workflows import wf_stat as stored_stat
from di.services.actions.decisions import comments
from di.services.actions.fabric_records import escalations
from di.services.actions.pipeline import CallContext
from di.services.engine.jsmath import js_round

# How a connector status shows on the screens (read by the integration screen and the source actions): failing and
# expired credentials show as stale; a disconnected source shows as not connected (`disconnected: true`, `discBy`).
# A paused one keeps the status it had before (`paused: true`; connectorStatus says `paused`).
SCREEN_STATUS = {"failing": "stale", "auth_expired": "stale", "disconnected": "unavailable"}
_REF = golden.load("screens/integration")
FR_XTYPES: dict[str, dict] = _REF["fr_xtypes"]
FR_CATOF: dict[str, str] = _REF["fr_catof"]
REF_SOURCES: list[dict] = golden.load("sources")["sources"]  # the demo's SOURCES, in its order
REF_BY_ID = {s["id"]: s for s in REF_SOURCES}
state.register("table_models", lambda: [(k, m | {"source": k}) for k, m in _REF["table_models"].items()])

DAY = 86_400_000
HOUR = 3_600_000
# the descriptive fields a saved source (workspace collection "source_config") overlays on the demo's record
OVERLAY = (
    "name", "short", "cat", "vendor", "ver", "env", "url", "mode", "auth", "rw", "inputs", "read", "write", "step",
    "authority", "method", "cfg", "cfgVer", "credAt", "credDays", "audit", "owner", "updatedBy", "frConnectedAt",
)  # fmt: skip
REAL_LIMIT = 100  # the newest real messages of each kind (sync runs, instructions, webhooks) the stream lists


def type_of(t: str) -> dict:
    """frTypeOf: a source type's label, short name, category and target model."""
    return SRC_TYPES.get(t) or FR_XTYPES.get(t) or {"label": t, "short": t, "cat": "internal", "target": "Asset & component"}


WF_DEC = ["Standard six-gate decision", "Pool allocation to approval", "Evidence gaps and demand first"]


def workflows() -> list[dict]:
    """The demo's starting workflows without their random run data: one ingest per source (a draft when the source is
    not connected), one outbound per write channel, and the three decision workflows. The Oracle Depot Repair ingest
    is the one whose last run failed (STARTING_FAILED_WORKFLOWS)."""
    out: list[dict] = []

    def add(name: str, src: str | None, status: str = "published") -> None:
        failing = name in ws.STARTING_FAILED_WORKFLOWS
        out.append({"id": f"WF-{101 + len(out)}", "name": name, "src": src, "status": status, "failing": failing})

    for s in SOURCES.values():
        add("Ingest · " + s["vendor"], s["id"], "draft" if s["status"] == "unavailable" else "published")
    for s in SOURCES.values():
        if s.get("write"):
            for ch in ("api", "file") if s["type"] == "erp" else ("api",):
                add("Outbound · " + s["vendor"] + (" (interface file)" if ch == "file" else ""), s["id"])
    for name in WF_DEC:
        add(name, None)
    return out


def wf_stat(w: dict) -> str:
    """The demo's wfStat."""
    return "failing" if w["status"] == "published" and w["failing"] else w["status"]


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


def cat_of(s: dict) -> str:
    """frCatOf."""
    return FR_CATOF.get(s["type"], "Custom")


def sla_minutes(s: dict) -> int:
    """frSla: twice the polling interval, 15 min for events, two days for a manual import, else an hour."""
    if s.get("interval"):
        return s["interval"] * 2
    if re.search("event|webhook", s.get("mode") or "", re.I):
        return 15
    return 2880 if s["status"] == "manual" else 60


def cred_days(s: dict, now: int) -> int | None:
    """frCredDays: days until the credential expires."""
    if not s.get("credAt") or s.get("credDays") is None:  # a registered extra system has a credential time but no lifetime
        return None
    return js_round((s["credAt"] + s["credDays"] * DAY - now) / DAY)


# ---------------------------------------------------------------- the backend's data
def _now() -> int:
    return ms(clock.now().isoformat())


@overload
def epoch_ms(v: datetime) -> int: ...
@overload
def epoch_ms(v: None) -> None: ...
def epoch_ms(v: datetime | None) -> int | None:
    return ms(v.astimezone(UTC).isoformat()) if v else None


def _run_view(r) -> dict:
    """A sync run in the demo's SyncRun shape."""
    dur = round((r["finished_at"] - r["started_at"]).total_seconds(), 1) if r["finished_at"] else None
    result = {"ok": "success"}.get(r["status"], r["status"])
    return {
        "id": f"SYNC-{r['id']}",
        "ts": epoch_ms(r["started_at"]),
        "trigger": r["trigger"].capitalize(),
        "rows": r["records_read"],
        "facts": r["facts_written"],
        "failed": r["records_failed"],
        "dur": dur,
        "result": result,
        "note": r["error"] or "",
    }


def table_models(s: Session) -> list[tuple[str, dict]]:
    """The table models (the demo's tgModel for every source in TBL_MODELS), keyed by source."""
    stored = [(m["source"], {k: v for k, v in m.items() if k != "source"}) for m in state.items(s, "table_models")]
    return discover.with_discovered(s, stored)  # sources created here: the tables they really send (plan 6 B5)


# ---------------------------------------------------------------- the live fabric (plan 6 B4)
class Fabric:
    """Everything the Connection Fabric screens read, loaded once per request."""

    def __init__(self, s: Session, p: Principal | None = None):  # Home and the Command Center read it without one
        self.s, self.p = s, p
        self.now = _now()
        rows = s.execute(
            text(
                "SELECT s.*, (SELECT count(*) FROM raw_record r WHERE r.source_id = s.id) AS records, "
                "(SELECT count(*) FROM conflict c WHERE c.status <> 'resolved' AND c.authority = s.id) AS open_conflicts "
                "FROM source_system s ORDER BY s.id"
            )
        ).mappings()
        # what people changed (di.connectors.lifecycle): saved settings and mappings, deleted sources left out
        self.deleted = lifecycle.deleted(s)
        self.cfg = lifecycle.configs(s)
        self.maps = lifecycle.mappings(MAPPINGS, self.cfg, self.deleted)
        self.rows = {r["id"]: r for r in rows if r["id"] not in self.deleted}
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
        self.ref = max(self.now, epoch_ms(newest) or 0)
        since7 = datetime.fromtimestamp((self.ref - 7 * DAY) / 1000, UTC)
        self.agg: dict[str, Any] = {
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
        self.latency: dict[str, int] = {
            r[0]: js_round(float(r[1]))
            for r in s.execute(text("SELECT source_id, avg(duration_ms) FROM fetch_log WHERE duration_ms IS NOT NULL GROUP BY 1"))
        }
        self.workflows = all_workflows(s)
        self.tables = dict(table_models(s))
        # stored credentials (plan 6 A1): what the Security tab shows, never the value
        self.creds = {
            r.source_id: {
                "kind": r.kind, "version": r.version, "last4": r.last4,
                "issued_at": epoch_ms(r.issued_at), "expires_at": epoch_ms(r.expires_at),
            }
            for r in s.execute(text("SELECT source_id, kind, version, last4, issued_at, expires_at FROM source_secret "
                                    "WHERE active AND kind = 'auth'"))
        }  # fmt: skip
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
        last = epoch_ms(row["last_success_at"])
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
            updatedAt=epoch_ms(row["updated_at"]),
            connector=sid in ADAPTERS,
            openConflicts=row["open_conflicts"],
        )
        base.pop("note", None)
        if row["note"]:
            base["note"] = row["note"]
        for k in ("c0", "k0", "updatedBy"):  # the demo's starting copies of completeness and confidence
            base.pop(k, None)
        return self._changed(base, row)

    def _changed(self, base: dict, row) -> dict:
        """What people changed (di.services.actions.fabric_sources) over the demo's record: saved settings, the paused and
        disconnected flags. A source nobody changed is returned as it is, so the seeded state stays the demo's."""
        cfg = self.cfg.get(base["id"])
        if base["id"] in self.creds:
            base["credential"] = self.creds[base["id"]]
        if cfg:
            base.update({k: v for k, v in cfg.items() if k in OVERLAY})
            if not base["records"] and cfg.get("records"):  # no connector: the synthetic first sync's count
                base["records"] = cfg["records"]
        if row["status"] == "paused":  # the demo: the status it had (live, stale ...), flagged paused
            prev = (cfg or {}).get("prev") or "live"
            base.update(status=SCREEN_STATUS.get(prev, prev), paused=True)
        elif row["status"] == "disconnected":  # the demo: not connected, no sync time, who did it
            base.update(disconnected=True, discBy=(cfg or {}).get("discBy"), lastSync=None, freshMin=None, fresh="—")
        return base

    # ---- derived per source
    def failing(self, s: dict) -> bool:
        """frSrcFailing: its ingest workflow is failing."""
        return any(w.get("src") == s["id"] and w["cat"] == "Ingest" and stored_stat(w) == "failing" for w in self.workflows)

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
        return sum(len(t["cols"]) for t in m["t"]) if m else len(self.maps.get(sid, []))

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
            "mapped": len(self.maps.get(s["id"], [])),
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
        return int(self.s.execute(q, {"i": sid, "s": since}).scalar_one())

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
            i = (epoch_ms(r["started_at"]) - start) // HOUR
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

    def conflicts(
        self, status: Literal["open", "resolved", "all"] = "open", source: str | None = None, limit: int | None = None
    ) -> tuple[list[dict], int]:
        # open and escalated ones lead the list (UI QA 21), newest first within each group
        where = {"open": "status IN ('open', 'escalated')", "resolved": "status = 'resolved'", "all": "true"}[status]
        args = {"src": source}
        cond = f'{where} AND (CAST(:src AS text) IS NULL OR authority = :src OR "values" ? :src)'
        total = self.s.execute(text(f"SELECT count(*) FROM conflict WHERE {cond}"), args).scalar_one()  # noqa: S608 - `where` comes from a fixed mapping; values are bound
        q = f"SELECT * FROM conflict WHERE {cond} ORDER BY (status = 'resolved'), id DESC" + (" LIMIT :n" if limit else "")  # noqa: S608 - `where` comes from a fixed mapping; values are bound
        rows = self.s.execute(text(q), args | ({"n": limit} if limit else {})).mappings()
        esc = escalations(self.s)
        return [self._conflict(r, esc.get(f"CF-{r['id']}")) for r in rows], total

    def _name(self, sid: str) -> str:
        s = self.by_id.get(sid) or REF_BY_ID.get(sid)
        return s["name"] if s else "Manual import" if sid == "manual" else sid  # manual: imports, Conflict Queue choices

    def _conflict(self, r, esc: dict | None = None) -> dict:
        """A conflict in the facade's Conflict shape: `a` is the authority's value, `b` the first other source's.
        An escalated conflict stays open (the demo's c.escalated beside status 'open'); `escalated` says who and when."""
        vals: dict = r["values"] or {}
        auth = r["authority"]
        others = sorted(k for k in vals if k != auth)
        b = others[0] if others else auth

        def val(v):
            return v if isinstance(v, str) else json.dumps(v)

        age = max(0, (self.ref - epoch_ms(r["opened_at"])) / 60000)
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
            "openedAt": epoch_ms(r["opened_at"]),
        }
        owner = (self.by_id.get(auth) or REF_BY_ID.get(auth) or {}).get("owner") or f"{self._name(auth)} data owner"
        if esc and r["status"] != "resolved":
            out["escalated"] = {"by": esc["by"], "at": esc["at"], "to": owner}  # to: the authority's data owner (B2)
        elif r["status"] == "escalated":
            at = datetime.isoformat(r["closed_at"]) if r["closed_at"] else None
            out["escalated"] = {"by": r["closed_by"], "at": at, "to": owner}
        if r["status"] == "resolved":
            out["resolved"] = {
                "by": r["closed_by"], "at": datetime.isoformat(r["closed_at"]) if r["closed_at"] else None, "note": r["note"],
            }  # fmt: skip
        return out

    def exceptions(self) -> list[dict]:
        """smExceptions: unconnected, expired and unmapped sources, manual imports, then every open conflict."""
        o = []
        for s in self.sources:
            if s["status"] == "unavailable":
                o.append({"src": s["name"], "obj": s["vendor"], "issue": "Not connected: no feed", "sev": "High", "st": "Open"})
            elif s["status"] == "stale":
                o.append({"src": s["name"], "obj": s["vendor"], "issue": "Feed token expired", "sev": "High", "st": "Open"})
            if s["status"] != "unavailable" and not self.maps.get(s["id"]):
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


def live(s: Session) -> Fabric:
    """The Connection Fabric as its screens read it now (sources, sync runs, conflicts, workflows)."""
    return Fabric(s)


def health(f: Fabric) -> tuple[list[dict], dict]:
    """The Monitor's 24 hourly buckets (successful, with failed records, failed sync runs) and their totals (hhTotals:
    ok, warn, bad, runs in progress, success share)."""
    hh = f.hourly()
    return hh, f.totals(hh)


def stale_now(f: Fabric) -> list[dict]:
    """Sources that are stale or not connected, as the Connection Fabric shows them now."""
    return [s for s in f.sources if s["status"] in ("stale", "unavailable")]


def failing_now(f: Fabric) -> int:
    """Published workflows whose last run failed (the Monitor's failing_workflows)."""
    return sum(1 for w in f.workflows if stored_stat(w) == "failing")


def open_conflicts_now(f: Fabric) -> int:
    """Open (and escalated) conflicts in the conflict table (the Source Map's open_conflicts)."""
    return f.conflicts("open", limit=1)[1]


# ---------------------------------------------------------------- the event stream (plan 6 B4)
def _sync_events(s: Session) -> list[tuple[datetime, dict]]:
    """Sync runs that carried something (read or failed records, or failed): inbound messages from the source. A sync
    that read nothing carried no message (the Monitor still counts it)."""
    rows = s.execute(
        text(
            "SELECT r.*, coalesce(r.finished_at, r.started_at) AS at, s.vendor FROM sync_run r "
            "JOIN source_system s ON s.id = r.source_id "
            "WHERE r.status <> 'running' AND (r.status <> 'ok' OR r.records_read > 0 OR r.records_failed > 0) "
            "ORDER BY r.id DESC LIMIT :n"
        ),
        {"n": REAL_LIMIT},
    ).mappings()
    out = []
    for r in rows:
        ok = r["status"] == "ok"
        if not ok:
            ack = "failed · " + (r["error"] or r["status"])[:160]
        elif r["records_failed"]:
            ack = f"acknowledged · {r['records_failed']:,} records failed"
        else:
            ack = "acknowledged"
        note = (
            f"{r['trigger'].capitalize()} sync of {r['vendor']}: {r['records_read']:,} records read, "
            f"{r['facts_written']:,} facts written, {r['records_failed']:,} failed"
        )
        out.append((r["at"], {
            "id": f"SYNC-{r['id']}", "dir": "in", "type": "sync.completed" if ok else "sync.failed", "caseId": None,
            "decisionId": None, "approval": None, "ver": None, "dest": r["vendor"], "ack": ack, "key": f"sync-{r['id']}",
            "note": note, "ts": iso(ms(r["at"].isoformat())), "retries": 0, "source": r["source_id"],
        }))  # fmt: skip
    return out


_INS_ACK = {"acknowledged": "acknowledged", "sent": "sent · awaiting acknowledgement"}


def _instruction_events(s: Session) -> list[tuple[datetime, dict]]:
    """Instructions that went out to a system (or failed to): outbound messages. Their acknowledgements are already in
    the log (adapter.acknowledge pushes them); queued ones have not gone anywhere yet."""
    rows = s.execute(
        text(
            "SELECT i.*, s.vendor FROM instruction i LEFT JOIN source_system s ON s.id = i.system "
            "WHERE i.sent_at IS NOT NULL OR i.status = 'failed' ORDER BY i.updated_at DESC, i.id DESC LIMIT :n"
        ),
        {"n": REAL_LIMIT},
    ).mappings()
    out = []
    for r in rows:
        st = r["status"]
        failed = st == "failed"
        ack = "failed · " + (r["last_error"] or "not delivered")[:160] if failed else _INS_ACK.get(st, st)
        cid = r["case_id"]
        when = r["acknowledged_at"] or r["sent_at"] or r["updated_at"]
        out.append((r["updated_at"], {
            "id": f"INS-{r['id']}", "dir": "out", "type": "instruction.failed" if failed else "instruction.sent",
            "caseId": cid, "decisionId": "DI-2026-" + cid[3:] if cid.startswith("RT-") else None,
            "approval": r["approval_ref"], "ver": None, "dest": f"{r['vendor'] or r['system']} · {r['kind']}", "ack": ack,
            "key": r["idem_key"], "note": f"Step {r['step'] + 1} ({r['kind']}) to {r['vendor'] or r['system']}"
            + (f", reference {r['doc_ref']}" if r["doc_ref"] else ""),
            "ts": iso(ms(when.isoformat())), "retries": max(0, r["attempts"] - 1),
        }))  # fmt: skip
    return out


def _webhook_events(s: Session) -> list[tuple[datetime, dict]]:
    """Webhook deliveries the api accepted (table webhook_event, plan 6 A7), when that table exists."""
    cols = set(s.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'webhook_event'")).scalars())
    if not {"event_id", "source_id", "received_at"} <= cols:
        return []
    rows = s.execute(
        text(
            "SELECT w.event_id, w.source_id, w.received_at, s.vendor FROM webhook_event w "
            "LEFT JOIN source_system s ON s.id = w.source_id ORDER BY w.received_at DESC LIMIT :n"
        ),
        {"n": REAL_LIMIT},
    ).mappings()
    return [
        (r["received_at"], {
            "id": f"WH-{r['event_id']}", "dir": "in", "type": "webhook.received", "caseId": None, "decisionId": None,
            "approval": None, "ver": None, "dest": r["vendor"] or r["source_id"], "ack": "acknowledged",
            "key": r["event_id"], "note": f"Signed event from {r['vendor'] or r['source_id']}, verified and accepted",
            "ts": iso(ms(r["received_at"].isoformat())), "retries": 0, "source": r["source_id"],
        })
        for r in rows
    ]  # fmt: skip


def stream(s: Session) -> list[dict]:
    """Event Streams: the workspace log (the demo's EVENTS and what actions push) and the backend's real messages
    (sync runs, instructions, webhook deliveries), newest first by when each was recorded. The log keeps its own
    order; a real message goes before the first log event recorded before it."""
    log = state.items(s, "events", newest_first=True)
    at: dict[str, Any] = dict(s.execute(text("SELECT id, updated_at FROM state_item WHERE collection = 'events'")).tuples().all())
    real = sorted(_sync_events(s) + _instruction_events(s) + _webhook_events(s), key=lambda x: x[0], reverse=True)
    out: list[dict] = []
    i = 0
    for e in log:
        t = at.get(e["id"])
        while i < len(real) and t is not None and real[i][0] > t:
            out.append(real[i][1])
            i += 1
        out.append(e)
    out.extend(r for _, r in real[i:])
    return out


def ws_events(ctx: CallContext) -> list[dict]:
    """The event stream, newest first (Event Streams' rows)."""
    return stream(ctx.session)


# ---------------------------------------------------------------- conflicts that hold up a decision (the menu badge)
HELD_STAGES = ("none", "awaiting_approval")  # a decision is still to be made or approved


def held_conflicts(ctx: CallContext, session: Session) -> int:
    """Open or escalated conflicts on the asset of a visible case whose decision is still pending (the menu badge)."""
    from di.repositories.context import visible_cases

    assets = [c.get("assetId") for c in visible_cases(ctx) if c["stage"] in HELD_STAGES and c.get("assetId")]
    if not assets:
        return 0
    q = "SELECT count(*) FROM conflict WHERE status IN ('open', 'escalated') AND key = ANY(:keys)"
    return session.execute(text(q), {"keys": assets}).scalar_one()
