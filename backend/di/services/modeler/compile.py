"""A flow compiled into the business rules that decisions apply (Domain spec D5; the prototype's compileEquip and
compileDevice).

A rule node counts only if it has a path, is reachable from the guardrail gate, reaches the decision, and breaks no
guardrail. Every path that owner approval cannot reach adds the pseudo-rule `FLOW` that excludes it.
"""

from dataclasses import dataclass
from typing import Any

from di.services.modeler.flow import Flow, Node, reach
from di.services.modeler.guard import rule_breaks
from di.services.modeler.templates import Template
from di.services.modeler.text import rule_text

__all__ = ["FLOW", "CompiledRule", "FlowVersion", "compile_flow", "rule_text"]

FLOW = "FLOW"


@dataclass(frozen=True)
class CompiledRule:
    id: str
    scope: dict[str, Any]
    action: str
    path: str
    text: str


@dataclass(frozen=True)
class FlowVersion:
    """The flow a decision is made under (registry I-6): its id (None for a rule set that belongs to no stored flow, such
    as a sample), its published version and its compiled rules."""

    flow_id: int | None
    ver: int
    rules: tuple[CompiledRule, ...]


def _first(f: Flow, t: str) -> Node:
    return next(n for n in f["nodes"] if n["t"] == t)


def compile_flow(t: Template, f: Flow) -> list[CompiledRule]:
    gate, dec, apr = _first(f, "gate"), _first(f, "decision"), _first(f, "approval")
    from_gate = reach(f, gate["id"])
    out = [
        CompiledRule(n.get("rid", ""), n.get("scope") or {}, n.get("action", ""), path, rule_text(t, n))
        for n in f["nodes"]
        if n["t"] == "rule" and (path := n.get("path"))
        and n["id"] in from_gate and dec["id"] in reach(f, n["id"]) and not rule_breaks(t, n)
    ]  # fmt: skip
    offered = reach(f, apr["id"])
    for k in t.path_ids():
        pn = next((n for n in f["nodes"] if n["t"] == "path" and n.get("path") == k), None)
        if pn is None or pn["id"] not in offered:
            out.append(CompiledRule(FLOW, {}, "exclude", k, "removed from flow"))
    return out
