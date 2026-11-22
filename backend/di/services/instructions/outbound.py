"""The outbound workflow an instruction for a target system follows (plan 6 follow-up: the delivery method's Timeout and
Retries and the write connector's Target operation are used).

    settings(s, "repair")   -> {"timeout_s": 5, "retries": 1, "operation": "teardown"}, or {} (the demo's sends)

The bound outbound workflow of a target is the newest one published here (status `published` with a published version
`pub`, category Outbound) whose graph (the version that runs) has a write connector (`wconn`) to the target, as
di/workflow/binding.py binds ingest workflows. The starting workflows the demo seeds as published (WF-122 ... WF-132)
have no `pub`, so no target is bound until a person publishes an outbound workflow, and the demo's instructions go
out exactly as before.

Only the settings a person changed count (a node stores only the settings that differ from the defaults, blocks.
compact_cfg): a workflow published with the defaults changes nothing either. From the graph:
- `timeout_s`, `retries`: the delivery method (`act`) that leads to the target's write connector (else the graph's first
  one). The timeout is the HTTP timeout of each write call (writers.timeout); retries is how many times a write that
  failed on a transient error (the system down, a timeout, refused credentials) is tried again before the instruction
  fails (send.py; never more than the job queue's own `job_max_attempts`).
- `operation`: the write connector's Target operation (one of writers.operations(target); writers.operation_for).
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from di.core import state

log = logging.getLogger("di.services.instructions")
KEYS_ACT = ("timeout_s", "retries")


def _wconn(g: dict, system: str) -> dict | None:
    nodes = [n for n in g.get("nodes") or [] if isinstance(n, dict)]
    return next((n for n in nodes if n.get("k") == "wconn" and n.get("ref") == system), None)


def _runs_to(w: dict, system: str) -> dict | None:
    """The graph that runs, when the workflow is an outbound workflow published here writing to the system."""
    if w.get("status") != "published" or not w.get("pub") or w.get("cat") != "Outbound":
        return None
    g = (w.get("pub") or {}).get("graph")
    return g if isinstance(g, dict) and _wconn(g, system) is not None else None


def _act_before(g: dict, wid: Any) -> dict | None:
    """The delivery method upstream of the node `wid` (the nearest first), else the graph's first one."""
    by = {n.get("id"): n for n in g.get("nodes") or [] if isinstance(n, dict)}
    pred: dict[Any, list] = {}
    for e in g.get("edges") or []:
        if isinstance(e, dict):
            pred.setdefault(e.get("b"), []).append(e.get("a"))
    seen, todo = {wid}, list(pred.get(wid, []))
    while todo:
        x = todo.pop(0)
        if x in seen:
            continue
        seen.add(x)
        if (by.get(x) or {}).get("k") == "act":
            return by[x]
        todo += pred.get(x, [])
    return next((n for n in by.values() if n.get("k") == "act"), None)


def bound(s: Session, system: str) -> tuple[dict, dict] | None:
    """(workflow, graph) of the target's bound outbound workflow, or None."""
    cands = [(w, g) for w in state.items(s, "workflows") if (g := _runs_to(w, system)) is not None]
    if not cands:
        return None
    cands.sort(key=lambda x: (x[0].get("updated") or 0, x[0]["id"]), reverse=True)
    return cands[0]


def settings(s: Session, system: str) -> dict[str, Any]:
    """The changed settings of the target's bound outbound workflow (see the module docstring); {} for none, or when
    they cannot be read (a workflow never stops an instruction)."""
    try:
        return _settings(s, system)
    except Exception:  # the instruction goes out as the demo sends it
        log.exception("outbound settings for %s could not be read", system)
        return {}


def _settings(s: Session, system: str) -> dict[str, Any]:
    b = bound(s, system)
    if b is None:
        return {}
    _, g = b
    w = _wconn(g, system) or {}
    out: dict[str, Any] = {}
    act = _act_before(g, w.get("id"))
    acfg = (act or {}).get("cfg") if isinstance((act or {}).get("cfg"), dict) else {}
    for k in KEYS_ACT:
        v = (acfg or {}).get(k)
        if isinstance(v, int | float) and not isinstance(v, bool):
            out[k] = v
    op = (w.get("cfg") or {}).get("operation") if isinstance(w.get("cfg"), dict) else None
    if isinstance(op, str) and op.strip():
        out["operation"] = op.strip()
    return out
