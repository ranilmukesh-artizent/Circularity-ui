"""The tool catalogue (plan 8, MVP-11.2): every action of the registry as a tool an agent could call.

    catalog() -> [{name, action, title, description, risk, input_schema, agent_allowed, agent_mode, implemented}]
        name           the action id as a tool name ("case.evidence" -> "case_evidence")
        input_schema   JSON Schema draft 2020-12 from ActionDef.input (t -> type, req -> required, ex -> examples,
                       min -> minLength)
        agent_mode     "no" for the actions no agent may run (di.services.agents.forbidden.FORBIDDEN_ACTIONS:
                       approving, overriding, declining, access, publishing, connection changes ...; the reads of
                       NO_AGENT_READS that handle a secret; system-only actions; actions with no handler yet),
                       "held" for a destructive or HELD_FOR_PERSON action (a person runs it), else "yes"
        destructive    a delete, discard or revert: the hold policy holds it at every autonomy level (P9-2.4, I-10)
        agent_allowed  agent_mode != "no"
        implemented    the action has a handler (an unbuilt one answers 501)

Generated from the registry each call, so an action declared in code shows up as soon as its module is imported.
GET /api/agents/tools (di.routes.agents) serves it, filtered to what the signed-in account may call.

Plan 9 P9-2.12: each property also carries `description` and `enum` from `di.services.agents.schema_notes.NOTES` (never
written into the golden catalogue), and `find_tools(query)` ranks the tools an agent may call against a few words, so a
model keeps a small toolset and searches for the rest (the `tools.find` read, di.services.actions.tools).
"""

import re
from collections.abc import Callable
from typing import Any, Literal

from di.services.actions.registry import ACTIONS, ActionDef
from di.services.agents.forbidden import NO_AGENT_READS, forbidden, held_for_person
from di.services.agents.schema_notes import NOTES

SCHEMA = "https://json-schema.org/draft/2020-12/schema"


def tool_name(action_id: str) -> str:
    return action_id.replace(".", "_")


def input_schema(a: ActionDef) -> dict[str, Any]:
    props: dict[str, dict[str, Any]] = {}
    notes = NOTES.get(a.id, {})
    for k, v in a.input.items():
        p: dict[str, Any] = {"type": v["t"]} if v.get("t") else {}
        if note := notes.get(k):
            p["description"] = note["desc"]
            if note.get("enum"):
                p["enum"] = list(note["enum"])  # type: ignore[call-overload]
        if v.get("ex") is not None:
            p["examples"] = [v["ex"]]
        if v.get("min") is not None:
            p["minLength"] = v["min"]
        props[k] = p
    req = [k for k, v in a.input.items() if v.get("req")]
    return {"$schema": SCHEMA, "type": "object", "properties": props, "required": req}


def agent_mode(a: ActionDef) -> Literal["yes", "held", "no"]:
    """May an agent call it? A read under a forbidden prefix (access.lookup) is a yes; one that handles a secret is not."""
    if a.risk == "system" or a.handler is None or a.id in NO_AGENT_READS:
        return "no"
    if forbidden(a.id) and a.risk != "read":
        return "no"
    return "held" if a.destructive or held_for_person(a.id) else "yes"


def agent_allowed(a: ActionDef) -> bool:
    return agent_mode(a) != "no"


def entry(a: ActionDef) -> dict[str, Any]:
    return {
        "name": tool_name(a.id),
        "action": a.id,
        "title": a.title,
        "description": a.desc,
        "risk": a.risk,
        "input_schema": input_schema(a),
        "agent_allowed": agent_allowed(a),
        "agent_mode": agent_mode(a),
        "destructive": a.destructive or held_for_person(a.id),
        "implemented": a.handler is not None,
    }


def catalog() -> list[dict[str, Any]]:
    return [entry(a) for a in ACTIONS.values()]


_STOP = frozenset({"a", "an", "the", "of", "to", "for", "and", "or", "in", "on", "it", "is", "me", "my", "i"})
_TITLE_W, _DESC_W, _FIELD_W = 3, 2, 1


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", re.sub(r"([a-z])([A-Z])", lambda m: m[1] + " " + m[2], text).lower())
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in _STOP}


def _score(query: set[str], a: ActionDef) -> int:
    """Query tokens found in the id and title (3 each), the description (2) and the field descriptions (1)."""
    fields = " ".join(f"{k} {n['desc']}" for k, n in NOTES.get(a.id, {}).items())
    return sum(
        w * len(query & _tokens(text)) for w, text in ((_TITLE_W, f"{a.id} {a.title}"), (_DESC_W, a.desc), (_FIELD_W, fields))
    )


def find_tools(query: str, *, limit: int = 10, allowed: Callable[[ActionDef], bool]) -> list[dict[str, Any]]:
    """The best `limit` catalogue entries for `query`: token overlap, ties by action id. Only actions an agent may call
    (`agent_allowed`, so never a forbidden one) that `allowed` also passes; an entry with no overlap is not listed."""
    q = _tokens(query)
    scored = [(_score(q, a), a) for a in ACTIONS.values() if agent_allowed(a) and allowed(a)]
    best = sorted(((s, a) for s, a in scored if s > 0), key=lambda sa: (-sa[0], sa[1].id))
    return [entry(a) for _, a in best[: max(limit, 0)]]
