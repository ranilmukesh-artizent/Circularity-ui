"""Workflow Studio (#/integration/studio): the workflow list, its run history and one workflow with its graph (B14).

    GET /api/screens/workflows?cat=&status=&src=&q=   the list (filtered), the status counts, the recent runs and what
                                                      needs attention
    GET /api/screens/workflows/blocks                 the block catalogue: every palette block's settings (plan 6 C1)
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
- endpoint GET /api/screens/workflows/blocks: blockSpecs, blockResources
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
- the controls the demo kept in browser memory, now actions (di/actions/workflows.py): saveAsTemplate
  (workflow.saveTemplate; the list's `templates`, S.frTpl, empty at the start), createFromTemplate (workflow.create
  with `tpl`), the run settings Retries and Alert when (workflow.save with `retries` and `alert`), reprocessFailed
  (workflow.reprocess), applySuggestedFix (workflow.applyFix); exportJson is built in the browser from this read
"""

import json

from fastapi import APIRouter, HTTPException

from di import clock, state
from di.auth import Principal
from di.deps import CurrentPrincipal, DbSession
from di.engine.jsmath import js_round
from di.reads.common import AS_OF, SOURCES, hash_id, ms, to_fixed
from di.reads.workflows import GOLDEN, all_workflows, failed_rows, recent_runs, run_counts, templates, wf_stat

router = APIRouter(prefix="/api/screens/workflows", tags=["screens: workflows"])

# wfBuild(tpl): the template graphs, keyed by template (a pure function of the template and the source reference)
_TEMPLATES = {json.dumps(w["tpl"], sort_keys=True): GOLDEN["detail"][w["id"]]["template"] for w in GOLDEN["starting"]}
_LIST_HIDDEN = ("graph", "saved", "tpl")  # the list leaves the graph out; GET /{id} has it


def require_studio(p: Principal) -> None:
    p.require_page("integration", "studio")


def template(tpl: dict | None, saved: list[dict] | None = None) -> dict | None:
    """wfBuild(tpl): the recorded template graph, or (for a template no starting workflow uses, such as a new blank
    pipeline) the port in di.actions.workflows. A workflow created from a saved template ({k: "tpl", id}) resets to
    that template's graph, from `saved` (the demo gives it {k: "none"}, which resets it to an empty canvas)."""
    if tpl and tpl.get("k") == "tpl":
        return next((t["tpl"] for t in saved or [] if t["id"] == tpl.get("id")), {"nodes": [], "edges": []})
    t = _TEMPLATES.get(json.dumps(tpl, sort_keys=True))
    if t is None and tpl:
        from di.actions.workflows import build

        t = build(tpl)
    return t


# ---------------------------------------------------------------- the collections


# ---------------------------------------------------------------- ports of the demo's helpers


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
    if (cat and w["cat"] != cat) or (status and wf_stat(w) != status) or (src and w.get("src") != src):
        return False
    if q:
        vendor = SOURCES.get(w.get("src") or "", {}).get("vendor", "") if w.get("src") else ""
        return q.strip().lower() in f"{w['name']} {w['id']} {w['owner']} {vendor}".lower()
    return True


# ---------------------------------------------------------------- endpoints
@router.get("")
def workflow_list(
    p: CurrentPrincipal,
    session: DbSession,
    cat: str | None = None,
    status: str | None = None,
    src: str | None = None,
    q: str | None = None,
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
        "templates": [{k: v for k, v in t.items() if k != "tpl"} for t in templates(session)],  # S.frTpl, no graphs
        "now": ms(clock.now().isoformat()),  # the workspace clock, which run times are on (the frontend's "ago")
    }


@router.get("/blocks")
def workflow_blocks(p: CurrentPrincipal):
    """The block catalogue (di/workflow/blocks.py, plan 6 C1): every palette block's settings, with their defaults and
    choices, and each connection's resources (the choices of a connector's Resources setting)."""
    require_studio(p)
    from di.workflow.blocks import catalogue

    return {"blocks": catalogue(), "resources": _resources()}


def _resources() -> dict[str, list[str]]:
    """The resources each source's adapter reads (none for a source without an adapter)."""
    try:
        from di.connectors.registry import ADAPTERS
    except Exception:  # noqa: BLE001 - the catalogue stands without the adapters
        return {}
    out: dict[str, list[str]] = {}
    for sid, a in ADAPTERS.items():
        try:
            out[sid] = [r.name for r in a.resources()]
        except Exception:  # noqa: BLE001 - one adapter that cannot list its resources leaves only its own list empty
            out[sid] = []
    return out


@router.get("/{workflow_id}")
def workflow_detail(workflow_id: str, p: CurrentPrincipal, session: DbSession):
    require_studio(p)
    w = state.get(session, "workflows", workflow_id)
    if w is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No workflow {workflow_id}."})
    c = run_counts(w)
    saved = json.loads(w["saved"]) if w.get("saved") else None
    tpl = w.get("tpl")
    return {
        "workflow": w | {"stat": wf_stat(w)},
        "saved": saved
        and {"graph": saved["g"], "name": saved["m"]["name"], "owner": saved["m"]["owner"], "trig": saved["m"]["trig"]}
        | {k: saved["m"][k] for k in ("retries", "alert") if k in saved["m"]},  # the run settings, once saved
        "template": template(tpl, templates(session) if tpl and tpl.get("k") == "tpl" else None),
        "history": history(w, recent_runs(session)),
        "run_counts": c,
        "run_from_last": run_from_last(w),
        "failed_rows": failed_rows(w, c),
        "success_pct": js_round(w["okN"] / w["runsN"] * 100) if w.get("runsN") else None,
    }
