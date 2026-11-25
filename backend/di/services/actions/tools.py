"""The tool search read (plan 9, P9-2.12): `find, don't list`.

    tools.find  read  {query, limit?}   the best tools for a few words: {tools: [catalogue entry]}, at most `limit`
                                        (1-50, ten by default)

Owns: the declaration and handler of `tools.find`. The ranking is `di.services.agents.catalog.find_tools`.
Never does: offer an action no agent may run (`FORBIDDEN_ACTIONS`, system actions: they are never listed, so a forbidden
action is never shown as callable), or an action the caller's own account may not call (`policy.can`). It changes
nothing and needs no permission; an agent may call it (a read).
"""

from typing import Any

from di.core import policy
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, guard, implement
from di.services.agents.catalog import find_tools

DEFAULT_LIMIT, MAX_LIMIT = 10, 50

ACTIONS.setdefault(
    "tools.find",
    ActionDef(
        id="tools.find", title="Find tools", verb="search the tool catalogue", risk="read", perm=None, scope="none",
        desc="Find the tools that fit a few words, among those you may call. Changes nothing.",
        input={"query": {"req": True, "t": "string", "ex": "request missing evidence"}, "limit": {"req": False, "t": "number"}},
    ),
)  # fmt: skip


@guard("tools.find")
def find_guard(i: dict[str, Any], _ctx: CallContext) -> tuple[str, str] | None:
    limit = i.get("limit")
    if limit is not None and not (isinstance(limit, int) and 1 <= limit <= MAX_LIMIT):
        return "validation_error", f"The limit is a whole number from 1 to {MAX_LIMIT}."
    return None


@implement("tools.find")
def find(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    actor = ctx.actor

    def mine(a: ActionDef) -> bool:
        return actor.account is None or a.permission is None or policy.can(actor.account, a.permission, actor.ctx)

    return {"tools": find_tools(str(i["query"]), limit=i.get("limit") or DEFAULT_LIMIT, allowed=mine)}
