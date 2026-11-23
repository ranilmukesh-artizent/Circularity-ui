"""What an agent may do in one pipeline call (plan 8, MVP-11.1): the pipeline's step 8 when `ctx.preparer` is set.

Admin's settings in Access (di.services.actions.access, workspace collection "access_settings"), checked in order:
    kill switch   "agents_off" ({agent: true}): a stopped agent does nothing, reads included (the demo's afAgentAllowed)
    autonomy      "autonomy" ({role: {type: level}}): the level of the actor's role for the action's type (the demo's
                  AF_AUTO_TYPES, afAutoLevel). Off refuses with the demo's text. Suggest allows no write unless a person
                  confirmed it. Prepare and Act let the agent prepare it as the person (a commit still needs `confirmed`:
                  the agent gate, step 6).
    run limits    "run_limits" ({actions, bulk}): a run may journal at most `actions` actions (counted by run_id), and
                  no list in a write's input may hold more than `bulk` items.
People's own calls never reach this module.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from di.core import golden, state

if TYPE_CHECKING:
    from di.services.actions.pipeline import CallContext
    from di.services.actions.registry import ActionDef

# Read from the golden files, not di.repositories.constants: the pipeline imports this module, and the repositories
# import the pipeline.
AGENTS_BY_ID: dict[str, dict] = {a["id"]: a for a in golden.load("tools")["agents"]}
AUTO_TYPES: list[dict] = golden.load("screens/access")["auto_types"]  # the demo's AF_AUTO_TYPES
LEVEL_RANK = {"off": 0, "suggest": 1, "prepare": 2, "act": 3}  # the demo's AF_LV_RANK
RUN_LIMITS = {"actions": 50, "bulk": 100}  # the demo's AF.cfg.max at the start (as the Access screen shows it)
TYPE_OF = {act: t for t in AUTO_TYPES for act in t["acts"]}  # the demo's afAutoType, by action id
Refusal = tuple[str, str]


def name_of(agent_id: str) -> str:
    a = AGENTS_BY_ID.get(agent_id)
    return a["name"] if a else agent_id


def _settings(ctx: "CallContext", item: str) -> Any:
    return state.get(ctx.session, "access_settings", item)


def auto_level(stored: dict, role: str, t: dict) -> str:
    """The demo's afAutoLevel: the role's level for an action type, its default when unset, never above its maximum."""
    v = (stored.get(role) or {}).get(t["k"]) or t["def"]
    return str(t["max"] if LEVEL_RANK[v] > LEVEL_RANK[t["max"]] else v)


def stopped(ctx: "CallContext", agent_id: str) -> bool:
    return bool((_settings(ctx, "agents_off") or {}).get(agent_id))


def _autonomy(a: "ActionDef", ctx: "CallContext", agent: str) -> Refusal | None:
    t = TYPE_OF.get(a.id)
    if t is None or not a.changes_state:
        return None
    level = auto_level(_settings(ctx, "autonomy") or {}, ctx.actor.role, t)
    if level == "off":
        return "out_of_scope", f"The agent may not {a.verb or a.title.lower()} for the {ctx.actor.role} role (autonomy: Off)."
    if LEVEL_RANK[level] < LEVEL_RANK["prepare"] and not ctx.confirmed:
        return "approval_required", f"{name_of(agent)} may only prepare this; a person must confirm it."
    return None


def _largest_list(i: dict[str, Any]) -> int:
    return max((len(v) for v in i.values() if isinstance(v, list)), default=0)


def _run_limits(a: "ActionDef", i: dict[str, Any], ctx: "CallContext") -> Refusal | None:
    if not a.changes_state:
        return None
    lim = {**RUN_LIMITS, **(_settings(ctx, "run_limits") or {})}
    if ctx.run_id:
        done = ctx.session.execute(
            text("SELECT count(*) FROM action_journal WHERE run_id = :r AND NOT undone"), {"r": ctx.run_id}
        ).scalar_one()
        if done >= lim["actions"]:
            return "conflict", f"Run limit reached: {lim['actions']} actions."
    if _largest_list(i) > lim["bulk"]:
        return "conflict", f"Bulk limit reached: {lim['bulk']} items."
    return None


def check(a: "ActionDef", i: dict[str, Any], ctx: "CallContext") -> Refusal | None:
    """The first refusal for an agent-prepared call, or None."""
    agent = ctx.preparer or ""
    if stopped(ctx, agent):
        return "out_of_scope", f"{name_of(agent)} is stopped by Admin, so it cannot prepare anything."
    return _autonomy(a, ctx, agent) or _run_limits(a, i, ctx)
