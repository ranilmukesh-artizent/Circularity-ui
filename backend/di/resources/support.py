"""Helpers the resource groups share (plan 3 task 3): the same server-side checks the screens and read actions use.

Owns: `principal(ctx)` (the signed-in account as the screens' `Principal`), `read(ctx, action, input)` (a read action
through the pipeline, so its permission, tenant boundary and warehouse lock apply; a refusal becomes an `ApiError` with
the pipeline's status), `require_page` (403 for a role that does not see a page), the query-string coercions and
`visible_case_ids`.

Never does: write. Reads only; every write is the router's call of an action through `pipeline.invoke` (AGENTS.md rule 8).
"""

from typing import Any

from di.core import policy
from di.core.auth import Principal
from di.core.errors import ApiError
from di.repositories.context import visible_cases
from di.services.actions.pipeline import ERROR_STATUS, CallContext, invoke

BIG = 100_000  # a page size no read action refuses: the router pages the rows itself


def principal(ctx: CallContext) -> Principal:
    """The caller as a `Principal` (invoke() refuses a caller who is not signed in, so there is an account)."""
    return Principal(account=ctx.actor.person, ctx=ctx.actor.ctx)


def refuse(code: str, message: str) -> ApiError:
    return ApiError(code, message, ERROR_STATUS.get(code, 400))


def read(ctx: CallContext, action: str, body: dict[str, Any], missing_ok: bool = False) -> Any:
    """Run a read action as the caller and return its output. A refusal raises; `missing_ok` turns not_found into None."""
    result = invoke(action, body, ctx)
    if result["ok"]:
        return result["output"]
    err = result["error"]
    if missing_ok and err["code"] == "not_found":
        return None
    raise refuse(err["code"], err["message"])


def require_page(ctx: CallContext, page: str, *sections: str) -> None:
    """403 unless the account sees the page (any of the sections given, or the page itself)."""
    a = ctx.actor.account
    if not any(policy.can_page(a, page, s) for s in (sections or (None,))):
        raise ApiError("out_of_scope", f"Not available for the {a.role if a else 'signed-out'} view.", 403)


def is_admin(ctx: CallContext) -> bool:
    return bool(policy.policy(ctx.actor.person).get("all"))


def visible_case_ids(ctx: CallContext) -> set[str]:
    return {c["id"] for c in visible_cases(ctx)}


def as_bool(v: str | None) -> bool | None:
    return None if v is None or v == "" else v.lower() in ("1", "true", "yes")


def as_int(v: str | None, name: str) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except ValueError:
        raise ApiError("validation_error", f"{name} must be a whole number.", 422) from None
