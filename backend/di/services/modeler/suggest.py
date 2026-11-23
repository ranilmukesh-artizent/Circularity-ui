"""Rule suggestions from Approver overrides (plan 8, MVP-12.3; the prototype's device suggestion "owners keep overriding
aged lots to Auction", line 2439).

The journaled decisions of a template (`decision.approve` and `decision.override`), one `DecisionRow` each, are
grouped by (template, from route, to route) and by each set dimension's value of the case. When at least
`min_overrides` overrides share a (to route, dimension value) and form at least `min_share` of that value's decisions,
the pattern becomes a suggested rule "<dimension value words>: prefer <to route name>". `place_rule` drafts it into a
flow as the assistant places a rule (Domain spec D10): between the last node feeding the decision and the decision.

A suggestion is only a proposal: a person adds it to their draft through the Modeler, and the flow is then submitted,
approved by someone else and published as any other change. Nothing here reads or writes the database.
"""

import copy
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from di.services.modeler.flow import Flow, fe, fn
from di.services.modeler.templates import Template
from di.services.modeler.text import js_str, rule_text

MIN_OVERRIDES = 3
MIN_SHARE = 0.6


@dataclass(frozen=True)
class DecisionRow:
    """One journaled decision: the route the engine recommended (`from_path`) and the one approved (`to_path`), with
    the case's value for each scope dimension (dim key -> value)."""

    case_id: str
    template: str
    from_path: str | None
    to_path: str
    values: Mapping[str, Any]

    @property
    def override(self) -> bool:
        return self.from_path is not None and self.to_path != self.from_path


@dataclass(frozen=True)
class OverrideGroup:
    template: str
    from_path: str
    to_path: str
    n: int


@dataclass(frozen=True)
class Suggestion:
    dim: str
    value: str
    path: str
    overrides: int
    decisions: int
    share: float
    text: str
    rule: dict[str, Any]


def override_groups(rows: Sequence[DecisionRow]) -> list[OverrideGroup]:
    """The overrides per (template, from route, to route), the largest first."""
    n = Counter((r.template, r.from_path or "", r.to_path) for r in rows if r.override)
    return [OverrideGroup(t, a, b, k) for (t, a, b), k in sorted(n.items(), key=lambda x: (-x[1], x[0]))]


def suggest(
    t: Template, rows: Sequence[DecisionRow], min_overrides: int = MIN_OVERRIDES, min_share: float = MIN_SHARE
) -> list[Suggestion]:
    """The suggested prefer rules for template `t`, the most overridden first."""
    mine = [r for r in rows if r.template == t.key]
    out: list[Suggestion] = []
    for d in (d for d in t.dims if d.kind == "set"):
        decisions = Counter(js_str(r.values[d.key]) for r in mine if r.values.get(d.key) not in (None, ""))
        overridden = Counter(
            (js_str(r.values[d.key]), r.to_path) for r in mine if r.override and r.values.get(d.key) not in (None, "")
        )
        for (value, path), k in sorted(overridden.items()):
            share = k / decisions[value]
            if k < min_overrides or share < min_share or t.path(path) is None:
                continue
            rule = {"action": "prefer", "path": path, "scope": {d.key: [value]}}
            out.append(Suggestion(d.key, value, path, k, decisions[value], share, rule_text(t, rule), rule))
    return sorted(out, key=lambda s: (-s.overrides, -s.share))


def _rid_number(rid: str) -> int:
    m = re.search(r"(\d+)$", rid)
    return int(m.group(1)) if m else 0


def place_rule(t: Template, g: Flow, rule: Mapping[str, Any], owner: str, src: str) -> tuple[Flow, str, str]:
    """A copy of `g` with `rule` as a new rule node with the next rid (`<pre>-nn`), between the last node feeding the
    decision and the decision, as the prototype's buildProposal places it. Answers (graph, node id, rid)."""
    c = copy.deepcopy(g)
    nodes, edges = c["nodes"], c["edges"]
    num = max([0, *(_rid_number(n["rid"]) for n in nodes if n.get("rid"))]) + 1
    rid = f"{t.pre}-{num:02d}"
    dec = next(n for n in nodes if n["t"] == "decision")["id"]
    gate = next(n for n in nodes if n["t"] == "gate")
    into = next((e for e in edges if e["b"] == dec), None)
    last = into["a"] if into else gate["id"]
    taken = {n["id"] for n in nodes}
    node_id, k = f"sg-{rid}", 1
    while node_id in taken:
        node_id, k = f"sg-{rid}-{k}", k + 1
    ys = [n["y"] for n in nodes if n["t"] == "rule"]
    y = (max(ys) if ys else 50) + 140
    nodes.append(fn(node_id, "rule", gate["x"], y, "", "", rid=rid, action=rule["action"], path=rule["path"],
                    scope=copy.deepcopy(dict(rule.get("scope") or {})), owner=owner, ai=True, src=src))  # fmt: skip
    if into is not None:
        edges.remove(into)
    edges += [fe(last, node_id), fe(node_id, dec)]
    return c, node_id, rid
