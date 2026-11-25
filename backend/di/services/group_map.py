"""The directory group to role map as rows people read: the Access screen's list and "which group gave this account".

Owns: reading table `idp_group_map` as display rows (with who changed and who approved each), and finding the group an
account's role and scope came from. Never does: change a row (`di.services.actions.group_map` does, with maker-checker),
decide what a group gives at sign-in (`policy.group_role`, from the rows in force that `auth.load_context` reads).
Implements P9-8.10 (story X-10).
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy

ROWS = text(
    "SELECT id, group_id, role, org_unit_id, site, warehouse, valid_from, valid_to, status, created_by, approved_by, "
    "created_at, approved_at FROM idp_group_map ORDER BY group_id, id"
)


def rows(session: Session) -> list[dict]:
    """Every mapping row, drafts and retired ones too, grouped by directory group, oldest first."""
    return [
        {
            "id": r.id, "group_id": r.group_id, "role": r.role, "org_unit_id": r.org_unit_id, "site": r.site,
            "warehouse": r.warehouse, "valid_from": r.valid_from.isoformat() if r.valid_from else None,
            "valid_to": r.valid_to.isoformat() if r.valid_to else None, "status": r.status, "created_by": r.created_by,
            "approved_by": r.approved_by, "created_at": r.created_at.isoformat(),
            "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        }
        for r in session.execute(ROWS)
    ]  # fmt: skip


def group_of(account: policy.Account, ctx: policy.Context) -> str | None:
    """The directory group this account's role and scope match in the rules in force (the demo's own group first)."""
    own = policy.IDP_GROUPS.get(account.id)
    if own is not None:
        return own
    wanted = (account.role, account.tenant, account.site, account.warehouse)
    for group, rule in (ctx.group_map or {}).items():
        if (rule.role, rule.org_unit_id, rule.site, rule.warehouse) == wanted:
            return group
    return None
