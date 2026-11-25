"""Language model actions (plan 9, P9-2.3; registry entry I-9): Admin reads the router's models and changes one.

    llm.models    read    {}                                      every model: provider, model id, roles, limits, use
                                                                  this minute and today, cooldown (never a key)
    llm.setModel  commit  {id, enabled?, priority?, roles?, rpm?, tpm?, rpd?}   switch a model on or off, order it, say
                                                                  which callers may use it, change its limits

Both need `manageAgents` (Admin) and are in `FORBIDDEN_ACTIONS` ("llm."): an agent never reads or changes which models
run, whatever its autonomy. `rpm`, `tpm` and `rpd` below 1 and unknown roles are `validation_error`, an unknown id
`not_found`. The Agents page's "Language models" panel calls them (frontend/src/pages/agents/LlmModelsPanel.tsx).
"""

from typing import Any

from sqlalchemy import text

from di.services.actions.decisions import rb_log
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, guard, implement
from di.services.llm.router import ROLES
from di.services.llm.view import models_view

_PERM = "manageAgents"
_OPT = {"req": False}
LIMITS = ("rpm", "tpm", "rpd")

ACTIONS.setdefault(
    "llm.models",
    ActionDef(
        id="llm.models", title="List language models", verb="read language models", risk="read", perm=_PERM, scope="none",
        desc="The language models Circularity may call, with their limits, use and cooldown. Changes nothing.", input={},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "llm.setModel",
    ActionDef(
        id="llm.setModel", title="Change a language model", verb="change language models", risk="commit", perm=_PERM,
        scope="none",
        desc="Switch a language model on or off, set its priority, the callers that may use it and its limits.",
        input={
            "id": {"req": True, "t": "string"}, "enabled": {**_OPT, "t": "boolean"}, "priority": {**_OPT, "t": "number"},
            "roles": {**_OPT, "t": "array"}, **{k: {**_OPT, "t": "number"} for k in LIMITS},
        },
    ),
)  # fmt: skip


@implement("llm.models")
def models(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:  # noqa: ARG001 - the handler signature
    return {"models": models_view(ctx.session)}


@guard("llm.setModel")
def set_model_guard(i: dict[str, Any], ctx: CallContext):
    if ctx.session.execute(text("SELECT 1 FROM llm_model WHERE id = :i"), {"i": i["id"]}).first() is None:
        return "not_found", f"No language model {i['id']}."
    for k in LIMITS:
        if i.get(k) is not None and int(i[k]) < 1:
            return "validation_error", f"{k} must be at least 1."
    roles = i.get("roles")
    if roles is not None and (not roles or [r for r in roles if r not in ROLES]):
        return "validation_error", f"Roles are one or more of {', '.join(ROLES)}."
    return None


@implement("llm.setModel")
def set_model(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    cols = {k: i[k] for k in ("enabled", "priority", "roles", *LIMITS) if i.get(k) is not None}
    for k, v in cols.items():  # one fixed column at a time
        ctx.session.execute(text(f"UPDATE llm_model SET {k} = :v WHERE id = :i"), {"v": v, "i": i["id"]})  # noqa: S608 - k is one of the column names above
    rb_log(ctx, "llm.model.updated", f"{i['id']} · {', '.join(cols) or 'no change'}", f"llm.setModel:{i['id']}")
    return next(m for m in models_view(ctx.session) if m["id"] == i["id"])
