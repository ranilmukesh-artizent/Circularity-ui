"""Which ingest workflow a source's sync runs (plan 6, task C5).

    bound(s, "erp")          -> (workflow, graph): the published ingest workflow bound to the source, or the default
    rebind(s, "erp")         -> the binding again from the workflows as they are now (on publish, unpublish, delete)
    rebind_for(s, w)         -> rebind every source the workflow reads (before and after a change)

The binding is `source_config.workflow` (the workspace collection of di.connectors.lifecycle): the newest ingest
workflow published here (status `published` with a published version `pub`, category Ingest) whose connector reads the
source, in the version that runs (`graph_for_run`). The starting workflows the demo seeds as published are not bound
until a person publishes one. A source without one syncs with `engine.default_graph`: New workflow's minimal ingest graph, whose
steps pass every record on unchanged, so its canonical data is exactly what the source's adapter maps
(tests/test_workflow_engine.py, test_engine_parity_canonical). A source nobody bound keeps no item in source_config,
so the seeded state stays the demo's.

A bound workflow handles only the resources its connector steps read (`resources` ticked; none ticked: every one).
The sync reads the source's other resources through `rest_graph`, the default graph narrowed to them, in the same
sync_run (di.connectors.sync.run_sync), so publishing a workflow that reads one resource (the tutorial's SAP workflow
reads purchase_order) never stops the rest of the source from syncing.

    unread(graph, "erp", ["product", "purchase_order"])  -> the resources no connector step of the graph reads
    rest_graph("erp", ["product"])                       -> the default graph reading only those
"""

from typing import Any

from sqlalchemy.orm import Session

from di.connectors import lifecycle
from di.core import state

KEY = "workflow"


def ingest_source(g: dict | None) -> str | None:
    """The source an ingest graph reads: its first connector's."""
    for n in (g or {}).get("nodes") or []:
        if isinstance(n, dict) and n.get("k") == "conn":
            return n.get("ref")
    return None


def _runs_on(w: dict, sid: str) -> bool:
    """Published here (Publish keeps the version that runs in `pub`, plan 6 C8), an ingest workflow, reading the source.
    The starting workflows the demo seeds as published have no `pub`: they are not bound until a person publishes
    them, so the demo's sources keep syncing exactly as their adapters map."""
    from di.services.actions.workflows import graph_for_run

    return (
        w.get("status") == "published" and bool(w.get("pub")) and w.get("cat") == "Ingest"
        and ingest_source(graph_for_run(w)) == sid
    )  # fmt: skip


def rebind(s: Session, sid: str) -> str | None:
    """Bind the source to its newest published ingest workflow (by the time it last changed), or unbind it. Returns
    the bound workflow's id. In the caller's transaction."""
    cands = [w for w in state.items(s, "workflows") if _runs_on(w, sid)]
    cands.sort(key=lambda w: (w.get("updated") or 0, w["id"]), reverse=True)
    wid = cands[0]["id"] if cands else None
    item = state.get(s, lifecycle.COLLECTION, sid, for_update=True)
    if item is None:
        if wid is None:
            return None
        item = {"id": sid}
    if item.get(KEY) == wid:
        return wid
    if wid is None:
        item.pop(KEY, None)
    else:
        item[KEY] = wid
    lifecycle.save(s, item)
    return wid


def rebind_for(s: Session, w: dict, *also: str | None) -> None:
    """Rebind the sources the workflow reads (its saved graph's, its published version's, its system) and `also`."""
    from di.services.actions.workflows import graph_of

    sids = {ingest_source((w.get("pub") or {}).get("graph")), w.get("src"), *also}
    if w.get("graph") or w.get("tpl"):
        sids.add(ingest_source(graph_of(w)))
    for sid in sorted(x for x in sids if x):
        rebind(s, sid)


def unread(g: dict, sid: str, names: list[str]) -> list[str]:
    """The resources among `names` (the adapter's, in its order) that no connector step of the graph reading the
    source reads: none when a connector step ticks no resource (it reads every one)."""
    from di.workflow.blocks import node_cfg

    read: set[str] = set()
    for n in g.get("nodes") or []:
        if isinstance(n, dict) and n.get("k") == "conn" and n.get("ref") == sid:
            want = node_cfg(n).get("resources") or []
            if not want:
                return []
            read.update(want)
    return [x for x in names if x not in read]


def rest_graph(sid: str, names: list[str]) -> dict:
    """The default ingest graph reading only these resources of the source."""
    from di.workflow.engine import default_graph

    g = default_graph(sid)
    for n in g["nodes"]:
        if n.get("k") == "conn" and n.get("ref") == sid:
            n["cfg"] = {**(n.get("cfg") or {}), "resources": list(names)}
    return g


def bound(s: Session, sid: str) -> tuple[dict[str, Any], dict]:
    """The workflow a sync of the source runs and its graph: the bound one while it is still published and still
    reads the source, otherwise the default ingest graph."""
    from di.services.actions.workflows import graph_for_run
    from di.workflow.engine import default_graph

    item = state.get(s, lifecycle.COLLECTION, sid) or {}
    wid = item.get(KEY)
    w = state.get(s, "workflows", wid) if wid else None
    if w is not None and _runs_on(w, sid):
        return w, graph_for_run(w)
    return default_wf(sid), default_graph(sid)


def default_wf(sid: str) -> dict[str, Any]:
    """The workflow record a sync with the default graph runs as."""
    return {"id": None, "name": f"Default ingest · {sid}", "src": sid, "kind": "pipe", "cat": "Ingest"}
