"""Organisation units (plan 8, MVP-1.2): the tree a tenant check reads.

A unit is a group, segment, company, site or customer (table `org_unit`, migration 0019). The seeded tree is the
root `workspace` with the demo's three tenants under it, and the tenant strings are the unit ids, so `case_record.owner`
and `tenant_grant.tenant` hold unit ids. A grant on a unit covers its whole subtree.

Pure: the policy gets the units through `policy.Context.org_units` (di.core.auth.load_context reads the table).
"""

from dataclasses import dataclass

ROOT = "workspace"
TENANT_KINDS = ("customer", "company")  # the units a case can belong to (policy.tenants)


@dataclass(frozen=True)
class OrgUnit:
    id: str
    parent_id: str | None
    kind: str
    name: str


# The seeded tree (migration 0019), in the seeded order: used when no context carries the table's rows.
SEEDED: dict[str, OrgUnit] = {
    ROOT: OrgUnit(ROOT, None, "group", "Workspace"),
    **{t: OrgUnit(t, ROOT, "customer", t) for t in ("Customer A", "Customer B", "Customer C")},
}


def subtree(units: dict[str, OrgUnit], root: str) -> set[str]:
    """`root` and every unit below it (empty if `root` is not a unit)."""
    if root not in units:
        return set()
    kids: dict[str, list[str]] = {}
    for u in units.values():
        if u.parent_id is not None:
            kids.setdefault(u.parent_id, []).append(u.id)
    seen, todo = {root}, [root]
    while todo:
        for kid in kids.get(todo.pop(), []):
            if kid not in seen:
                seen.add(kid)
                todo.append(kid)
    return seen


def ancestors(units: dict[str, OrgUnit], uid: str) -> list[str]:
    """`uid` and its parents up to the root, nearest first (empty if `uid` is not a unit)."""
    out: list[str] = []
    cur: str | None = uid
    while cur is not None and cur in units and cur not in out:
        out.append(cur)
        cur = units[cur].parent_id
    return out
