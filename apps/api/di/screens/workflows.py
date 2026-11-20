"""Workflow Studio (#/integration/studio): the workflow list, its run history and one workflow with its graph (B14).

    GET /api/screens/workflows?cat=&status=&src=&q=   the list (filtered), the status counts, the recent runs and what
                                                      needs attention
    GET /api/screens/workflows/{id}                   one workflow: its graph, the saved version, the template graph,
                                                      the run history, records in and out of each step in the last run,
                                                      the last run as the canvas paints it, and its failed records

Both need the Workflow Studio section of the Connection Fabric (`integration/studio`: Admin and Developer); other
accounts get 403 `out_of_scope`, as the actions do.

Where the data comes from. The demo keeps its workflows and their runs in browser memory (`S.wf`), seeded with
Math.random on first use. Here they are two workspace collections (di.state), seeded from the demo's starting values
as fixtures/golden/screens/workflows.json recorded them (apps/web/scripts/golden/fabric.mjs):
- "workflows": `S.wf.list`, each with its graph already built from its template (what opening it does);
- "workflow_runs": `S.wf.runs`, the recent runs, newest first.
The workflow actions (di/actions/workflows.py, B15) write them; runs are worker jobs that write their progress into the
run record. What is computed here, from the collections, is ported from
the demo: the status (wfStat), the history (frWfHistory), the step counts (frRunCounts), the last run on the canvas
(wfRunFromLast), the failed records (frFailedRows) and the attention list (frWfAttn). Times are the demo's clock
(the as-of time), as the seeded runs are. The attention list's stale sources and the failed records' field names come
from the demo's source reference (sources.json, canonical.json mappings), so the studio stays at parity with the demo
until workflows run on the synced sources.

The actions the facade invokes (workflow.save, publish, setStatus, create, duplicate, delete, run and the read
workflow.validate) are in di/actions/workflows.py (B15).

Facade (apps/web/src/api/workflows.ts) → here, export by export:

- endpoint GET /api/screens/workflows: workflows, workflow, recentRuns (`runs`), wfStat (`workflows[].stat`),
  attention, nowMs (`now`, the workspace clock the run times are on)
- endpoint GET /api/screens/workflows/{id}: graphOf (`workflow.graph`), savedOf (`saved`), templateOf (`template`),
  history, runCounts for the last run (`run_counts`), runFromLast (`run_from_last`), failedRows (`failed_rows`)
- endpoint GET /api/screens/integration/sources: usedBy (`health.workflows`), sources, source, sourceExists,
  sourceLabel, sourceShortLabel, channelsOf (`health.channels`), readableSources, writableSources,
  sourceCompleteness (`compl`), systemOf
- reference: mapTarget, mappings, deliverOf, deliverMap, CH, sourceCategoryLabel, transforms, frTransforms, actTypes,
  tools, agentsUsing, fixedStep, sourceGroups, sourceCats, RUN_LABEL, RUN_CHIP, NOWF, statusPill, templates (S.frTpl,
  empty at the start)
- frontend-only (formatting, canvas view): trigText, ageShort, ago, hashId, runErrors, edgePath, WF_W, WF_H, WF_WH,
  worldWidth, logoHtml, nodeIconHtml, iconTileHtml, statusChipHtml, setOpenWorkflow, stepInfo
- frontend-only (checks and the test-run simulation on the unsaved draft the canvas holds; the saved graph's checks
  are the read action workflow.validate): validate, canLink, runOrder, analyze, evalStep, runTimes, runCounts with a
  draft's test-run states
- actions (di/actions/workflows.py): saveWorkflow, publishWorkflow, setWorkflowStatus, createWorkflow,
  duplicateWorkflow, deleteWorkflow, runWorkflow (a worker job; progress as `workflow` stream events), validateSaved
- browser-only view flags in the demo (not journaled there), need actions before B17: exportJson, saveAsTemplate,
  applySuggestedFix, reprocessFailed, setRunSetting
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from di import clock, golden, state
from di.auth import Principal, principal
from di.db import get_session
from di.engine.jsmath import js_round
from di.reads.common import AS_OF, SOURCES, STARTING_MAPPINGS, hash_id, ms, to_fixed

router = APIRouter(prefix="/api/screens/workflows", tags=["screens: workflows"])

_GOLDEN = golden.load("screens/workflows")
state.register("workflows", lambda: [(w["id"], w) for w in _GOLDEN["starting"]])
# S.wf.runs is newest first; the collection keeps insertion order, so it is seeded oldest first and read newest first
state.register("workflow_runs", lambda: [(r["id"], r) for r in reversed(_GOLDEN["runs"])])
# wfBuild(tpl): the template graphs, keyed by template (a pure function of the template and the source reference)
_TEMPLATES = {json.dumps(w["tpl"], sort_keys=True): _GOLDEN["detail"][w["id"]]["template"] for w in _GOLDEN["starting"]}
_FAILED_RULES = [
    "Required field is empty",
    "Date is not in ISO 8601",
    "Unknown status code",
    "Currency has no dated rate",
    "Value outside allowed range",
    "Duplicate key in this batch",
]
_FAILED_VALUE = {
    "Required field is empty": "",
    "Date is not in ISO 8601": "31/13/2026",
    "Unknown status code": "ZZ",
    "Currency has no dated rate": "1250 XAU",
    "Value outside allowed range": "-4",
}
_LIST_HIDDEN = ("graph", "saved", "tpl")  # the list leaves the graph out; GET /{id} has it


def require_studio(p: Principal) -> None:
    p.require_page("integration", "studio")


def template(tpl: dict | None) -> dict | None:
    """wfBuild(tpl): the recorded template graph, or (for a template no starting workflow uses, such as a new blank
    pipeline) the port in di.actions.workflows."""
    t = _TEMPLATES.get(json.dumps(tpl, sort_keys=True))
    if t is None and tpl:
        from di.actions.workflows import build

        t = build(tpl)
    return t


# ---------------------------------------------------------------- the collections
def all_workflows(s: Session) -> list[dict]:
    return state.items(s, "workflows")


def recent_runs(s: Session) -> list[dict]:
    return state.items(s, "workflow_runs", newest_first=True)


# ---------------------------------------------------------------- ports of the demo's helpers
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


def fr_ago(ms: float) -> str:
    """frAgo: "4 min ago"."""
    s = max(0, js_round(ms / 1000))
    if s < 60:
        return f"{s} sec ago"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 172800:
        return f"{s // 3600} h ago"
    return f"{s // 86400} days ago"


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


def _rej(w: dict, rows: float) -> int:
    return max(1, js_round(rows * (0.004 + (int(hash_id(w["id"] + "rej"), 16) % 9) / 1000)))


def run_counts(w: dict) -> dict[str, dict]:
    """frRunCounts: records in and out of each step in the last run (validation rejects a fixed share)."""
    g = w.get("graph") or {"nodes": [], "edges": []}
    by, _, pred = _analyze(g)
    last = w.get("last")
    rows = last["rows"] if last else 0
    st = (w.get("lastRun") or {}).get("states") or {}
    rej = _rej(w, rows)
    o: dict[str, dict] = {}
    for i in _order(g):
        n = by[i]
        ps = [(o[p]["out"] if p in o else 0) or 0 for p in pred[i]]
        if n["k"] == "conn":
            inn = rows
        elif n["ref"] == "x_err":
            first = o.get(pred[i][0]) if pred[i] else None
            inn = (first["rej"] if first else 0) or 0
        else:
            inn = max([0, *ps, 0])
        s = st.get(i)
        out = 0 if s in ("failed", "upstream_failed", "skipped") else inn
        r = 0
        if n["k"] == "xf" and n["ref"] == "x_val" and s != "failed":
            r = min(rej, inn)
            out = inn - r
        o[i] = {"in": inn, "out": out, "rej": r}
    return o


def run_from_last(w: dict) -> dict | None:
    """wfRunFromLast: the last real run as the canvas paints it."""
    lr = w.get("lastRun")
    if not lr:
        return None
    ids = {n["id"] for n in (w.get("graph") or {"nodes": []})["nodes"]}
    return {
        "status": "success" if lr["status"] == "warning" else lr["status"],
        "warn": lr["status"] == "warning",
        "states": dict(lr["states"]),
        "dur": lr["dur"],
        "order": [i for i in lr["order"] if i in ids],
        "i": len(lr["order"]),
        "approved": True,
        "t0": lr["t0"],
        "id": lr["id"],
        "trig": lr["trig"],
    }


def history(w: dict, runs: list[dict], now: int = AS_OF) -> list[dict]:
    """frWfHistory: every run of the workflow, latest first: its real runs, then earlier ones derived from its counts."""
    real = [
        {k: x[k] for k in ("id", "ts", "state", "dur", "rows", "trig", "note")} | {"real": True}
        for x in runs
        if x["wf"] == w["id"]
    ]
    last = w.get("last")
    if not last:
        return real
    t = w["trig"].get("t")  # a saved trigger may be empty ({}): then it counts as hourly, as in the demo
    every = (w["trig"]["min"] if t == "schedule" else 10 if t == "event" else 60) * 60000
    n = min(30, w.get("runsN") or 0)
    bad = js_round((1 - w["okN"] / w["runsN"]) * n) if w.get("runsN") else 0
    out = list(real)
    lr = w.get("lastRun")
    k = 1
    while len(out) < n:
        h = int(hash_id(f"{w['id']}h{k}"), 16)
        ts = (real[-1]["ts"] if real else last["ts"]) - k * every
        if ts > now:
            k += 1
            continue
        failed = k <= bad and h % 3 == 0
        out.append(
            {
                "id": "RUN-" + hash_id(f"{w['id']}r{k}")[:5],
                "ts": ts,
                "state": "failed" if failed else "success",
                "dur": float(to_fixed((last.get("dur") or 2) * (0.8 + (h % 40) / 100), 1)),
                "rows": js_round((last.get("rows") or 100) * (0.9 + (h % 20) / 100)),
                "trig": lr["trig"] if lr else "Schedule",
                "note": "Validation: schema drift" if failed else "",
            }
        )
        k += 1
    if not real:
        out.insert(
            0,
            {
                "id": lr["id"] if lr else "RUN-" + hash_id(w["id"])[:5],
                "ts": last["ts"],
                "state": last["state"],
                "dur": last["dur"],
                "rows": last["rows"],
                "trig": lr["trig"] if lr else "Schedule",
                "note": last["note"],
            },
        )
    return sorted(out, key=lambda r: -r["ts"])  # stable, as the demo's sort


def failed_rows(w: dict, counts: dict[str, dict] | None = None) -> list[dict]:
    """frFailedRows: the invalid rows of the latest run, with the field and the rule each broke."""
    m = STARTING_MAPPINGS.get(w.get("src") or "", [])
    c = counts if counts is not None else run_counts(w)
    n = min(40, next((x["rej"] for x in c.values() if x["rej"] > 0), 0))
    out = []
    for i in range(n):
        f = m[i % len(m)] if m else ["record_id", "—"]
        h = int(hash_id(f"{w['id']}f{i}"), 16)
        rule = _FAILED_RULES[h % len(_FAILED_RULES)]
        out.append(
            {
                "rec": (w.get("src") or "rec").upper() + "-" + str(10000 + h % 89999),
                "field": f[0],
                "value": _FAILED_VALUE.get(rule, str(f[1])),
                "rule": rule,
            }
        )
    return out


def attention(workflows: list[dict], now: int = AS_OF) -> list[dict]:
    """frWfAttn: failing workflows, expired source credentials (the demo's stale sources), high failure rates."""
    o = []
    for w in workflows:
        if wf_stat(w) == "failing":
            s = (w["last"].get("note") or "Last run failed") + " · " + fr_ago(now - w["last"]["ts"])
            o.append({"ic": "alert", "h": "alert", "t": w["name"], "s": s, "arg": "run|" + w["id"], "go": w["id"]})
    for src in SOURCES.values():
        if src["status"] == "stale":
            o.append(
                {
                    "ic": "key",
                    "h": "dec",
                    "t": src["vendor"],
                    "s": "Authentication expired · " + src["fresh"],
                    "arg": "source|" + src["id"],
                }
            )
    for w in workflows:
        if (w.get("runsN") or 0) >= 10 and w["okN"] / w["runsN"] < 0.9 and wf_stat(w) != "failing":
            pct = js_round(100 - w["okN"] / w["runsN"] * 100)
            o.append(
                {
                    "ic": "activity",
                    "h": "dec",
                    "t": w["name"],
                    "s": f"High failure rate ({pct}%)",
                    "arg": "run|" + w["id"],
                    "go": w["id"],
                }
            )
    return o


def counts(workflows: list[dict]) -> dict:
    """The list's tiles (frWfTiles): totals by status, and how many source systems the workflows cover."""
    c = dict.fromkeys(("published", "draft", "paused", "failing"), 0)
    for w in workflows:
        c[wf_stat(w)] += 1
    return {"total": len(workflows), **c, "systems": len({w["src"] for w in workflows if w.get("src")})}


def _matches(w: dict, cat: str | None, status: str | None, src: str | None, q: str | None) -> bool:
    """frWfFilter: type, status (with failing), system and a search over name, id, owner and the system's vendor."""
    if cat and w["cat"] != cat or status and wf_stat(w) != status or src and w.get("src") != src:
        return False
    if q:
        vendor = SOURCES.get(w.get("src") or "", {}).get("vendor", "") if w.get("src") else ""
        return q.strip().lower() in f"{w['name']} {w['id']} {w['owner']} {vendor}".lower()
    return True


# ---------------------------------------------------------------- endpoints
@router.get("")
def workflow_list(
    cat: str | None = None,
    status: str | None = None,
    src: str | None = None,
    q: str | None = None,
    p: Principal = Depends(principal),
    session: Session = Depends(get_session),
):
    require_studio(p)
    wl = all_workflows(session)
    rows = [
        {k: v for k, v in w.items() if k not in _LIST_HIDDEN} | {"stat": wf_stat(w)}
        for w in wl
        if _matches(w, cat, status, src, q)
    ]
    return {
        "workflows": rows,
        "counts": counts(wl),
        "runs": recent_runs(session),
        "attention": attention(wl),
        "now": ms(clock.now().isoformat()),  # the workspace clock, which run times are on (the frontend's "ago")
    }


@router.get("/{workflow_id}")
def workflow_detail(workflow_id: str, p: Principal = Depends(principal), session: Session = Depends(get_session)):
    require_studio(p)
    w = state.get(session, "workflows", workflow_id)
    if w is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No workflow {workflow_id}."})
    c = run_counts(w)
    saved = json.loads(w["saved"]) if w.get("saved") else None
    return {
        "workflow": w | {"stat": wf_stat(w)},
        "saved": saved
        and {"graph": saved["g"], "name": saved["m"]["name"], "owner": saved["m"]["owner"], "trig": saved["m"]["trig"]},
        "template": template(w.get("tpl")),
        "history": history(w, recent_runs(session)),
        "run_counts": c,
        "run_from_last": run_from_last(w),
        "failed_rows": failed_rows(w, c),
        "success_pct": js_round(w["okN"] / w["runsN"] * 100) if w.get("runsN") else None,
    }
