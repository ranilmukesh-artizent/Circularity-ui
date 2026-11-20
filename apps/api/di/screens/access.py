"""Access & Governance (#/access): accounts, identity provider, delegations, requests, agent autonomy, approval limits,
agents and kill switches, agent metrics (B14).

    GET /api/screens/access      every section of the Access page the signed-in account may see, keyed by section
                                 (accounts, identity, delegations, requests, autonomy, limits, agentsx, metrics)

Only an account with the Access page (Admin) gets it; others get 403 `out_of_scope`, as the access actions do.

Where the data comes from (all at parity with the demo; fixtures/golden/screens/access.json):
- accounts as the identity mapping has them now (state "accounts"), their role policy (policy.json) and tenant grants
  (table tenant_grant);
- the directory (state "idp_users", and "access_settings" item "idp"), the directory groups (policy.IDP_GROUPS);
- delegations (table delegation), with the demo's labels and descriptions (DELEG);
- requests (state "requests"), each with whether this account may decide it (the demo's canDecide);
- approval limits and self-approval (state "access_settings" item "approval");
- agent autonomy per role (AF.cfg.auto), stopped agents (AF.cfg.off) and run limits (AF.cfg.max): written by
  access.setAutonomy, agent.setEnabled and access.setRunLimits (di.actions.access) to the "access_settings" items
  "autonomy" ({role: {type: level}}), "agents_off" ({agent: true}) and "run_limits", which do not exist at the
  start, and default to the demo's starting values ({}, {}, 50 actions and 100 in bulk);
- agent metrics (afMetrics) from the action journal: the share of actions per role prepared by an agent, undo rate,
  time to decision. The demo's click and prompt counts per approval and its agent runs (AF.ui) live in the browser:
  `interactions`, `acceptance`, `edit`, `fallback` and `ms` are null and `runs` is 0 until agent runs reach the server
  (B16b); `approvals` counts journaled approvals.

Facade (apps/web/src/api/access.ts) → here:

| export | where |
|---|---|
| requests, canDecide, inboxRequests | GET /api/screens/access → `requests` (each with `can_decide`; `inbox`) |
| mcpProposals | GET /api/screens/mcp/proposals |
| delegations | `delegations` |
| accountRows | `accounts` |
| idp, idpRoleOf, idpRoles | `identity` (each user with `role`; `roles`) |
| autoLevel, autoTypes, levels | `autonomy` (`matrix`, `types`, `levels`) |
| approvalLimit, selfApproveAllowed, runLimits | `limits` |
| governedAgents, hardRules | `agentsx` |
| agentMetrics | `metrics` |
| REQ_KIND, facilities, roles, levelRank | reference |
| delegationLabel, fmtDateTime, pctTxt | frontend-only (formatting) |
"""

import math

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import golden, policy, state
from di.actions.registry import ACTIONS
from di.auth import Principal, principal
from di.db import get_session
from di.reads.access import can_decide, request_rows
from di.reads.common import af_days, requests
from di.reads.constants import AGENTS, AUTO_TYPES, DELEG, HARD_RULES, LEVEL_RANK, LEVELS

router = APIRouter(prefix="/api/screens/access", tags=["screens: access"])

_REF = golden.load("screens/access")
IDP_ROLES = _REF["idp_roles"]  # the demo's IDP_ROLES, in its order (policy.idp_roles() has policy.json's sorted keys)
HOME_LABEL = _REF["home_label"]  # the demo's HOME_LABEL: landing route -> page name
RUN_LIMITS = {"actions": 50, "bulk": 100}  # AF.cfg.max at the start
SECTIONS = ("accounts", "identity", "delegations", "requests", "autonomy", "limits", "agentsx", "metrics")


# ---------------------------------------------------------------- shared with the MCP screen (proposals)


# ---------------------------------------------------------------- sections
def _account(a: policy.Account) -> dict:
    return {k: v for k, v in a.__dict__.items() if v is not None}


def accounts(p: Principal) -> list[dict]:
    """accountRows: each account as mapped now, its role policy, the tenants it sees and the page it lands on."""
    rows = []
    for a in policy.accounts(p.ctx):
        pol = policy.roles()[a.role]
        h = pol["landing"]
        tenants = ", ".join([a.tenant or "", *p.ctx.grants.get(a.id, [])]) if pol.get("tenantScoped") else "All"
        rows.append({"account": _account(a), "policy": pol, "tenants": tenants, "landsOn": HOME_LABEL.get(h, h)})
    return rows


def identity(s: Session, p: Principal) -> dict:
    """S.idp: the role source, last sync, groups, users (each with the role it maps to) and out-of-office delegations."""
    idp = state.get(s, "access_settings", "idp") or {}
    users = [u | {"role": policy.idp_role_of(u, p.ctx)} for u in state.items(s, "idp_users")]
    return {
        "src": idp.get("src"),
        "lastSync": idp.get("lastSync"),
        "ooo": idp.get("ooo", []),
        "groups": policy.IDP_GROUPS,
        "users": users,
        "roles": IDP_ROLES,
    }


def delegations(p: Principal) -> list[dict]:
    return [d | {"on": bool(p.ctx.delegations.get(d["k"]))} for d in DELEG]


def auto_level(stored: dict, role: str, k: str) -> str:
    """afAutoLevel: the role's level for an action type, its default when unset, never above the type's maximum."""
    t = next((x for x in AUTO_TYPES if x["k"] == k), None)
    if t is None:
        return "prepare"
    v = (stored.get(role) or {}).get(k) or t["def"]
    return t["max"] if LEVEL_RANK[v] > LEVEL_RANK[t["max"]] else v


def autonomy(s: Session) -> dict:
    stored = state.get(s, "access_settings", "autonomy") or {}
    matrix = {r: {t["k"]: auto_level(stored, r, t["k"]) for t in AUTO_TYPES} for r in policy.roles()}
    return {"levels": LEVELS, "types": AUTO_TYPES, "matrix": matrix}


def limits(s: Session, p: Principal) -> dict:
    """approvalLimit per role (null: unlimited, as the demo's Infinity or an unset role), self-approval, run limits."""

    def out(v):
        return None if v is None or (isinstance(v, float) and math.isinf(v)) else v

    return {
        "limits": {r: out(p.ctx.limits.get(r)) for r in policy.roles()},
        "self_approve": p.ctx.self_approval,
        "run_limits": dict(state.get(s, "access_settings", "run_limits") or RUN_LIMITS),
    }


def agents(s: Session) -> dict:
    """governedAgents: identities, scopes, limits, kill switch, and how many journaled actions each prepared."""
    off = state.get(s, "access_settings", "agents_off") or {}
    prepared = dict(s.execute(text("SELECT preparer, count(*) FROM action_journal WHERE preparer IS NOT NULL GROUP BY 1")).all())
    rows = [
        {"id": a["id"], "name": a["name"], "scopes": list(a["scopes"]), "limit": a["limit"], "stopped": bool(off.get(a["id"])),
         "prepared": prepared.get(a["id"], 0)}
        for a in AGENTS
    ]  # fmt: skip
    return {"agents": rows, "hard_rules": HARD_RULES}


def _median(xs: list[float]) -> float:
    """The demo's med."""
    s = sorted(xs)
    m = len(s) >> 1
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def metrics(s: Session) -> dict:
    """afMetrics, from the action journal (see the module docstring for what stays in the browser)."""
    rows = s.execute(text("SELECT action, role, preparer, undone, case_id, at FROM action_journal ORDER BY seq")).mappings().all()
    live = [r for r in rows if not r["undone"] and r["action"] in ACTIONS and ACTIONS[r["action"]].risk != "read"]
    share: dict[str, dict] = {}
    for r in live:
        b = share.setdefault(r["role"], {"all": 0, "agent": 0})
        b["all"] += 1
        b["agent"] += 1 if r["preparer"] else 0
    prep = [r for r in rows if r["preparer"]]
    approvals = [r for r in live if r["action"] in ("decision.approve", "decision.override")]
    received = {}
    if approvals:
        ids = list({r["case_id"] for r in approvals})
        q = text("SELECT id, data->>'received' FROM case_record WHERE id = ANY(:i)")
        received = dict(s.execute(q, {"i": ids}).all())
    ttd = [af_days(received[r["case_id"]], r["at"].isoformat()) for r in approvals if received.get(r["case_id"])]
    return {
        "interactions": None,
        "approvals": len(approvals),
        "share": share,
        "acceptance": None,
        "edit": None,
        "undo": (sum(1 for r in prep if r["undone"]) / len(prep)) if prep else None,
        "fallback": None,
        "ttd": _median(ttd) if ttd else None,
        "runs": 0,
        "ms": None,
    }


# ---------------------------------------------------------------- endpoint
@router.get("")
def access_page(p: Principal = Depends(principal), session: Session = Depends(get_session)):
    p.require_page("access")
    secs = [x for x in SECTIONS if policy.can_page(p.account, "access", x)]
    build = {
        "accounts": lambda: accounts(p),
        "identity": lambda: identity(session, p),
        "delegations": lambda: delegations(p),
        "requests": lambda: {
            "requests": request_rows(session, p),
            "inbox": [r["id"] for r in requests(session) if can_decide(p, r)],
        },
        "autonomy": lambda: autonomy(session),
        "limits": lambda: limits(session, p),
        "agentsx": lambda: agents(session),
        "metrics": lambda: metrics(session),
    }
    return {"sections": secs} | {x: build[x]() for x in secs}
