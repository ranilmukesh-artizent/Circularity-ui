"""The access policy (docs/backend-steps.md, B7): who may see and do what. A port of the demo's RBAC block
(index.html, /*RBAC-START*/ … /*RBAC-END*/), so the server refuses exactly what the screens hide.

The policy itself (roles, their pages and permissions, the demo accounts, sign-in IDs) is configuration, read from
the B1 golden file `policy.json`. What changes at run time lives in the database and reaches the rules through
`Context` (loaded per request by di.core.auth.load_context):
- the Approver's delegations (decisions, MCP proposals, tenant access) and a Planner's live tenant grants (their
  tables; a grant may end or be revoked, migration 0027);
- the accounts as the identity mapping has them now (state collection "accounts"; access.mapIdentity changes an
  account's role, tenant, site, warehouse and label, and every rule then sees the changed account);
- the approval settings, the demo's AF.cfg.limits and AF.cfg.self (state collection "access_settings", item
  "approval").
The directory the identity provider syncs (the demo's S.idp: users, groups, role source, out-of-office delegations)
is state too ("idp_users", and "access_settings" item "idp"); only the access actions read it.
"""

import math
import re
from dataclasses import dataclass, field
from functools import cache

from di.core import golden, orgs, state
from di.core.dates import AS_OF, add_days, iso

# Features the demo keeps hidden (index.html FEAT: pools:false): these sections are never visible.
HIDDEN_SECTIONS = {("product", "pools"), ("analytics", "pool")}
DELEGATION_SCOPES = ("decisions", "mcp", "tenantAccess")
# AF.cfg.limits at the start, in dollars per role; None is the demo's Infinity (no limit). A role not listed falls
# back to afLimitFor's default: unlimited for Approver and Admin, $0 for everyone else.
STARTING_LIMITS: dict[str, float | None] = {"Approver": None, "Admin": None, "Planner": 0}
# Plan 8 (MVP-1.2): permissions, pages and sections beyond the demo's, declared here beside the golden ones (role ->
# allowed). They are not delegations: an Approver's approve.flows does not depend on the delegation switches.
EXTRA_PERMS: dict[str, tuple[str, ...]] = {
    "manageOrgs": ("Admin",),
    "manageFlows": ("Admin", "Planner"),
    "approve.flows": ("Admin", "Approver"),
    "manageAgents": ("Admin",),
    "openCases": ("Admin", "Developer", "Planner"),
    "managePacks": ("Admin", "Planner"),  # plan 9 P9-1.6: import and submit a pack version
    "approve.packs": ("Admin", "Approver"),  # plan 9 P9-1.6: approve or return a pack version
}
EXTRA_PAGES: dict[str, tuple[str, ...]] = {
    "modeler": ("Admin", "Planner", "Approver", "Executive"),
    "agents": ("Admin", "Developer"),
    "mywork": ("Admin", "Developer", "Planner", "Approver", "Engineer", "Finance", "Executive", "Warehouse Manager"),
}
EXTRA_SECTIONS: dict[tuple[str, str], tuple[str, ...]] = {("access", "orgs"): ("Admin",)}


@dataclass(frozen=True)
class Account:
    id: str
    role: str
    label: str
    tenant: str | None = None
    site: str | None = None
    warehouse: str | None = None
    home: str | None = None


@dataclass
class Context:
    """Run-time access state (from the database). The defaults are the demo's starting state."""

    delegations: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(DELEGATION_SCOPES, True))
    grants: dict[str, list[str]] = field(default_factory=dict)  # account id -> extra tenants (live grants only)
    # account id -> {tenant: when the grant ends, ISO; None: no end} for the live grants (migration 0027)
    grant_ends: dict[str, dict[str, str | None]] = field(default_factory=dict)
    accounts: dict[str, Account] | None = None  # id -> account as mapped now, in the demo's order; None: the starting ones
    limits: dict[str, float | None] = field(default_factory=lambda: dict(STARTING_LIMITS))
    self_approval: bool = False
    org_units: dict[str, orgs.OrgUnit] | None = None  # the org tree (table org_unit); None: the seeded one


@cache
def _data() -> dict:
    return golden.load("policy")


@cache
def _world() -> dict:
    return golden.load("world")


def roles() -> dict[str, dict]:
    return _data()["role_policy"]


def sections() -> dict[str, list[str]]:
    return _data()["sections"]


def org_units(ctx: Context | None = None) -> dict[str, orgs.OrgUnit]:
    """The org tree: the context's (the table's rows) or the seeded one."""
    if ctx is not None and ctx.org_units is not None:
        return ctx.org_units
    return orgs.SEEDED


def tenants(ctx: Context | None = None) -> list[str]:
    """The units a case can belong to (customers and companies), in the tree's order. Without a context, the demo's
    tenants (world.json), which are the seeded units."""
    if ctx is None or ctx.org_units is None:
        return _world()["tenants"]
    return [u.id for u in ctx.org_units.values() if u.kind in orgs.TENANT_KINDS]


def permissions() -> list[str]:
    return [*_data()["perm_acts"], "approve.mcp", "approve.tenantAccess", *EXTRA_PERMS]


@cache
def starting_accounts() -> tuple[Account, ...]:
    return tuple(Account(**{k: a.get(k) for k in Account.__dataclass_fields__}) for a in _data()["accounts"])


def accounts(ctx: Context | None = None) -> list[Account]:
    """The accounts, in the demo's order: as the identity mapping has them now when given the context."""
    if ctx is not None and ctx.accounts is not None:
        return list(ctx.accounts.values())
    return list(starting_accounts())


def account(account_id: str, ctx: Context | None = None) -> Account | None:
    return next((a for a in accounts(ctx) if a.id == account_id), None)


def resolve_sign_in(value: str, ctx: Context | None = None) -> Account | None:
    """A typed user ID or work email ("exec", "planner.b@northfield.example") → account (the demo's signInResolve)."""
    v = (value or "").strip().lower()
    local, _, domain = v.partition("@")
    if not local or (domain and domain != _data()["signin_domain"]) or " " in v or v.count("@") > 1:
        return None
    ids = _data()["signin_ids"]
    return account(ids.get(local, ""), ctx) or account(local, ctx)


def sign_in_email(a: Account) -> str:
    local = {
        "executive": "executive",
        "planner-a": "planner.a",
        "planner-b": "planner.b",
        "planner-c": "planner.c",
        "wm-1": "warehouse1",
        "wm-2": "warehouse2",
    }.get(a.id, a.id)
    return f"{local}@{_data()['signin_domain']}"


# ---------------------------------------------------------------- the rules (same names as the demo)
def policy(a: Account) -> dict:
    return roles()[a.role]


def limit_for(a: Account | None, ctx: Context | None = None) -> float:
    """The demo's afLimitFor: the account's approval limit in dollars (math.inf: no limit)."""
    if a is None:
        return 0
    limits = (ctx or Context()).limits
    if a.role not in limits:
        return math.inf if a.role in ("Approver", "Admin") else 0
    v = limits[a.role]
    return math.inf if v is None else v


def can(a: Account | None, perm: str, ctx: Context | None = None) -> bool:
    if a is None:
        return False
    perm = _data()["perm_alias"].get(perm, perm)
    if perm in EXTRA_PERMS:
        return a.role in EXTRA_PERMS[perm]
    # the demo's later can(): a Planner may approve once Admin raises the Planner approval limit above $0
    if perm == "approve.decisions" and a.role == "Planner" and limit_for(a, ctx) > 0:
        return True
    p = policy(a)
    if p.get("all"):
        return True
    if perm not in p["perms"]:
        return False
    if a.role == "Approver" and perm.startswith("approve."):
        return (ctx or Context()).delegations.get(perm[len("approve.") :], False)
    return True


def can_page(a: Account | None, page: str, section: str | None = None) -> bool:
    if a is None or (page, section) in HIDDEN_SECTIONS:
        return False
    if page in EXTRA_PAGES:
        return section is None and a.role in EXTRA_PAGES[page]
    if section is not None and (page, section) in EXTRA_SECTIONS:
        return a.role in EXTRA_SECTIONS[(page, section)]
    secs = policy(a)["pages"].get(page)
    if secs is None:
        return False
    return section is None or section in secs


def allowed_tenants(a: Account, ctx: Context | None = None) -> list[str]:
    """The tenants (customer and company units) the account may see: every one, or for a tenant-scoped role those in
    the subtree of its own tenant or of a unit granted to it (a grant on a group covers the units below it)."""
    if not policy(a).get("tenantScoped"):
        return list(tenants(ctx))
    units = org_units(ctx)
    roots = [r for r in (a.tenant, *(ctx or Context()).grants.get(a.id, [])) if r]
    covered = set().union(*(orgs.subtree(units, r) for r in roots))
    return [t for t in tenants(ctx) if t in covered]


def tenant_ok(a: Account, tenant: str, ctx: Context | None = None) -> bool:
    """True if `tenant` (an org unit id) is in the subtree of a tenant the account may see."""
    units = org_units(ctx)
    return any(tenant in orgs.subtree(units, t) for t in allowed_tenants(a, ctx))


def location_ok(a: Account, location: str) -> bool:
    """A Warehouse Manager is locked to one warehouse (the asset's current location)."""
    return not policy(a).get("warehouseScoped") or location == a.warehouse


def home(a: Account | None) -> str:
    if a is None:
        return "command"
    return a.home or policy(a)["landing"]


def summary(a: Account, ctx: Context | None = None) -> dict:
    """Everything the frontend needs to shape itself for this account (as the identity mapping has it now)."""
    a = account(a.id, ctx) or a
    return {
        "account": a.__dict__ | {"email": sign_in_email(a)},
        "description": policy(a)["desc"],
        "home": home(a),
        "permissions": [p for p in permissions() if can(a, p, ctx)],
        "pages": {
            pg: [s for s in [*secs, *(x for p_, x in EXTRA_SECTIONS if p_ == pg)] if can_page(a, pg, s)]
            for pg, secs in sections().items()
            if can_page(a, pg)
        }
        | {pg: [] for pg in EXTRA_PAGES if can_page(a, pg)},  # plan 8 pages without sections (modeler, agents)
        "tenants": allowed_tenants(a, ctx),
        # the account's live tenant grants and when each ends (None: no end); the web app re-reads this at the end
        "grants": [{"tenant": t, "expires_at": e} for t, e in (ctx or Context()).grant_ends.get(a.id, {}).items()],
        "tenant_scoped": bool(policy(a).get("tenantScoped")),
        "warehouse": a.warehouse if policy(a).get("warehouseScoped") else None,
    }


# ---------------------------------------------------------------- identity: the directory and the role mapping
# The roles a directory group may map to (the demo's IDP_ROLES): Admin is assigned directly, never through a group.
def idp_roles() -> list[str]:
    return [r for r in roles() if r != "Admin"]


# The demo's S.idp.groups: the directory group (or App Role) each account is mapped from.
IDP_GROUPS = {
    "planner-a": "circ-planners-customer-a",
    "planner-b": "circ-planners-customer-b",
    "planner-c": "circ-planners-customer-c",
    "approver": "circ-approvers",
    "engineer": "circ-engineering",
    "finance": "circ-finance",
    "developer": "circ-integration-devs",
    "executive": "circ-executives",
    "wm-1": "circ-warehouse-1",
    "wm-2": "circ-warehouse-2",
}


def _idp_email(label: str) -> str:
    return re.sub(r"\s+", "-", label.lower().replace(" · ", ".")) + "@example.com"


def starting_idp_users() -> list[dict]:
    """The demo's S.idp.users: one per account (email from its starting label), plus two deputies without an account."""
    users = [{"id": a.id, "email": _idp_email(a.label), "acct": a.id} for a in starting_accounts()]
    return [
        *users,
        {"id": "dep-ap", "email": "approver.deputy@example.com", "acct": None, "role": "Approver"},
        {"id": "dep-pl", "email": "planner.deputy@example.com", "acct": None, "role": "Planner"},
    ]


def idp_role_of(u: dict, ctx: Context | None = None) -> str | None:
    """The demo's idpRoleOf: a user's role is their account's (as mapped now), or the directory's for a deputy."""
    if u.get("acct"):
        a = account(u["acct"], ctx)
        return a.role if a else None
    return u.get("role")


def map_identity(a: Account, field_: str, value: str | None) -> Account:
    """The demo's access.mapIdentity handler: the account after mapping its group to another role, or to another site
    (a Warehouse Manager's warehouse). The label is rebuilt from the result."""
    d = dict(a.__dict__)
    if field_ == "role":
        if value is None:  # not reached: the action's input requires the role
            raise ValueError("Mapping a group to a role needs the role.")
        p = roles()[value]
        d["role"] = value
        if p.get("tenantScoped") and not d["tenant"]:
            d["tenant"] = "Customer A"
        if p.get("warehouseScoped") and not d["warehouse"]:
            d["warehouse"] = d["site"] if d["site"] and d["site"] != "Repair centre" else "Warehouse 1"
        if not p.get("warehouseScoped"):
            d["warehouse"] = None
    elif roles()[d["role"]].get("warehouseScoped"):
        if value in ("Warehouse 1", "Warehouse 2"):
            d["warehouse"] = value
    else:
        d["site"] = value or None
    p = roles()[d["role"]]
    d["label"] = (
        d["role"]
        + (" · " + d["tenant"] if p.get("tenantScoped") and d["tenant"] else "")
        + (" · " + d["warehouse"] if d["warehouse"] else "")
    )
    return Account(**d)


# ---------------------------------------------------------------- run-time state, seeded with the demo's start
def _idp_start() -> dict:
    return {"src": "approles", "lastSync": iso(add_days(AS_OF, -0.08)), "ooo": []}


state.register("accounts", lambda: [(a.id, dict(a.__dict__)) for a in starting_accounts()])
state.register("idp_users", lambda: [(u["id"], u) for u in starting_idp_users()])
state.register(
    "access_settings",
    lambda: [("approval", {"limits": dict(STARTING_LIMITS), "self": False}), ("idp", _idp_start())],
)
