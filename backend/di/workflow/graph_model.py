"""The typed workflow graph (plan 9, P9-8.12): `WorkflowGraph`, built from the block catalogue in `di.workflow.blocks`.

    WorkflowGraph        nodes (a union discriminated on `k`, and on `ref` for a transform) and edges `(a, b, port)`
    parse(raw)           `(WorkflowGraph | None, errors)`; each error is `{node, field, message}`, ready to go back to a model
    structure_errors(g)  duplicate ids, edges to nobody, a step wired to itself (what a typed shape cannot say)
    engine_graph(g)      the dict the engine, `workflow.validate` and the canvas read: `{nodes, edges}` with positions
    json_schema()        what a model is shown as the shape to write

Owns: the pydantic shape of a graph. Each block's `cfg` is a model made from its `FieldSpec`s (type, choices, bounds), with
every setting optional (a stored `cfg` keeps only what differs from the defaults) and no setting the block lacks. A node of a
block that does not exist, or a kind that is not a step kind, fails on its tag, and the error names the node.
Never does: read the database, know a source's fields (`blocks.cfg_errors` and `workflow.validate` check those, with the
source), publish or save anything. The engine has no edge ports: a `port` is kept in the typed shape so a model can say which
edge is the else path or the error path, and `engine_graph` orders a branch's else edge after its main one (which is how the
engine reads the second successor of a branch).

Implements no registry entry (an enabler for `workflow_author`, `di.services.agents.playbooks.workflow_author`).
"""

from typing import Annotated, Any, Literal, Union, cast

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, ValidationError, create_model

from di.workflow.blocks import BLOCKS, FieldSpec
from di.workflow.schema import STEP_KINDS

X0, DX, Y0, DY = 24, 206, 170, 90  # where the canvas puts the first step, and the step to step spacing
GraphError = dict[str, Any]  # {"node": step id | None, "field": str, "message": str}


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    check: Literal["present", "type", "regex", "range", "in"]
    arg: str | float | None = None


def _literal(values: list[Any]) -> Any:
    return Literal.__getitem__(tuple(values))


def _setting(f: FieldSpec) -> Any:
    """The type of one setting; it accepts what `blocks.cfg_errors` accepts on shape, choices and bounds."""
    if f.type == "text":
        return str
    if f.type == "number":
        return Annotated[int | float, Field(ge=f.min, le=f.max)]
    if f.type == "bool":
        return bool
    if f.type == "select":
        if f.key == "version":  # "latest" or a saved version number
            return Union[Literal["latest"], Annotated[int, Field(ge=1)]]  # noqa: UP007
        return _literal(list(f.choices) + ([] if f.required else [""])) if f.choices else str
    if f.type in ("multi", "fields"):
        return list[_literal(list(f.choices))] if f.choices else list[str]  # type: ignore[misc]
    if f.type == "rules":
        return list[Rule]
    return dict[str, _literal(list(f.choices))] if f.choices else dict[str, str]  # type: ignore[misc]


def _cfg_model(key: str) -> type[BaseModel]:
    fields: dict[str, Any] = {f.key: (_setting(f) | None, None) for f in BLOCKS[key].fields}
    return create_model(f"Cfg_{key}", __config__=ConfigDict(extra="forbid"), **fields)


class _Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str | None = None
    x: float | None = None
    y: float | None = None


KIND_KEYS = [k for k in STEP_KINDS if k != "xf" and k in BLOCKS]  # a block per kind (conn, map, fixed ...)
XF_REFS = [r for r in BLOCKS if r not in STEP_KINDS]  # a block per transform (x_val, x_filter ...)


def _node_model(key: str, xf: bool) -> type[BaseModel]:
    kind, ref = (Literal["xf"], _literal([key])) if xf else (_literal([key]), str)
    fields: dict[str, Any] = {"k": (kind, ...), "ref": (ref, Field(min_length=1)), "cfg": (_cfg_model(key) | None, None)}
    return create_model(f"Node_{key}", __base__=_Step, **fields)


_TAGS: dict[str, type[BaseModel]] = {k: _node_model(k, False) for k in KIND_KEYS} | {
    f"xf:{r}": _node_model(r, True) for r in XF_REFS
}


def _tag(v: Any) -> str | None:
    k, ref = (v.get("k"), v.get("ref")) if isinstance(v, dict) else (getattr(v, "k", None), getattr(v, "ref", None))
    tag = f"xf:{ref}" if k == "xf" else k
    return tag if tag in _TAGS else None


Node = Annotated[Union[tuple(Annotated[m, Tag(t)] for t, m in _TAGS.items())], Discriminator(_tag)]  # type: ignore[valid-type]  # noqa: UP007


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: str
    b: str
    port: Literal["else", "error"] | None = None


class WorkflowGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[Node] = Field(min_length=1)  # type: ignore[valid-type]
    edges: list[Edge]


def json_schema() -> dict[str, Any]:
    return WorkflowGraph.model_json_schema()


def _describe(e: Any, raw: Any) -> GraphError:
    """One pydantic error as `(node, field, message)`; the node is the id of the step the error's path runs through."""
    loc = [p for p in e["loc"] if not (isinstance(p, str) and p in _TAGS)]  # the tag of the union branch is not a field
    node = None
    if len(loc) > 1 and loc[0] == "nodes" and isinstance(loc[1], int):
        nodes = raw.get("nodes") if isinstance(raw, dict) else None
        n = nodes[loc[1]] if isinstance(nodes, list) and loc[1] < len(nodes) else None
        node = n.get("id") if isinstance(n, dict) else None
        if node is None:
            node = f"nodes[{loc[1]}]"
    path = ".".join(str(p) for p in (loc[2:] if node else loc))
    if e["type"] in ("union_tag_invalid", "union_tag_not_found"):
        n = (raw["nodes"][loc[1]] if node else None) or {}
        what = f"k={n.get('k')!r} ref={n.get('ref')!r}" if isinstance(n, dict) else "this step"
        return {
            "node": node,
            "field": "ref",
            "message": f"No block {what}. Use a block of the catalogue: k and, for k xf, its ref.",
        }
    if e["type"] == "missing":
        return {"node": node, "field": path, "message": f"{path} is required."}
    if e["type"] == "extra_forbidden":
        return {"node": node, "field": path, "message": f"{path} is not a setting of this block."}
    return {"node": node, "field": path, "message": str(e["msg"])}


def parse(raw: Any) -> tuple[WorkflowGraph | None, list[GraphError]]:
    """Validate a model's graph: the typed graph, or every problem found with its step and setting."""
    try:
        return WorkflowGraph.model_validate(raw), []
    except ValidationError as ve:
        seen: set[tuple[Any, str, str]] = set()
        out: list[GraphError] = []
        for e in ve.errors(include_url=False):
            d = _describe(e, raw)
            key = (d["node"], d["field"], d["message"])
            if key not in seen:
                seen.add(key)
                out.append(d)
        return None, out


def structure_errors(g: WorkflowGraph) -> list[GraphError]:
    ids = [n.id for n in g.nodes]  # type: ignore[attr-defined]
    out: list[GraphError] = [
        {"node": i, "field": "id", "message": f"Step id {i} is used twice."} for i in dict.fromkeys(ids) if ids.count(i) > 1
    ]
    for e in g.edges:
        for end in (e.a, e.b):
            if end not in ids:
                out.append(
                    {"node": None, "field": "edges", "message": f"The edge {e.a} to {e.b} names {end}, which is not a step."}
                )
        if e.a == e.b:
            out.append({"node": e.a, "field": "edges", "message": f"Step {e.a} is wired to itself."})
    return out


def _depths(ids: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    d = dict.fromkeys(ids, 0)
    for _ in range(len(ids)):  # longest path from a start, bounded so a cycle cannot loop
        for a, b in edges:
            if a in d and b in d and d[b] < d[a] + 1 < len(ids):
                d[b] = d[a] + 1
    return d


def engine_graph(g: WorkflowGraph) -> dict[str, Any]:
    """The graph the engine runs: `{id, k, ref, x, y, cfg?, ai}` nodes and `{id, a, b, locked}` edges. A step with no
    position is laid out left to right by its depth; every node carries `ai: 1` (an assistant wrote it)."""
    ids = [n.id for n in g.nodes]  # type: ignore[attr-defined]
    depth = _depths(ids, [(e.a, e.b) for e in g.edges])
    row: dict[int, int] = {}
    nodes: list[dict[str, Any]] = []
    for n in cast("list[Any]", g.nodes):
        r = row.get(depth[n.id], 0)
        row[depth[n.id]] = r + 1
        out: dict[str, Any] = {
            "id": n.id, "k": n.k, "ref": n.ref,
            "x": n.x if n.x is not None else X0 + DX * depth[n.id], "y": n.y if n.y is not None else Y0 + DY * r,
        }  # fmt: skip
        cfg = n.cfg.model_dump(exclude_none=True) if n.cfg is not None else {}
        if cfg:
            out["cfg"] = cfg
        nodes.append(out | {"ai": 1})
    ordered = sorted(g.edges, key=lambda e: e.port == "else")  # stable: a branch's else edge comes after its main one
    edges = [{"id": f"e{i}", "a": e.a, "b": e.b, "locked": False} for i, e in enumerate(ordered)]
    return {"nodes": nodes, "edges": edges}
