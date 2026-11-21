"""Workflow Studio (#/integration/studio): the workflow list, its run history and one workflow with its graph (B14).

    GET /api/screens/workflows?cat=&status=&src=&q=   the list (filtered), the status counts, the recent runs and what
                                                      needs attention
    GET /api/screens/workflows/blocks                 the block catalogue: every palette block's settings (plan 6 C1)
    GET /api/screens/workflows/{id}                   one workflow: its graph, the saved version, the template graph,
                                                      the run history, records in and out of each step in the last run,
                                                      the last run as the canvas paints it, and its failed records;
                                                      its versions and the published one (plan 6 C8)
    GET /api/screens/workflows/{id}/compare?a=&b=     what changed from version a to version b (default: current)

Both need the Workflow Studio section of the Connection Fabric (`integration/studio`: Admin and Developer); other
accounts get 403 `out_of_scope`, as the actions do.

Where the data comes from. The demo keeps its workflows and their runs in browser memory (`S.wf`), seeded with
Math.random on first use. Here they are two workspace collections (di.state), seeded from the demo's starting values
as fixtures/golden/screens/workflows.json recorded them (apps/web/scripts/golden/fabric.mjs):
- "workflows": `S.wf.list`, each with its graph already built from its template (what opening it does);
- "workflow_runs": `S.wf.runs`, the recent runs, newest first.
The workflow actions (di/actions/workflows.py, B15) write them; runs are worker jobs that write their progress into the
run record. What is computed here, from the collections, is ported from
the demo: the status (wfStat), the history (frWfHistory, without the runs it derived: only runs that happened, plan 6
C8), the step counts (frRunCounts), the last run on the canvas
(wfRunFromLast), the failed records (frFailedRows) and the attention list (frWfAttn). Times are the demo's clock
(the as-of time), as the seeded runs are. The attention list's stale sources and the search by a system's vendor read
the sources as they are now (di/workflow/live.py: a catalogue or hand-made source too, an expired one listed), which
for the seeded workspace are the demo's reference, so the studio stays at parity with the demo.

The actions the facade invokes (workflow.save, publish, setStatus, create, duplicate, delete, run and the read
workflow.validate) are in di/actions/workflows.py (B15).

Facade (apps/web/src/api/workflows.ts) → here, export by export:

- endpoint GET /api/screens/workflows: workflows, workflow, recentRuns (`runs`), wfStat (`workflows[].stat`),
  attention, nowMs (`now`, the workspace clock the run times are on)
- endpoint GET /api/screens/workflows/{id}: graphOf (`workflow.graph`), savedOf (`saved`), templateOf (`template`),
  history, runCounts for the last run (`run_counts`), runFromLast (`run_from_last`), failedRows (`failed_rows`),
  versions, publishedVersion (`published_ver`), runFigures (`run_figures`: per history entry the run's real in / out /
  held, or `{"real": false}` for a seeded run, whose figures stay the demo's estimate in the page), runQuality
  (`quality`: the latest real run's records read, held and passed and its held records by step, field and rule; None
  when the last run is seeded)
- endpoint GET /api/screens/workflows/{id}/compare: compareVersions; action workflow.restore: restoreVersion
- endpoint GET /api/screens/workflows/blocks: blockSpecs, blockResources, blockOperations (`operations`)
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
from di.actions.workflow_drafts import draft_for
from di.auth import Principal
from di.deps import CurrentPrincipal, DbSession
from di.engine.jsmath import js_round
from di.reads.common import AS_OF, SOURCES, hash_id, iso, ms
from di.reads.workflows import (
    GOLDEN,
    all_workflows,
    failed_rows,
    keyed_runs,
    recent_runs,
    run_counts,
    run_figures,
    run_quality,
    templates,
    wf_stat,
)
from di.workflow import live, versions

router = APIRouter(prefix="/api/screens/workflows", tags=["screens: workflows"])

# wfBuild(tpl): the template graphs, keyed by template (a pure function of the template and the source reference)
_TEMPLATES = {json.dumps(w["tpl"], sort_keys=True): GOLDEN["detail"][w["id"]]["template"] for w in GOLDEN["starting"]}
_LIST_HIDDEN = ("graph", "saved", "tpl", "pub")  # the list leaves the graph out; GET /{id} has it
_HIDDEN = ("pub",)  # the published version's graph: the detail gives its number (`published_ver`) instead


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


def history(w: dict, runs: list[dict]) -> list[dict]:
    """The runs of the workflow that happened, latest first (plan 6 C8): its run records, or, when it has none, its
    recorded last run. The demo's frWfHistory added up to 30 earlier runs derived from the workflow's counts (hashed
    times, durations and failures); those never happened, so they are gone."""
    real = [
        {k: x[k] for k in ("id", "ts", "state", "dur", "rows", "trig", "note")} | {"real": True}
        for x in runs
        if x["wf"] == w["id"]
    ]
    last = w.get("last")
    if real or not last:
        return real
    lr = w.get("lastRun")
    return [
        {
            "id": lr["id"] if lr else "RUN-" + hash_id(w["id"])[:5],
            "ts": last["ts"],
            "state": last["state"],
            "dur": last["dur"],
            "rows": last["rows"],
            "trig": lr["trig"] if lr else "Schedule",
            "note": last["note"],
        }
    ]


def figures(session, w: dict, runs: list[tuple[str, dict]]) -> list[dict]:
    """The Runs table's figures, one per `history` entry (di.reads.workflows.run_figures): from the run records, or for
    the recorded last run that history lists without one, real only when that run happened in the app (has a key)."""
    if runs:
        return run_figures(session, runs)
    last, lr = w.get("last"), w.get("lastRun") or {}
    if not last:
        return []
    if lr.get("key"):
        return run_figures(session, [(str(lr["key"]), last | {"wf": w["id"]})])
    return [{"real": False}]


def attention(workflows: list[dict], now: int = AS_OF, sources: dict[str, dict] | None = None) -> list[dict]:
    """frWfAttn: failing workflows, expired source credentials (the stale sources: `sources`, the sources as they are
    now, di/workflow/live.py, which for the seeded workspace are the demo's; default the demo's reference), high failure
    rates."""
    o = []
    for w in workflows:
        if wf_stat(w) == "failing":
            s = (w["last"].get("note") or "Last run failed") + " · " + fr_ago(now - w["last"]["ts"])
            o.append({"ic": "alert", "h": "alert", "t": w["name"], "s": s, "arg": "run|" + w["id"], "go": w["id"]})
    for src in (SOURCES if sources is None else sources).values():
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


def _matches(w: dict, cat: str | None, status: str | None, src: str | None, q: str | None, lv: dict[str, dict]) -> bool:
    """frWfFilter: type, status (with failing), system and a search over name, id, owner and the system's vendor (the
    sources as they are now, `lv`: a catalogue or hand-made source's vendor too)."""
    if (cat and w["cat"] != cat) or (status and wf_stat(w) != status) or (src and w.get("src") != src):
        return False
    if q:
        vendor = lv.get(w.get("src") or "", {}).get("vendor", "") if w.get("src") else ""
        return q.strip().lower() in f"{w['name']} {w['id']} {w['owner']} {vendor}".lower()
    return True


def _upstream(w: dict, lv: dict[str, dict]) -> dict:
    """{"upstream": "paused"} when the workflow's source is paused in the Connection Fabric (the list's "Paused
    upstream", plan 6 C10); nothing otherwise, so the seeded workspace answers as the demo does."""
    s = lv.get(w.get("src") or "")
    return {"upstream": "paused"} if s and s.get("paused") else {}


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
    lv = live.sources(session)  # plan 6 C10: the sources as they are now (paused, disconnected ...)
    rows = [
        {k: v for k, v in w.items() if k not in _LIST_HIDDEN} | {"stat": wf_stat(w)} | _upstream(w, lv)
        for w in wl
        if _matches(w, cat, status, src, q, lv)
    ]
    return {
        "live": live.overlay(lv),  # the browser's checks read the sources' status from here, as the server's do
        "workflows": rows,
        "counts": counts(wl),
        "runs": recent_runs(session),
        "attention": attention(wl, sources=lv),  # a stale catalogue source too; the seeded workspace: the demo's
        "templates": [{k: v for k, v in t.items() if k != "tpl"} for t in templates(session)],  # S.frTpl, no graphs
        "now": ms(clock.now().isoformat()),  # the workspace clock, which run times are on (the frontend's "ago")
    }


@router.get("/blocks")
def workflow_blocks(p: CurrentPrincipal):
    """The block catalogue (di/workflow/blocks.py, plan 6 C1): every palette block's settings, with their defaults and
    choices, each connection's resources (the choices of a connector's Resources setting) and each target system's
    write operations (the choices of a write connector's Target operation, di/instructions/writers.py; a target not
    listed takes none)."""
    require_studio(p)
    from di.instructions.writers import SYSTEM_OF, operations
    from di.workflow.blocks import catalogue

    ops = {sid: operations(sid) for sid in dict.fromkeys(SYSTEM_OF.values())}
    return {"blocks": catalogue(), "resources": _resources(), "operations": ops}


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
    runs = keyed_runs(session, w["id"])
    return {
        "workflow": {k: v for k, v in w.items() if k not in _HIDDEN}
        | {"stat": wf_stat(w)}
        | _upstream(w, live.sources(session)),  # plan 6 C10: "Paused upstream"
        "saved": saved
        and {"graph": saved["g"], "name": saved["m"]["name"], "owner": saved["m"]["owner"], "trig": saved["m"]["trig"]}
        | {k: saved["m"][k] for k in ("retries", "alert") if k in saved["m"]},  # the run settings, once saved
        "template": template(tpl, templates(session) if tpl and tpl.get("k") == "tpl" else None),
        "history": history(w, [r for _, r in runs]),
        "run_figures": figures(session, w, runs),  # one per history entry: in / out / held of the runs that happened
        "run_counts": c,
        "run_from_last": run_from_last(w),
        "failed_rows": failed_rows(w, c, session),  # the latest run's held records (failed_record, plan 6 C5)
        "quality": run_quality(session, w),  # the latest real run's figures and held records by rule, or None
        "success_pct": js_round(w["okN"] / w["runsN"] * 100) if w.get("runsN") else None,
        "versions": versions.listing(session, w, iso),  # plan 6 C8: every version, newest first
        "published_ver": (w.get("pub") or {}).get("ver"),  # the version runs use (None: not published)
        "draft": draft_for(session, w["id"], p.account.id),  # plan 6 C9: this person's autosaved working copy, or None
    }


@router.get("/{workflow_id}/compare")
def workflow_compare(workflow_id: str, a: str, p: CurrentPrincipal, session: DbSession, b: str | None = None):
    """The History tab's Compare (plan 6 C8): what changed from version `a` to version `b` (default: the current one),
    blocks added, removed and changed (with each changed setting), links added and removed, and changed settings."""
    require_studio(p)
    w = state.get(session, "workflows", workflow_id)
    if w is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No workflow {workflow_id}."})
    from di.actions.workflows import label, live_sources

    b = b or w["ver"]
    va, vb = versions.resolve(session, w, a), versions.resolve(session, w, b)
    if va is None or vb is None:
        ver = a if va is None else b
        raise HTTPException(404, {"code": "not_found", "message": f"No version {ver} of {w['name']}."})
    with live_sources(session):  # a source made in the Connection Fabric by its name
        return versions.diff(va, vb, label)
