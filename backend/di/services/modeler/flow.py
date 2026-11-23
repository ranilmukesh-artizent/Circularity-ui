"""The process flow graph (Domain spec D1; the prototype's `FN`, `FE`, `tplEquip`, `tplDevice`, `fReach`, `nodeLabel`).

A node is `{id, t, x, y, label, sub, h, lock, rid?, action?, path?, scope?, owner?, ai?, src?}`; an edge is
`{id: a + ">" + b, a, b, l}`. Business rules are `rule` nodes; the locked node types (`LOCKED`) are the core
prediction, the guardrail gate, the decision, owner approval, execution and learning, which no flow edit changes.
"""

import copy
from collections import deque
from typing import Any, NotRequired, TypedDict

from di.core import golden
from di.services.modeler.templates import Template
from di.services.modeler.text import rule_text

LOCKED = ("trigger", "agent", "gate", "guard", "decision", "approval", "execute", "learn")
NODE_TYPES = ("trigger", "agent", "gate", "guard", "rule", "decision", "approval", "path", "execute", "learn", "step")
PO_FLOW = {"tool_fleet": "equip", "device": "device"}  # template key -> key in fixtures/golden/po/flows.json


class Node(TypedDict):
    id: str
    t: str
    x: int
    y: int
    label: str
    sub: str
    h: int
    lock: bool
    rid: NotRequired[str]
    action: NotRequired[str]
    path: NotRequired[str | None]
    scope: NotRequired[dict[str, Any]]
    owner: NotRequired[str]
    ai: NotRequired[bool]
    src: NotRequired[str]


class Edge(TypedDict):
    id: str
    a: str
    b: str
    l: str  # noqa: E741 (the prototype's field name: the edge's label)


class Flow(TypedDict):
    nodes: list[Node]
    edges: list[Edge]


def fn(id_: str, t: str, x: int, y: int, label: str, sub: str = "", **extra: Any) -> Node:
    """The prototype's FN: a node with its height (path nodes are lower) and its lock (by type)."""
    n: Node = {"id": id_, "t": t, "x": x, "y": y, "label": label, "sub": sub, "h": 104 if t == "path" else 112,
               "lock": t in LOCKED}  # fmt: skip
    n.update(extra)  # type: ignore[typeddict-item]
    return n


def fe(a: str, b: str, label: str = "") -> Edge:
    return {"id": a + ">" + b, "a": a, "b": b, "l": label}


def _industrial(t: Template) -> Flow:
    """The D1 shape over the demo's routes, without agent or rule nodes: the published default has no business rules,
    so the demo's cases evaluate exactly as before."""
    gates = " · ".join(g.id for g in t.guardrails[:-1])
    nodes = [
        fn("in", "trigger", 24, 40, "Asset returned", "Intake · source systems and manual entry"),
        fn("gate", "gate", 220, 40, "Guardrail gate", gates),
        fn("dec", "decision", 416, 330, "Choose best route", "Decision engine · net of cost and time"),
        fn("apr", "approval", 612, 330, "Owner approves", t.guardrails[-1].id + " · named owner"),
    ]
    nodes += [fn("p-" + p.id, "path", 808, 20 + i * 116, p.name, p.app, path=p.id, owner=p.owner) for i, p in enumerate(t.paths)]
    nodes += [
        fn("exe", "execute", 1200, 280, "Execute in owning application", "Follow-through agent"),
        fn("lrn", "learn", 1200, 420, "Outcome to learning memory", "Feeds valuation and disposition models"),
    ]
    edges = [fe("in", "gate"), fe("gate", "dec"), fe("dec", "apr")]
    edges += [fe("apr", "p-" + k) for k in t.path_ids()] + [fe("p-" + k, "exe") for k in t.path_ids()] + [fe("exe", "lrn")]
    return {"nodes": nodes, "edges": edges}


def default_flow(t: Template) -> Flow:
    """The template's default flow, a fresh copy: the prototype's tplEquip / tplDevice (as the PO golden records
    them) for `tool_fleet` and `device`; for `industrial`, the D1 shape over the demo's 7 routes."""
    if t.key in PO_FLOW:
        g = golden.load("po/flows")[PO_FLOW[t.key]]
        return {"nodes": copy.deepcopy(g["n"]), "edges": copy.deepcopy(g["e"])}
    return _industrial(t)


def reach(f: Flow, start: str, skip: str | None = None) -> set[str]:
    """The nodes reachable from `start` along the edges, never entering `skip` (the prototype's fReach)."""
    seen, q = {start}, deque([start])
    while q:
        x = q.popleft()
        for e in f["edges"]:
            if e["a"] == x and e["b"] != skip and e["b"] not in seen:
                seen.add(e["b"])
                q.append(e["b"])
    return seen


def node_label(n: Node, t: Template | None = None) -> str:
    """A node's label; a rule node reads "<rid> · <never|only|prefer path>" (or "set a path"), which needs its
    template's wording."""
    if n["t"] != "rule":
        return n["label"]
    tail = rule_text(t, n).split(": ")[-1] if n.get("path") and t else "set a path"
    return n.get("rid", "") + " · " + tail
