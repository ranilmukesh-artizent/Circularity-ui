"""The Connection Fabric's health as Home and the Command Center read it: the starting workflow catalogue without its
random run data (wfSeed, wfStat), the live fabric (the same object the Connection Fabric screens read, so the tiles equal
the Monitor and the Source Map), and the event stream.

Plan 6 B4: the integration health is real. The demo drew its hourly buckets from a hash (hhInit); they are gone. Home's
and the Command Center's health figures, hourly line, exceptions, stale sources, open conflicts and failing workflows come
from `live(s)` (di.screens.integration.Fabric: source_system, sync_run, conflict, the stored workflows), and the event
stream is the workspace log plus the backend's real messages (`stream`). Home's alerts and the Developer briefing list
the sources, conflicts and failed workflows of the live fabric too (`stale_now`, `open_conflicts_now`, `failing_now`),
not the demo's three stale sources and starting conflicts."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di import golden, state
from di.actions.pipeline import CallContext
from di.reads import workspace as ws
from di.reads.common import SOURCES, iso, ms
from di.reads.constants import SRC_TYPES
from di.reads.workflows import wf_stat as stored_stat

if TYPE_CHECKING:
    from di.screens.integration import Fabric

# How a connector status shows on the screens (read by the integration screen and the source actions): failing and
# expired credentials show as stale; a disconnected source shows as not connected (`disconnected: true`, `discBy`).
# A paused one keeps the status it had before (`paused: true`; connectorStatus says `paused`).
SCREEN_STATUS = {"failing": "stale", "auth_expired": "stale", "disconnected": "unavailable"}
FR_XTYPES: dict[str, dict] = golden.load("screens/integration")["fr_xtypes"]
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


# ---------------------------------------------------------------- the live fabric (plan 6 B4)
def live(s: Session) -> Fabric:
    """The Connection Fabric as its screens read it now (sources, sync runs, conflicts, workflows)."""
    from di.screens.integration import Fabric  # the screen module imports this one

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
