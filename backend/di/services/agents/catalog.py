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
"""

from typing import Any, Literal

from di.services.actions.registry import ACTIONS, ActionDef
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, NO_AGENT_READS, held_for_person

SCHEMA = "https://json-schema.org/draft/2020-12/schema"


def tool_name(action_id: str) -> str:
    return action_id.replace(".", "_")


def input_schema(a: ActionDef) -> dict[str, Any]:
    props: dict[str, dict[str, Any]] = {}
    for k, v in a.input.items():
        p: dict[str, Any] = {"type": v["t"]} if v.get("t") else {}
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
    if a.id.startswith(FORBIDDEN_ACTIONS) and a.risk != "read":
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
