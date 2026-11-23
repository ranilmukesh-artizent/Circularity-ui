"""Guardrail checks on a rule (the prototype's ruleGuardE / ruleGuardD, as each guardrail's `forbids`)."""

from collections.abc import Mapping
from typing import Any

from di.services.modeler.templates import Forbid, Template


def _forbidden(f: Forbid, rule_like: Mapping[str, Any]) -> bool:
    scope = rule_like.get("scope") or {}
    return (
        rule_like.get("path") == f.path
        and rule_like.get("action") in f.actions
        and all(set(scope.get(k) or ()) & set(vals) for k, vals in f.scope_any.items())
    )


def rule_breaks(t: Template, rule_like: Mapping[str, Any]) -> str | None:
    """The first guardrail id whose `forbids` match the rule, or None."""
    return next((g.id for g in t.guardrails if any(_forbidden(f, rule_like) for f in g.forbids)), None)
