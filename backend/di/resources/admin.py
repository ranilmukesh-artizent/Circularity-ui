"""Accounts, identity mappings and the journal as resources (plan 3 task 3).

`accounts` (Admin: page access/accounts): who can sign in, as the Access screen shows them. Read only: an account comes
from the identity provider (the directory group map and SCIM provision and deactivate them, as the system), so change
who gets which role through `identity-mappings`.
`identity-mappings` (Admin: page access/identity): the directory users and the account each maps to. update =
`access.mapIdentity` (id = the account), delete = `access.removeUser`.
`journal` (page audit/log): the action journal, newest first, without the entries of cases the account may not see
(the same rule as `GET /api/journal`); each row's `id` is its `seq`. Read only: it is the record of every write.
"""

from typing import Any

from sqlalchemy import text

from di.resources import Resource, register
from di.resources.support import principal, require_page
from di.services import journal as journal_service
from di.services.actions.pipeline import CallContext
from di.services.actions.scope import case_scope
from di.services.screens import access as screen


# ---------------------------------------------------------------- accounts
def list_accounts(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:  # noqa: ARG001 - no filters
    require_page(ctx, "access", "accounts")
    return [{**row["account"], "tenants": row["tenants"], "lands_on": row["landsOn"]} for row in screen.accounts(principal(ctx))]


def get_account(ctx: CallContext, account_id: str) -> dict[str, Any] | None:
    return next((a for a in list_accounts(ctx, {}) if a["id"] == account_id), None)


register(
    Resource(
        name="accounts", list=list_accounts, get=get_account, create=None, update=None, delete=None,
        why_not={
            "create": "Accounts are provisioned from the identity provider (directory group map or SCIM), not created here.",
            "update": "A role comes from the identity provider's group map: change it on identity-mappings or the group map.",
            "delete": "A leaver is deactivated by the directory sync; their history stays.",
        },
    )
)  # fmt: skip


# ---------------------------------------------------------------- identity mappings
def list_identity(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:  # noqa: ARG001 - no filters
    require_page(ctx, "access", "identity")
    return screen.identity(ctx.session, principal(ctx))["users"]


def get_identity(ctx: CallContext, uid: str) -> dict[str, Any] | None:
    return next((u for u in list_identity(ctx, {}) if u["id"] == uid), None)


register(
    Resource(
        name="identity-mappings", list=list_identity, get=get_identity, create=None, update="access.mapIdentity",
        delete="access.removeUser", id_field="acct", id_keys={"access.removeUser": "id"}, fields=("field", "value"),
        why_not={"create": "A user joins through the directory (sign-in provisioning or SCIM), not by hand."},
    )
)  # fmt: skip


# ---------------------------------------------------------------- journal
JOURNAL_COLUMNS = "seq, action, input, actor, role, preparer, run_id, case_id, output_ref, undone, at"
MAX_ROWS = 500  # what `GET /api/journal` returns at most


def list_journal(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:
    require_page(ctx, "audit", "log")
    rows = journal_service.entries(principal(ctx), ctx.session, q.get("case_id"), MAX_ROWS)
    return [r | {"id": r["seq"]} for r in rows]


def get_journal(ctx: CallContext, seq: str) -> dict[str, Any] | None:
    require_page(ctx, "audit", "log")
    if not seq.isdigit():
        return None
    row = (
        ctx.session.execute(
            text(f"SELECT {JOURNAL_COLUMNS} FROM action_journal WHERE seq = :s"),  # noqa: S608 - fixed column list
            {"s": int(seq)},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    where = case_scope(row["case_id"]) if row["case_id"] else None
    p = principal(ctx)
    if where and not (p.tenant_ok(where[0]) and p.location_ok(where[1])):
        return None  # an entry of a case this account may not see is not there for it
    return dict(row) | {"id": row["seq"]}


register(
    Resource(
        name="journal", list=list_journal, get=get_journal, create=None, update=None, delete=None, filters=("case_id",),
        why_not={
            "create": "The journal is written by the action pipeline, one entry per write; it cannot be added to.",
            "update": "A journal entry is a record and is never edited (an undo is marked with POST /api/journal/undo).",
            "delete": "The journal is the audit trail and is never deleted.",
        },
    )
)  # fmt: skip
