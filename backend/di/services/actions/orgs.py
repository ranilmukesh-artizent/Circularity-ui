"""Org unit actions (plan 8, MVP-1.3): create, rename and move a unit of the organisation tree, and read the tree.

The demo has no org tree, so these are declared here, beside the catalog's actions (as di.services.actions.fabric_sources
declares the source lifecycle). The writes need `manageOrgs` (Admin, di.core.policy.EXTRA_PERMS), are commits and are
journaled by the pipeline. Agents never run them (di.mcp.policy.FORBIDDEN_ACTIONS: they change access).

    org.create  commit  {id, parent_id, kind, name}  a new unit under an existing one
    org.update  commit  {id, name}                   rename a unit
    org.move    commit  {id, parent_id}              a unit (and its subtree) under another parent; never the root,
                                                     never under itself or its own children
    org.tree    read    {}                           {units: [{id, parent_id, kind, name, children: [...]}]}

A grant on a unit covers its subtree (di.core.policy.tenant_ok), so moving a company moves who sees its cases.
"""

import re
from typing import Any

from sqlalchemy import text

from di.core import orgs
from di.repositories import orgs as repo
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, guard, implement

ID_RE = re.compile(r"^[A-Za-z0-9 ._-]{2,64}$")
KINDS = ("group", "segment", "company", "site", "customer")
_PERM = "manageOrgs"


def _declare(action_id: str, title: str, verb: str, desc: str, risk: Any, inp: dict[str, dict[str, Any]], perm: Any) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=perm, scope="none", input=inp, verb=verb),
    )


_STR = {"req": True, "t": "string"}
_declare(
    "org.create", "Create an org unit", "create org units",
    "Add a group, segment, company, site or customer under an existing org unit.", "commit",
    {"id": _STR, "parent_id": _STR, "kind": _STR, "name": _STR}, _PERM,
)  # fmt: skip
_declare("org.update", "Rename an org unit", "rename org units", "Change an org unit's name.", "commit",
         {"id": _STR, "name": _STR}, _PERM)  # fmt: skip
_declare(
    "org.move", "Move an org unit", "move org units",
    "Move an org unit, with everything below it, under another parent. Grants on the new parent then cover it.",
    "commit", {"id": _STR, "parent_id": _STR}, _PERM,
)  # fmt: skip
_declare("org.tree", "Read the org tree", "read the org tree", "The org units as a tree. Changes nothing.", "read", {}, None)


def _exists(ctx: CallContext, uid: str) -> bool:
    return ctx.session.execute(text("SELECT 1 FROM org_unit WHERE id = :i"), {"i": uid}).first() is not None


def _name_problem(name: str) -> tuple[str, str] | None:
    return ("validation_error", "Give the org unit a name.") if not name.strip() else None


# ---------------------------------------------------------------- create
@guard("org.create")
def create_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if not ID_RE.match(i["id"]):
        return "validation_error", "An org unit id has 2 to 64 letters, digits, spaces, dots, dashes or underscores."
    if i["kind"] not in KINDS:
        return "validation_error", f"The kind is one of {', '.join(KINDS)}."
    if bad := _name_problem(i["name"]):
        return bad
    if _exists(ctx, i["id"]):
        return "conflict", f"Org unit {i['id']} already exists."
    if not _exists(ctx, i["parent_id"]):
        return "not_found", f"No org unit {i['parent_id']}."
    return None


@implement("org.create")
def create(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    ctx.session.execute(
        text("INSERT INTO org_unit (id, parent_id, kind, name) VALUES (:i, :p, :k, :n)"),
        {"i": i["id"], "p": i["parent_id"], "k": i["kind"], "n": i["name"].strip()},
    )
    return {"id": i["id"]}


# ---------------------------------------------------------------- rename
@guard("org.update")
def update_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if not _exists(ctx, i["id"]):
        return "not_found", f"No org unit {i['id']}."
    return _name_problem(i["name"])


@implement("org.update")
def update(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    ctx.session.execute(text("UPDATE org_unit SET name = :n WHERE id = :i"), {"i": i["id"], "n": i["name"].strip()})
    return {"id": i["id"]}


# ---------------------------------------------------------------- move
@guard("org.move")
def move_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    units = repo.units(ctx.session)
    if i["id"] not in units:
        return "not_found", f"No org unit {i['id']}."
    if i["parent_id"] not in units:
        return "not_found", f"No org unit {i['parent_id']}."
    if i["id"] == orgs.ROOT:
        return "conflict", "The workspace root cannot move."
    if i["parent_id"] in orgs.subtree(units, i["id"]):
        return "conflict", "An org unit cannot move under itself or its own children."
    return None


@implement("org.move")
def move(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    ctx.session.execute(text("UPDATE org_unit SET parent_id = :p WHERE id = :i"), {"i": i["id"], "p": i["parent_id"]})
    return {"id": i["id"]}


# ---------------------------------------------------------------- the tree
@implement("org.tree")
def tree(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:  # noqa: ARG001 - handlers take (input, ctx)
    return {"units": repo.tree(ctx.session)}
