"""The Workflow Studio's collections and the demo's workflow helpers, read by the studio and integration screens and the
workflow actions (di.actions.workflows): the workspace collections "workflows" (S.wf.list, each with its graph) and
"workflow_runs" (S.wf.runs), seeded from fixtures/golden/screens/workflows.json, and "workflow_templates" (S.frTpl,
empty at the start); wfStat, wfUsing, wfAnalyze, wfOrder; what the last real run counted and held (plan 6 C5); and
"workflow_run_stats", what every real run measured (duration, state, per-step durations), which the Monitor reads
(plan 6 D1); and the run views' figures (plan 6 follow-up): per run its records in, out and still held (run_figures)
and the latest real run's held records by step, field and rule (run_quality), counted from failed_record like View
failed records, so the Runs table, the Data quality panel and the failed records agree."""

import json
import math
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di import golden, state
from di.engine.jsmath import js_round

GOLDEN = golden.load("screens/workflows")
state.register("workflows", lambda: [(w["id"], w) for w in GOLDEN["starting"]])
# S.wf.runs is newest first; the collection keeps insertion order, so it is seeded oldest first and read newest first
state.register("workflow_runs", lambda: [(r["id"], r) for r in reversed(GOLDEN["runs"])])
# S.frTpl: the templates saved from workflows (workflow.saveTemplate), oldest first; none at the start
state.register("workflow_templates", lambda: [])
# what each real run measured, for the Monitor (plan 6 D1; record_run_stats): none at the start, the demo's runs have none
state.register("workflow_run_stats", lambda: [])


def all_workflows(s: Session) -> list[dict]:
    return state.items(s, "workflows")


def templates(s: Session) -> list[dict]:
    """The saved templates, oldest first, each with its graph (`tpl`)."""
    return state.items(s, "workflow_templates")


def recent_runs(s: Session) -> list[dict]:
    return state.items(s, "workflow_runs", newest_first=True)


def wf_stat(w: dict) -> str:
    """wfStat: a published workflow whose last run failed is failing."""
    last = w.get("last")
    return "failing" if w["status"] == "published" and last and last.get("state") == "failed" else w["status"]


def wf_using(workflows: list[dict], source_id: str) -> list[str]:
    """wfUsing: the workflows that read or write the source (by their graph, or their system before it is built)."""
    out = []
    for w in workflows:
        g = w.get("graph")
        if g:
            hit = any(n["ref"] == source_id and n["k"] in ("conn", "wconn", "map") for n in g["nodes"])
        else:
            hit = w.get("src") == source_id
        if hit:
            out.append(w["name"])
    return out


def _analyze(g: dict) -> tuple[dict, dict, dict]:
    """wfAnalyze: nodes by id, successors and predecessors (edges whose two ends exist)."""
    by = {n["id"]: n for n in g["nodes"]}
    succ: dict[str, list[str]] = {i: [] for i in by}
    pred: dict[str, list[str]] = {i: [] for i in by}
    for e in g["edges"]:
        if e["a"] in by and e["b"] in by:
            succ[e["a"]].append(e["b"])
            pred[e["b"]].append(e["a"])
    return by, succ, pred


def _order(g: dict) -> list[str]:
    """wfOrder: topological order (Kahn), starting from the nodes without predecessors in node order."""
    _, succ, pred = _analyze(g)
    deg = {n["id"]: len(pred[n["id"]]) for n in g["nodes"]}
    q = [n["id"] for n in g["nodes"] if not deg[n["id"]]]
    out = []
    while q:
        x = q.pop(0)
        out.append(x)
        for y in succ[x]:
            deg[y] -= 1
            if deg[y] == 0:
                q.append(y)
    return out


def run_counts(w: dict) -> dict[str, dict]:
    """Records in, out and rejected at each step of the last run, as the engine counted them (plan 6 C5; the run job
    keeps them in `lastRun.counts`). A workflow that has not really run (the demo's seeded last runs) has none: the
    demo's counts (frRunCounts, a fixed share of an invented record count) are gone with the simulation."""
    return dict((w.get("lastRun") or {}).get("counts") or {})


STATS_KEPT = 2000  # run stats kept (newest); the run records themselves keep the demo's 40


def record_run_stats(
    s: Session, key: str, wid: str, ts: int, dur: float | None, st: str, steps: dict[str, float] | None = None,
    labels: dict[str, str] | None = None,
) -> None:  # fmt: skip
    """File what a real run measured for the Monitor (plan 6 D1), under the run's key (its held records' run_id): when
    it finished, its duration in seconds, its state and each step's duration and label. The run record keeps the
    demo's shape {id, wf, name, ts, trig, dur, rows, state, note}, so the stats are a collection of their own."""
    state.put(s, "workflow_run_stats", key, {"key": key, "wf": wid, "ts": ts, "dur": dur, "state": st,
                                              "steps": steps or {}, "labels": labels or {}})  # fmt: skip
    s.execute(
        text(
            "DELETE FROM state_item WHERE collection = 'workflow_run_stats' AND seq NOT IN "
            "(SELECT seq FROM state_item WHERE collection = 'workflow_run_stats' ORDER BY seq DESC LIMIT :n)"
        ),
        {"n": STATS_KEPT},
    )


def p95(xs: list[float]) -> float | None:
    """The 95th percentile by nearest rank (the smallest value at least 95 % of the values are not above)."""
    v = sorted(xs)
    return v[max(0, math.ceil(0.95 * len(v)) - 1)] if v else None


def monitor_stats(s: Session, since: int) -> dict[str, dict]:
    """Per workflow, its real runs that finished at or after `since` (ms): runs, ok (not failed), success share,
    p95 and mean duration, the newest run's state, and per step the p95 duration and the records still held by rule
    (failed_record, run_kind 'workflow', status 'held', under the runs' keys). Workflows without real runs are absent."""
    state.get(s, "workflow_run_stats", "")  # seeds the (empty) collection on its first read
    runs = s.execute(
        text(
            "SELECT data FROM state_item WHERE collection = 'workflow_run_stats' "
            "AND (data->>'ts')::bigint >= :t ORDER BY (data->>'ts')::bigint, seq"
        ),
        {"t": since},
    ).scalars()
    by: dict[str, list[dict]] = {}
    for r in runs:
        by.setdefault(r["wf"], []).append(r)
    held: dict[tuple[str, str], dict[str, int]] = {}  # (workflow, step) -> rule -> records
    wf_of = {r["key"]: wid for wid, rs in by.items() for r in rs}
    if wf_of:
        for rid, step, rule, n in s.execute(
            text(
                "SELECT run_id, coalesce(step, ''), coalesce(rule, 'error'), count(*) FROM failed_record "
                "WHERE run_kind = 'workflow' AND status = 'held' AND run_id = ANY(:k) GROUP BY 1, 2, 3 ORDER BY 4 DESC, 3"
            ),
            {"k": list(wf_of)},
        ).all():
            d = held.setdefault((wf_of[rid], step), {})
            d[rule] = d.get(rule, 0) + n
    out = {}
    for wid, rs in by.items():
        durs = [float(r["dur"]) for r in rs if r.get("dur") is not None]
        ok = sum(1 for r in rs if r["state"] != "failed")
        order: list[str] = []  # the newest run's steps first, then those only older runs had
        for r in reversed(rs):
            order += [k for k in r.get("steps") or {} if k not in order]
        order += [st for (w, st) in held if w == wid and st not in order]
        labels: dict[str, str] = {}
        for r in rs:
            labels |= r.get("labels") or {}
        steps = []
        for sid in order:
            sd = [float(r["steps"][sid]) for r in rs if (r.get("steps") or {}).get(sid) is not None]
            h = dict(sorted(held.get((wid, sid), {}).items(), key=lambda kv: (-kv[1], kv[0])))
            steps.append({"id": sid, "label": labels.get(sid) or sid or "—", "p95": p95(sd), "held": h, "heldN": sum(h.values())})
        out[wid] = {
            "runs": len(rs), "ok": ok, "success": js_round(ok / len(rs) * 100), "p95": p95(durs),
            "avg": round(sum(durs) / len(durs), 2) if durs else None, "lastState": rs[-1]["state"], "steps": steps,
        }  # fmt: skip
    return out


# ---------------------------------------------------------------- the run views' figures (plan 6 follow-up)
_SEEDED_RUNS = {r["id"]: r for r in GOLDEN["runs"]}  # the demo's S.wf.runs, as seeded (keyed by their ids)
# a held record counted once however many of its fields broke a rule (the canonical step holds one row per fact)
_HELD_RECORDS = "count(DISTINCT coalesce(resource, '') || '/' || coalesce(ext_id, 'row:' || id::text))"


def keyed_runs(s: Session, wid: str) -> list[tuple[str, dict]]:
    """The workflow's run records with their keys (the run id their held records are filed under), newest first."""
    state.get(s, "workflow_runs", "")  # seeds the collection on its first read
    rows = s.execute(
        text("SELECT id, data FROM state_item WHERE collection = 'workflow_runs' AND data->>'wf' = :w ORDER BY seq DESC"),
        {"w": wid},
    ).all()
    return [(r.id, r.data) for r in rows]


def seeded_run(key: str, r: dict) -> bool:
    """A run record of the demo's seeded history (never ran in the app), as it was seeded."""
    return _SEEDED_RUNS.get(key) == r


def held_records(s: Session, keys: list[str]) -> dict[str, int]:
    """The records each workflow run (by key) still holds in failed_record (status 'held'), one per record."""
    if not keys:
        return {}
    q = text(
        f"SELECT run_id, {_HELD_RECORDS} FROM failed_record WHERE run_kind = 'workflow' AND status = 'held' "  # noqa: S608 - a fixed expression
        "AND run_id = ANY(:k) GROUP BY 1"
    )
    return {k: int(n) for k, n in s.execute(q, {"k": keys}).all()}


def run_figures(s: Session, runs: list[tuple[str, dict]]) -> list[dict]:
    """What the Runs table shows for each run (key, record), in order: a seeded run `{"real": False}` (the page keeps
    the demo's estimate, as the Monitor keeps its seeded figures); a run in progress no figures yet; a finished run the
    records it read (`in`), the records it still holds (`held`, as View failed records and the Data quality panel count
    them) and `out` = in - held (None for a failed run, which did not finish its records)."""
    held = held_records(s, [k for k, r in runs if not seeded_run(k, r)])
    out: list[dict] = []
    for k, r in runs:
        if seeded_run(k, r):
            out.append({"real": False})
        elif r.get("state") == "running":
            out.append({"real": True, "key": k, "in": None, "out": None, "held": None})
        else:
            rows, n = r.get("rows"), held.get(k, 0)
            passed = None if r.get("state") == "failed" or rows is None else max(0, int(rows) - n)
            out.append({"real": True, "key": k, "in": rows, "out": passed, "held": n})
    return out


def run_quality(s: Session, w: dict) -> dict | None:
    """The Data quality panel and the Investigation's held records: the latest real run (`lastRun.key`), the records it
    read, still holds and passed, and its held records by step, field and rule (most first, at most 8). None when the
    latest run is seeded (never ran in the app)."""
    lr = w.get("lastRun") or {}
    key = lr.get("key")
    if not key:
        return None
    rec = state.get(s, "workflow_runs", str(key))
    last = w.get("last") or {}
    rows = rec.get("rows") if rec else last.get("rows") if last.get("ts") == lr.get("ts") else None
    held = held_records(s, [str(key)]).get(str(key), 0)
    by = {n["id"]: n for n in (w.get("graph") or {}).get("nodes") or []}
    groups = s.execute(
        text(
            f"SELECT coalesce(step, '') AS step, coalesce(field, '') AS field, coalesce(rule, 'error') AS rule, "  # noqa: S608 - a fixed expression
            f"{_HELD_RECORDS} AS n FROM failed_record WHERE run_kind = 'workflow' AND status = 'held' AND run_id = :k "
            "GROUP BY 1, 2, 3 ORDER BY 4 DESC, 2, 3, 1 LIMIT 8"
        ),
        {"k": str(key)},
    ).mappings()
    return {
        "real": True, "key": key, "run": lr.get("id"), "state": lr.get("status"), "in": rows, "held": held,
        "valid": max(0, rows - held) if rows is not None else None,
        "groups": [{"step": g["step"], "label": _step_label(by.get(g["step"]), g["step"]), "field": g["field"] or "—",
                    "rule": g["rule"], "n": int(g["n"])} for g in groups],
    }  # fmt: skip


def _step_label(n: dict | None, step: str) -> str:
    if n is not None:
        from di.workflow.engine import label

        return label(n)
    return "Canonical model" if step == "canonical" else step or "—"


def _shown(v: Any) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else json.dumps(v, default=str)


def failed_rows(w: dict, counts: dict[str, dict] | None = None, s: Session | None = None) -> list[dict]:  # noqa: ARG001
    """The records the latest run held (failed_record under the run's key), oldest first, at most 40: the record, the
    field, its real value, the rule it broke and why. None for a workflow that has not really run, or without a
    session. `counts` is accepted for the callers of the demo's frFailedRows and not needed."""
    key = (w.get("lastRun") or {}).get("key")
    if s is None or not key:
        return []
    rows = s.execute(
        text(
            "SELECT ext_id, resource, field, value, rule, reason, step FROM failed_record WHERE run_kind = 'workflow' "
            "AND run_id = :k AND status = 'held' ORDER BY id LIMIT 40"
        ),
        {"k": str(key)},
    ).mappings()
    return [
        {"rec": r["ext_id"] or "—", "field": r["field"] or "—", "value": _shown(r["value"]), "rule": r["rule"] or "error",
         "reason": r["reason"], "resource": r["resource"], "step": r["step"]}
        for r in rows
    ]  # fmt: skip
