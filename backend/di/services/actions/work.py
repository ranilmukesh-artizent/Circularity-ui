"""Work item actions (plan 9, P9-1.7; registry entry I-20): asking a question, resolving an item, handing it on. The logic
and the timers are di.services.cases.process.

    case.needInfo   act  {case_id, question, to_role}    case scope: opens a `needs_info` item for the role, due as the
                                                         pack's `runtime.sla_hours.needs_info` says; agents may ask
    work.resolve    act  {item_id, outcome, note?}       the owner role or account, or Admin, closes the item; an
                                                         answer to a question becomes a note on the case
    work.assign     act  {item_id, account}              the owner or Admin hands the item to one account

`work.resolve` and `work.assign` are in `FORBIDDEN_ACTIONS` (di.services.agents.forbidden): only a person resolves or
hands on a piece of work, however the call arrives. A tenant-scoped person reaches only the items of their units. These
actions never approve, decline or override a decision.
"""

from typing import Any

from sqlalchemy import text

from di.core import policy
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.cases import process, store
from di.services.device import lock, verify

_STR = {"req": True, "t": "string"}
ACTIONS.setdefault(
    "case.needInfo",
    ActionDef(
        id="case.needInfo", title="Ask for information", verb="ask for information",
        desc="Ask a role a question about a case. It appears in that role's My work, due as the pack's SLA says.",
        risk="act", perm=None, scope="case",
        input={
            "case_id": _STR,
            "question": {"req": True, "t": "string", "min": 5, "minText": "Write the question."},
            "to_role": _STR,
        },
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "work.resolve",
    ActionDef(
        id="work.resolve", title="Resolve a work item", verb="resolve work items",
        desc="Close an exception, question or step with an outcome. An answer to a question is added to the case as a note.",
        risk="act", perm=None, scope="none",
        input={"item_id": {"req": True, "t": "number"}, "outcome": _STR, "note": {"t": "string"}},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "work.assign",
    ActionDef(
        id="work.assign", title="Assign a work item", verb="assign work items",
        desc="Hand a work item to one account.", risk="act", perm=None, scope="none",
        input={"item_id": {"req": True, "t": "number"}, "account": _STR},
    ),
)  # fmt: skip


# ---------------------------------------------------------------- helpers
def _row(ctx: CallContext, item_id: Any, for_update: bool = False) -> dict[str, Any] | None:
    r = ctx.session.execute(
        text("SELECT * FROM work_item WHERE id = :i" + (" FOR UPDATE" if for_update else "")),  # noqa: S608 - only the fixed FOR UPDATE suffix is appended; values are bound
        {"i": int(item_id)},
    ).mappings().first()  # fmt: skip
    return dict(r) if r else None


def _refusal(row: dict[str, Any] | None, ctx: CallContext) -> tuple[str, str] | None:
    """Why this person may not act on the item: it is not there or not open, they are not its owner, or it belongs to a
    tenant they cannot see."""
    if row is None:
        return "not_found", "No such work item."
    if row["status"] != "open":
        return "conflict", "That item is already closed."
    a = ctx.actor.account
    if a is None:
        return "out_of_scope", "Sign in first."
    scoped = policy.policy(a).get("tenantScoped")
    if scoped and row["org_unit_id"] and not policy.tenant_ok(a, row["org_unit_id"], ctx.actor.ctx):
        return "tenant_boundary", f"{row['org_unit_id']} is a tenant you cannot see. Request tenant access first."
    if a.role == "Admin" or a.role == row["owner_role"] or a.id == row["owner_account"]:
        return None
    return "out_of_scope", f"This item is for {row['owner_role']}."


# ---------------------------------------------------------------- case.needInfo
@guard("case.needInfo")
def need_info_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:  # noqa: ARG001 - the Guard signature
    if i["to_role"] not in policy.roles():
        return "validation_error", f"No role {i['to_role']}."
    return None


@implement("case.needInfo")
def need_info(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    c = store.get(ctx.session, i["case_id"])
    if c is None:
        raise ActionError("not_found", f"No live case {i['case_id']}.")
    item = process.open_item(
        ctx.session, kind="needs_info", case_id=c["id"], org_unit_id=c["owner"], type="needs_info",
        title=f"Question on {c['id']} for {i['to_role']}", cause=i["question"].strip(), action="Answer the question",
        owner_role=i["to_role"], due_hours=process.sla_hours(ctx.session, c["id"], "needs_info"), by=ctx.actor.id,
    )  # fmt: skip
    return {"id": item, "case_id": c["id"], "log": f"Asked {i['to_role']}: {i['question'].strip()}"}


# ---------------------------------------------------------------- work.resolve
def _answer_device_item(ctx: CallContext, row: dict[str, Any], outcome: str) -> None:
    """Value the case again after a person's answer on a device exception (the case moves on from `none` with a stage log row
    by the person when it has a recommendation). A quote mismatch keeps the answer on the case: a re-quote accepted lets the
    channels go, the trade-in returned keeps them held (P9-6.5). A registry hit needs no mark: the gate reads the registry,
    and `work.resolve` was refused unless a newer clear check was on file (P9-6.6)."""
    from di.services.cases import intake, lifecycle  # intake imports the actions layer

    c = store.get(ctx.session, row["case_id"], for_update=True)
    if c is None:
        return
    held = c["stage"] == "none"
    if row["type"] == verify.QUOTE_MISMATCH:
        verify.resolved(c, outcome, ctx.actor.id, ctx.now.isoformat())
    intake.revalue(ctx.session, c)
    if held and c.get("recommendation"):
        what = "Quote mismatch resolved" if row["type"] == verify.QUOTE_MISMATCH else "Registry hit released"
        lifecycle.move(ctx.session, c, "awaiting_approval", f"{what}: {outcome}", ctx.actor.id)
    else:
        store.save(ctx.session, c)


@guard("work.resolve")
def resolve_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = _row(ctx, i["item_id"])
    if bad := _refusal(row, ctx):
        return bad
    if row is not None and row["type"] == lock.BLACKLIST_HIT and row["case_id"]:  # a release needs a newer registry check
        c = store.get(ctx.session, row["case_id"])
        if c is not None and (why := lock.resolve_refusal(ctx.session, c, process.pack_of(ctx.session, row["case_id"]))):
            return "conflict", why
    return None


@implement("work.resolve")
def resolve(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(ctx, i["item_id"], for_update=True)
    if row is None:
        raise ActionError("not_found", "No such work item.")
    process.close_item(ctx.session, row["id"], i["outcome"], ctx.actor.id)
    note = (i.get("note") or "").strip()
    if row["kind"] == "needs_info" and row["case_id"]:
        c = store.get(ctx.session, row["case_id"], for_update=True)
        if c is not None:
            c.setdefault("caseNotes", []).append(
                {"at": ctx.now.isoformat(), "by": ctx.actor.id, "text": f"Answer to '{row['cause']}': {note or i['outcome']}"}
            )
            store.save(ctx.session, c)
    if row["type"] in (verify.QUOTE_MISMATCH, lock.BLACKLIST_HIT) and row["case_id"]:  # a device exception (P9-6.5, P9-6.6)
        _answer_device_item(ctx, row, i["outcome"])
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "outcome": i["outcome"],
        "log": f"Resolved: {row['title']} ({i['outcome']})",
    }


# ---------------------------------------------------------------- work.assign
@guard("work.assign")
def assign_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _refusal(_row(ctx, i["item_id"]), ctx):
        return bad
    if policy.account(i["account"], ctx.actor.ctx) is None:
        return "not_found", f"No account {i['account']}."
    return None


@implement("work.assign")
def assign(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    ctx.session.execute(
        text("UPDATE work_item SET owner_account = :a WHERE id = :i AND status = 'open'"),
        {"a": i["account"], "i": int(i["item_id"])},
    )
    return {"id": int(i["item_id"]), "account": i["account"], "log": f"Assigned work item {int(i['item_id'])} to {i['account']}"}
