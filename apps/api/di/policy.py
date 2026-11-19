"""The access policy (docs/BACKEND_STEPS.md, B7): who may see and do what. A port of the demo's RBAC block
(index.html, /*RBAC-START*/ … /*RBAC-END*/), so the server refuses exactly what the screens hide.

The policy itself (roles, their pages and permissions, the demo accounts, sign-in IDs) is configuration, read from
the B1 golden file `policy.json`. What changes at run time lives in the database: the Approver's delegations
(decisions, MCP proposals, tenant access) and the tenant grants a Planner was given.
"""

from dataclasses import dataclass, field
from functools import cache

from di import golden

# Features the demo keeps hidden (index.html FEAT: pools:false): these sections are never visible.
HIDDEN_SECTIONS = {("product", "pools"), ("analytics", "pool")}
DELEGATION_SCOPES = ("decisions", "mcp", "tenantAccess")


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
    """Run-time access state: Approver delegations and tenant grants (from the database)."""

    delegations: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(DELEGATION_SCOPES, True))
    grants: dict[str, list[str]] = field(default_factory=dict)  # account id -> extra tenants


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


def tenants() -> list[str]:
    return _world()["tenants"]


def permissions() -> list[str]:
    return list(_data()["perm_acts"]) + ["approve.mcp", "approve.tenantAccess"]


def accounts() -> list[Account]:
    return [Account(**{k: a.get(k) for k in Account.__dataclass_fields__}) for a in _data()["accounts"]]


def account(account_id: str) -> Account | None:
    return next((a for a in accounts() if a.id == account_id), None)


def resolve_sign_in(value: str) -> Account | None:
    """A typed user ID or work email ("exec", "planner.b@northfield.example") → account (the demo's signInResolve)."""
    v = (value or "").strip().lower()
    local, _, domain = v.partition("@")
    if not local or (domain and domain != _data()["signin_domain"]) or " " in v or v.count("@") > 1:
        return None
    ids = _data()["signin_ids"]
    return account(ids.get(local, "")) or account(local)


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


def can(a: Account | None, perm: str, ctx: Context | None = None) -> bool:
    if a is None:
        return False
    perm = _data()["perm_alias"].get(perm, perm)
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
    secs = policy(a)["pages"].get(page)
    if secs is None:
        return False
    return section is None or section in secs


def allowed_tenants(a: Account, ctx: Context | None = None) -> list[str]:
    if not policy(a).get("tenantScoped"):
        return list(tenants())
    extra = (ctx or Context()).grants.get(a.id, [])
    return [t for t in tenants() if t == a.tenant or t in extra]


def tenant_ok(a: Account, tenant: str, ctx: Context | None = None) -> bool:
    return tenant in allowed_tenants(a, ctx)


def location_ok(a: Account, location: str) -> bool:
    """A Warehouse Manager is locked to one warehouse (the asset's current location)."""
    return not policy(a).get("warehouseScoped") or location == a.warehouse


def home(a: Account | None) -> str:
    if a is None:
        return "command"
    return a.home or policy(a)["landing"]


def summary(a: Account, ctx: Context | None = None) -> dict:
    """Everything the frontend needs to shape itself for this account."""
    return {
        "account": a.__dict__ | {"email": sign_in_email(a)},
        "description": policy(a)["desc"],
        "home": home(a),
        "permissions": [p for p in permissions() if can(a, p, ctx)],
        "pages": {pg: [s for s in secs if can_page(a, pg, s)] for pg, secs in sections().items() if can_page(a, pg)},
        "tenants": allowed_tenants(a, ctx),
        "tenant_scoped": bool(policy(a).get("tenantScoped")),
        "warehouse": a.warehouse if policy(a).get("warehouseScoped") else None,
    }
