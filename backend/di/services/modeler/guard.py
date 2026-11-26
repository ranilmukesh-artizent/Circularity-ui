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


# The order the prototype's textGuard (line 2435) checks a template's text patterns in, where it is not the guardrails'
# own order (audit F10): the tool fleet checks GR-02 last. A text that matches two gets the prototype's guardrail id.
TEXT_ORDER: dict[str, tuple[str, ...]] = {"tool_fleet": ("GR-03", "GR-04", "GR-05", "GR-02")}


def text_breaks(t: Template, text: str) -> str | None:
    """The first guardrail whose `protects` pattern matches the text (lowercased), or None: a plain-language change
    that would alter a guardrail, which only its owner may change."""
    low = text.lower()
    rank = {g: i for i, g in enumerate(TEXT_ORDER.get(t.key, ()))}
    ordered = sorted(t.guardrails, key=lambda g: rank.get(g.id, -1))  # stable: unranked guardrails keep their order
    return next((g.id for g in ordered if any(_matches(p, low) for p in g.protects)), None)


# Words that weaken or remove what they name. With a guardrail named (its id, or the word "guardrail"), the sentence is
# about changing a guardrail, which only its owner may do (plan 10 T8): a pack whose guardrails carry no `protects`
# pattern (the industrial GR-I1..I4, at demo parity) still refuses it instead of reading it as an unclear rule.
_WEAKEN = re.compile(
    r"\b(skip\w*|bypass\w*|ignor\w*|remov\w*|delet\w*|disabl\w*|drop\w*|turn(?:ing)? off|switch(?:ing)? off|waiv\w*"
    r"|relax\w*|loosen\w*|lower\w*|overrid\w*|suspend\w*|exempt\w*|unlock\w*)\b"
)  # not "without": "never resell units without a guardrail check" tightens, it does not weaken
_GUARDRAIL_WORD = re.compile(r"\bguard ?rails?\b")
ANY_GUARDRAIL = "*"


def text_names_guardrail(t: Template, text: str) -> str | None:
    """The guardrail a weakening sentence names by id ("Skip GR-I2"), `ANY_GUARDRAIL` when it weakens "the guardrails"
    without naming one, or None (no weakening word, or no guardrail named). Checked after `text_breaks`."""
    low = text.lower()
    if not _WEAKEN.search(low):
        return None
    named = next((g.id for g in t.guardrails if re.search(r"(?<![\w-])" + re.escape(g.id.lower()) + r"(?![\w-])", low)), None)
    if named:
        return named
    return ANY_GUARDRAIL if _GUARDRAIL_WORD.search(low) else None
