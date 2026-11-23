"""Guardrail checks on a rule (the prototype's ruleGuardE / ruleGuardD, as each guardrail's `forbids`) and on a
plain-language text (its textGuard, as each guardrail's `protects`)."""

import re
from collections.abc import Mapping
from typing import Any

from di.services.modeler.templates import Forbid, Template, TextPattern


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


def _matches(p: TextPattern, low: str) -> bool:
    return all(re.search(rx, low) for rx in p.all_of)


def text_breaks(t: Template, text: str) -> str | None:
    """The first guardrail whose `protects` pattern matches the text (lowercased), or None: a plain-language change
    that would alter a guardrail, which only its owner may change."""
    low = text.lower()
    return next((g.id for g in t.guardrails if any(_matches(p, low) for p in g.protects)), None)
