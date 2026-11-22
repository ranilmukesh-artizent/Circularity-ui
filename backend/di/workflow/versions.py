"""Workflow versions (plan 6 C8): every version a workflow had, with its graph and its settings.

The demo kept only the latest graph of a workflow (and a version log, `hist`, without the graphs). Here every save,
publish, restore and applied fix keeps the version it makes in the workspace collection "workflow_versions", one item
per version under the key `<workflow id>@<version>`:

    {id, wf, ver, at, by, note, graph, settings: {name, owner, trig, retries?, alert?}}

The version a workflow had before its first change here (a starting workflow, or a new one at 0.1) is kept the first
time it changes (`keep_prior`), so it can be compared and restored too. The collection starts empty, so the demo
reset (state.reset) forgets every version made in the app. Deleting a workflow forgets its versions (ids are reused).

Which version runs: a published workflow carries the version that was published as `pub` ({ver, graph, settings}), set
when it is published and kept while a person saves drafts (`di.services.actions.workflows.graph_for_run`). The screens leave
`pub` out of the workflow and show `published_ver` instead.

`diff` is the History tab's Compare: blocks added, removed and changed (kind, reference, failure flag and every setting
with the defaults filled in; the position on the canvas is left out), links added and removed, and changed settings.
"""

import copy
from collections.abc import Callable
from typing import Any

from sqlalchemy import CursorResult, text
from sqlalchemy.orm import Session

from di.core import state
from di.workflow import blocks

COLL = "workflow_versions"
state.register(COLL, lambda: [])
SETTINGS = ("name", "owner", "trig", "retries", "alert")
_EMPTY: dict = {"nodes": [], "edges": []}


def key(wid: str, ver: str) -> str:
    return f"{wid}@{ver}"


def snapshot(w: dict) -> dict:
    """The graph and the settings of the workflow as it is now."""
    return {
        "graph": copy.deepcopy(w.get("graph") or _EMPTY),
        "settings": {k: copy.deepcopy(w[k]) for k in SETTINGS if w.get(k) is not None},
    }


def get(s: Session, wid: str, ver: str) -> dict | None:
    return state.get(s, COLL, key(wid, ver))


def of(s: Session, wid: str) -> list[dict]:
    """The stored versions of a workflow, newest first."""
    state.get(s, COLL, "")  # seeds the collection (empty) on its first read
    return list(
        s.execute(
            text("SELECT data FROM state_item WHERE collection = :c AND data->>'wf' = :w ORDER BY seq DESC"),
            {"c": COLL, "w": wid},
        ).scalars()
    )


def keep(s: Session, w: dict, by: str, at: str, note: str) -> dict:
    """Store the workflow's current version (replacing a stored one of the same number)."""
    v = {"id": key(w["id"], w["ver"]), "wf": w["id"], "ver": w["ver"], "at": at, "by": by, "note": note} | snapshot(w)
    state.put(s, COLL, v["id"], v)
    return v


def prior_entry(w: dict, iso: Callable[[Any], str]) -> dict:
    """The current version as it was before versions were kept: who and when from the version log when it has the
    version, else the workflow's owner and its last update."""
    h = next((x for x in w.get("hist") or [] if x.get("ver") == w["ver"]), None)
    at = h["at"] if h else (iso(w["updated"]) if isinstance(w.get("updated"), int | float) else str(w.get("updated") or ""))
    by = h["by"] if h else (w.get("owner") or "—")
    note = h["note"] if h else "Starting version"
    return {"id": key(w["id"], w["ver"]), "wf": w["id"], "ver": w["ver"], "at": at, "by": by, "note": note}


def keep_prior(s: Session, w: dict, iso: Callable[[Any], str]) -> None:
    """Before a change: store the current version if it is not stored yet."""
    if get(s, w["id"], w["ver"]) is None:
        v = prior_entry(w, iso) | snapshot(w)
        state.put(s, COLL, v["id"], v)


def forget(s: Session, wid: str) -> int:
    state.get(s, COLL, "")
    r = s.execute(text("DELETE FROM state_item WHERE collection = :c AND data->>'wf' = :w"), {"c": COLL, "w": wid})
    return r.rowcount if isinstance(r, CursorResult) else 0


def listing(s: Session, w: dict, iso: Callable[[Any], str]) -> list[dict]:
    """The History tab's versions, newest first: version, when, by, note, and which one is current and published."""
    stored = of(s, w["id"])
    if not any(v["ver"] == w["ver"] for v in stored):
        stored = [prior_entry(w, iso), *stored]
    pub = (w.get("pub") or {}).get("ver")
    return [
        {k: v.get(k) for k in ("ver", "at", "by", "note")} | {"current": v["ver"] == w["ver"], "published": v["ver"] == pub}
        for v in stored
    ]


def resolve(s: Session, w: dict, ver: str) -> dict | None:
    """A version's graph and settings: stored, or the workflow itself for its current version."""
    v = get(s, w["id"], ver)
    if v is None and ver == w["ver"]:
        return {"ver": ver} | snapshot(w)
    return v


def _cfg(n: dict) -> dict:
    try:
        return blocks.node_cfg(n)
    except Exception:  # noqa: BLE001 - a block the catalogue does not know: its stored settings as they are
        return dict(n.get("cfg") or {})


def diff(a: dict, b: dict, label: Callable[[dict], str]) -> dict:
    """What changed from version a to version b."""

    def lb(n: dict) -> str:
        try:
            return label(n)
        except (LookupError, StopIteration, KeyError):
            return n.get("ref") or n["id"]

    na = {n["id"]: n for n in a["graph"].get("nodes") or []}
    nb = {n["id"]: n for n in b["graph"].get("nodes") or []}
    changed = []
    for nid, y in nb.items():
        x = na.get(nid)
        if x is None:
            continue
        fields = [{"field": f, "from": x.get(f), "to": y.get(f)} for f in ("k", "ref") if x.get(f) != y.get(f)]
        if bool(x.get("fail")) != bool(y.get("fail")):
            fields.append({"field": "fail", "from": bool(x.get("fail")), "to": bool(y.get("fail"))})
        ca, cb = _cfg(x), _cfg(y)
        fields += [{"field": f, "from": ca.get(f), "to": cb.get(f)} for f in dict.fromkeys([*ca, *cb]) if ca.get(f) != cb.get(f)]
        if fields:
            changed.append({"id": nid, "label": lb(y), "fields": fields})

    def links(g: dict) -> list[tuple[str, str]]:
        return list(dict.fromkeys((e["a"], e["b"]) for e in g.get("edges") or []))

    la, lb_ = links(a["graph"]), links(b["graph"])
    sa, sb = a.get("settings") or {}, b.get("settings") or {}
    return {
        "a": a["ver"],
        "b": b["ver"],
        "blocks": {
            "added": [{"id": i, "label": lb(n)} for i, n in nb.items() if i not in na],
            "removed": [{"id": i, "label": lb(n)} for i, n in na.items() if i not in nb],
            "changed": changed,
        },
        "links": {
            "added": [{"a": x, "b": y} for x, y in lb_ if (x, y) not in la],
            "removed": [{"a": x, "b": y} for x, y in la if (x, y) not in lb_],
        },
        "settings": [{"key": k, "from": sa.get(k), "to": sb.get(k)} for k in SETTINGS if sa.get(k) != sb.get(k)],
    }
