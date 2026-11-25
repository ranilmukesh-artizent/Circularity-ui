"""MCP tools generated from the action catalogue (plan 9, P9-2.13; G §2.8, §2.9).

    tools_for(agent) -> [types.Tool]     one tool per `agent_allowed` action in the agent's registry tools, plus `tools_find`
    action_of(name) -> ActionDef | None  the action behind a generated tool name (None: not a generated tool)
    may_call(agent_tools, action)        the agent's tool list names it (`tools.find` is always allowed)
    as_tool(action) -> dict              the action shaped as a row of `di.mcp.tools.TOOLS`, so the call checks
                                         (scope, input schema, tenant boundary) read it like a hand-written tool
    run(action, call) -> dict            the action through `pipeline.invoke` as the account, `preparer` = the agent

Annotations (MCP tool annotations; the spec says clients treat them as hints from a server they do not trust, so the
pipeline stays the control): `read_only_hint` = risk "read"; `destructive_hint` = the catalogue's `destructive` (a
delete, discard or revert, or an action held for a person); `idempotent_hint` = a read, or an action with its own
idempotency key. `meta.requiresHumanApproval` = the call would hold for this agent (autonomy "propose" or risk
"commit" for a write, or a destructive one).

Owns: which catalogue actions become tools and how a call to one runs. Implements the generated half of I-8/G §2.8.
Never does: make a tool of an action an agent may not run (`catalog.agent_allowed`: every FORBIDDEN_ACTIONS write,
delete or approve, system action, secret read) whatever the agent's tool list says; skip the pipeline (permission,
tenant boundary, agent gate, hold policy all run inside `invoke`); change the 12 hand-written tools.
"""

from typing import Any

import mcp_types as types

from di.mcp.tools import Refused, ToolCall
from di.services.actions.pipeline import invoke
from di.services.actions.registry import ACTIONS, ActionDef
from di.services.agents import catalog
from di.services.agents.forbidden import forbidden
from di.services.agents.registry import Agent

FIND = "tools.find"  # the one read every agent has: the catalogue search (P9-2.12)


def unsafe() -> list[str]:
    """Registered actions that would become a tool though an agent may never run them (empty by construction)."""
    return sorted(a.id for a in ACTIONS.values() if catalog.agent_allowed(a) and forbidden(a.id) and a.risk != "read")


def actions_of(agent: Agent) -> list[ActionDef]:
    """The agent's tools that are catalogue actions an agent may call, in its order, then `tools.find`."""
    ids = [i for i in dict.fromkeys(agent.tools) if i in ACTIONS and i != FIND]
    found = [ACTIONS[i] for i in ids if catalog.agent_allowed(ACTIONS[i])]
    return found + ([ACTIONS[FIND]] if FIND in ACTIONS else [])


def action_of(name: str) -> ActionDef | None:
    """The action a generated tool name stands for, if an agent may call it at all."""
    for a in ACTIONS.values():
        if catalog.tool_name(a.id) == name and catalog.agent_allowed(a):
            if a.id in unsafe():  # pragma: no cover - the invariant of `unsafe`
                raise RuntimeError(f"{a.id} would be a tool though no agent may run it")
            return a
    return None


def may_call(agent_tools: list[str], a: ActionDef) -> bool:
    return a.id == FIND or a.id in agent_tools


def _needs_person(a: ActionDef, agent: Agent) -> bool:
    if a.risk == "read":
        return False
    return bool(catalog.entry(a)["destructive"]) or a.risk == "commit" or agent.autonomy == "propose"


def _tool(a: ActionDef, agent: Agent) -> types.Tool:
    read = a.risk == "read"
    return types.Tool(
        name=catalog.tool_name(a.id),
        title=a.title,
        description=a.desc,
        input_schema=catalog.input_schema(a),
        annotations=types.ToolAnnotations(
            read_only_hint=read,
            destructive_hint=bool(catalog.entry(a)["destructive"]),
            idempotent_hint=read or a.idem is not None,
        ),
        meta={"action": a.id, "risk": a.risk, "requiresHumanApproval": _needs_person(a, agent), "generated": True},
    )


def tools_for(agent: Agent) -> list[types.Tool]:
    return [_tool(a, agent) for a in actions_of(agent)]


def as_tool(a: ActionDef) -> dict:
    """The action in the shape of a TOOLS row: `input` keeps t, req and ex of each field."""
    read = a.risk == "read"
    return {
        "id": catalog.tool_name(a.id), "desc": a.desc, "rw": "read" if read else "write", "step": [6],
        "approval": "none" if read else "human approval required", "input": a.input,
    }  # fmt: skip


def run(a: ActionDef, t: ToolCall) -> dict[str, Any]:
    """Run the action as the account, prepared by the agent. A refusal, or a hold for a person, is the tool's refusal."""
    r = invoke(a.id, t.args, t.ctx)
    if r["ok"]:
        out = r["output"]
        if isinstance(out, dict) and "held" in out:
            p = out["held"]
            t.step("Hold for human approval", False, f"Proposal {p} waits for a person")
            raise Refused(
                "held", f"Held for a person: proposal {p} waits until someone accepts it.",
                {"proposal": p, "reasons": out.get("reasons") or []},
            )  # fmt: skip
        return out if isinstance(out, dict) else {}
    e = r["error"]
    extra = {k: v for k, v in e.items() if k not in ("code", "message")}
    raise Refused(e["code"], e["message"], extra, step=f"{a.id}: {e['code']}")
