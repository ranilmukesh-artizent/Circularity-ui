"""What a person (or Ask) reads about a workflow and one of its runs, assembled from the Workflow Studio's own read model
(plan 9, P9-2.23).

    workflow_row(w)                        one list row: id, name, status, source, last run
    workflow_view(s, w)                    one workflow: its blocks, version, trigger, last run, recent runs
    history(s, w, limit)                   the runs that happened, newest first ({id, state, started, ...})
    run_view(s, w, run_id)                 one run: steps, error, retries, log lines, held records, the suggested fix
    log_lines(n, run, label)               the Investigation panel's error log, as `errorLog` in the web app writes it

Owns: the shape of these four views. Every figure is read from the collections and queries Workflow Studio shows
(`di.repositories.workflows`: all_workflows, keyed_runs, run_counts, run_quality, failed_rows, wf_stat; the workflow's
`lastRun` record; `workflow.applyFix`'s own `_fix_for` for the suggested fix), never a second query.
Never does: write anything, or run, reprocess or fix a workflow (those are the page's buttons), or decide who may see
a workflow (`di.services.actions.workflow_read` does, before it calls these).
"""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from di.repositories import workflows as studio
from di.repositories.common import iso
from di.workflow import live
from di.workflow.engine import label

RECENT = 5
HELD_SAMPLE = 5
BUTTONS = ("Diagnose", "Fix", "Run now", "Reprocess failed records")  # the page's own; Ask only points to them


def _t(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%H:%M:%S")


def log_lines(n: int, run: dict[str, Any], step_label: str) -> list[str]:
    """The Investigation panel's error log (frontend/src/pages/workflows/investigation.ts `errorLog`): start, one warning
    per failed attempt before the last, the error, the downstream note. Times are seconds before the run's end."""
    warns = max(0, n - 1)
    start = 2000 + 2000 * warns + 3000
    ts = run["ts"]
    out = [f"{_t(ts - start)} INFO  run {run['id']} started · trigger {run['trig']}"]
    out += [f"{_t(ts - (2000 + 2000 * (warns - k + 1)))} WARN  {step_label}: attempt {k} failed" for k in range(1, warns + 1)]
    out.append(f"{_t(ts - 2000)} ERROR {run.get('note') or step_label + ' failed'}")
    out.append(f"{_t(ts)} INFO  downstream steps marked upstream failed; held records kept")
    return out


def _source(w: dict[str, Any]) -> str | None:
    return w.get("src")


def workflow_row(w: dict[str, Any]) -> dict[str, Any]:
    last = w.get("last") or {}
    return {
        "id": w["id"], "name": w["name"], "status": studio.wf_stat(w), "category": w.get("cat"), "source": _source(w),
        "owner": w.get("owner"), "last_run_state": last.get("state"), "last_run_id": (w.get("lastRun") or {}).get("id"),
        "last_run_note": last.get("note"),
    }  # fmt: skip


def history(s: Session, w: dict[str, Any], limit: int = RECENT) -> list[dict[str, Any]]:
    """The runs that happened, newest first: the run records, or when it has none the workflow's recorded last run (as
    Workflow Studio's Runs tab lists them)."""
    real = [r for _, r in studio.keyed_runs(s, w["id"])]
    last, lr = w.get("last"), w.get("lastRun") or {}
    if not real and last:
        real = [{"id": lr.get("id"), "ts": last["ts"], "state": last["state"], "dur": last["dur"], "rows": last["rows"],
                 "trig": lr.get("trig", "Schedule"), "note": last.get("note")}]  # fmt: skip
    return [
        {"id": r["id"], "state": r["state"], "finished": iso(r["ts"]), "seconds": r["dur"], "records_read": r["rows"],
         "trigger": r["trig"], "note": r.get("note")}
        for r in real[:limit]
    ]  # fmt: skip


def workflow_view(s: Session, w: dict[str, Any]) -> dict[str, Any]:
    src = live.sources(s)
    blocks = [
        {"id": n["id"], "label": label(n, sources=src), "kind": n.get("k")} for n in (w.get("graph") or {}).get("nodes") or []
    ]
    runs = history(s, w)
    return {
        "workflow": workflow_row(w)
        | {"version": w.get("ver"), "published_version": (w.get("pub") or {}).get("ver"), "trigger": dict(w.get("trig") or {}),
           "description": w.get("desc"), "runs_total": w.get("runsN"), "runs_ok": w.get("okN")},
        "blocks": blocks,
        "last_run": runs[0] if runs else None,
        "recent_runs": runs,
    }  # fmt: skip


def find_run(s: Session, run_id: str, workflows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
    """The workflow a run belongs to and its record (None for the recorded last run of a seeded workflow)."""
    for w in workflows:
        if (w.get("lastRun") or {}).get("id") == run_id:
            return w, next((r for _, r in studio.keyed_runs(s, w["id"]) if r["id"] == run_id), None)
    by_id = {w["id"]: w for w in workflows}
    for w in workflows:
        rec = next((r for _, r in studio.keyed_runs(s, w["id"]) if r["id"] == run_id), None)
        if rec:
            return by_id[w["id"]], rec
    return None


def _steps(w: dict[str, Any], lr: dict[str, Any], src: dict[str, dict]) -> list[dict[str, Any]]:
    nodes = {n["id"]: n for n in (w.get("graph") or {}).get("nodes") or []}
    counts, attempts, dur = lr.get("counts") or {}, lr.get("attempts") or {}, lr.get("dur") or {}
    out = []
    for nid in lr.get("order") or list(lr.get("states") or {}):
        n = nodes.get(nid)
        c = counts.get(nid) or {}
        out.append({
            "id": nid, "label": label(n, sources=src) if n else nid, "state": (lr.get("states") or {}).get(nid),
            "seconds": dur.get(nid) if isinstance(dur, dict) else None, "records_in": c.get("in"),
            "records_out": c.get("out"), "records_rejected": c.get("rej"), "tries": attempts.get(nid),
        })  # fmt: skip
    return out


def _fix(s: Session, w: dict[str, Any]) -> str | None:
    """The page's suggested fix as text (what Apply the suggested fix would do), or None when there is none."""
    from di.services.actions.workflows import _fix_for, _fix_text

    f = _fix_for(s, w)
    return _fix_text(f) if isinstance(f, dict) else None


def _held(s: Session, w: dict[str, Any], lr: dict[str, Any]) -> dict[str, Any]:
    q = studio.run_quality(s, w)
    rows = studio.failed_rows(w, studio.run_counts(w), s)[:HELD_SAMPLE]
    if not q or q.get("key") != lr.get("key"):
        return {"records": 0, "by_rule": [], "sample": []}
    return {
        "records": q["held"],
        "by_rule": [{"step": g["label"], "field": g["field"], "rule": g["rule"], "records": g["n"]} for g in q["groups"]],
        "sample": [{k: r[k] for k in ("rec", "field", "value", "rule", "reason")} for r in rows],
    }


def run_view(s: Session, w: dict[str, Any], run_id: str, rec: dict[str, Any] | None) -> dict[str, Any]:
    """One run. The latest run of a workflow has its steps, log and held records; an older one only its record."""
    lr = w.get("lastRun") or {}
    latest = lr.get("id") == run_id
    last = w.get("last") or {}
    src = live.sources(s)
    base = {
        "workflow": {"id": w["id"], "name": w["name"], "source": _source(w), "version": lr.get("ver") or w.get("ver")},
        "buttons": list(BUTTONS),
    }
    if not latest:
        r = rec or {}
        return base | {
            "run": {"id": run_id, "state": r.get("state"), "trigger": r.get("trig"),
                    "finished": iso(r["ts"]) if r.get("ts") else None,
                    "seconds": r.get("dur"), "records_read": r.get("rows")},
            "error": r.get("note"), "detail": "summary",
        }  # fmt: skip
    steps = _steps(w, lr, src)
    bad = next((x for x in steps if x["state"] == "failed"), None)
    retries = lr.get("retries")
    retries = studio_retries(w) if retries is None else retries
    run = {"id": run_id, "ts": lr["ts"], "trig": lr.get("trig"), "note": lr.get("note") or last.get("note")}
    return base | {
        "run": {"id": run_id, "state": lr.get("status"), "trigger": lr.get("trig"), "started": iso(lr["t0"]),
                "finished": iso(lr["ts"]),
                "seconds": last.get("dur"), "records_read": (rec or {}).get("rows", last.get("rows"))},
        "failed_step": {"id": bad["id"], "label": bad["label"], "state": bad["state"]} if bad else None,
        "error": run["note"],
        "retries": retries,
        "steps": steps,
        "log": log_lines(retries, run, bad["label"] if bad else w["name"]) if bad else [],
        "held": _held(s, w, lr),
        "suggested_fix": _fix(s, w) if bad else None,
        "detail": "full",
    }  # fmt: skip


def studio_retries(w: dict[str, Any]) -> int:
    """The workflow's Retries setting (3 unless a person saved another), as the Investigation panel reads it."""
    saved = json.loads(w["saved"]) if w.get("saved") else {}
    r = (saved.get("m") or {}).get("retries")
    return 3 if r is None else int(r)
