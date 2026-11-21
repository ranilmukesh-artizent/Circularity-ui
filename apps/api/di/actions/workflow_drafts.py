"""Working drafts of workflows on the server, and the honest test run (plan 6, task C9).

**Drafts.** The canvas edits a copy of the workflow (apps/web/src/pages/workflows/draftStore.ts). It used to live only in
browser memory, so a reload or a sign-out lost it. Now the copy is autosaved after two seconds of quiet:

    workflow.draft.save     {id, graph, name, owner?, trig?, retries?, alert?, base?}   one draft per workflow and person
    workflow.draft.discard  {id}                                                         drops it (Discard, after Save)

kept in the workspace collection "workflow_drafts" under "<workflow id>|<account id>". The workflow's own page reads
the signed-in person's draft from GET /api/screens/workflows/{id} (`draft`) when it opens. A draft is not a version:
Save (workflow.save) is still what makes one; the page drops the draft after Save, Publish and Discard. Deleting a
workflow drops its drafts (`forget`), so a new workflow under a reused id starts clean.

**Test run.** `workflow.testRun` {id, graph?, sample?} runs the draft's graph (or the saved one) through the workflow
engine as a DRY run (di.workflow.engine.run_graph(..., dry=True, sample=N)): real records, real per-step counts and
before/after samples, nothing written. It is a read action: the pipeline journals nothing and the engine writes
nothing in a dry run.
"""

import copy
from typing import Any

from sqlalchemy import text

from di import state
from di.actions.pipeline import CallContext
from di.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.reads.common import iso, ms

COLLECTION = "workflow_drafts"
state.register(COLLECTION, list)

_DRAFT_IN: dict[str, dict[str, Any]] = {
    "id": {"req": True, "t": "string"},
    "graph": {"req": True, "t": "object"},
    "name": {"req": True, "t": "string"},
    "owner": {"req": False, "t": "string"},
    "trig": {"req": False, "t": "object"},
    "retries": {"req": False, "t": "number"},
    "alert": {"req": False, "t": "string"},
    "base": {"req": False, "t": "string"},
}
_FIELDS = ("graph", "name", "owner", "trig", "retries", "alert", "base")


def _declare(action_id: str, title: str, desc: str, risk: Any, inp: dict[str, dict[str, Any]]) -> None:
    # not journaled: an autosave every few seconds is the person's scratch copy, not an activity worth an audit row
    ACTIONS.setdefault(
        action_id,
        ActionDef(
            id=action_id, title=title, desc=desc, risk=risk, perm="manageWorkflows", scope="none", input=inp,
            verb="change workflows", journaled=False,
        ),
    )  # fmt: skip


_declare("workflow.draft.save", "Autosave a workflow draft", "Keep the working copy of a workflow for this person.", "draft",
         _DRAFT_IN)  # fmt: skip
_declare("workflow.draft.discard", "Discard a workflow draft", "Drop this person's working copy of a workflow.", "draft",
         {"id": {"req": True, "t": "string"}})  # fmt: skip


def key(wid: str, account: str) -> str:
    return f"{wid}|{account}"


def _account(ctx: CallContext) -> str:
    return ctx.actor.account.id if ctx.actor.account else "system"


def draft_for(s, wid: str, account: str) -> dict[str, Any] | None:
    """The person's draft of the workflow, or None."""
    d = state.get(s, COLLECTION, key(wid, account))
    return {k: copy.deepcopy(d[k]) for k in (*_FIELDS, "at") if k in d} if d else None


def forget(s, wid: str) -> None:
    """Every person's draft of a workflow (it was deleted; its id may be reused by a new one)."""
    state.items(s, COLLECTION)  # seeds the collection on first use
    s.execute(
        text("DELETE FROM state_item WHERE collection = :c AND id LIKE :p"),
        {"c": COLLECTION, "p": wid.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "|%"},
    )


def _graph_problem(g: Any) -> str | None:
    if not isinstance(g, dict) or not isinstance(g.get("nodes"), list) or not isinstance(g.get("edges"), list):
        return "The draft's graph needs nodes and edges."
    if not all(isinstance(n, dict) and isinstance(n.get("id"), str) for n in g["nodes"]):
        return "Every step in the draft needs an id."
    return None


@guard("workflow.draft.save")
def draft_save_guard(i: dict[str, Any], ctx: CallContext):
    if state.get(ctx.session, "workflows", i["id"]) is None:
        return "not_found", f"No workflow {i['id']}."
    p = _graph_problem(i["graph"])
    return ("validation_error", p) if p else None


@implement("workflow.draft.save")
def draft_save(i: dict[str, Any], ctx: CallContext):
    acct = _account(ctx)
    now = ms(ctx.now.isoformat())
    d: dict[str, Any] = {"id": key(i["id"], acct), "wf": i["id"], "by": acct, "at": iso(now)}
    d |= {k: copy.deepcopy(i[k]) for k in _FIELDS if i.get(k) is not None}
    state.put(ctx.session, COLLECTION, d["id"], d)
    return {"id": i["id"], "at": d["at"]}


@implement("workflow.draft.discard")
def draft_discard(i: dict[str, Any], ctx: CallContext):
    gone = state.delete(ctx.session, COLLECTION, key(i["id"], _account(ctx)))
    return {"id": i["id"], "discarded": bool(gone)}


# ---------------------------------------------------------------- the honest test run
_declare(
    "workflow.testRun", "Test run a workflow",
    "Run the draft dry over a sample of real records: every step's state, records in and out, samples. Writes nothing.",
    "read",
    {"id": {"req": True, "t": "string"}, "graph": {"req": False, "t": "object"}, "sample": {"req": False, "t": "number"},
     "approved": {"req": False, "t": "boolean"}},
)  # fmt: skip
SAMPLE = 25  # records read per connector when the caller does not say
SAMPLE_MAX = 500


def _test_graph(i: dict[str, Any], w: dict[str, Any]) -> dict:
    from di.actions import workflows as wf
    from di.workflow import blocks

    return blocks.compact_graph(copy.deepcopy(i["graph"] if i.get("graph") is not None else wf.graph_of(dict(w))))


@guard("workflow.testRun")
def test_run_guard(i: dict[str, Any], ctx: CallContext):
    from di.actions import workflows as wf

    w = state.get(ctx.session, "workflows", i["id"])
    if w is None:
        return "not_found", f"No workflow {i['id']}."
    if i.get("graph") is not None and (p := _graph_problem(i["graph"])):
        return "validation_error", p
    n = i.get("sample")
    if n is not None and (isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= SAMPLE_MAX):
        return "validation_error", f"Sample must be a whole number from 1 to {SAMPLE_MAX}."
    e = len(wf.errors(_test_graph(i, w), w["kind"], ctx.session))
    return ("conflict", f"Fix {e} error{'s' if e > 1 else ''} before running. The checks say what and why.") if e else None


def _descendants(succ: dict[str, list[str]], nid: str) -> set[str]:
    seen: set[str] = set()
    st = [nid]
    while st:
        for y in succ.get(st.pop(), []):
            if y not in seen:
                seen.add(y)
                st.append(y)
    return seen


@implement("workflow.testRun")
def test_run(i: dict[str, Any], ctx: CallContext):
    """A dry run of the graph through the engine (see the module docstring). Human approval stops it, as a real run
    waits for a person: the steps after it are `waiting` and the run `held`, until it is run again with `approved`
    (Approve and continue; still dry, so no instruction reaches any system)."""
    from di.reads.workflows import _analyze, _order
    from di.workflow.engine import run_graph

    w = state.get(ctx.session, "workflows", i["id"])
    if w is None:  # the guard refused it
        raise ActionError("not_found", f"No workflow {i['id']}.")
    g = _test_graph(i, w)
    _, succ, _ = _analyze(g)
    order = _order(g)
    approved = bool(i.get("approved"))
    stops = [] if approved else [n["id"] for n in g["nodes"] if n["k"] == "fixed" and n["ref"] == "appr"]
    after: set[str] = set()
    for a in stops:
        after |= _descendants(succ, a)
    run = g if not after else {
        "nodes": [n for n in g["nodes"] if n["id"] not in after],
        "edges": [e for e in g["edges"] if e["a"] not in after and e["b"] not in after],
    }  # fmt: skip
    r = run_graph(ctx.session, w, run, trigger="Test", dry=True, sample=i.get("sample") or SAMPLE, full=True, now=ctx.now)
    states, counts = dict(r.states), {k: dict(v) for k, v in r.counts.items()}
    dur = {k: round(v / 1000, 2) for k, v in r.dur_ms.items()}
    held = False
    for a in stops:
        if states.get(a) == "success":  # reached the person: it waits for them
            states[a], held = "held", True
            counts[a] = {"in": counts.get(a, {}).get("in", 0), "out": 0, "rej": 0}
    for x in after:
        up = any(states.get(a) in ("failed", "upstream_failed") for a in stops if x in _descendants(succ, a))
        states[x] = "upstream_failed" if up else "waiting"
        counts[x], dur[x] = {"in": 0, "out": 0, "rej": 0}, 0
    failed = any(v == "failed" for v in states.values())
    status = "failed" if failed else "held" if held else "success"
    samples = {k: v for k, v in r.samples.items() if k not in after}
    return {
        "id": w["id"], "name": w["name"], "dry": True, "status": status, "states": {k: states[k] for k in order if k in states},
        "counts": counts, "dur": dur, "order": order, "samples": samples, "rows": r.rows, "held": r.held,
        "note": r.note, "approved": approved,
    }  # fmt: skip
