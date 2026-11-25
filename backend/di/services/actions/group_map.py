"""Directory group mapping actions (P9-8.10, story X-10): a person saves a mapping, another person approves it.

Owns: access.saveGroupMap (act: a draft row) and access.approveGroupMap (commit: the draft takes effect, the group's
previous approved row retires). Never does: let an agent run either (the `access.` family is in FORBIDDEN_ACTIONS),
give Admin through a group, let the maker approve, or read the rows (`di.services.group_map`). The reading actions
access.roleMatrix and access.testUser stay in `di.services.actions.access`.
"""

from datetime import date
from typing import Any

from sqlalchemy import text

from di.core import policy
from di.repositories.common import can
from di.services.actions.decisions import rb_log
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, guard, implement

MAKER_CHECKER = "Maker-checker: you changed this mapping, so another person must approve it."
_OPT = {"req": False, "t": "string"}
ACTIONS.setdefault(
    "access.saveGroupMap",
    ActionDef(id="access.saveGroupMap", title="Save a group mapping", verb="save a group mapping", risk="act", perm=None,
              scope="none", input={"group_id": {"req": True, "t": "string"}, "role": {"req": True, "t": "string"},
                                   "org_unit_id": _OPT, "site": _OPT, "warehouse": _OPT, "valid_from": _OPT, "valid_to": _OPT},
              desc="Map a directory group to a role and a scope as a draft. It takes effect when another person approves it."),
)  # fmt: skip
ACTIONS.setdefault(
    "access.approveGroupMap",
    ActionDef(id="access.approveGroupMap", title="Approve a group mapping", verb="approve a group mapping", risk="commit",
              perm=None, scope="none", input={"id": {"req": True, "t": "number"}},
              desc="Put a drafted group mapping in force. The group's previous mapping retires. Not the person who saved it."),
)  # fmt: skip


def _date(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


@guard("access.saveGroupMap")
def save_guard(i: dict[str, Any], ctx: CallContext):
    if not can(ctx, "manageIdentity"):
        return "out_of_scope", f"The {ctx.actor.role} view cannot change group mappings."
    if i["role"] not in policy.idp_roles():
        return "validation_error", "A directory group never gives this role."
    unit = i.get("org_unit_id")
    if unit and unit not in policy.org_units(ctx.actor.ctx):
        return "tenant_boundary", f"{unit} is not an organisation in this workspace."
    try:
        start, end = _date(i.get("valid_from")), _date(i.get("valid_to"))
    except ValueError:
        return "validation_error", "Dates are written year-month-day."
    if start and end and end < start:
        return "validation_error", "The end date must be on or after the start date."
    return None


@implement("access.saveGroupMap")
def save_group_map(i: dict[str, Any], ctx: CallContext):
    row = ctx.session.execute(
        text(
            "INSERT INTO idp_group_map (group_id, role, org_unit_id, site, warehouse, valid_from, valid_to, status, created_by) "
            "VALUES (:g, :r, :o, :s, :w, :f, :t, 'draft', :by) RETURNING id"
        ),
        {"g": i["group_id"], "r": i["role"], "o": i.get("org_unit_id") or None, "s": i.get("site") or None,
         "w": i.get("warehouse") or None, "f": _date(i.get("valid_from")), "t": _date(i.get("valid_to")), "by": ctx.actor.id},
    ).one()  # fmt: skip
    rb_log(ctx, "identity.group_map.drafted", f"{i['group_id']} → {i['role']} drafted", f"idp-map:{row.id}")
    return {"id": row.id, "status": "draft"}


@guard("access.approveGroupMap")
def approve_guard(i: dict[str, Any], ctx: CallContext):
    if not can(ctx, "approve.tenantAccess"):
        return "out_of_scope", f"The {ctx.actor.role} view cannot approve group mappings."
    row = ctx.session.execute(text("SELECT status, created_by FROM idp_group_map WHERE id = :i"), {"i": int(i["id"])}).first()
    if row is None:
        return "not_found", "No such mapping."
    if row.status != "draft":
        return "conflict", "Only a draft mapping can be approved."
    if row.created_by == ctx.actor.id:
        return "conflict", MAKER_CHECKER
    return None


@implement("access.approveGroupMap")
def approve_group_map(i: dict[str, Any], ctx: CallContext):
    row_id = int(i["id"])
    group, role = ctx.session.execute(text("SELECT group_id, role FROM idp_group_map WHERE id = :i"), {"i": row_id}).one()
    ctx.session.execute(
        text("UPDATE idp_group_map SET status = 'retired' WHERE group_id = :g AND status = 'approved' AND id <> :i"),
        {"g": group, "i": row_id},
    )
    ctx.session.execute(
        text("UPDATE idp_group_map SET status = 'approved', approved_by = :by, approved_at = now() WHERE id = :i"),
        {"by": ctx.actor.id, "i": row_id},
    )
    rb_log(ctx, "identity.group_map.approved", f"{group} → {role} approved", f"idp-map:{row_id}")
    return {"id": row_id, "status": "approved"}
