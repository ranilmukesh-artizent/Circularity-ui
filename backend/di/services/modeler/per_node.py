"""How many cases reach and leave each node of a flow on a queue (plan 9, P9-8.15; `flow.simulate`'s `per_node`).

Owns: `per_node(template, flow, queue)`, pure. For every node `{in, out, examples}`:
- `in`: the cases that reach the node (all of the queue for a node on the way from intake through the gate to the decision;
  none for a node no case can reach, such as a rule with no path from the gate);
- `out`: the cases that leave it towards the decision. A rule that counts (the same test as `compile.compile_flow`) with the
  action `exclude` removes the cases in its scope; `prefer` and `require` redirect a case without removing it, so every
  case leaves. Every other node passes every case on;
- `examples`: at most three case ids, the removed cases first, then the cases in a rule's scope, then the first cases.
Never does: decide a case (the valuation and the simulation stay in `simulate.py`), read the database, or edit the flow.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from di.services.modeler.flow import Flow, Node, reach
from di.services.modeler.guard import rule_breaks
from di.services.modeler.scope import in_scope
from di.services.modeler.templates import Template

EXAMPLES = 3


def _counts(n: Node, f: Flow, t: Template, queue: Sequence[Mapping[str, Any]], dec: str) -> dict[str, Any]:
    ids = [str(c["id"]) for c in queue]
    if n["t"] != "rule":
        return {"in": len(ids), "out": len(ids), "examples": ids[:EXAMPLES]}
    scope = n.get("scope") or {}
    hit = [str(c["id"]) for c in queue if in_scope(c, scope, t.dims)]
    counts = bool(n.get("path")) and dec in reach(f, n["id"]) and not rule_breaks(t, n)
    gone = hit if counts and n.get("action") == "exclude" else []
    shown = gone or hit or ids
    return {"in": len(ids), "out": len(ids) - len(gone), "examples": shown[:EXAMPLES]}


def per_node(t: Template, f: Flow, queue: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """`{node id: {in, out, examples}}` for the flow on the queue."""
    gate = next(n["id"] for n in f["nodes"] if n["t"] == "gate")
    dec = next(n["id"] for n in f["nodes"] if n["t"] == "decision")
    from_gate = reach(f, gate)
    out: dict[str, dict[str, Any]] = {}
    for n in f["nodes"]:
        on_the_way = n["id"] in from_gate or gate in reach(f, n["id"])
        if on_the_way:
            out[n["id"]] = _counts(n, f, t, queue, dec)
        else:
            out[n["id"]] = {"in": 0, "out": 0, "examples": []}
    return out
