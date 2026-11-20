"""Workflow Studio actions (docs/BACKEND_STEPS.md, B15 part 2): workflow.save, publish, setStatus, create, duplicate,
delete and run, and the read workflow.validate.

Ports of the demo's handlers (index.html, `defAction('workflow.save', ...)` and the ones after it) and of what they call:
the template graphs (wfBuild with the Connection Fabric's extra branches), the checks (wfValidate, with the Fabric's
override for start and branch steps) and the run simulation (wfSimRun, wfEval, wfSimOutcome). They write the two
workspace collections the Workflow Studio reads (di/screens/workflows.py): "workflows" (S.wf.list) and
"workflow_runs" (S.wf.runs). The pipeline has validated the input and checked the permission; the guards here are the
demo's, in its order. None of the workflow actions has an idempotency key in the demo; repeats are refused by state
(already published, already running).

**Runs are worker jobs.** The demo's workflow.run marks the workflow running and finishes the run after a timer (one
to four and a half seconds), computing the outcome all at once. Here workflow.run marks the workflow running, adds a
run record in state "running" to "workflow_runs" and queues a `workflow.run` job; the action returns at once with the
demo's output ({id, name}) plus `run`, the run record's id. The job (`run_job`, registered in di/worker.py) walks the
graph in its run order as the canvas' test run does (wfStep): each step goes to "running" and then to its state
(steps that do nothing - upstream failed, waiting, skipped - go straight to their state), and after each change the run
record is written with the states so far and the records in and out of the finished steps (frRunCounts). Each write
is a commit, so it reaches GET /api/stream as a `workflow` event (migration 0009). At the end the workflow gets its
last run (`last`, `lastRun`, the counts) and the run record takes the demo's shape {id, wf, name, ts, trig, dur, rows,
state, note}.

**Random draws.** The demo draws a run's duration and record count with Math.random (not the action's seeded
generator), so they cannot be reproduced; here they come from mulberry32 seeded from the run record's key, in the
demo's ranges. Everything else in a run (the step states, the note, the per-step durations, the run id) is
a function of the graph and the sources, as in the demo.

**Not ported.** A manual run of an ingest workflow also starts the demo's simulated sync of its source (startSync)
and bumps the Command Centre's hourly health bar (hhBump); the backend's sources sync through the connectors (B9)
and its health bars are fixed, so neither happens here.

**Times.** The workspace clock (di/clock.py, `ctx.now`): pinned to the demo's as-of time in the tests, as the demo's
Date.now() is in its sandbox.
"""

import copy
import json
import logging
import math
import time
from collections.abc import Callable

from sqlalchemy import text

from di import clock, jobs, state
from di.actions.registry import guard, implement
from di.reads.common import SOURCES, STARTING_MAPPINGS, hash_id, iso, ms, to_fixed
from di.screens import workflows as screen
from di.screens.integration import SRC_TYPES, channels
from di.screens.reference import lists

log = logging.getLogger("di.workflows")
_REF = lists()
XF: list[dict] = _REF["XF"]
FR_XF: list[dict] = _REF["FR_XF"]
FXD: dict[str, dict] = _REF["FXD"]
ACT_TYPES: list[dict] = _REF["ACT_TYPES"]
DELIVER: dict[str, list] = _REF["DELIVER"]
CH_ARR: dict[str, str] = _REF["CH_ARR"]
CH_DEL: dict[str, str] = _REF["CH_DEL"]
SH: dict[str, str] = _REF["SH"]
MAP_TARGET: dict[str, str] = _REF["MAP_TARGET"]
TOOLS: list[dict] = _REF["TOOLS"]
MAPPINGS: dict[str, list] = STARTING_MAPPINGS

RUNS_KEPT = 40  # S.wf.runs.length = Math.min(S.wf.runs.length, 40)
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
    "event": lambda t: "On event",
    "approval": lambda t: "On approval",
    "manual": lambda t: "Manual",
    "case": lambda t: "On case request",
    "file": lambda t: "On file arrival",
}


# ---------------------------------------------------------------- small ports
def src(sid: str | None) -> dict | None:
    """SRC: the source reference (the demo's SOURCES)."""
    return SOURCES.get(sid) if isinstance(sid, str) else None


def src_or(sid: str) -> dict:
    """srcOr: the source, or what a deleted one looks like."""
    return src(sid) or {
        "id": sid, "name": SH.get(sid) or "Deleted source", "vendor": "Deleted", "status": "unavailable", "mode": "—",
        "auth": "—", "read": [], "write": [], "cat": "internal", "fresh": "—", "deleted": True, "authority": [],
    }  # fmt: skip


def trig_text(t: dict) -> str:
    return TRIG_L.get(t.get("t"), TRIG_L["manual"])(t)


def _xf(ref: str) -> dict | None:
    return next((x for x in XF if x["id"] == ref), None)


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
        return _xf(ref)["label"]
    if k == "map":
        return f"{SH.get(ref)} fields"
    t = next((x for x in TOOLS if x["id"] == ref), None)
    return t["id"] if t else ref


def snap(w: dict) -> str:
    """wfSnap: the saved snapshot, as the demo's JSON.stringify writes it."""
    m = {"name": w.get("name"), "owner": w.get("owner"), "trig": w.get("trig")}
    return json.dumps({"g": w.get("graph"), "m": m}, separators=(",", ":"), ensure_ascii=False)


def bump(w: dict) -> None:
    """wfBump: 1.4 -> 1.5."""
    a, _, b = str(w["ver"]).partition(".")
    b = b.split(".")[0]
    w["ver"] = f"{a}.{(int(b) if b.isdigit() else 0) + 1}"


# ---------------------------------------------------------------- template graphs (wfBuild)
def _n(nid: str, k: str, ref: str, x: float, y: float) -> dict:
    return {"id": nid, "k": k, "ref": ref, "x": x, "y": y}


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
    xf = not file_only and XFORM.get(s.get("type"))
    if xf:
        nodes.append(_n("t", "xf", xf, col(), y0))
        edges.append(_e("v", "t"))
        prev = ["t"]
    nodes.append(_n("m", "map", sid, col(), y0))
    edges.append(_e(prev[0], "m"))
    c = CANON_FIX.get(MAP_TARGET.get(sid) or "Outcome")
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
    head = {
        "standard": (
            [("evid", "fixed", "evid", 24, 130), ("gates", "fixed", "gates", 262, 130)]
            + [(f"tl_{t}", "tool", t, x, 130) for t, x in (("list_eligible_routes", 500), ("predict_outcomes", 738))]
            + [("tl_request_approval", "tool", "request_approval", 976, 130)],
            [("evid", "gates", 1), ("gates", "tl_list_eligible_routes"), ("tl_list_eligible_routes", "tl_predict_outcomes")]
            + [("tl_predict_outcomes", "tl_request_approval")],
        ),
        "pool": (
            [("evid", "fixed", "evid", 24, 130), ("gates", "fixed", "gates", 262, 130)]
            + [(f"tl_{t}", "tool", t, x, 130) for t, x in (("predict_outcomes", 500), ("optimize_pool", 738))]
            + [("tl_request_approval", "tool", "request_approval", 976, 130)],
            [("evid", "gates", 1), ("gates", "tl_predict_outcomes"), ("tl_predict_outcomes", "tl_optimize_pool")]
            + [("tl_optimize_pool", "tl_request_approval")],
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
    g = (
        _ingest(tpl.get("src"))
        if k == "ingest"
        else _outbound(tpl.get("src"), tpl.get("ch"))
        if k == "out"
        else _decision(tpl.get("id"))
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
        self.by, self.succ, self.pred = screen._analyze(g)

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
            st, vis, bad = [(nid, False, False, False)], set(), {}
            hit = no_ing = no_val = False
            while st:
                x, vm, vi, vv = st.pop()
                if (x, vm, vi, vv) in vis:
                    continue
                vis.add((x, vm, vi, vv))
                for y in A.succ[x]:
                    m = A.by[y]
                    v2 = vm or m["k"] == "map"
                    i2 = vi or bool(m["k"] == "xf" and _xf(m["ref"]).get("ingest"))
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
                    f"{lb} is fed by {', '.join(str(SH.get(c['ref'])) for c in anc)}. Field names would not line up.",
                )
            if not MAPPINGS.get(ref):
                add("error", nid, f"No field mapping is defined for {SH.get(ref)} yet.")
            if not ns:
                add("warn", nid, f"{lb} does not lead to a canonical model.")
            elif canon and MAP_TARGET.get(ref) not in canon:
                add("error", nid, f"{lb} maps to {MAP_TARGET.get(ref)}, but it is wired to {', '.join(canon)}.")
        if k == "xf":
            x = _xf(ref)
            anc_ids = A.anc(nid)
            anc_n = [A.by[i] for i in anc_ids]
            conns = [m for m in anc_n if m["k"] == "conn"]

            def names(lst: list[dict]) -> str:
                return ", ".join(dict.fromkeys(str(SH.get(c["ref"])) for c in lst))

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
                    acc = DELIVER.get(w["ref"]) or []
                    if a["ch"] not in acc:
                        add(
                            "error",
                            nid,
                            f"{SH.get(w['ref'])} does not accept {CH_DEL[a['ch']]}. "
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
                miss = [i for i in r.get("after", []) if i not in anc_s]
                late = [i for i in r.get("before", []) if i not in dsc_s]
                if miss:
                    add("error", nid, f"{ref} has to come after {' and '.join(WF_NM[i] for i in miss)}. {r['why']}")
                if late:
                    add("error", nid, f"{ref} has to come before {' and '.join(WF_NM[i] for i in late)}. {r['why']}")
        if k == "fixed" and kind == "pipe" and FXD[ref].get("canon") and ref not in ("c_dec", "c_out") and not np_:
            add("warn", nid, f"Nothing feeds {lb}. AI services will report an evidence gap.")
    if kind == "dec":
        dec = next((n for n in g["nodes"] if n["id"] == "c_dec"), None)
        if dec and not any(A.by[i]["k"] == "tool" and A.by[i]["ref"] == "send_instruction" for i in A.desc("c_dec")):
            add("warn", "c_dec", "The approved decision is not carried out. Add send_instruction after the Decision record.")
    return sorted(out, key=lambda o: _RANK[o["sev"]])


def validate(g: dict, kind: str) -> list[dict]:
    """wfValidate: errors, warnings and notes, each with the step it belongs to, errors first."""
    out, A = _validate_base(g, kind), _Graph(g)
    by = {n["id"]: n for n in g["nodes"]}

    def keep(o: dict) -> bool:
        n = by.get(o["id"])
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
    return sorted(out, key=lambda o: _RANK[o["sev"]])


def errors(g: dict, kind: str) -> list[dict]:
    return [e for e in validate(g, kind) if e["sev"] == "error"]


# ---------------------------------------------------------------- the run simulation (wfEval, wfSimRun, wfSimOutcome)
def evaluate(states: dict, A: _Graph, n: dict, approved: bool = True) -> str:
    """wfEval: a step's state from its predecessors' states, its source and its failure flag."""
    ps = [states.get(p) for p in A.pred[n["id"]]]
    if any(s in ("failed", "upstream_failed") for s in ps):
        return "upstream_failed"
    if any(s in ("held", "waiting") for s in ps):
        return "waiting"
    if n["k"] == "fixed":
        f = FXD[n["ref"]]
        needs = bool(f.get("in") and not f.get("start"))
    else:
        needs = n["k"] != "conn"
    if needs and (not ps or all(s == "skipped" for s in ps)):
        return "skipped"
    if n.get("fail"):
        return "failed"
    if n["k"] in ("conn", "wconn"):
        s = src_or(n["ref"])
        if s["status"] == "unavailable":
            return "failed"
        if s["status"] == "stale":
            return "warning"
    if n["k"] == "fixed" and n["ref"] == "appr" and not approved:
        return "held"
    return "success"


def step_dur(nid: str, wid: str) -> float:
    """A step's duration in the run: +(.2 + (hashId(id + wf).charCodeAt(0) % 20) / 10).toFixed(2)."""
    return float(to_fixed(0.2 + (ord(hash_id(nid + wid)[0]) % 20) / 10, 2))


def sim_outcome(w: dict) -> dict:
    """wfSimOutcome (a manual run: no injected failure): every step's state, the run's state and its note."""
    g = graph_of(w)
    A, order = _Graph(g), screen._order(g)
    states: dict[str, str] = {}
    dur: dict[str, float] = {}
    bad = None
    for nid in order:
        st = evaluate(states, A, A.by[nid])
        states[nid] = st
        dur[nid] = step_dur(nid, w["id"])
        if st == "failed" and bad is None:
            bad = nid
    vs = list(states.values())
    status = "failed" if "failed" in vs else "warning" if "warning" in vs else "success"
    note = ""
    if bad:
        n = A.by[bad]
        note = label(n) + (" has no connected feed" if n["k"] in ("conn", "wconn") else " failed")
    elif status == "warning":
        s = next(
            (x for x in (src_or(n["ref"]) for n in g["nodes"] if n["k"] in ("conn", "wconn")) if x["status"] == "stale"), None
        )
        note = f"{s['name']} feed is stale; last fresh data used" if s else ""
    state_ = status
    er = errors(g, w["kind"])
    if state_ != "failed" and er:
        states[er[0]["id"]] = "failed"
        for d in A.desc(er[0]["id"]):
            states[d] = "upstream_failed"
        status = state_ = "failed"
        msg = er[0]["msg"]
        note = msg[:94] + "…" if len(msg) > 96 else msg
    if state_ == "success":
        mn = next(
            (x for x in (src_or(n["ref"]) for n in g["nodes"] if n["k"] in ("conn", "wconn")) if x["status"] == "manual"), None
        )
        if mn:
            note = f"{mn['name']} is a controlled import"
    return {"state": state_, "note": note, "states": states, "dur": dur, "order": order, "status": status}


# ---------------------------------------------------------------- helpers for the handlers
def _now(ctx=None) -> int:
    return ms((ctx.now if ctx is not None else clock.now()).isoformat())


def _by(ctx) -> str:
    return ctx.actor.account.label if ctx.actor.account else "Enterprise system adapter"


def _get(ctx, wid: str, for_update: bool = False) -> dict | None:
    return state.get(ctx.session, "workflows", wid, for_update=for_update)


def _put(ctx, w: dict) -> None:
    state.put(ctx.session, "workflows", w["id"], w)


def _not_found(i) -> tuple[str, str]:
    return "not_found", f"No workflow {i['id']}."


def _wf_guard(i, ctx) -> tuple[str, str] | None:
    return None if _get(ctx, i["id"]) else _not_found(i)


def _ids(ctx) -> set[str]:
    return {w["id"] for w in screen.all_workflows(ctx.session)}


# ---------------------------------------------------------------- the actions
@guard("workflow.save")
def save_guard(i, ctx):
    return _wf_guard(i, ctx) or (None if i["name"].strip() else ("validation_error", "Enter a workflow name before saving."))


@implement("workflow.save")
def save(i, ctx):
    w = _get(ctx, i["id"], for_update=True)
    w["graph"] = copy.deepcopy(i["graph"])
    w["name"] = i["name"].strip()
    if i.get("owner") is not None:
        w["owner"] = i["owner"]
    if i.get("trig") is not None:
        w["trig"] = dict(i["trig"])
    bump(w)
    now = _now(ctx)
    w.update(updated=now, dirty=False, warned=False)
    w["saved"] = snap(w)
    w["hist"] = [
        {"ver": w["ver"], "by": _by(ctx), "at": iso(now), "note": i.get("note") or "Saved", "prep": ctx.preparer},
        *(w.get("hist") or []),
    ]
    _put(ctx, w)
    return {"id": w["id"], "ver": w["ver"], "name": w["name"]}


@guard("workflow.publish")
def publish_guard(i, ctx):
    w = _get(ctx, i["id"])
    if w is None:
        return _not_found(i)
    if w["status"] == "published":
        return "duplicate", f"{w['name']} is already published"
    n = len(errors(i.get("graph") or graph_of(w), w["kind"]))
    return ("conflict", f"Cannot publish: {n} error{'s' if n > 1 else ''} in the checks. Fix them first.") if n else None


@implement("workflow.publish")
def publish(i, ctx):
    w = _get(ctx, i["id"], for_update=True)
    graph_of(w)
    if i.get("graph") is not None and (w.get("dirty") or i["graph"] != w.get("graph")):
        w["graph"] = copy.deepcopy(i["graph"])
        w["saved"] = snap(w)
        bump(w)
        w["dirty"] = False
    now = _now(ctx)
    w["status"], w["updated"] = "published", now
    w["hist"] = [{"ver": w["ver"], "by": _by(ctx), "at": iso(now), "note": "Published"}, *(w.get("hist") or [])]
    _put(ctx, w)
    return {"id": w["id"], "ver": w["ver"], "name": w["name"], "trig": trig_text(w["trig"])}


@guard("workflow.setStatus")
def set_status_guard(i, ctx):
    w = _get(ctx, i["id"])
    if w is None:
        return _not_found(i)
    if i["status"] not in ("draft", "paused", "published"):
        return "validation_error", "Unknown status."
    if i["status"] == "published" and (er := errors(graph_of(w), w["kind"])):
        return "conflict", f"Cannot publish {w['name']}: {er[0]['msg']}"
    return None


@implement("workflow.setStatus")
def set_status(i, ctx):
    w = _get(ctx, i["id"], for_update=True)
    was = w["status"]
    w["status"], w["updated"] = i["status"], _now(ctx)
    _put(ctx, w)
    return {"id": w["id"], "was": was, "status": w["status"], "name": w["name"]}


@guard("workflow.create")
def create_guard(i, ctx):
    return ("validation_error", "Choose a system first.") if i["type"] in ("ingest", "out") and not src(i.get("src")) else None


@implement("workflow.create")
def create(i, ctx):
    state.next_number(ctx.session, "workflows", "WF-", 0)  # holds the numbering lock for this transaction
    ids = _ids(ctx)
    k = 100
    while f"WF-{k}" in ids:
        k += 1
    k = max(k, 100 + len(ids))
    while f"WF-{k}" in ids:
        k += 1
    t, so = i["type"], src(i.get("src"))
    nm = (i.get("name") or "").strip() or (
        f"Ingest · {so['vendor']}"
        if t == "ingest"
        else f"Outbound · {so['vendor']}"
        if t == "out"
        else "Decision workflow"
        if t == "dec"
        else "New pipeline"
    )
    if t == "ingest":
        base = {
            "cat": "Ingest", "kind": "pipe", "tpl": {"k": "ingest", "src": so["id"]}, "src": so["id"], "owner": so["owner"],
            "trig": {"t": "schedule", "min": so["interval"]} if so.get("interval") else {"t": "event"},
            "desc": f"{so['name']} into the {SRC_TYPES[so['type']]['target']} model through validation and field mapping.",
        }  # fmt: skip
    elif t == "out":
        tpl = {"k": "out", "src": so["id"]} | ({"ch": i["ch"]} if i.get("ch") is not None else {})
        base = {
            "cat": "Outbound", "kind": "pipe", "tpl": tpl, "src": so["id"], "owner": so["owner"], "trig": {"t": "approval"},
            "desc": f"Approved instruction to {so['name']}.",
        }  # fmt: skip
    elif t == "dec":
        base = {
            "cat": "Decision", "kind": "dec", "tpl": {"k": "dec", "id": "standard"}, "src": None, "owner": "Decision Services",
            "trig": {"t": "case"}, "desc": WF_DEC["standard"]["desc"],
        }  # fmt: skip
    else:
        base = {
            "cat": "Ingest", "kind": "pipe", "tpl": {"k": "blank"}, "src": None, "owner": "Unassigned", "trig": {"t": "manual"},
            "desc": "Blank pipeline. Drag steps from the left and connect them.",
        }  # fmt: skip
    w = {
        "id": f"WF-{k}", "name": nm, "status": "draft", "ver": "0.1", "graph": None, "saved": None, "dirty": False,
        "running": False, "updated": _now(ctx), "runsN": 0, "okN": 0, "last": None, "prep": ctx.preparer,
    } | base  # fmt: skip
    if i.get("desc"):
        w["desc"] = i["desc"]
    if i.get("graph") is not None:
        w["graph"] = copy.deepcopy(i["graph"])
        w["saved"] = snap(w)
    else:
        graph_of(w)  # what opening it does in the demo: the graph built from its template, and its saved snapshot
    state.add(ctx.session, "workflows", w["id"], w)
    return {"id": w["id"], "name": nm}


@guard("workflow.duplicate")
def duplicate_guard(i, ctx):
    return _wf_guard(i, ctx)


@implement("workflow.duplicate")
def duplicate(i, ctx):
    state.next_number(ctx.session, "workflows", "WF-", 0)  # the numbering lock
    w = _get(ctx, i["id"])
    ids = _ids(ctx)
    n = 100
    while f"WF-{n}" in ids:
        n += 1
    c = w | {
        "id": f"WF-{n}", "name": i.get("name") or f"{w['name']} (copy)", "status": "draft", "ver": "0.1",
        "graph": copy.deepcopy(graph_of(w)), "dirty": False, "running": False, "last": None, "runsN": 0, "okN": 0,
        "trig": dict(w["trig"]), "updated": _now(ctx), "warned": False, "hist": [], "prep": ctx.preparer,
    }  # fmt: skip
    c["saved"] = snap(c)
    state.add(ctx.session, "workflows", c["id"], c)
    return {"id": c["id"], "name": c["name"]}


@guard("workflow.delete")
def delete_guard(i, ctx):
    return _wf_guard(i, ctx)


@implement("workflow.delete")
def delete(i, ctx):
    w = _get(ctx, i["id"], for_update=True)
    state.delete(ctx.session, "workflows", w["id"])
    return {"id": w["id"], "name": w["name"]}


@guard("workflow.validate")
def validate_guard(i, ctx):
    return _wf_guard(i, ctx)


@implement("workflow.validate")
def validate_action(i, ctx):
    w = _get(ctx, i["id"])
    v = validate(graph_of(w), w["kind"])
    # the demo reads x.node, which its checks never set (they carry the step as `id`), so `node` is always null
    return {
        "id": w["id"],
        "name": w["name"],
        "errors": [{"msg": x["msg"], "node": None} for x in v if x["sev"] == "error"],
        "warnings": [{"msg": x["msg"], "node": None} for x in v if x["sev"] != "error"],
    }


@guard("workflow.run")
def run_guard(i, ctx):
    w = _get(ctx, i["id"])
    if w is None:
        return _not_found(i)
    if w.get("running"):
        return "duplicate", f"{w['name']} is already running"
    if w["status"] == "draft":
        o = sim_outcome(w)
        if o["state"] == "failed":
            return "conflict", f"{w['name']} is a draft with errors: {o['note']}"
    return None


def run_id(wid: str, now: int) -> str:
    """The demo's run id: 'RUN-' + hashId(workflow id + the time)[:5]."""
    return "RUN-" + hash_id(f"{wid}{now}")[:5].upper()


@implement("workflow.run")
def run(i, ctx):
    w = _get(ctx, i["id"], for_update=True)
    graph_of(w)
    w["running"] = True
    _put(ctx, w)
    now = _now(ctx)
    rid = run_id(w["id"], now)
    # the demo's ids repeat when a workflow runs twice at the same time (its clock is pinned); the record's key must not
    key, n = rid, 1
    while state.get(ctx.session, "workflow_runs", key) is not None:
        n += 1
        key = f"{rid}~{n}"
    # in progress: the demo's run fields (duration and records known at the end) and, once the job starts, the steps
    record = {
        "id": rid,
        "wf": w["id"],
        "name": w["name"],
        "ts": now,
        "trig": "Manual",
        "dur": None,
        "rows": None,
        "state": "running",
        "note": "",
    }
    state.add(ctx.session, "workflow_runs", key, record)
    jobs.enqueue(ctx.session, "workflow.run", {"run": key, "wf": w["id"], "trig": "Manual"})
    return {"id": w["id"], "name": w["name"], "run": key}


# ---------------------------------------------------------------- the run job
def _mulberry(key: str) -> Callable[[], float]:
    """mulberry32 seeded from the key's hashId (the demo's seeded generator)."""
    a = int(hash_id(key), 16)

    def rnd() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rnd


def _rr(rnd: Callable[[], float], a: int, b: int) -> int:
    return a + math.floor(rnd() * (b - a + 1))


def counts_for(w: dict, g: dict, rows: int, states: dict) -> dict:
    """frRunCounts for the given states (records in and out of each step)."""
    return screen.run_counts({"id": w["id"], "graph": g, "last": {"rows": rows}, "lastRun": {"states": states}})


def progress(w: dict, g: dict, outcome: dict, rows: int) -> list[dict]:
    """The run as the canvas animates it (wfStep): one entry per state change, with every step's state at that point."""
    states = dict.fromkeys(outcome["order"], "queued")
    out = []
    for nid in outcome["order"]:
        st = outcome["states"][nid]
        if st not in QUICK:
            states[nid] = "running"
            out.append({"step": nid, "state": "running", "states": dict(states)})
        states[nid] = st
        out.append({"step": nid, "state": st, "states": dict(states)})
    for nid, st in outcome["states"].items():  # steps outside the run order (in a loop) that a failure marks
        if states.get(nid) != st:
            states[nid] = st
            out.append({"step": nid, "state": st, "states": dict(states)})
    for e in out:
        done = {k: v for k, v in e["states"].items() if v not in ("queued", "running")}
        c = counts_for(w, g, rows, e["states"])
        e["counts"] = {k: v for k, v in c.items() if k in done}
    return out


def draws(w: dict, seed: str) -> tuple[float, int]:
    """The run's duration (1 to 4.5 s) and record count, in the demo's ranges (it draws them with Math.random)."""
    rnd = _mulberry(seed)
    dur = _rr(rnd, 10, 45) / 10
    rows = _rr(rnd, 1, 6) if w["cat"] == "Outbound" else 1 if w["cat"] == "Decision" else _rr(rnd, 30, 900)
    return dur, rows


def run_job(payload: dict) -> dict:
    """The `workflow.run` job: run the workflow step by step, writing progress into its run record, then finish it as
    the demo's wfStartRun does."""
    from di.db import SessionLocal

    key, wid = payload["run"], payload["wf"]
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid)
        record = state.get(s, "workflow_runs", key)
        if record is None:
            return {"run": key, "skipped": "no run record"}
        if w is None:  # deleted before it ran: the demo's timer finds it gone and records nothing
            state.delete(s, "workflow_runs", key)
            s.commit()
            return {"run": key, "skipped": "workflow deleted"}
        g = graph_of(w)
        o = sim_outcome(w)
        dur, rows = draws(w, f"workflow.run#{key}")
    steps = progress(w, g, o, rows)
    for e in steps:
        with SessionLocal() as s:
            record = state.get(s, "workflow_runs", key, for_update=True)
            if record is None:
                return {"run": key, "skipped": "run record removed"}
            record.update(
                state="running", step=e["step"], step_state=e["state"], states=e["states"], counts=e["counts"], order=o["order"]
            )
            state.put(s, "workflow_runs", key, record)
            s.commit()
        pause = QUICK_SECONDS if e["state"] in QUICK else STEP_SECONDS
        if pause:
            time.sleep(pause)
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid, for_update=True)
        record = state.get(s, "workflow_runs", key, for_update=True)
        if w is None:
            if record is not None:
                state.delete(s, "workflow_runs", key)
            s.commit()
            return {"run": key, "skipped": "workflow deleted"}
        o = sim_outcome(w)  # the demo decides the outcome when the run finishes, on the graph as it is then
        now = _now()
        trig = payload.get("trig") or "Manual"
        w["running"] = False
        w["last"] = {"ts": now, "state": o["state"], "dur": dur, "rows": rows, "note": o["note"]}
        w["runsN"] = (w.get("runsN") or 0) + 1
        if o["state"] != "failed":
            w["okN"] = (w.get("okN") or 0) + 1
        w["lastRun"] = {
            "id": (record or {}).get("id") or run_id(wid, now), "ts": now, "t0": now - dur * 1000, "trig": trig,
            "states": o["states"], "dur": o["dur"], "order": o["order"], "status": o["status"], "note": o["note"],
        }  # fmt: skip
        state.put(s, "workflows", wid, w)
        final = {
            "id": w["lastRun"]["id"], "wf": wid, "name": w["name"], "ts": now, "trig": trig, "dur": dur, "rows": rows,
            "state": o["state"], "note": o["note"],
        }  # fmt: skip
        state.put(s, "workflow_runs", key, final)
        _keep_recent_runs(s)
        s.commit()
    log.info("workflow run %s (%s): %s", key, wid, o["state"])
    return {"run": key, "state": o["state"], "steps": len(steps)}


def _keep_recent_runs(s) -> None:
    """S.wf.runs keeps the 40 newest runs."""
    s.execute(
        text(
            "DELETE FROM state_item WHERE collection = 'workflow_runs' AND seq NOT IN "
            "(SELECT seq FROM state_item WHERE collection = 'workflow_runs' ORDER BY seq DESC LIMIT :n)"
        ),
        {"n": RUNS_KEPT},
    )
