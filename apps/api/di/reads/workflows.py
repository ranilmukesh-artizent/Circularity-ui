"""The Workflow Studio's collections and the demo's workflow helpers, read by the studio and integration screens and the
workflow actions (di.actions.workflows): the workspace collections "workflows" (S.wf.list, each with its graph) and
"workflow_runs" (S.wf.runs), seeded from fixtures/golden/screens/workflows.json, and "workflow_templates" (S.frTpl,
empty at the start); wfStat, wfUsing, wfAnalyze, wfOrder; and what the last real run counted and held (plan 6 C5)."""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di import golden, state

GOLDEN = golden.load("screens/workflows")
state.register("workflows", lambda: [(w["id"], w) for w in GOLDEN["starting"]])
# S.wf.runs is newest first; the collection keeps insertion order, so it is seeded oldest first and read newest first
state.register("workflow_runs", lambda: [(r["id"], r) for r in reversed(GOLDEN["runs"])])
# S.frTpl: the templates saved from workflows (workflow.saveTemplate), oldest first; none at the start
state.register("workflow_templates", lambda: [])


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
