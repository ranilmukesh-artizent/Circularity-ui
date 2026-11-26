"""Business rules applied to a case's routes after the gate rules (Domain spec D4; the prototype's applyRules).

Rules apply in order, only to cases in their scope, and only to a route that is still eligible:
- exclude: the route fails at gate 2 (Policy & certification) with "Excluded by business rule <id>: <text>" (the flow
  pseudo-rule FLOW: "Path removed from the published process flow", and its id is not listed);
- require: every other eligible route fails with "Business rule <id> sends this return to <path name>";
- prefer: the route becomes the preference (the ranking puts it first).
If no route is left eligible, the rules are waived: every route is restored as it was (Review Focus 1).
"""

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from di.services.engine.routes import POLICY, Route, fail
from di.services.modeler.compile import FLOW, CompiledRule
from di.services.modeler.scope import in_scope
from di.services.modeler.templates import Template

FLOW_REMOVED = "Path removed from the published process flow"
KEPT = ("excluded", "failGate", "failReason", "gates")


def _on(route: Route, path: str) -> bool:
    """Whether the route is the rule's path: its id, or its channel's base id (`retail:<lot>` is on `retail`, P9-9.10)."""
    return route["id"] == path or route["id"].split(":", 1)[0] == path


@dataclass
class RuleOutcome:
    ids: list[str]
    preferred: str | None
    waived: bool


def apply_rules(case: Mapping[str, Any], routes: list[Route], rules: Sequence[CompiledRule], t: Template) -> RuleOutcome:
    """Apply `rules` to `routes` in place."""
    eligible_before = any(not r["excluded"] for r in routes)
    keep = [{k: copy.deepcopy(r[k]) for k in KEPT} for r in routes]
    ids: list[str] = []
    preferred: str | None = None
    for rule in rules:
        if not in_scope(case, rule.scope, t.dims):
            continue
        hits = [r for r in routes if _on(r, rule.path) and not r["excluded"]]  # a case may offer a path twice
        if not hits:
            continue
        if rule.action == "exclude":
            for hit in hits:
                fail(hit, POLICY, FLOW_REMOVED if rule.id == FLOW else f"Excluded by business rule {rule.id}: {rule.text}")
            if rule.id != FLOW:
                ids.append(rule.id)
        elif rule.action == "require":
            p = t.path(rule.path)
            name = (p.name if p else rule.path).lower()
            for r in routes:
                if not _on(r, rule.path) and not r["excluded"]:
                    fail(r, POLICY, f"Business rule {rule.id} sends this return to {name}")
            ids.append(rule.id)
        elif rule.action == "prefer":
            preferred = max(hits, key=lambda h: h["net"])["id"]  # the best of the lots when the path has several
            ids.append(rule.id)
    if not any(not r["excluded"] for r in routes):
        for r, k in zip(routes, keep, strict=True):
            r.update(k)
        return RuleOutcome([], None, eligible_before)
    return RuleOutcome(ids, preferred, False)
