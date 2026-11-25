"""Workflow Studio actions (docs/backend-steps.md, B15 part 2): workflow.save, publish, setStatus, create, duplicate,
delete and run, and the read workflow.validate; and three the demo ran in the browser without an action, declared
here beside the catalog: workflow.saveTemplate (frWfTpl), workflow.reprocess (frReproc), workflow.applyFix
(frFixApply); and workflow.restore (plan 6 C8). workflow.save also takes the Settings tab's run settings (`retries`,
`alert`: frWfSet) and workflow.create a saved template (`tpl`: frTplUse). Runs use the retries and raise the alert the
settings ask for.

Ports of the demo's handlers (index.html, `defAction('workflow.save', ...)` and the ones after it) and of what they call:
the template graphs (wfBuild with the Connection Fabric's extra branches), the checks (wfValidate, with the Fabric's
override for start and branch steps); runs go through the workflow engine (di/workflow/engine.py). They write the two
workspace collections the Workflow Studio reads (di/services/screens/workflows.py): "workflows" (S.wf.list) and
"workflow_runs" (S.wf.runs). The pipeline has validated the input and checked the permission; the guards here are the
demo's, in its order. None of the workflow actions has an idempotency key in the demo; repeats are refused by state
(already published, already running).

**Runs are worker jobs, and they are real (plan 6 C5, C7).** workflow.run marks the workflow running, adds a run
record in state "running" to "workflow_runs" and queues a `workflow.run` job; the action returns at once with the
demo's output ({id, name}) plus `run`, the run record's key. The job (`run_job`, registered in di/worker.py) runs the
version that runs (graph_for_run) through the engine (di.workflow.engine.run_graph): connectors read the source,
mapping and canonical steps write the canonical store, transforms change the records, rejected records are held in
failed_record. After each state change the run record is written with the states so far and the real records in and
out of the finished steps; each write is a commit, so it reaches GET /api/stream as a `workflow` event (migration
0009). At the end the workflow gets its last run (`last`, `lastRun` with the real states, per-step durations, counts,
tries and the run key its held records are filed under) and the run record takes the demo's shape {id, wf, name, ts,
trig, dur, rows, state, note}. Durations and record counts are measured, no longer drawn (decision D-Fabric).

**One run at a time; retries.** The job holds the workflow's run lock (RUN_LOCK) for the whole run: a second job of
the same workflow is dropped (its record removed), Run now is refused while a run is queued or going (run_active),
and a run that crashes is closed as failed. A worker that dies loses the lock with its connection; the next Run now
closes that run as "Failed: worker lost" (reap_lost_run). A step that raises is tried again the workflow's Retries
times (1 s, 2 s, 4 s ... apart); the tries are kept per step for the run table's Try column.

**Block settings (plan 6 C2).** A node may carry `cfg`, the settings of its block (di/workflow/blocks.py) that differ
from the defaults; save, publish and create store only those (blocks.compact_graph), so a graph whose settings are all
the defaults is the demo's graph. The checks add one error per bad setting, naming the block and the field
(cfg_checks); save keeps a bad setting, publish refuses it (its guard counts the errors).

**Versions, reprocess and the fix (plan 6 C8).** Every save, publish, restore and applied fix keeps the version it makes
(graph and settings) in "workflow_versions" (di/workflow/versions.py); workflow.restore puts an earlier one back as a
new version. A published workflow carries the version that was published (`pub`), and runs use it (graph_for_run,
settings_for_run) while a person saves drafts; a published workflow whose saved version is newer can be published
again. workflow.reprocess sends the held records back through the engine from the step that rejected them;
workflow.applyFix gives the failed step its settings from the last good version, with a text that says what changed.

**Not ported.** The demo's manual run of an ingest workflow starts a simulated sync of its source (startSync) and
bumps the Command Centre's hourly health bar (hhBump). Here the run itself reads the source and writes the canonical
store (under the source's sync lock, from its cursors), but records no sync_run row; the health bars are fixed.

**Times.** The workspace clock (di/core/clock.py, `ctx.now`): pinned to the demo's as-of time in the tests, as the demo's
Date.now() is in its sandbox.
"""

import copy
import json
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]  # no stubs in the dev lock
from sqlalchemy import text

from di.core import clock, jobs, policy, state
from di.repositories import workflows as studio
from di.repositories.common import SOURCES, hash_id, iso, ms
from di.repositories.constants import MAP_TARGET, MAPPINGS, SRC_TYPES, TOOLS
from di.repositories.reference import channels, lists
from di.services.actions.decisions import NOTE_SEQ_START, rb_log
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.engine.jsmath import js_round
from di.workflow import binding, blocks, triggers, versions
from di.workflow.schema import STEP_KINDS, workflow_schema

log = logging.getLogger("di.workflows")
_REF = lists()
XF: list[dict] = [*_REF["XF"], *blocks.PALETTE]  # plus the blocks the demo has no tile for (plan 8: Open case)
FR_XF: list[dict] = [*_REF["FR_XF"], *blocks.PALETTE]
FXD: dict[str, dict] = _REF["FXD"]
ACT_TYPES: list[dict] = _REF["ACT_TYPES"]
DELIVER: dict[str, list] = _REF["DELIVER"]
CH_ARR: dict[str, str] = _REF["CH_ARR"]
CH_DEL: dict[str, str] = _REF["CH_DEL"]
SH: dict[str, str] = _REF["SH"]

RUNS_KEPT = 40  # S.wf.runs.length = Math.min(S.wf.runs.length, 40)
# the Settings tab's run settings (frWfSet): retries default 3, alert default "A run fails"
RETRIES = (0, 1, 3, 5)
ALERTS = ("A run fails", "Two runs fail in a row", "Success rate drops below 95%", "Never")
ALERT_TO = "developer"  # who a workflow alert is addressed to (Admin sees every notification too)


# ---------------------------------------------------------------- actions the demo's catalog does not name
# The demo ran these controls in the browser without an action (ACT.frWfTpl, frReproc, frFixApply, frWfSet). Here every
# write goes through the pipeline, so they are declared beside the catalog's 76: the same permission as the other
# workflow actions (manageWorkflows; the demo adds them to PERM_ACTS.manageWorkflows), journaled like them.
def _declare(action_id: str, title: str, desc: str, inp: dict[str, dict[str, Any]]) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(
            id=action_id, title=title, desc=desc, risk="act", perm="manageWorkflows", scope="none", input=inp,
            verb="change workflows",
        ),
    )  # fmt: skip


_ID = {"id": {"req": True, "t": "string"}}
_declare("workflow.saveTemplate", "Save workflow as template", "Save a workflow's graph as a template for New workflow.", _ID)
_declare("workflow.reprocess", "Reprocess failed records", "Send the records the latest run held back through validation.", _ID)
_declare("workflow.applyFix", "Apply the suggested fix", "Apply the suggested fix for the step the last run failed at.", _ID)
_declare(
    "workflow.restore", "Restore a workflow version", "Put an earlier version's graph and settings back as a new version.",
    _ID | {"ver": {"req": True, "t": "string"}},
)  # fmt: skip
ACTIONS["workflow.save"].input |= {"retries": {"req": False, "t": "number"}, "alert": {"req": False, "t": "string"}}
ACTIONS["workflow.create"].input |= {"tpl": {"req": False, "t": "string"}}
# the canvas' test run (wfStep): a step that runs shows "running" for 320 ms; one that does nothing takes 25 ms.
# Tests set both to 0.
STEP_SECONDS = 0.32
QUICK_SECONDS = 0.025
QUICK = ("upstream_failed", "waiting", "skipped")

# the demo's ordering rules for agent tools on a decision canvas (WF_TR) and the names of the steps they cite (WF_NM)
WF_TR = {
    "get_case_evidence": {"after": ["evid"], "why": "It reads the case evidence bundle, so it follows Case evidence."},
    "find_demand": {
        "after": ["evid"],
        "before": ["gates"],
        "why": "Demand fit is gate 4, so demand has to be found before the gates run.",
    },
    "request_missing_evidence": {
        "after": ["evid"],
        "before": ["gates"],
        "why": "Missing evidence has to be requested before the gates, or the route is withheld.",
    },
    "list_eligible_routes": {"after": ["gates"], "why": "Only the gates decide which routes are eligible."},
    "predict_outcomes": {"after": ["gates"], "why": "Predictions run only on routes that passed all six gates."},
    "optimize_pool": {
        "after": ["gates"],
        "before": ["appr"],
        "why": "Allocation works on eligible routes, and nothing is committed until a person approves.",
    },
    "get_model_validation": {"after": ["gates"], "why": "Model validation is read alongside predictions, after the gates."},
    "request_approval": {
        "after": ["gates"],
        "before": ["appr"],
        "why": "Recommendations go to a person, so this tool has to feed Human approval.",
    },
    "send_instruction": {
        "after": ["appr", "c_dec"],
        "why": "Instructions go out only after a person approves and the Decision record carries the approval reference.",
    },
    "reconcile_outcome": {
        "after": ["c_out"],
        "why": "Reconciliation links actuals to the decision, so it follows returned outcomes.",
    },
}
WF_NM = {
    "evid": "Case evidence",
    "gates": "Six eligibility gates",
    "appr": "Human approval",
    "c_dec": "Decision",
    "c_out": "Outcome",
}
XFORM = {
    "oms": "x_utc", "tms": "x_units", "eam": "x_units", "eng": "x_units", "esg": "x_units", "erp": "x_fx", "proc": "x_fx",
    "mkt": "x_fx", "dlr": "x_fx", "repair": "x_fx", "crm": "x_utc", "lease": "x_utc", "fsm": "x_utc", "rl": "x_utc",
    "wms": "x_utc", "insp": "x_lookup", "qms": "x_lookup", "rcy": "x_lookup",
}  # fmt: skip
CANON_FIX = {
    "Asset & component": "c_asset",
    "Condition & eligibility": "c_cond",
    "Demand opportunity": "c_dem",
    "Outcome": "c_out",
}
WF_DEC = {
    "standard": {
        "name": "Standard six-gate decision",
        "desc": "Evidence, gates, routes and predictions, a recommendation to a person, then the approved instruction and "
        "the returned outcome.",
    },
}
TRIG_L: dict[str, Callable[[dict], str]] = {
    "schedule": lambda t: f"Every {t.get('min')} min",
    "event": lambda t: "On event",  # noqa: ARG005 - every trigger label takes the trigger
    "approval": lambda t: "On approval",  # noqa: ARG005 - every trigger label takes the trigger
    "manual": lambda t: "Manual",  # noqa: ARG005 - every trigger label takes the trigger
    "case": lambda t: "On case request",  # noqa: ARG005 - every trigger label takes the trigger
    "file": lambda t: "On file arrival",  # noqa: ARG005 - every trigger label takes the trigger
}


# ---------------------------------------------------------------- small ports
# The sources the checks read (plan 6 C10): the demo's reference, or, while `validate(..., s=session)` runs, the
# sources as they are now (di/workflow/live.py: paused, disconnected, failing ... over the demo's statuses). The field
# mappings likewise. Set per call (a context variable), so the ports below keep their signatures.
_LIVE: ContextVar[dict[str, dict] | None] = ContextVar("workflow_live_sources", default=None)
_LIVE_MAPS: ContextVar[dict[str, list] | None] = ContextVar("workflow_live_mappings", default=None)


def src(sid: str | None) -> dict | None:
    """SRC: the source (the demo's SOURCES, or the live sources while the checks read them)."""
    if not isinstance(sid, str):
        return None
    lv = _LIVE.get()
    return (lv if lv is not None else SOURCES).get(sid)


def _maps() -> dict[str, list]:
    lm = _LIVE_MAPS.get()
    return lm if lm is not None else MAPPINGS


def src_or(sid: str) -> dict:
    """srcOr: the source, or what a deleted one looks like."""
    return src(sid) or {
        "id": sid, "name": SH.get(sid) or "Deleted source", "vendor": "Deleted", "status": "unavailable", "mode": "—",
        "auth": "—", "read": [], "write": [], "cat": "internal", "fresh": "—", "deleted": True, "authority": [],
    }  # fmt: skip


@contextmanager
def live_sources(s: Any) -> Iterator[None]:
    """src() reads the sources as they are now (di/workflow/live.py) while the block runs: New workflow does, so a
    source connected from the catalogue or made by hand gets a workflow too (and a deleted one none). A demo source
    that people have not changed is the demo's reference record itself, so its workflow is built as before."""
    from di.workflow import live

    tok = _LIVE.set(live.sources(s))
    try:
        yield
    finally:
        _LIVE.reset(tok)


def src_or_live(sid: str, s: Any) -> dict | None:
    """The source as it is now (di/workflow/live.py): a demo source as src() has it, one connected from the catalogue
    or made by hand too; None for an unknown or deleted one. For callers outside an action (the worker's triggers)."""
    with live_sources(s):
        return src(sid)


def label_in(n: dict, sources: dict[str, dict] | None) -> str:
    """label(n) with the sources as `sources` (di/workflow/live.py `sources`) has them: a source connected from the
    catalogue or made by hand by its own name, one deleted in the Connection Fabric "Deleted source". None: the
    sources the context reads (the demo's reference outside live_sources). For whatever names a step outside the
    checks: run notes, the Monitor's step labels, Compare, Reprocess and Apply fix."""
    if sources is None:
        return label(n)
    tok = _LIVE.set(sources)
    try:
        return label(n)
    finally:
        _LIVE.reset(tok)


def made_here_lookups(sources: dict[str, dict]) -> dict[str, dict]:
    """For each source made in the Connection Fabric, what the demo's MAP_TARGET and DELIVER do not know: the canonical
    model its field mapping feeds (`target`, map_target) and how it accepts instructions (`deliver`). The browser's
    checks read them from the workflow list's `live` overlay, so they agree with these."""
    tok = _LIVE.set(sources)
    try:
        return {sid: {"target": map_target(sid), "deliver": deliver(sid)} for sid in sources if made_here(sid)}
    finally:
        _LIVE.reset(tok)


def made_here(sid: str) -> bool:
    """A source the demo does not know (connected from the catalogue or made by hand) that exists now."""
    return sid not in SOURCES and src(sid) is not None


def sh(sid: str) -> str | None:
    """SH: the demo's short name of a source, or the name of one made in the Connection Fabric."""
    return (src(sid) or {}).get("name") if made_here(sid) else SH.get(sid)


def map_target(sid: str) -> str | None:
    """MAP_TARGET: the canonical model a source's field mapping feeds. A source made in the Connection Fabric feeds
    its type's target when that is a canonical step (CANON_FIX), else Outcome."""
    if not made_here(sid):
        return MAP_TARGET.get(sid)
    from di.repositories.fabric import type_of

    t = type_of(str((src(sid) or {}).get("type") or ""))["target"]
    return t if t in CANON_FIX else "Outcome"


def deliver(sid: str) -> list:
    """DELIVER: how a source accepts instructions. A source made in the Connection Fabric with write operations takes
    API calls (its POST operations)."""
    if made_here(sid):
        return ["api"] if (src(sid) or {}).get("write") else []
    return DELIVER.get(sid) or []


def trig_text(t: dict) -> str:
    kind: Any = t.get("t")
    return TRIG_L.get(kind, TRIG_L["manual"])(t)


def _xf(ref: str) -> dict | None:
    return next((x for x in XF if x["id"] == ref), None)


def _xf_req(ref: str) -> dict[str, Any]:
    """The transform a graph step names (the palette offers only known ones)."""
    x = _xf(ref)
    if x is None:
        raise LookupError(f"unknown transform {ref}")
    return x


def _fr_xf(ref: str) -> dict | None:
    return next((x for x in FR_XF if x["id"] == ref), None)


def label(n: dict) -> str:
    """wfInfo(n).label."""
    k, ref = n["k"], n["ref"]
    if k == "fixed":
        return FXD[ref]["label"]
    if k in ("conn", "wconn"):
        s = src_or(ref)
        return "Deleted source" if s.get("deleted") else SH.get(ref, s["name"])
    if k == "act":
        return next(t for t in ACT_TYPES if t["id"] == ref)["label"]
    if k == "xf":
        return _xf_req(ref)["label"]
    if k == "map":
        return f"{sh(ref)} fields"
    t = next((x for x in TOOLS if x["id"] == ref), None)
    return t["id"] if t else ref


def snap(w: dict) -> str:
    """wfSnap: the saved snapshot, as the demo's JSON.stringify writes it."""
    m = {"name": w.get("name"), "owner": w.get("owner"), "trig": w.get("trig")}
    m |= {k: w[k] for k in ("retries", "alert") if k in w}  # the run settings, once a person has saved them
    return json.dumps({"g": w.get("graph"), "m": m}, separators=(",", ":"), ensure_ascii=False)


def bump(w: dict) -> None:
    """wfBump: 1.4 -> 1.5."""
    a, _, b = str(w["ver"]).partition(".")
    b = b.split(".")[0]
    w["ver"] = f"{a}.{(int(b) if b.isdigit() else 0) + 1}"


# ---------------------------------------------------------------- template graphs (wfBuild)
def _n(nid: str, k: str, ref: str, x: float, y: float, cfg: dict | None = None) -> dict:
    """A graph node. `cfg`: the block's settings (di/workflow/blocks.py); only those that differ from the defaults are
    kept, and a node with none has no `cfg` (so the template graphs stay the demo's)."""
    return blocks.compact_cfg({"id": nid, "k": k, "ref": ref, "x": x, "y": y, "cfg": cfg})


def _e(a: str, b: str, locked: bool = False) -> dict:
    return {"a": a, "b": b, "locked": bool(locked)}


def _tail(nodes: list, edges: list, req_from: str) -> None:
    nodes += [
        _n("appr", "fixed", "appr", 24, 400),
        _n("c_dec", "fixed", "c_dec", 262, 400),
        _n("tl_send_instruction", "tool", "send_instruction", 500, 400),
        _n("c_out", "fixed", "c_out", 738, 400),
        _n("tl_reconcile_outcome", "tool", "reconcile_outcome", 976, 400),
    ]
    edges += [
        _e(req_from, "appr"),
        _e("appr", "c_dec", True),
        _e("c_dec", "tl_send_instruction"),
        _e("tl_send_instruction", "c_out"),
        _e("c_out", "tl_reconcile_outcome"),
    ]


def _ingest(sid: str) -> dict:
    """bIngest, with the Fabric's error handler, audit log and event-stream branches."""
    s, nodes, edges, y0 = src_or(sid), [], [], 170
    ch = channels(s)
    xs = [24]

    def col() -> int:
        c = xs[0]
        xs[0] += 206
        return c

    nodes.append(_n("r", "conn", sid, col(), y0))
    prev = ["r"]
    file_only = "file" in ch and "api" not in ch and "event" not in ch
    if file_only:
        for i, r in enumerate(["x_trig", "x_unzip", "x_chunk"]):
            nodes.append(_n(f"f{i}", "xf", r, col(), y0))
            edges.append(_e(prev[0], f"f{i}"))
            prev = [f"f{i}"]
    else:
        rs = (["x_gw"] if "api" in ch else []) + (["x_evt"] if "event" in ch else [])
        cx, ids, use = col(), [], rs or ["x_gw"]
        for i, r in enumerate(use):
            nid = f"ig{i}"
            nodes.append(_n(nid, "xf", r, cx, y0 - 80 + i * 160 if len(use) > 1 else y0))
            edges.append(_e("r", nid))
            ids.append(nid)
        prev = ids
    nodes.append(_n("v", "xf", "x_val", col(), y0))
    edges += [_e(p, "v") for p in prev]
    prev = ["v"]
    stype: Any = s.get("type")
    xf = not file_only and XFORM.get(stype)
    if xf:
        nodes.append(_n("t", "xf", xf, col(), y0))
        edges.append(_e("v", "t"))
        prev = ["t"]
    nodes.append(_n("m", "map", sid, col(), y0))
    edges.append(_e(prev[0], "m"))
    c: Any = CANON_FIX.get(MAP_TARGET.get(sid) or "Outcome")
    nodes.append(_n(c, "fixed", c, col(), y0))
    edges.append(_e("m", c))
    if c != "c_out" and not file_only:
        nodes.append(_n("snap", "fixed", "snap", col(), y0))
        edges.append(_e(c, "snap", True))
    by = {n["id"]: n for n in nodes}
    v, m = by.get("v"), by.get("m")
    cn = next((n for n in nodes if n["k"] == "fixed" and FXD[n["ref"]].get("canon")), None)
    if v:
        nodes.append(_n("err", "xf", "x_err", v["x"], v["y"] + 170))
        edges.append(_e("v", "err"))
    if m:
        nodes.append(_n("aud", "xf", "x_audit", m["x"], m["y"] + 170))
        edges.append(_e("m", "aud"))
    if cn and cn["ref"] != "c_out":
        nodes.append(_n("pub", "xf", "x_pub", cn["x"], cn["y"] - 150))
        edges.append(_e(cn["id"], "pub"))
    return {"nodes": nodes, "edges": edges}


def _outbound(sid: str, ch: str | None) -> dict:
    """bOut, with the Fabric's audit-log branch."""
    xs, y0 = [24, 230, 436, 642, 848, 1054, 1260, 1466], 200
    rec = {"api": "a_api", "event": "a_evt", "file": "a_file", "proc": "a_proc"}.get(ch or "", "a_api")
    nodes = [
        _n("c_dec", "fixed", "c_dec", xs[0], y0),
        _n("appr", "fixed", "appr", xs[1], y0),
        _n("t_env", "xf", "x_env", xs[2], y0),
        _n("a", "act", rec, xs[3], y0),
    ]
    edges = [_e("c_dec", "appr", True), _e("appr", "t_env"), _e("t_env", "a")]
    prev, i = "a", 4
    if ch == "file":
        nodes.append(_n("f_man", "xf", "x_man", xs[i], y0))
        i += 1
        edges.append(_e(prev, "f_man"))
        prev = "f_man"
    nodes.append(_n("w", "wconn", sid, xs[i], y0))
    i += 1
    edges.append(_e(prev, "w"))
    nodes.append(_n("c_out", "fixed", "c_out", xs[i], y0))
    edges.append(_e("w", "c_out"))
    if ch == "file":
        nodes += [_n("f_cb", "xf", "x_cb", xs[i], y0 + 170), _n("f_note", "xf", "x_notify", xs[i + 1], y0 + 170)]
        edges += [_e("w", "f_cb"), _e("f_cb", "f_note")]
    nodes.append(_n("aud", "xf", "x_audit", 436, y0 + 170))
    edges.append(_e("t_env", "aud"))
    return {"nodes": nodes, "edges": edges}


def _decision(kind: str) -> dict:
    """WF_DEC[kind].build(), with the Fabric's audit-log branch."""
    head: tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]] = {
        "standard": (
            [("evid", "fixed", "evid", 24, 130), ("gates", "fixed", "gates", 262, 130)]
            + [(f"tl_{t}", "tool", t, x, 130) for t, x in (("list_eligible_routes", 500), ("predict_outcomes", 738))]
            + [("tl_request_approval", "tool", "request_approval", 976, 130)],
            [
                ("evid", "gates", 1),
                ("gates", "tl_list_eligible_routes"),
                ("tl_list_eligible_routes", "tl_predict_outcomes"),
                ("tl_predict_outcomes", "tl_request_approval"),
            ],
        ),
        "pool": (
            [("evid", "fixed", "evid", 24, 130), ("gates", "fixed", "gates", 262, 130)]
            + [(f"tl_{t}", "tool", t, x, 130) for t, x in (("predict_outcomes", 500), ("optimize_pool", 738))]
            + [("tl_request_approval", "tool", "request_approval", 976, 130)],
            [
                ("evid", "gates", 1),
                ("gates", "tl_predict_outcomes"),
                ("tl_predict_outcomes", "tl_optimize_pool"),
                ("tl_optimize_pool", "tl_request_approval"),
            ],
        ),
        "gap": (
            [
                ("evid", "fixed", "evid", 24, 130),
                ("tl_request_missing_evidence", "tool", "request_missing_evidence", 262, 20),
                ("tl_find_demand", "tool", "find_demand", 262, 250),
                ("gates", "fixed", "gates", 500, 130),
                ("tl_list_eligible_routes", "tool", "list_eligible_routes", 738, 130),
                ("tl_request_approval", "tool", "request_approval", 976, 130),
            ],
            [
                ("evid", "gates", 1),
                ("evid", "tl_request_missing_evidence"),
                ("tl_request_missing_evidence", "gates"),
                ("evid", "tl_find_demand"),
                ("tl_find_demand", "gates"),
                ("gates", "tl_list_eligible_routes"),
                ("tl_list_eligible_routes", "tl_request_approval"),
            ],
        ),
    }[kind]
    nodes = [_n(*x) for x in head[0]]
    edges = [_e(*x) for x in head[1]]
    _tail(nodes, edges, "tl_request_approval")
    nodes.append(_n("aud", "xf", "x_audit", 500, 540))
    edges.append(_e("c_dec", "aud"))
    return {"nodes": nodes, "edges": edges}


def build(tpl: dict) -> dict:
    """wfBuild(tpl): the template graph; edges are numbered e0, e1 ... in order."""
    k = tpl.get("k")
    if k == "min":  # a workflow made in New workflow: only the blocks it needs to run (the AI builder's MINIMAL)
        from di.services.actions.workflow_builder import minimal_graph  # imports this module

        return minimal_graph(tpl)
    sid: Any = tpl.get("src")
    ch: Any = tpl.get("ch")
    tid: Any = tpl.get("id")
    g = (
        _ingest(sid)
        if k == "ingest"
        else _outbound(sid, ch)
        if k == "out"
        else _decision(tid)
        if k == "dec"
        else {"nodes": [], "edges": []}
    )
    for i, e in enumerate(g["edges"]):
        e["id"] = f"e{i}"
    return g


def graph_of(w: dict) -> dict:
    """wfGraphOf: the workflow's graph, built from its template (with the saved snapshot) the first time."""
    if not w.get("graph"):
        w["graph"] = build(w.get("tpl") or {})
        w["saved"] = snap(w)
    return w["graph"]


# ---------------------------------------------------------------- the checks (wfValidate with the Fabric's override)
class _Graph:
    """wfAnalyze: nodes by id, successors, predecessors, and what is reachable either way (in the demo's order)."""

    def __init__(self, g: dict):
        self.by, self.succ, self.pred = studio._analyze(g)

    def _reach(self, nid: str, adj: dict) -> list[str]:
        seen: dict[str, None] = {}
        st = [nid]
        while st:
            x = st.pop()
            for y in adj[x]:
                if y not in seen:
                    seen[y] = None
                    st.append(y)
        return list(seen)

    def anc(self, nid: str) -> list[str]:
        return self._reach(nid, self.pred)

    def desc(self, nid: str) -> list[str]:
        return self._reach(nid, self.succ)

    def bypass(self, nid: str, stop: Callable[[dict], bool]) -> bool:
        """wfBypass: a path back to a fixed step that does not pass the step `stop` names."""
        seen, st = set(), [nid]
        while st:
            x = st.pop()
            for y in self.pred[x]:
                if y in seen:
                    continue
                seen.add(y)
                m = self.by[y]
                if stop(m):
                    continue
                if m["k"] == "fixed":
                    return True
                st.append(y)
        return False


_RANK = {"error": 0, "warn": 1, "info": 2}


def _is_xf(m: dict, ref: str) -> bool:
    return m["k"] == "xf" and m["ref"] == ref


def _validate_base(g: dict, kind: str) -> list[dict]:
    A, out = _Graph(g), []

    def add(sev: str, nid: str, msg: str) -> None:
        out.append({"sev": sev, "id": nid, "msg": msg})

    for n in g["nodes"]:
        nid, k, ref = n["id"], n["k"], n["ref"]
        lb, np_, ns = label(n), len(A.pred[nid]), len(A.succ[nid])
        if k in ("conn", "wconn", "map") and not src(ref):
            add(
                "error", nid, f"{SH.get(ref) or 'This source'} was deleted from the Source map. Reconnect it or remove this step."
            )
            continue
        if k == "conn":
            s = src_or(ref)
            if s["status"] == "unavailable":
                add(
                    "error",
                    nid,
                    f"{s['name']} has no connected feed. Circularity will not infer data, so this evidence would be missing.",
                )
            elif s["status"] == "stale":
                add("warn", nid, f"{s['name']} is {s['fresh']} old. Predictions fall back to the last fresh data and say so.")
            elif s["status"] == "manual":
                add("info", nid, f"{s['name']} is a manual import. It supports evaluation, not live automation.")
            if s.get("paused"):  # paused in the Connection Fabric (plan 6 C10)
                add("warn", nid, f"{s['name']} is paused. Runs read nothing from it until it is resumed.")
            st, vis = [(nid, False, False, False)], set[tuple[str, bool, bool, bool]]()
            bad: dict[str, None] = {}
            hit = no_ing = no_val = False
            while st:
                x, vm, vi, vv = st.pop()
                if (x, vm, vi, vv) in vis:
                    continue
                vis.add((x, vm, vi, vv))
                for y in A.succ[x]:
                    m = A.by[y]
                    v2 = vm or m["k"] == "map"
                    i2 = vi or bool(m["k"] == "xf" and _xf_req(m["ref"]).get("ingest"))
                    w2 = vv or _is_xf(m, "x_val")
                    if m["k"] == "fixed":
                        hit = True
                        if not v2 and FXD[m["ref"]].get("canon"):
                            bad[label(m)] = None
                        if v2:
                            no_ing = no_ing or not i2
                            no_val = no_val or not w2
                    else:
                        st.append((y, v2, i2, w2))
            if bad:
                add(
                    "error",
                    nid,
                    f"{s['name']} reaches {', '.join(bad)} without a field mapping. "
                    "Raw vendor values would enter the canonical model.",
                )
            elif not hit:
                add(
                    "warn",
                    nid,
                    f"{s['name']} does not reach a canonical model." if ns else f"{s['name']} is not wired into the workflow.",
                )
            elif no_ing or no_val:
                miss = " or ".join(
                    t for t in ("an ingestion channel" if no_ing else "", "validation and enrichment" if no_val else "") if t
                )
                add(
                    "warn",
                    nid,
                    f"{s['name']} reaches the models without {miss}. "
                    "Access, ordering and bad rows are then not handled in one place.",
                )
        if k == "map":
            anc = [A.by[i] for i in A.anc(nid) if A.by[i]["k"] == "conn"]
            canon = [
                FXD[m["ref"]]["model"] for m in (A.by[i] for i in A.desc(nid)) if m["k"] == "fixed" and FXD[m["ref"]].get("canon")
            ]
            if not np_:
                add("warn", nid, f"{lb} is not fed by a connector.")
            elif not anc:
                add("error", nid, f"{lb} has no connector upstream, so there is nothing to map.")
            elif not any(c["ref"] == ref for c in anc):
                add(
                    "error",
                    nid,
                    f"{lb} is fed by {', '.join(str(sh(c['ref'])) for c in anc)}. Field names would not line up.",
                )
            if not _maps().get(ref):
                add("error", nid, f"No field mapping is defined for {sh(ref)} yet.")
            if not ns:
                add("warn", nid, f"{lb} does not lead to a canonical model.")
            elif canon and map_target(ref) not in canon:
                add("error", nid, f"{lb} maps to {map_target(ref)}, but it is wired to {', '.join(canon)}.")
        if k == "xf":
            x = cast(Any, _xf(ref))  # used only on a wired step
            anc_ids = A.anc(nid)
            anc_n = [A.by[i] for i in anc_ids]
            conns = [m for m in anc_n if m["k"] == "conn"]

            def names(lst: list[dict]) -> str:
                return ", ".join(dict.fromkeys(str(sh(c["ref"])) for c in lst))

            if not np_ or (not ns and ref != "x_notify"):
                add("warn", nid, f"{lb} is not wired between a source and a target.")
            else:
                if x.get("ingest"):
                    bad_c = [
                        c for c in conns if (q := src_or(c["ref"]))["status"] != "unavailable" and x["ingest"] not in channels(q)
                    ]
                    if bad_c:
                        add("error", nid, f"{lb} receives {names(bad_c)}, which does not arrive as {CH_ARR[x['ingest']]}.")
                if x.get("fileIn") and conns and not any("file" in channels(src_or(c["ref"])) for c in conns):
                    add("error", nid, f"{lb} needs a file to work on, but {names(conns)} does not deliver files.")
                if ref == "x_man" and not any(m["k"] == "act" and m["ref"] == "a_file" for m in anc_n):
                    add(
                        "error",
                        nid,
                        "Create manifest follows File generation. The manifest lists the files the target will import.",
                    )
                if ref == "x_cb" and not any(m["k"] == "wconn" for m in anc_n):
                    add(
                        "error", nid, "Fetch import log runs after a target system has imported, so it follows a write connector."
                    )
                if ref == "x_notify" and not any(_is_xf(m, "x_cb") for m in anc_n):
                    add("error", nid, "The notification carries log links, so it follows Fetch import log.")
        if k == "act":
            a = next(t for t in ACT_TYPES if t["id"] == ref)
            anc_ids = A.anc(nid)
            anc_n = [A.by[i] for i in anc_ids]
            dsc = [A.by[i] for i in A.desc(nid) if A.by[i]["k"] == "wconn"]
            if not np_:
                add("warn", nid, f"{lb} is not wired to receive an instruction.")
            elif "appr" not in anc_ids or A.bypass(nid, lambda m: m["id"] == "appr"):
                add(
                    "error",
                    nid,
                    f"{lb} bypasses Human approval. Anything that commits stock, spend or price always stops at a person.",
                )
            elif not any(_is_xf(m, "x_env") for m in anc_n) or A.bypass(nid, lambda m: _is_xf(m, "x_env")):
                add(
                    "error",
                    nid,
                    f"{lb} needs an Instruction envelope upstream, so the receiving system can trace and de-duplicate it.",
                )
            if np_:
                if not dsc:
                    add("warn", nid, f"{lb} does not lead to a system that receives it.")
                for w in dsc:
                    acc = deliver(w["ref"])
                    if a["ch"] not in acc:
                        add(
                            "error",
                            nid,
                            f"{sh(w['ref'])} does not accept {CH_DEL[a['ch']]}. "
                            f"It accepts {', '.join(CH_DEL[c] for c in acc)}.",
                        )
        if k == "wconn":
            s = src_or(ref)
            anc_ids = A.anc(nid)
            anc_n = [A.by[i] for i in anc_ids]
            if s["status"] == "unavailable":
                add("error", nid, f"{s['name']} has no connected system to write to.")
            elif s["status"] == "stale":
                add("warn", nid, f"{s['name']} has an expired token. Instructions would queue until it is refreshed.")
            if not np_:
                add("warn", nid, f"{s['name']} is not wired to receive an instruction.")
            elif "appr" not in anc_ids or A.bypass(nid, lambda m: m["id"] == "appr"):
                add(
                    "error",
                    nid,
                    f"Writes to {s['name']} bypass Human approval. "
                    "Anything that commits stock, spend or price always stops at a person.",
                )
            elif not any(_is_xf(m, "x_env") for m in anc_n) or A.bypass(nid, lambda m: _is_xf(m, "x_env")):
                add(
                    "error",
                    nid,
                    f"Writes to {s['name']} need an Instruction envelope. Without the decision ID and approval reference, "
                    "the receiving system cannot trace or de-duplicate it.",
                )
        if k == "tool":
            r = WF_TR.get(ref)
            if not np_ and not ns:
                add("warn", nid, f"{ref} is not wired in.")
            elif r:
                anc_s, dsc_s = set(A.anc(nid)), set(A.desc(nid))
                after = [i for i in r.get("after", []) if i not in anc_s]
                late = [i for i in r.get("before", []) if i not in dsc_s]
                if after:
                    add("error", nid, f"{ref} has to come after {' and '.join(WF_NM[i] for i in after)}. {r['why']}")
                if late:
                    add("error", nid, f"{ref} has to come before {' and '.join(WF_NM[i] for i in late)}. {r['why']}")
        if k == "fixed" and kind == "pipe" and FXD[ref].get("canon") and ref not in ("c_dec", "c_out") and not np_:
            add("warn", nid, f"Nothing feeds {lb}. AI services will report an evidence gap.")
    if kind == "dec":
        dec = next((n for n in g["nodes"] if n["id"] == "c_dec"), None)
        if dec and not any(A.by[i]["k"] == "tool" and A.by[i]["ref"] == "send_instruction" for i in A.desc("c_dec")):
            add("warn", "c_dec", "The approved decision is not carried out. Add send_instruction after the Decision record.")
    return sorted(out, key=lambda o: _RANK[o["sev"]])


def validate(g: dict, kind: str, s: Any = None) -> list[dict]:
    """wfValidate: errors, warnings and notes, each with the step it belongs to, errors first. With a session `s` the
    checks read the sources and mappings as they are now and check field settings against the fields the source's
    records carry (plan 6 C10, di/workflow/live.py); without one, the demo's reference (the AI builder's plans)."""
    if s is None:
        return _validate(g, kind, None)
    from di.workflow import live

    maps = live.mappings(s)
    t1, t2 = _LIVE.set(live.sources(s)), _LIVE_MAPS.set(maps)
    known: dict[str, set[str] | None] = {}

    def fields_of(sid: str) -> set[str] | None:
        if sid not in known:
            known[sid] = live.fields(s, sid, maps)
        return known[sid]

    try:
        return _validate(g, kind, fields_of)
    finally:
        _LIVE.reset(t1)
        _LIVE_MAPS.reset(t2)


def _validate(g: dict, kind: str, fields_of: Callable[[str], set[str] | None] | None) -> list[dict]:
    out, A = _validate_base(g, kind), _Graph(g)
    by = {n["id"]: n for n in g["nodes"]}

    def keep(o: dict) -> bool:
        n: Any = by.get(o["id"])
        x = n and n["k"] == "xf" and _fr_xf(n["ref"])
        if not x or "not wired between" not in o["msg"]:
            return True
        np_, ns = len(A.pred[n["id"]]), len(A.succ[n["id"]])
        return not ((x.get("start") and ns) or (x.get("sink") and np_))

    out = [o for o in out if keep(o)]
    for n in g["nodes"]:
        if n["k"] != "xf":
            continue
        anc = [A.by[i] for i in A.anc(n["id"])]
        has_pred = bool(A.pred[n["id"]])
        if n["ref"] == "x_err" and has_pred and not any(_is_xf(m, "x_val") for m in anc):
            out.append(
                {
                    "sev": "error",
                    "id": n["id"],
                    "msg": "Error handler receives the records that fail validation, so it follows Validation & enrichment.",
                }
            )
        if n["ref"] == "x_pub" and has_pred and not any(m["k"] == "fixed" and FXD[m["ref"]].get("canon") for m in anc):
            out.append(
                {
                    "sev": "error",
                    "id": n["id"],
                    "msg": "Publish to event stream announces a model update, so it follows a canonical model.",
                }
            )
        x = _fr_xf(n["ref"])
        if x and x.get("start") and has_pred:
            out.append({"sev": "warn", "id": n["id"], "msg": f"{x['label']} starts a workflow, so nothing should feed it."})
    out += cfg_checks(g, fields_of)
    return sorted(out, key=lambda o: _RANK[o["sev"]])


def _fields_for(A: "_Graph", nid: str, fields_of: Callable[[str], set[str] | None]) -> list[str] | None:
    """The field names the records reaching a step carry: those of every read connector upstream of it (sorted), or
    None when it has none or one of them is not known (the field checks are then skipped)."""
    out: set[str] = set()
    conns = [A.by[i]["ref"] for i in A.anc(nid) if A.by[i]["k"] == "conn"]
    for sid in dict.fromkeys(conns):
        f = fields_of(sid)
        if f is None:
            return None
        out |= f
    return sorted(out) if conns else None


def _resources(sid: str) -> list[str] | None:
    """The resources a source's adapter reads, or None (no adapter: not checked)."""
    try:
        from di.connectors.registry import ADAPTERS

        a = ADAPTERS.get(sid)
        return [r.name for r in a.resources()] if a else None
    except Exception:  # noqa: BLE001 - without the adapters the setting is not checked against them
        return None


def cfg_checks(g: dict, fields_of: Callable[[str], set[str] | None] | None = None) -> list[dict]:
    """The block settings' errors (plan 6 C2), one per problem, each naming the block and the field. A node without
    `cfg` has the defaults, which always pass, so the demo's graphs get none. `fields_of(source id)`: the fields a
    source's records carry (plan 6 C10); with it, a field setting naming a field the records lack is an error."""
    out = []
    A = _Graph(g) if fields_of is not None else None
    for n in g["nodes"]:
        if n.get("cfg") is None:
            continue
        try:
            lb = label(n)
        except (LookupError, StopIteration, KeyError):
            lb = n.get("ref") or "This step"
        ctx: dict[str, Any] = {"label": lb}
        if n["k"] == "conn":
            ctx["resources"] = _resources(n["ref"])
        elif A is not None and fields_of is not None and n["id"] in A.by:
            ctx["fields"] = _fields_for(A, n["id"], fields_of)
        out += [{"sev": "error", "id": n["id"], "msg": m} for m in blocks.cfg_errors(n, ctx)]
    return out


def errors(g: dict, kind: str, s: Any = None) -> list[dict]:
    return [e for e in validate(g, kind, s) if e["sev"] == "error"]


# ---------------------------------------------------------------- helpers for the handlers
def _now(ctx: CallContext | None = None) -> int:
    return ms((ctx.now if ctx is not None else clock.now()).isoformat())


def _by(ctx: CallContext) -> str:
    return ctx.actor.account.label if ctx.actor.account else "Enterprise system adapter"


def _get(ctx: CallContext, wid: str, for_update: bool = False) -> dict[str, Any] | None:
    return state.get(ctx.session, "workflows", wid, for_update=for_update)


def _must(ctx: CallContext, wid: str, for_update: bool = False) -> dict[str, Any]:
    """The workflow a handler works on; its guard has already refused one that does not exist."""
    w = _get(ctx, wid, for_update=for_update)
    if w is None:
        raise ActionError("not_found", f"No workflow {wid}.")
    return w


def _put(ctx: CallContext, w: dict[str, Any]) -> None:
    state.put(ctx.session, "workflows", w["id"], w)


def _not_found(i: dict[str, Any]) -> tuple[str, str]:
    return "not_found", f"No workflow {i['id']}."


def _wf_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return None if _get(ctx, i["id"]) else _not_found(i)


def _ids(ctx: CallContext) -> set[str]:
    return {w["id"] for w in studio.all_workflows(ctx.session)}


# ---------------------------------------------------------------- the actions
@guard("workflow.save")
def save_guard(i: dict[str, Any], ctx: CallContext):
    return (
        _wf_guard(i, ctx)
        or _new_decision_draft(i, ctx)
        or (None if i["name"].strip() else ("validation_error", "Enter a workflow name before saving."))
        or _settings_problem(i)
    )


def _new_decision_draft(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    """P9-0.16: a decision workflow that was never published or run is a new draft, and Studio no longer saves those
    (business rules live in the Modeler). The demo's published ones, and any that ran, save, run and export as before."""
    w = _get(ctx, i["id"])
    if w and w.get("kind") == "dec" and w.get("status") == "draft" and not w.get("runsN") and not w.get("pub"):
        return "validation_error", "Decision rules live in the Modeler"
    return None


def _settings_problem(i: dict[str, Any]) -> tuple[str, str] | None:
    """The run settings offer fixed choices (the Settings tab's two selects)."""
    if i.get("retries") is not None and (isinstance(i["retries"], bool) or i["retries"] not in RETRIES):
        return "validation_error", "Retries must be 0, 1, 3 or 5."
    if i.get("alert") is not None and i["alert"] not in ALERTS:
        return "validation_error", "Alert when must be one of: " + ", ".join(ALERTS) + "."
    return None


@implement("workflow.save")
def save(i: dict[str, Any], ctx: CallContext):
    w = _must(ctx, i["id"], for_update=True)
    _before_change(ctx, w)
    w["graph"] = blocks.compact_graph(copy.deepcopy(i["graph"]))  # settings: only those that differ from the defaults
    w["name"] = i["name"].strip()
    if i.get("owner") is not None:
        w["owner"] = i["owner"]
    if i.get("trig") is not None:
        w["trig"] = dict(i["trig"])
    if (blk := triggers.from_graph(w["graph"])) is not None:  # a Scheduler / Event trigger block sets the trigger
        w["trig"] = blk
    if i.get("retries") is not None:
        w["retries"] = int(i["retries"])
    if i.get("alert") is not None:
        w["alert"] = i["alert"]
    bump(w)
    now = _now(ctx)
    w.update(updated=now, dirty=False, warned=False)
    w["saved"] = snap(w)
    w["hist"] = [
        {"ver": w["ver"], "by": _by(ctx), "at": iso(now), "note": i.get("note") or "Saved", "prep": ctx.preparer},
        *(w.get("hist") or []),
    ]
    versions.keep(ctx.session, w, _by(ctx), iso(now), i.get("note") or "Saved")
    _put(ctx, w)
    return {"id": w["id"], "ver": w["ver"], "name": w["name"]}


# ---------------------------------------------------------------- versions (plan 6 C8; di/workflow/versions.py)
def _before_change(ctx: CallContext, w: dict[str, Any]) -> None:
    """Before a change makes a new version: keep the current one, and, for a published workflow that has not recorded
    its published version yet (a starting one), record it, so its runs keep using it while drafts are saved."""
    graph_of(w)
    versions.keep_prior(ctx.session, w, iso)
    if w.get("status") in ("published", "paused") and not w.get("pub"):
        _set_pub(w)


def _set_pub(w: dict[str, Any]) -> None:
    """The version that runs: the workflow as it is now."""
    w["pub"] = {"ver": w["ver"]} | versions.snapshot(w)


def graph_for_run(w: dict[str, Any]) -> dict:
    """The graph a run of the workflow uses: the published version's (kept while drafts are saved), or, for a workflow
    that is not published (a draft tried with Run now), its saved graph."""
    pub = w.get("pub")
    return pub["graph"] if pub else graph_of(w)


def settings_for_run(w: dict[str, Any]) -> dict:
    """The run settings (retries, alert, trigger) of the version that runs."""
    pub = w.get("pub")
    if pub:
        return dict(pub.get("settings") or {})
    return {k: w[k] for k in versions.SETTINGS if w.get(k) is not None}


@guard("workflow.restore")
def restore_guard(i: dict[str, Any], ctx: CallContext):
    w = _get(ctx, i["id"])
    if w is None:
        return _not_found(i)
    if i["ver"] == w["ver"]:
        return "conflict", f"v{i['ver']} is the current version."
    if versions.get(ctx.session, w["id"], i["ver"]) is None:
        return "not_found", f"No version {i['ver']} of {w['name']}."
    return None


@implement("workflow.restore")
def restore(i: dict[str, Any], ctx: CallContext):
    """Restore: the version's graph and settings become the workflow's, as a new version (a draft change: a published
    workflow keeps running its published version until it is published again)."""
    w = _must(ctx, i["id"], for_update=True)
    v = versions.get(ctx.session, w["id"], i["ver"])
    if v is None:  # the guard refused it
        raise ActionError("not_found", f"No version {i['ver']} of {w['name']}.")
    _before_change(ctx, w)
    w["graph"] = copy.deepcopy(v["graph"])
    st = v.get("settings") or {}
    for k in versions.SETTINGS:
        if st.get(k) is not None:
            w[k] = copy.deepcopy(st[k])
        elif k in ("retries", "alert"):
            w.pop(k, None)
    bump(w)
    now = _now(ctx)
    note = f"Restored v{i['ver']}"
    w.update(updated=now, dirty=False, warned=False)
    w["saved"] = snap(w)
    w["hist"] = [{"ver": w["ver"], "by": _by(ctx), "at": iso(now), "note": note, "prep": ctx.preparer}, *(w.get("hist") or [])]
    versions.keep(ctx.session, w, _by(ctx), iso(now), note)
    _put(ctx, w)
    return {"id": w["id"], "name": w["name"], "ver": w["ver"], "from": i["ver"]}


@guard("workflow.publish")
def publish_guard(i: dict[str, Any], ctx: CallContext):
    w = _get(ctx, i["id"])
    if w is None:
        return _not_found(i)
    # a published workflow whose saved version is not the one that runs (plan 6 C8) can publish that version
    if w["status"] == "published" and not (w.get("pub") and w["pub"]["ver"] != w["ver"]):
        return "duplicate", f"{w['name']} is already published"
    n = len(errors(i.get("graph") or graph_of(w), w["kind"], ctx.session))
    return ("conflict", f"Cannot publish: {n} error{'s' if n > 1 else ''} in the checks. Fix them first.") if n else None


@implement("workflow.publish")
def publish(i: dict[str, Any], ctx: CallContext):
    w = _must(ctx, i["id"], for_update=True)
    _before_change(ctx, w)
    gi = blocks.compact_graph(copy.deepcopy(i["graph"])) if i.get("graph") is not None else None
    bumped = False
    if gi is not None and (w.get("dirty") or gi != w.get("graph")):
        w["graph"] = gi
        w["saved"] = snap(w)
        bump(w)
        w["dirty"] = False
        bumped = True
    now = _now(ctx)
    w["status"], w["updated"] = "published", now
    w["hist"] = [{"ver": w["ver"], "by": _by(ctx), "at": iso(now), "note": "Published"}, *(w.get("hist") or [])]
    if bumped:  # a new version; otherwise the saved version, kept already, is the one published
        versions.keep(ctx.session, w, _by(ctx), iso(now), "Published")
    _set_pub(w)
    _put(ctx, w)
    binding.rebind_for(ctx.session, w)  # its source's syncs now run it (plan 6 C5)
    return {"id": w["id"], "ver": w["ver"], "name": w["name"], "trig": trig_text(w["trig"])}


@guard("workflow.setStatus")
def set_status_guard(i: dict[str, Any], ctx: CallContext):
    w = _get(ctx, i["id"])
    if w is None:
        return _not_found(i)
    if i["status"] not in ("draft", "paused", "published"):
        return "validation_error", "Unknown status."
    if i["status"] == "published" and (er := errors(graph_of(w), w["kind"], ctx.session)):
        return "conflict", f"Cannot publish {w['name']}: {er[0]['msg']}"
    return None


@implement("workflow.setStatus")
def set_status(i: dict[str, Any], ctx: CallContext):
    w = _must(ctx, i["id"], for_update=True)
    was = w["status"]
    _before_change(ctx, w)  # a paused or published workflow keeps its published version
    w["status"], w["updated"] = i["status"], _now(ctx)
    if i["status"] == "draft":  # unpublished: nothing is published any more
        w.pop("pub", None)
    elif i["status"] == "published" and was == "draft":  # published from the list: the saved version
        _set_pub(w)
    _put(ctx, w)
    binding.rebind_for(ctx.session, w)  # published: its source syncs with it; paused or draft: no longer (plan 6 C5)
    return {"id": w["id"], "was": was, "status": w["status"], "name": w["name"]}


@guard("workflow.create")
def create_guard(i: dict[str, Any], ctx: CallContext):
    if i.get("tpl") is not None:
        return None if _template(ctx, i["tpl"]) else ("not_found", f"No template {i['tpl']}.")
    if i["type"] not in ("ingest", "out"):
        return None
    with live_sources(ctx.session):  # any source that exists now: the demo's, or one made in the Connection Fabric
        so = src(i.get("src"))
        if not so:
            return "validation_error", "Choose a system first."
        if i["type"] == "out" and made_here(so["id"]) and not deliver(so["id"]):
            return "validation_error", f"{so['name']} takes no instructions. Grant it write access first."
    return None


def _template(ctx: CallContext, tid: str) -> dict | None:
    return state.get(ctx.session, "workflow_templates", tid)


def _interval_min(ctx: CallContext, sid: str) -> int:
    """The sync interval of a source made in the Connection Fabric (source_system), 0 for one that syncs on events."""
    iv = ctx.session.execute(text("SELECT interval_min FROM source_system WHERE id = :i"), {"i": sid}).scalar()
    return int(iv or 0)


@implement("workflow.create")
def create(i: dict[str, Any], ctx: CallContext):
    if i.get("tpl") is not None:
        return _create_from_template(i["tpl"], ctx)
    with live_sources(ctx.session):  # the guard's sources: a source made in the Connection Fabric gets a workflow too
        return _create_new(i, ctx)


def _create_new(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    state.next_number(ctx.session, "workflows", "WF-", 0)  # holds the numbering lock for this transaction
    ids = _ids(ctx)
    k = 100
    while f"WF-{k}" in ids:
        k += 1
    k = max(k, 100 + len(ids))
    while f"WF-{k}" in ids:
        k += 1
    t = i["type"]
    so: Any = src(i.get("src"))  # the guard refused an ingest or outbound workflow without a source
    nm = (i.get("name") or "").strip() or (
        f"Ingest · {so['vendor']}"
        if t == "ingest"
        else f"Outbound · {so['vendor']}"
        if t == "out"
        else "Decision workflow"
        if t == "dec"
        else "New pipeline"
    )
    # New workflow starts from the blocks the workflow needs to run (tpl {k: "min"}), not the demo's full template:
    # the person adds the rest from the palette (decision log, 21 Nov 2026)
    if t == "ingest":
        made = made_here(so["id"])  # made in the Connection Fabric: its schedule and model from source_system, its type
        iv = _interval_min(ctx, so["id"]) if made else so.get("interval")
        trig = {"t": "schedule", "min": iv} if iv else {"t": "event"}
        target = map_target(so["id"]) if made else SRC_TYPES[so["type"]]["target"]
        base = {
            "cat": "Ingest", "kind": "pipe", "src": so["id"], "owner": so["owner"], "trig": trig,
            "tpl": {"k": "min", "type": "ingest", "src": so["id"], "arrive": "event" if trig["t"] == "event" else "api"},
            "desc": f"{so['name']} into the {target} model through validation and field mapping.",
        }  # fmt: skip
    elif t == "out":
        tpl = {"k": "min", "type": "out", "src": so["id"], "ch": i.get("ch") or (deliver(so["id"]) or ["api"])[0]}
        base = {
            "cat": "Outbound", "kind": "pipe", "tpl": tpl, "src": so["id"], "owner": so["owner"], "trig": {"t": "approval"},
            "desc": f"Approved instruction to {so['name']}.",
        }  # fmt: skip
    elif t == "dec":
        base = {
            "cat": "Decision", "kind": "dec", "tpl": {"k": "min", "type": "dec", "id": "standard"}, "src": None,
            "owner": "Decision Services", "trig": {"t": "case"}, "desc": WF_DEC["standard"]["desc"],
        }  # fmt: skip
    else:
        base = {
            "cat": "Ingest", "kind": "pipe", "tpl": {"k": "blank"}, "src": None, "owner": "Unassigned", "trig": {"t": "manual"},
            "desc": "Blank pipeline. Drag steps from the left and connect them.",
        }  # fmt: skip
    w: dict[str, Any] = {
        "id": f"WF-{k}", "name": nm, "status": "draft", "ver": "0.1", "graph": None, "saved": None, "dirty": False,
        "running": False, "updated": _now(ctx), "runsN": 0, "okN": 0, "last": None, "prep": ctx.preparer,
    } | base  # fmt: skip
    if i.get("desc"):
        w["desc"] = i["desc"]
    if i.get("graph") is not None:
        w["graph"] = blocks.compact_graph(copy.deepcopy(i["graph"]))
        w["saved"] = snap(w)
    else:
        graph_of(w)  # what opening it does in the demo: the graph built from its template, and its saved snapshot
    state.add(ctx.session, "workflows", w["id"], w)
    return {"id": w["id"], "name": nm}


@guard("workflow.duplicate")
def duplicate_guard(i: dict[str, Any], ctx: CallContext):
    return _wf_guard(i, ctx)


@implement("workflow.duplicate")
def duplicate(i: dict[str, Any], ctx: CallContext):
    state.next_number(ctx.session, "workflows", "WF-", 0)  # the numbering lock
    w = _must(ctx, i["id"])
    ids = _ids(ctx)
    n = 100
    while f"WF-{n}" in ids:
        n += 1
    c = w | {
        "id": f"WF-{n}", "name": i.get("name") or f"{w['name']} (copy)", "status": "draft", "ver": "0.1",
        "graph": copy.deepcopy(graph_of(w)), "dirty": False, "running": False, "last": None, "runsN": 0, "okN": 0,
        "trig": dict(w["trig"]), "updated": _now(ctx), "warned": False, "hist": [], "prep": ctx.preparer,
    }  # fmt: skip
    c.pop("pub", None)  # a copy is a draft with versions of its own
    c["saved"] = snap(c)
    state.add(ctx.session, "workflows", c["id"], c)
    return {"id": c["id"], "name": c["name"]}


@guard("workflow.delete")
def delete_guard(i: dict[str, Any], ctx: CallContext):
    return _wf_guard(i, ctx)


@implement("workflow.delete")
def delete(i: dict[str, Any], ctx: CallContext):
    w = _must(ctx, i["id"], for_update=True)
    state.delete(ctx.session, "workflows", w["id"])
    binding.rebind_for(ctx.session, w)  # its source no longer syncs with it (plan 6 C5)
    versions.forget(ctx.session, w["id"])  # ids are reused: a new workflow under this id starts without versions
    from di.services.actions import workflow_drafts

    workflow_drafts.forget(ctx.session, w["id"])  # and without anyone's working draft (plan 6 C9)
    return {"id": w["id"], "name": w["name"]}


# ---------------------------------------------------------------- export (plan 9, P9-0.8)
ACTIONS.setdefault(
    "workflow.export",
    ActionDef(
        id="workflow.export", title="Export a workflow", verb="export workflows", risk="read", perm=None, scope="none",
        desc="A workflow as the JSON a workflow export file holds (steps, links and only the settings that differ from "
        "the defaults). Changes nothing; workflow.import reads the same shape.",
        input={"workflow_id": {"req": True, "t": "string"}},
    ),
)  # fmt: skip


def export_json(
    s: Any, workflow_id: str, by: str, at: str, *, published: bool = False, sources: dict[str, dict] | None = None
) -> dict[str, Any] | None:
    """The one workflow export (the browser's Export button, the MCP tool and the org pack share it): the keys of
    exportJson in its order, `cfg` only where a setting differs from its block's default. `published`: the graph runs
    use (the org pack exports what is live), not the saved one. None for an unknown id."""
    w = state.get(s, "workflows", workflow_id)
    if w is None:
        return None
    g = blocks.compact_graph(copy.deepcopy(graph_for_run(w) if published else graph_of(w)))
    live = sources if sources is not None else _live_sources_now(s)
    return {
        "id": w["id"], "name": w["name"], "version": w.get("ver"), "type": w.get("cat"), "status": w.get("status"),
        "owner": w.get("owner"), "trigger": w.get("trig"),
        "source": src_or_in(w["src"], live)["vendor"] if w.get("src") else None,
        "source_id": w.get("src"), "description": w.get("desc"),
        "steps": [{"id": n["id"], "kind": n["k"], "ref": n["ref"], "label": label_in(n, live), "x": n["x"], "y": n["y"]}
                  | ({"cfg": n["cfg"]} if n.get("cfg") else {}) for n in g["nodes"]],
        "links": [{"from": e["a"], "to": e["b"], "fixed": bool(e.get("locked"))} for e in g["edges"]],
        "exported_by": by, "exported_at": at,
    }  # fmt: skip


def _live_sources_now(s: Any) -> dict[str, dict]:
    from di.workflow import live

    return live.sources(s)


def src_or_in(sid: str, sources: dict[str, dict]) -> dict:
    """srcOr with the sources as `sources` has them."""
    tok = _LIVE.set(sources)
    try:
        return src_or(sid)
    finally:
        _LIVE.reset(tok)


@guard("workflow.export")
def export_guard(i: dict[str, Any], ctx: CallContext):
    if not policy.can_page(ctx.actor.account, "integration", "studio"):
        return "out_of_scope", "Not available for this view."
    return None if _get(ctx, i["workflow_id"]) else ("not_found", f"No workflow {i['workflow_id']}.")


@implement("workflow.export")
def export_action(i: dict[str, Any], ctx: CallContext):
    out = export_json(ctx.session, i["workflow_id"], _by(ctx), ctx.now.isoformat())
    if out is None:
        raise ActionError("not_found", f"No workflow {i['workflow_id']}.")
    return out


# ---------------------------------------------------------------- import (plan 6 C10)
# The JSON Export JSON writes (frontend/src/api/workflows.ts exportJson): {name, type, owner, trigger, source,
# source_id, description, steps: [{id, kind, ref, label, x, y, cfg?}], links: [{from, to, fixed}], ...}. It becomes a
# new draft; the steps' blocks and sources must exist (sources as they are now, di/workflow/live.py).
_declare(
    "workflow.import", "Import a workflow", "Create a draft workflow from the JSON a workflow export wrote.",
    {"data": {"req": True, "t": "object"}},
)  # fmt: skip
_KINDS = STEP_KINDS
_CAT_KIND = {"Ingest": "pipe", "Outbound": "pipe", "Decision": "dec"}
Problem = dict[str, str]  # {"path": "steps[2].cfg.interval", "message": ...}
Report = Callable[[str, str], None]


def _known_block(k: str, ref: str) -> bool:
    if k == "xf":
        return _xf(ref) is not None
    if k == "fixed":
        return ref in FXD
    if k == "act":
        return any(t["id"] == ref for t in ACT_TYPES)
    return any(t["id"] == ref for t in TOOLS)  # tool


def _path(error: Any) -> str:
    """`steps[2].cfg.interval` for a schema error's location in the file."""
    out = ""
    for part in error.absolute_path:
        out += f"[{part}]" if isinstance(part, int) else f".{part}" if out else str(part)
    return out


def _schema_problems(data: dict[str, Any]) -> list[Problem]:
    """Pass 1: every way the file departs from the workflow JSON Schema (di/workflow/schema.py), in file order."""
    found: list[Problem] = []
    errors = Draft202012Validator(workflow_schema()).iter_errors(data)
    for e in sorted(errors, key=lambda x: [str(p) for p in x.absolute_path]):
        at = _path(e)
        if e.validator == "required" and isinstance(e.instance, dict):
            names = [n for n in e.validator_value if n not in e.instance]
            found += [{"path": f"{at}.{n}" if at else n, "message": f"'{n}' is a required property"} for n in names]
        else:
            found.append({"path": at, "message": e.message})
    return found


def _import_nodes(steps: list[Any], sources: dict[str, dict], bad: Report) -> list[dict]:
    """The nodes the steps describe; every problem found goes to `bad(path, message)`."""
    nodes: list[dict] = []
    for i, st in enumerate(steps):
        at = f"steps[{i}]"
        if not isinstance(st, dict):
            bad(at, "A step must be an object.")
            continue
        sid, k, ref = st.get("id"), st.get("kind"), st.get("ref")
        if not isinstance(sid, str) or not sid.strip():
            bad(f"{at}.id", "Every step needs an id.")
            continue
        if any(n["id"] == sid for n in nodes):
            bad(f"{at}.id", f"Step {sid} appears twice.")
        if not isinstance(k, str) or k not in _KINDS:
            bad(f"{at}.kind", f"Unknown block {k} in step {sid}.")
        elif not isinstance(ref, str) or not ref:
            bad(f"{at}.ref", f"Step {sid} does not say which block it is.")
        elif k in ("conn", "wconn", "map"):
            if ref not in sources:
                bad(f"{at}.ref", f"Unknown source {ref} in step {sid}.")
        elif not _known_block(k, ref):
            bad(f"{at}.ref", f"Unknown block {ref} in step {sid}.")
        x, y = st.get("x", 0), st.get("y", 0)
        if not all(isinstance(v, int | float) and not isinstance(v, bool) for v in (x, y)):
            bad(at, f"Step {sid} needs a position (x and y).")
        cfg = st.get("cfg")
        if cfg is not None and not isinstance(cfg, dict):
            bad(f"{at}.cfg", f"The settings of step {sid} must be an object.")
        nodes.append({"id": sid, "k": k, "ref": ref, "x": x, "y": y} | ({"cfg": copy.deepcopy(cfg)} if cfg else {}))
    return nodes


def _import_edges(links: list[Any], ids: set[str], bad: Report) -> list[dict]:
    edges: list[dict] = []
    for i, ln in enumerate(links):
        a, b = (ln.get("from"), ln.get("to")) if isinstance(ln, dict) else (None, None)
        for end, v in (("from", a), ("to", b)):
            if v not in ids:
                bad(f"links[{i}].{end}", f"Link {a} → {b} names a step the workflow does not have.")
        edges.append({"id": f"e{i}", "a": a, "b": b, "locked": bool(isinstance(ln, dict) and ln.get("fixed"))})
    return edges


def _import_source(data: dict[str, Any], nodes: list[dict], sources: dict[str, dict], bad: Report) -> str | None:
    conns = [n["ref"] for n in nodes if n["k"] in ("conn", "wconn")]
    sid_given, vendor = data.get("source_id"), data.get("source")
    if isinstance(sid_given, str) and sid_given:
        if sid_given not in sources:
            bad("source_id", f"Unknown source {sid_given}.")
            return None
        return sid_given
    if isinstance(vendor, str) and vendor:
        same = [x for x in sources if sources[x].get("vendor") == vendor]
        if not same:
            bad("source", f"Unknown source {vendor}.")
            return None
        return next((x for x in same if x in conns), same[0])
    return conns[0] if conns else None


def _parse_import(data: dict[str, Any], sources: dict[str, dict]) -> tuple[dict[str, Any] | None, list[Problem]]:
    """Passes 1 and 2: the draft an export describes and every problem with the file (the importer's own checks, whose
    texts name the step, then what the schema adds; a second problem at the same path is dropped). The draft is None
    when there is a problem."""
    problems: list[Problem] = []
    seen: set[str] = set()

    def bad(path: str, message: str) -> None:
        if path not in seen:
            seen.add(path)
            problems.append({"path": path, "message": message})

    steps, links = data.get("steps"), data.get("links", [])
    if not isinstance(steps, list) or not steps:
        bad("steps", "This is not a workflow export: it has no steps.")
    if not isinstance(links, list):
        bad("links", "This is not a workflow export: its links are not a list.")
    nodes = _import_nodes(steps if isinstance(steps, list) else [], sources, bad)
    edges = _import_edges(links if isinstance(links, list) and nodes else [], {n["id"] for n in nodes}, bad)
    src_id = _import_source(data, nodes, sources, bad)
    for p in _schema_problems(data):
        bad(p["path"], p["message"])
    if problems:
        return None, problems
    conns = any(n["k"] == "conn" for n in nodes)
    cat = data.get("type")
    if cat not in _CAT_KIND:
        cat = "Outbound" if any(n["k"] == "wconn" for n in nodes) else "Ingest" if conns else "Decision"
    if _CAT_KIND[cat] == "dec":  # P9-0.17: an import is always a new draft, and Studio makes no decision workflows
        return None, [{"path": "type", "message": "Decision rules live in the Modeler"}]
    t = data.get("trigger")
    trig: dict[str, Any] = {"t": "manual"}
    if isinstance(t, dict) and t.get("t") in TRIG_L:
        trig = {"t": t["t"]}
        if t["t"] == "schedule":
            m = t.get("min")
            trig["min"] = m if isinstance(m, int) and not isinstance(m, bool) and 1 <= m <= 1440 else 60
    so = sources.get(src_id) if src_id else None
    name = str(data.get("name") or "").strip()[:80] or "Imported workflow"
    owner = str(data.get("owner") or "").strip()[:60] or (so or {}).get("owner") or "Unassigned"
    return {
        "name": name, "cat": cat, "kind": _CAT_KIND[cat], "src": src_id, "owner": owner, "trig": trig,
        "desc": str(data.get("description") or "").strip() or "Imported from a workflow export.",
        "graph": {"nodes": nodes, "edges": edges},
    }, []  # fmt: skip


def _graph_problems(draft: dict[str, Any], s: Any) -> list[Problem]:
    """Pass 3: each error `workflow.validate` finds on the graph the import would create, at the step it names."""
    g = blocks.compact_graph(copy.deepcopy(draft["graph"]))
    at = {n["id"]: f"steps[{i}]" for i, n in enumerate(g["nodes"])}
    checks = validate(g, draft["kind"], s)
    return [{"path": at.get(c["id"], "graph"), "message": c["msg"]} for c in checks if c["sev"] == "error"]


def _import_sources(ctx: CallContext) -> dict[str, dict]:
    from di.workflow import live

    return live.sources(ctx.session)


def _import_check(i: dict[str, Any], ctx: CallContext, graph_checks: bool) -> tuple[dict[str, Any] | None, list[Problem]]:
    """The draft the file makes, or every problem with it: schema and the importer's checks, then (the guard asks for
    them; the org pack's import calls the handler for sources that are not connected yet) the graph checks."""
    draft, problems = _parse_import(i["data"], _import_sources(ctx))
    if draft is not None and graph_checks:
        problems = _graph_problems(draft, ctx.session)
    return (None, problems) if problems else (draft, [])


def _refusal(problems: list[Problem]) -> tuple[str, str, dict[str, Any]]:
    n = len(problems)
    head = f"{n} {'problem' if n == 1 else 'problems'} in this file. The first: {problems[0]['message']}"
    return "validation_error", head, {"problems": problems}


@guard("workflow.import")
def import_guard(i: dict[str, Any], ctx: CallContext):
    _, problems = _import_check(i, ctx, True)
    return _refusal(problems) if problems else None


@implement("workflow.import")
def import_workflow(i: dict[str, Any], ctx: CallContext):
    p, problems = _import_check(i, ctx, False)
    if p is None:  # the guard refused it
        raise ActionError(*_refusal(problems))
    state.next_number(ctx.session, "workflows", "WF-", 0)  # the numbering lock
    ids = _ids(ctx)
    n = 100
    while f"WF-{n}" in ids:
        n += 1
    w: dict[str, Any] = {
        "id": f"WF-{n}", "status": "draft", "ver": "0.1", "saved": None, "dirty": False, "running": False,
        "updated": _now(ctx), "tpl": {"k": "blank"}, "runsN": 0, "okN": 0, "last": None, "prep": ctx.preparer,
    } | p  # fmt: skip
    w["graph"] = blocks.compact_graph(w["graph"])
    w["saved"] = snap(w)
    state.add(ctx.session, "workflows", w["id"], w)
    return {"id": w["id"], "name": w["name"]}


# ---------------------------------------------------------------- templates (ACT.frWfTpl, frTplUse)
@guard("workflow.saveTemplate")
def save_template_guard(i: dict[str, Any], ctx: CallContext):
    return _wf_guard(i, ctx)


@implement("workflow.saveTemplate")
def save_template(i: dict[str, Any], ctx: CallContext):
    """frWfTpl: one template per workflow (saving again keeps the first), numbered TPL-1, TPL-2 ... in order."""
    w = _must(ctx, i["id"])
    have = studio.templates(ctx.session)
    t = next((x for x in have if x["from"] == w["id"]), None)
    if t is None:
        t = {
            "id": f"TPL-{len(have) + 1}", "from": w["id"], "name": f"{w['name']} template",
            "tpl": copy.deepcopy(graph_of(w)), "cat": w["cat"], "kind": w["kind"], "src": w.get("src"),
            "owner": w["owner"], "trig": dict(w["trig"]),
        }  # fmt: skip
        state.add(ctx.session, "workflow_templates", t["id"], t)
    rb_log(ctx, "workflow.template.saved", f"{w['id']} · {w['name']}", "workflow.saveTemplate")
    return {"id": t["id"], "name": t["name"], "from": w["id"]}


def _create_from_template(tid: str, ctx: CallContext) -> dict[str, Any]:
    """frTplUse: a draft with the template's graph, system, owner and trigger, under the first free id from WF-100."""
    t = _template(ctx, tid)
    if t is None:  # the guard refused an unknown template
        raise ActionError("not_found", f"No template {tid}.")
    state.next_number(ctx.session, "workflows", "WF-", 0)  # the numbering lock
    ids = _ids(ctx)
    n = 100
    while f"WF-{n}" in ids:
        n += 1
    name = t["name"].removesuffix(" template") + " (from template)"
    w: dict[str, Any] = {
        "id": f"WF-{n}", "status": "draft", "ver": "0.1", "graph": copy.deepcopy(t["tpl"]), "saved": None,
        "dirty": False, "running": False, "updated": _now(ctx), "name": name, "desc": f"Created from {t['name']}.",
        "cat": t["cat"], "kind": t["kind"], "tpl": {"k": "tpl", "id": t["id"]}, "src": t["src"], "owner": t["owner"],
        "trig": dict(t["trig"]), "runsN": 0, "okN": 0, "last": None, "prep": ctx.preparer,
    }  # fmt: skip
    w["saved"] = snap(w)
    state.add(ctx.session, "workflows", w["id"], w)
    return {"id": w["id"], "name": name}


# ---------------------------------------------------------------- failed records (ACT.frReproc)
def _failed_rows(w: dict, s=None) -> list[dict]:
    """The records the latest run held (failed_record, plan 6 C5)."""
    return studio.failed_rows(w, s=s)


REPROCESS_MAX = 2000  # held records sent back in one Reprocess


def _held_of(s, w: dict) -> list[dict]:
    """The records the workflow's runs hold (failed_record, run_kind 'workflow', status 'held'), oldest first: those of
    the runs it still has a record of, and of its last run."""
    state.get(s, "workflow_runs", "")  # seeds the collection on its first read
    keys = set(
        s.execute(
            text("SELECT id FROM state_item WHERE collection = 'workflow_runs' AND data->>'wf' = :w"), {"w": w["id"]}
        ).scalars()
    )
    lr = w.get("lastRun") or {}
    keys |= {str(x) for x in (lr.get("key"), lr.get("id")) if x}
    if not keys:
        return []
    rows = s.execute(
        text(
            "SELECT * FROM failed_record WHERE run_kind = 'workflow' AND status = 'held' AND run_id = ANY(:k) "
            "ORDER BY id LIMIT :n"
        ),
        {"k": sorted(keys), "n": REPROCESS_MAX},
    ).mappings()
    return [dict(r) for r in rows]


def _start_step(g: dict, step: str | None) -> str | None:
    """The step a held record goes back to: the one that rejected it. An error handler that held it took it from the
    step before it; a fact that did not fit its canonical model ("canonical") goes back through the field mapping; a
    canonical step itself needs mapped records, so the mapping before it too."""
    by, _succ, pred = studio._analyze(g)
    if step in by:
        n = by[step]
        if n["k"] == "xf" and n["ref"] == "x_err":
            return pred[step][0] if pred[step] else None
        if n["k"] == "fixed" and (FXD.get(n["ref"]) or {}).get("canon"):
            return next((p for p in pred[step] if by[p]["k"] == "map"), step)
        return step
    if step == "canonical":
        return next((n["id"] for n in g["nodes"] if n["k"] == "map"), None)
    return None


def _from_step(g: dict, start: str, sid: str) -> dict:
    """The part of the graph from `start` on (it and everything after it), fed by a connector node on `sid` that
    replays the held records."""
    _by, succ, _pred = studio._analyze(g)
    keep, st = {start}, [start]
    while st:
        for y in succ[st.pop()]:
            if y not in keep:
                keep.add(y)
                st.append(y)
    nodes = [{"id": "__held", "k": "conn", "ref": sid, "x": 0, "y": 0}] + [
        copy.deepcopy(n) for n in g["nodes"] if n["id"] in keep
    ]
    edges = [{"id": "__e", "a": "__held", "b": start, "locked": False}] + [
        copy.deepcopy(e) for e in g["edges"] if e["a"] in keep and e["b"] in keep
    ]
    return {"nodes": nodes, "edges": edges}


class _Replay:
    """An adapter that reads the held records again (their stored payloads) and maps with the source's own adapter."""

    def __init__(self, rows: list[dict], real: Any):
        self.rows, self.real = rows, real
        self.source_id = getattr(real, "source_id", "")

    def resources(self) -> list:
        from di.connectors.base import Record, Resource

        def reader(name: str):
            def read(_client, _since):
                for r in self.rows:
                    if (r["resource"] or "records") == name:
                        data = r["payload"] if isinstance(r["payload"], dict) else {"value": r["payload"]}
                        yield Record(name, r["ext_id"] or str(r["id"]), dict(data), None, None)

            return read

        return [Resource(n, reader(n), delta=False) for n in dict.fromkeys(r["resource"] or "records" for r in self.rows)]

    def map(self, rec: Any) -> list:
        if self.real is None:
            raise LookupError(f"no field mapping for {self.source_id or 'this source'}")
        return self.real.map(rec)


@guard("workflow.reprocess")
def reprocess_guard(i: dict[str, Any], ctx: CallContext):
    w = _get(ctx, i["id"])
    if w is None:
        return _not_found(i)
    return None if _held_of(ctx.session, w) else ("conflict", "No held records to reprocess.")


@implement("workflow.reprocess")
def reprocess(i: dict[str, Any], ctx: CallContext):
    """Reprocess (plan 6 C8): the records the workflow's runs hold go back through the graph that runs
    (graph_for_run), from the step that rejected them on (that step with its settings as they are now, so a fixed rule
    lets them through, and every step after it), through the engine. A record no step rejects again is marked
    `reprocessed`; one that is rejected again stays held (its row is kept, the engine's new copy is removed). A step
    whose On failure is `reject` drops what it rejects, so such a record counts as reprocessed. A held record whose step
    is no longer in the graph stays held."""
    from di.connectors import mapping
    from di.connectors.registry import ADAPTERS, adapter_for
    from di.core.db import SessionLocal
    from di.workflow import engine

    w = _must(ctx, i["id"], for_update=True)
    rows = _held_of(ctx.session, w)
    g = graph_for_run(w)
    rid = f"REPROC-{w['id']}-{_now(ctx)}"
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        start = _start_step(g, r["step"])
        sid = r["source_id"] or w.get("src")
        if start and sid:
            groups.setdefault((start, sid), []).append(r)
    done: list[int] = []
    labels: list[str] = []
    for (start, sid), grp in groups.items():
        with live_sources(ctx.session):  # a source made in the Connection Fabric by its name
            labels.append(label(studio._analyze(g)[0][start]))
        with SessionLocal() as s:
            real = adapter_for(s, sid)
            conf = s.execute(text("SELECT confidence FROM source_system WHERE id = :i"), {"i": sid}).scalar()
            feed = engine.Feed(
                sid, _Replay(grp, real), None, None, True, float(conf) if conf is not None else None,
                mapping.mapper(s, sid, sid in ADAPTERS) if real is not None else None,
            )  # fmt: skip
            engine.run_graph(s, w, _from_step(g, start, sid), trigger="Reprocess", feeds={sid: feed}, run_id=rid)
            again = s.execute(
                text("SELECT resource, ext_id FROM failed_record WHERE run_kind = 'workflow' AND run_id = :r"), {"r": rid}
            ).all()
            s.execute(text("DELETE FROM failed_record WHERE run_kind = 'workflow' AND run_id = :r"), {"r": rid})
            s.commit()
        held_again = {(x.resource or "records", x.ext_id) for x in again}
        done += [r["id"] for r in grp if (r["resource"] or "records", r["ext_id"] or str(r["id"])) not in held_again]
    if done:
        ctx.session.execute(text("UPDATE failed_record SET status = 'reprocessed' WHERE id = ANY(:i)"), {"i": done})
    n, ok, held = len(rows), len(done), len(rows) - len(done)
    via = " and ".join(dict.fromkeys(labels)) or "the workflow"
    w["frReproc"] = f"{n} records at {ctx.now:%H:%M}: {ok} reprocessed, {held} still held"
    _put(ctx, w)
    note = f"{w['id']} · {n} held records sent back through {via}: {ok} reprocessed, {held} still held"
    rb_log(ctx, "workflow.reprocessed", note, "workflow.reprocess")
    return {"id": w["id"], "name": w["name"], "n": n, "reprocessed": ok, "held": held}


# ---------------------------------------------------------------- the suggested fix (ACT.frFixApply)
@guard("workflow.applyFix")
def apply_fix_guard(i: dict[str, Any], ctx: CallContext):
    w = _get(ctx, i["id"])
    if w is None:
        return _not_found(i)
    if w.get("frFix"):
        return "duplicate", "The suggested fix is already applied. Run now to confirm."
    if (w.get("last") or {}).get("state") != "failed":
        return "conflict", f"The last run of {w['name']} did not fail, so there is nothing to fix."
    found = _fix_for(ctx.session, w)
    return found if isinstance(found, tuple) else None


def _failed_step(w: dict) -> str | None:
    """The first step that failed in the last run."""
    lr = w.get("lastRun") or {}
    states = lr.get("states") or {}
    return next((n for n in (lr.get("order") or list(states)) if states.get(n) == "failed"), None)


def _fix_for(s, w: dict) -> dict | tuple[str, str]:
    """The fix for the last run's failure: the failed step, and the last good version of its settings: the newest
    version older than the one that ran (the published one, else the saved one) in which the step had other settings.
    Or the refusal (code, message) when there is none. Steps are named with the sources as they are now."""
    with live_sources(s):
        return _fix_named(s, w)


def _fix_named(s, w: dict) -> dict | tuple[str, str]:
    nid = _failed_step(w)
    if nid is None:
        return "conflict", f"No step failed in the last run of {w['name']}, so there is no step to fix."
    ran = (w.get("lastRun") or {}).get("ver") or (w.get("pub") or {}).get("ver") or w["ver"]
    vs = versions.of(s, w["id"])  # newest first
    at = next((k for k, v in enumerate(vs) if v["ver"] == ran), None)
    ran_g = (w.get("pub") or {}).get("graph") if (w.get("pub") or {}).get("ver") == ran else None
    ran_g = ran_g or (vs[at]["graph"] if at is not None else graph_of(w))
    bad = next((n for n in ran_g["nodes"] if n["id"] == nid), None)
    cur = next((n for n in graph_of(w)["nodes"] if n["id"] == nid), None)
    some = bad or cur
    lb = label(some) if some else nid
    if bad is None or cur is None:
        return "conflict", f"{lb} is no longer in {w['name']}, so there is no step to fix."
    for v in vs[at + 1 :] if at is not None else []:
        good = next((n for n in v["graph"].get("nodes") or [] if n["id"] == nid), None)
        if good is None:
            continue
        d = versions.diff({"ver": ran, "graph": {"nodes": [bad]}}, {"ver": v["ver"], "graph": {"nodes": [good]}}, label)
        fields = d["blocks"]["changed"][0]["fields"] if d["blocks"]["changed"] else []
        if fields:
            return {"node": nid, "label": lb, "ver": v["ver"], "good": good, "fields": fields}
    return (
        "conflict",
        f"There is no earlier version of {w['name']} with other settings for {lb} to restore. Change its settings by hand.",
    )


def _fix_text(fix: dict) -> str:
    def one(f: dict) -> str:
        if f["field"] == "fail":
            return "failure toggle " + ("on" if f["to"] else "off")
        to = f["to"]
        return f"{f['field']} back to {json.dumps(to, ensure_ascii=False) if isinstance(to, dict | list) else to}"

    return f"{fix['label']} is back to its settings from v{fix['ver']}: {', '.join(one(f) for f in fix['fields'])}."


@implement("workflow.applyFix")
def apply_fix(i: dict[str, Any], ctx: CallContext):
    """Apply fix (plan 6 C8): the step the last run failed at gets back its settings (block settings and failure
    toggle) from the last good version (`_fix_for`), as a new version. A published workflow whose saved version was the
    one that runs publishes the fix, so Run now confirms it; one with unpublished changes keeps them and is told to
    publish. The text says exactly what changed."""
    w = _must(ctx, i["id"], for_update=True)
    fix = _fix_for(ctx.session, w)
    if isinstance(fix, tuple):  # the guard refused it
        raise ActionError(*fix)
    _before_change(ctx, w)
    runs_saved = bool(w.get("pub")) and w["pub"]["ver"] == w["ver"]
    n = next(x for x in w["graph"]["nodes"] if x["id"] == fix["node"])
    good = fix["good"]
    for k in ("k", "ref"):
        n[k] = good[k]
    n.pop("cfg", None)
    n.pop("fail", None)
    if good.get("cfg"):
        n["cfg"] = copy.deepcopy(good["cfg"])
    if good.get("fail"):
        n["fail"] = True
    bump(w)
    text_ = _fix_text(fix)
    if w.get("pub") and not runs_saved:
        text_ += f" Publish v{w['ver']} to make runs use it."
    now = _now(ctx)
    w.update(frFix=text_, updated=now, dirty=False)
    w["saved"] = snap(w)
    w["hist"] = [
        {"ver": w["ver"], "by": _by(ctx), "at": iso(now), "note": "Fix applied", "prep": ctx.preparer},
        *(w.get("hist") or []),
    ]
    versions.keep(ctx.session, w, _by(ctx), iso(now), f"Fix applied: {fix['label']} settings from v{fix['ver']}")
    if runs_saved:
        _set_pub(w)
    _put(ctx, w)
    rb_log(ctx, "workflow.fixed", f"{w['id']} · {text_}", "workflow.applyFix")
    return {"id": w["id"], "name": w["name"], "ver": w["ver"], "fix": text_}


# `graph`: an unsaved draft (the canvas' copy), checked with the server's full checks (live sources, field-aware
# settings) so the Checks panel shows what Test run and Publish would refuse on (plan 6 follow-up, G2)
ACTIONS["workflow.validate"].input |= {"graph": {"req": False, "t": "object"}}


@guard("workflow.validate")
def validate_guard(i: dict[str, Any], ctx: CallContext):
    from di.services.actions.workflow_drafts import _graph_problem

    if i.get("graph") is not None and (p := _graph_problem(i["graph"])):
        return "validation_error", p
    return _wf_guard(i, ctx)


@implement("workflow.validate")
def validate_action(i: dict[str, Any], ctx: CallContext):
    w = _must(ctx, i["id"])
    if i.get("graph") is not None:  # a draft: each check carries its step (`node`) and severity for the canvas
        d = validate(blocks.compact_graph(copy.deepcopy(i["graph"])), w["kind"], ctx.session)
        return {
            "id": w["id"],
            "name": w["name"],
            "errors": [{"msg": x["msg"], "node": x["id"], "sev": x["sev"]} for x in d if x["sev"] == "error"],
            "warnings": [{"msg": x["msg"], "node": x["id"], "sev": x["sev"]} for x in d if x["sev"] != "error"],
        }
    v = validate(graph_of(w), w["kind"], ctx.session)
    # the demo reads x.node, which its checks never set (they carry the step as `id`), so `node` is always null
    return {
        "id": w["id"],
        "name": w["name"],
        "errors": [{"msg": x["msg"], "node": None} for x in v if x["sev"] == "error"],
        "warnings": [{"msg": x["msg"], "node": None} for x in v if x["sev"] != "error"],
    }


@guard("workflow.run")
def run_guard(i: dict[str, Any], ctx: CallContext):
    w = _get(ctx, i["id"])
    if w is None:
        return _not_found(i)
    if w.get("running") and run_active(ctx.session, w["id"]):  # one run at a time (plan 6 C7)
        return "duplicate", f"{w['name']} is already running"
    if w["status"] == "draft":  # a draft runs only when it can: its sources connected, its checks clean
        g = graph_for_run(w)
        with live_sources(ctx.session):  # a source made in the Connection Fabric by its name
            msg = next((f"{label(n)} has no connected feed" for n in (_Graph(g).by[i] for i in studio._order(g))
                        if n["k"] in ("conn", "wconn") and not _connected(ctx.session, n["ref"])), None)  # fmt: skip
        if msg is None and (er := errors(g, w["kind"], ctx.session)):  # the sources now (catalogue ones too)
            msg = er[0]["msg"]
        if msg:
            return "conflict", f"{w['name']} is a draft with errors: {msg[:94] + '…' if len(msg) > 96 else msg}"
    return None


def _connected(s, sid: str) -> bool:
    """The source exists and is connected (source_system): not unavailable, disconnected or deleted."""
    st = s.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": sid}).scalar()
    return st is not None and st not in ("unavailable", "disconnected", "deleted")


def run_id(wid: str, now: int) -> str:
    """The demo's run id: 'RUN-' + hashId(workflow id + the time)[:5]."""
    return "RUN-" + hash_id(f"{wid}{now}")[:5].upper()


@implement("workflow.run")
def run(i: dict[str, Any], ctx: CallContext):
    w = _must(ctx, i["id"], for_update=True)
    reap_lost_run(ctx.session, w, _now(ctx))  # a run whose worker died leaves `running` set: it is closed first
    key = start_run(ctx.session, w, "Manual", _now(ctx))
    return {"id": w["id"], "name": w["name"], "run": key}


def start_run(s, w: dict[str, Any], trig: str, now: int, *, enqueue: bool = True) -> str:
    """Start a run of `w` (loaded for update): mark it running, add its run record in state "running" labelled `trig`
    (Manual for Run now; Schedule, Event, File, Approval or Case from di/workflow/triggers.py) and, unless the caller
    is already the run's job (a triggered run, `enqueue=False`), queue the `workflow.run` job. Returns the record's key."""
    graph_of(w)
    w["running"] = True
    state.put(s, "workflows", w["id"], w)
    rid = run_id(w["id"], now)
    # the demo's ids repeat when a workflow runs twice at the same time (its clock is pinned); the record's key must not
    key, n = rid, 1
    while state.get(s, "workflow_runs", key) is not None:
        n += 1
        key = f"{rid}~{n}"
    # in progress: the demo's run fields (duration and records known at the end) and, once the job starts, the steps
    record = {
        "id": rid,
        "wf": w["id"],
        "name": w["name"],
        "ts": now,
        "trig": trig,
        "dur": None,
        "rows": None,
        "state": "running",
        "note": "",
    }
    state.add(s, "workflow_runs", key, record)
    if enqueue:
        jobs.enqueue(s, "workflow.run", {"run": key, "wf": w["id"], "trig": trig})
    return key


# ---------------------------------------------------------------- the run job
RUN_LOCK = 7311  # the advisory lock of a workflow's run: (RUN_LOCK, hashtext('wf:' || id)), held by the run's job
BACKOFF_SECONDS = 1.0  # a failing step is tried again after 1 s, 2 s, 4 s ... (tests set 0)
DEFAULT_RETRIES = 3  # the Settings tab's default (frWfSet)
_ACTIVE = text(
    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND classid = :c AND objsubid = 2 "
    "AND objid::bigint = (hashtext(:k)::bigint & 4294967295)) "
    "OR (SELECT count(*) FROM job WHERE kind = 'workflow.run' AND payload->>'wf' = :w AND (status = 'queued' "
    "OR (status = 'running' AND locked_at > now() - interval '2 minutes'))) > :n"  # a claimed job still starting
)


class _RunGone(Exception):
    """The run record went while the run was going (the workflow was deleted)."""


def run_active(s, wid: str, jobs_ok: int = 0) -> bool:
    """A run of the workflow is queued or going: its job is waiting, or a worker holds the run lock. A `running` flag
    without either is left by a worker that died (the lock goes with its connection). `jobs_ok`: the caller's own jobs
    of the workflow (a triggered run's job, taken but not yet running) that do not count."""
    return bool(s.execute(_ACTIVE, {"c": RUN_LOCK, "k": f"wf:{wid}", "w": wid, "n": jobs_ok}).scalar())


def reap_lost_run(s, w: dict[str, Any], now: int, jobs_ok: int = 0) -> bool:
    """Close the run a dead worker left (`running` set, nothing queued or going): its record fails with "worker lost"
    and the workflow is no longer running. In the caller's transaction; True when there was one. Run now calls it,
    and a triggered run's start (di/workflow/triggers.py start, with its own job as `jobs_ok`)."""
    if not w.get("running") or run_active(s, w["id"], jobs_ok):
        return False
    for key, r in _run_keys(s, w["id"]):
        if r.get("state") == "running":
            state.put(s, "workflow_runs", key, _final_record(r, w, now, "failed", "Failed: worker lost", r.get("rows")))
            studio.record_run_stats(s, key, w["id"], now, None, "failed")  # the Monitor counts it, without a duration
    w["running"] = False
    w["last"] = {"ts": now, "state": "failed", "dur": None, "rows": None, "note": "Failed: worker lost"}
    state.put(s, "workflows", w["id"], w)
    log.warning("workflow %s: closed a run its worker lost", w["id"])
    return True


def _run_keys(s, wid: str) -> list[tuple[str, dict]]:
    rows = s.execute(
        text("SELECT id, data FROM state_item WHERE collection = 'workflow_runs' AND data->>'wf' = :w"), {"w": wid}
    ).all()
    return [(r.id, r.data) for r in rows]


def _final_record(r: dict, w: dict, now: int, st: str, note: str, rows: Any) -> dict:
    """The run record as it stays: the demo's shape {id, wf, name, ts, trig, dur, rows, state, note}."""
    dur = round((now - r["ts"]) / 1000, 2) if isinstance(r.get("ts"), int | float) else None
    return {"id": r["id"], "wf": w["id"], "name": w["name"], "ts": now, "trig": r.get("trig") or "Manual", "dur": dur,
            "rows": rows, "state": st, "note": note}  # fmt: skip


def _retries(w: dict) -> int:
    r = settings_for_run(w).get("retries")
    return DEFAULT_RETRIES if r is None else int(r)


def run_job(payload: dict) -> dict:
    """The `workflow.run` job (plan 6 C5, C7): one run at a time per workflow, through the engine.

    The job takes the workflow's run lock on a connection of its own for the whole run; a second run of the same
    workflow that finds it taken (a schedule tick during Run now) is dropped: its record goes and nothing runs, so it
    is queued once. A run that raises is closed as failed (its workflow stops running) instead of being retried by
    the queue; a worker that dies loses the lock with its connection, and the next Run now closes the run
    (reap_lost_run)."""
    from di.core.db import engine as db

    key, wid = payload["run"], payload["wf"]
    with db.connect() as lock:
        got = lock.execute(text("SELECT pg_try_advisory_xact_lock(:c, hashtext(:k))"), {"c": RUN_LOCK, "k": f"wf:{wid}"}).scalar()
        if not got:
            lock.rollback()
            _drop_duplicate(key)
            return {"run": key, "skipped": "already_running"}
        try:
            return _run_locked(payload)
        except _RunGone:
            return {"run": key, "skipped": "run record removed"}
        except Exception as e:  # a crashed run never leaves its workflow running
            log.exception("workflow run %s (%s) crashed", key, wid)
            return _crashed(payload, e)
        finally:
            lock.rollback()  # releases the run lock


def _drop_duplicate(key: str) -> None:
    from di.core.db import SessionLocal

    with SessionLocal() as s:
        r = state.get(s, "workflow_runs", key, for_update=True)
        if r is not None and r.get("state") == "running":
            state.delete(s, "workflow_runs", key)
        s.commit()


def _crashed(payload: dict, e: Exception) -> dict:
    from di.core.db import SessionLocal

    key, wid = payload["run"], payload["wf"]
    note = f"Failed: {type(e).__name__}: {e}"
    note = note[:94] + "…" if len(note) > 96 else note
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid, for_update=True)
        r = state.get(s, "workflow_runs", key, for_update=True)
        if w is not None:
            now = _now()
            w["running"] = False
            w["last"] = {"ts": now, "state": "failed", "dur": None, "rows": None, "note": note}
            w["runsN"] = (w.get("runsN") or 0) + 1
            state.put(s, "workflows", wid, w)
            if r is not None:
                state.put(s, "workflow_runs", key, _final_record(r, w, now, "failed", note, None))
                studio.record_run_stats(s, key, wid, now, None, "failed")  # a failed run, no duration measured
        s.commit()
    return {"run": key, "state": "failed", "error": note}


def _run_locked(payload: dict) -> dict:
    """Run the workflow's version that runs (graph_for_run) through the engine, writing each state change into its run
    record (the live canvas follows it on the stream), then finish it: the workflow's last run with the real states,
    counts, durations and tries, the run record in the demo's shape, and the alert its rule asks for."""
    from di.core.db import SessionLocal
    from di.workflow import engine

    key, wid = payload["run"], payload["wf"]
    trig = payload.get("trig") or "Manual"
    t0 = time.monotonic()
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid)
        record = state.get(s, "workflow_runs", key)
        if record is None:
            return {"run": key, "skipped": "no run record"}
        if w is None:  # deleted before it ran: the demo's timer finds it gone and records nothing
            state.delete(s, "workflow_runs", key)
            s.commit()
            return {"run": key, "skipped": "workflow deleted"}
        if record.get("state") != "running":  # a job claimed again after its run was closed
            return {"run": key, "skipped": "finished"}
        g = copy.deepcopy(graph_for_run(w))
        ran_ver = (w.get("pub") or {}).get("ver") or w.get("ver")  # the version that runs (Apply fix reads it)
        order = studio._order(g)

        def on_step(e: dict) -> None:
            with SessionLocal() as s2:
                r = state.get(s2, "workflow_runs", key, for_update=True)
                if r is None:
                    raise _RunGone(key)
                r.update(state="running", step=e["step"], step_state=e["state"], states=e["states"], counts=e["counts"],
                         order=order)  # fmt: skip
                state.put(s2, "workflow_runs", key, r)
                s2.commit()
            pause = STEP_SECONDS if e["state"] == "running" else QUICK_SECONDS if e["state"] in QUICK else 0
            if pause:  # long enough for the canvas to show the step going
                time.sleep(pause)

        er = errors(g, w["kind"], s)  # the sources as they are now: a catalogue or hand-made source's step runs
        if er:  # a graph with errors does not run: its first error fails, the steps after it upstream failed
            res = engine.refused(g, er[0]["id"], er[0]["msg"])
            states = dict.fromkeys(res.order, "queued")
            for nid in res.order:
                states[nid] = res.states[nid]
                on_step({"step": nid, "state": res.states[nid], "states": dict(states), "counts": {}})
            res.steps = len(res.order)
        else:
            res = engine.run_graph(
                s, w, g, trigger=trig, on_step=on_step, retries=_retries(w), backoff=BACKOFF_SECONDS, run_id=key,
                run_kind="workflow", resume=payload.get("wait"),  # a Wait step's parked records (di/workflow/waits.py)
            )  # fmt: skip
    dur = round(time.monotonic() - t0, 2)
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid, for_update=True)
        record = state.get(s, "workflow_runs", key, for_update=True)
        if w is None:
            if record is not None:
                state.delete(s, "workflow_runs", key)
            s.commit()
            return {"run": key, "skipped": "workflow deleted"}
        now = _now()
        before = {
            "failed": (w.get("last") or {}).get("state") == "failed",
            "okN": w.get("okN") or 0,
            "runsN": w.get("runsN") or 0,
        }
        w["running"] = False
        w["last"] = {"ts": now, "state": res.status, "dur": dur, "rows": res.rows, "note": res.note}
        w["runsN"] = (w.get("runsN") or 0) + 1
        if res.status != "failed":
            w["okN"] = (w.get("okN") or 0) + 1
        w["lastRun"] = {
            "id": (record or {}).get("id") or run_id(wid, now), "ts": now, "t0": now - dur * 1000, "trig": trig,
            "states": res.states, "dur": {k: round(v / 1000, 2) for k, v in res.dur_ms.items()}, "order": res.order,
            "status": res.status, "note": res.note,
            # what really happened (plan 6 C5, C7): records in and out of each step, tries, held records, the run key
            "counts": res.counts, "attempts": res.attempts, "held": res.held, "key": key, "ver": ran_ver,
        }  # fmt: skip
        if (r := settings_for_run(w).get("retries")) is not None:  # the setting this run used ("failed after N retries")
            w["lastRun"]["retries"] = r
        # a new latest run: its held records and its failures are new, so the marks for the previous run go
        w.pop("frReproc", None)
        w.pop("frFix", None)
        state.put(s, "workflows", wid, w)
        if alert := _alert(w, before):
            _raise_alert(s, w, alert, now)
        final = {
            "id": w["lastRun"]["id"], "wf": wid, "name": w["name"], "ts": now, "trig": trig, "dur": dur, "rows": res.rows,
            "state": res.status, "note": res.note,
        }  # fmt: skip
        state.put(s, "workflow_runs", key, final)
        steps = w["lastRun"]["dur"]  # what the Monitor reads (plan 6 D1): the run, and each step with its label
        with live_sources(s):  # a source made in the Connection Fabric by its name
            labels = {n["id"]: engine.label(n) for n in g["nodes"] if n["id"] in steps}
        studio.record_run_stats(s, key, wid, now, dur, res.status, steps, labels)
        _keep_recent_runs(s)
        s.commit()
    log.info("workflow run %s (%s): %s", key, wid, res.status)
    return {"run": key, "state": res.status, "steps": res.steps, "rows": res.rows, "held": res.held}


def _keep_recent_runs(s) -> None:
    """S.wf.runs keeps the 40 newest runs."""
    s.execute(
        text(
            "DELETE FROM state_item WHERE collection = 'workflow_runs' AND seq NOT IN "
            "(SELECT seq FROM state_item WHERE collection = 'workflow_runs' ORDER BY seq DESC LIMIT :n)"
        ),
        {"n": RUNS_KEPT},
    )


# ---------------------------------------------------------------- run alerts (the Settings tab's "Alert when")
def _alert(w: dict, before: dict) -> tuple[str, str] | None:
    """The alert a finished run raises under the workflow's rule, as (severity, message), or None. The demo offers the
    rule but raises nothing; here a run that meets it adds a notification (the "notes" collection, as notify.send
    does), which reaches its addressee on the live stream and on the Alerts page."""
    rule = w.get("alert") or ALERTS[0]
    last, lr = w["last"], w["lastRun"]
    failed = last["state"] == "failed"
    note = f" {last['note']}" if last.get("note") else ""
    if rule == "A run fails" and failed:
        return "High", f"{w['name']}: run {lr['id']} failed.{note}"
    if rule == "Two runs fail in a row" and failed and before["failed"]:
        return "High", f"{w['name']}: two runs failed in a row. Latest run {lr['id']}.{note}"
    if rule == "Success rate drops below 95%" and w["runsN"]:
        was = before["okN"] / before["runsN"] if before["runsN"] else 1
        now = w["okN"] / w["runsN"]
        if was >= 0.95 > now:
            return "Medium", f"{w['name']}: success rate dropped to {js_round(now * 100)}%, below 95%."
    return None


def _raise_alert(s, w: dict, alert: tuple[str, str], now: int) -> None:
    to = policy.account(ALERT_TO)
    n = state.next_number(s, "notes", "NTF-", NOTE_SEQ_START)
    note: dict[str, Any] = {
        "id": f"NTF-{n}", "exId": f"wf:{w['id']}", "title": f"Workflow alert · {w['name']}", "msg": alert[1],
        "sev": alert[0], "to": ALERT_TO, "toLabel": to.label if to else ALERT_TO, "from": "Workflow Studio",
        "at": iso(now), "status": "open", "ids": [],
    }  # fmt: skip
    state.add(s, "notes", note["id"], note)
