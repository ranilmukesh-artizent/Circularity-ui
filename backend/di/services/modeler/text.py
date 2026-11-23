"""A business rule in words (the prototype's `ruleTextE` and `ruleTextD`, generalised over a template's wording):
"<scope phrases or 'every return'>: never|only|prefer <path name>"."""

from collections.abc import Mapping
from typing import Any

from di.services.modeler.templates import Template

VERB = {"exclude": "never ", "require": "only "}


def js_str(v: Any) -> str:
    """A scope value as JavaScript's String() writes it (40.0 -> "40")."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def rule_text(t: Template, rule_like: Mapping[str, Any]) -> str:
    s = rule_like.get("scope") or {}
    parts: list[str] = []
    for ph in t.wording.phrases:
        v = s.get(ph.key)
        if isinstance(v, list | tuple):
            if v:
                parts.append(ph.fmt.format(ph.joiner.join(ph.words.get(x, js_str(x)) for x in v)))
        elif v is not None and v != "":
            parts.append(ph.fmt.format(js_str(v)))
    path = t.wording.path_names.get(rule_like.get("path") or "", "?")
    return (", ".join(parts) or t.wording.every) + ": " + VERB.get(rule_like.get("action") or "", "prefer ") + path
