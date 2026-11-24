"""An optional language-model reading of a plain-language rule (plan 8, MVP-5.3), for flow.propose.

The deterministic parser (di.services.modeler.parse) reads every sentence it can. When it finds no path, and
GROQ_API_KEY is set (and ASK_PROVIDER is groq), the model is asked once, in one short JSON request through the groq SDK
(as workflow_builder.model_slots does), to read the sentence into {path, action, scope}. Every value is checked
against the template's paths, actions and scope dimensions; anything else is dropped. Any failure gives {} and the
deterministic answer stands. The key goes to the SDK only; it is never logged or returned.
"""

import logging
from typing import Any

from di.services.modeler.templates import Template

log = logging.getLogger("di.modeler_read")
ACTIONS = ("exclude", "require", "prefer")


def _key() -> str:
    """The Groq key when the model may be used (a key, and ASK_PROVIDER groq), else ""."""
    from di.core.config import get_settings

    st = get_settings()
    key = st.groq_api_key.get_secret_value().strip()
    return key if key and (st.ask_provider or "groq").strip().lower() == "groq" else ""


def _ask(key: str, system: str, text: str) -> dict[str, Any]:  # noqa: ARG001 - complete_json reads the key itself
    """One JSON completion through the model chain (di.services.ask.complete); {} when every model fails."""
    from di.core.config import get_settings
    from di.services.ask import complete

    return complete.complete_json(system, text[:500], max_tokens=200, timeout=min(get_settings().ask_timeout_seconds, 10))


def _system(t: Template) -> str:
    paths = "; ".join(f"{p.id}={p.name}" for p in t.paths)
    dims = "; ".join(f"{d.key} ({d.kind}{': ' + ', '.join(d.values) if d.values else ''})" for d in t.dims)
    return (
        "You read one business rule for a returns desk into JSON. Reply with one JSON object only: "
        '{"path": one path id, "action": "exclude"|"require"|"prefer", "scope": {dimension: values}}. '
        "Leave out every key the rule does not state; never guess. "
        f"Paths: {paths}. Scope dimensions (set: a list of the values; min/max: a number): {dims}."
    )


def checked(raw: dict[str, Any], t: Template) -> dict[str, Any]:
    """Only the values the template allows."""
    out: dict[str, Any] = {}
    if raw.get("path") in t.path_ids():
        out["path"] = raw["path"]
    if raw.get("action") in ACTIONS:
        out["action"] = raw["action"]
    sc = raw.get("scope")
    scope: dict[str, Any] = sc if isinstance(sc, dict) else {}
    keep: dict[str, Any] = {}
    for d in t.dims:
        v = scope.get(d.key)
        if d.kind == "set" and isinstance(v, list) and v and all(x in d.values for x in v):
            keep[d.key] = list(v)
        elif d.kind != "set" and isinstance(v, int | float) and not isinstance(v, bool):
            keep[d.key] = v
    if keep:
        out["scope"] = keep
    return out


def model_rule(text: str, t: Template) -> dict[str, Any]:
    """The model's reading of `text`, checked against the template; {} without a key or on any failure."""
    key = _key()
    if not key:
        return {}
    try:
        return checked(_ask(key, _system(t), text), t)
    except Exception:  # noqa: BLE001 - the model is an optional helper; the parser's reading stands on its own
        log.info("flow.propose: the language model did not answer; using the parser's reading")
        return {}
