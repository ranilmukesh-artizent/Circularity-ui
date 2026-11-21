"""The Workflow Studio's collections and the demo's workflow helpers, read by the studio and integration screens and the
workflow actions (di.actions.workflows): the workspace collections "workflows" (S.wf.list, each with its graph) and
"workflow_runs" (S.wf.runs), seeded from fixtures/golden/screens/workflows.json, and "workflow_templates" (S.frTpl,
empty at the start); wfStat, wfUsing, wfAnalyze, wfOrder and frRunCounts."""

from sqlalchemy.orm import Session

from di import golden, state
from di.engine.jsmath import js_round
from di.reads.common import STARTING_MAPPINGS, hash_id

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


# frFailedRows: the rules a held record broke, and the value shown for each
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
