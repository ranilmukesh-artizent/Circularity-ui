"""The menu and the signed-in session (docs/BACKEND_STEPS.md, B14): what apps/web/src/api/nav.ts and session.ts read.

    GET /api/screens/nav?cc_mode=operational&last_asset=&tenant_filter=All
        groups   the demo's NAV as the account sees it (nav.ts navigation()): the groups it may open, each with the
                 sections it may open, their links and badge keys. cc_mode is the Command Center view an Admin picked
                 ("operational" or "senior": the senior view has fewer sections); last_asset is the asset the user
                 last opened (the Asset intelligence link points at it when the account may see it, else at its first
                 visible case)
        badges   nav.ts navBadges(): cases awaiting approval, the approvals inbox, open conflicts, and the per-section
                 counts keyed as in NAV (conf, srcissue, wffail, inbox)
        tasks    the open tasks count in the menu (the demo's frCounts().tasks: Actions on me)
    GET /api/screens/nav/accounts   the accounts as the identity mapping has them now, with their sign-in email: the
                 sign-in page lists them before anyone has signed in (the demo's ACCOUNTS)

Where the counts come from:
- awaiting, inbox, tasks: the cases in the database and the workspace collections, as the reads compute them;
- conf: the demo's conflict list (di.reads.common.STARTING_CONFLICTS), as the Command Center and Home reads count
  them. The connectors' conflict table (B9) holds the real queue (hundreds after a sync); B17 decides which one the
  menu shows, together with the Connection Fabric's conflicts page;
- srcissue: the backend's source_system table (sources stale or unavailable), the real connector state, which gives
  the demo's count after a sync;
- wffail: the demo's starting failed workflows (di.reads.common.STARTING_FAILED_WORKFLOWS), until workflows move.

Session: /api/auth/me (di/routers/auth.py) already returns the account, its email, description, home route, the
permissions it holds, the pages and sections it may open, its tenants and warehouse; nothing is added to it.

Facade mapping, for the switch-over (B17):

| export (nav.ts)       | served by                                                                         |
|-----------------------|-----------------------------------------------------------------------------------|
| navigation()          | endpoint: GET /api/screens/nav (groups)                                           |
| navBadges()           | endpoint: same answer (badges)                                                    |
| navCounts()           | endpoint: tasks here; alerts = the home area's alerts endpoint, unacknowledged     |
| alerts()              | endpoint: the home area's alerts (the demo's frAlerts), not duplicated here        |
| liveAgo()             | frontend-only: a clock text ("updated 2 min ago")                                 |
| regionSummary()       | frontend-only: the user's region settings (S.rg) and RG_CUR (reference)           |
| logos(), iconSvg()    | frontend-only: assets (LOGO, LOGO_INK, ICON) to bundle with the app                |

| export (session.ts)   | served by                                                                         |
|-----------------------|-----------------------------------------------------------------------------------|
| currentAccount()      | endpoint: GET /api/auth/me (account)                                              |
| resolveSignIn, signIn | endpoint: POST /api/auth/login (resolves an ID or email, returns the token and me) |
| signOut()             | frontend-only: drop the token                                                     |
| accounts()            | endpoint: GET /api/screens/nav/accounts                                           |
| accountById(id)       | frontend-only: find in accounts()                                                 |
| signInEmail(a)        | endpoint: accounts()[].email and /api/auth/me account.email                        |
| rolePolicy(role)      | reference: ROLE_POLICY                                                            |
| roleAvatar(role)      | reference: RB_AV                                                                  |
| can(perm)             | frontend-only: me.permissions, with PERM_ALIAS (reference) for "approve"          |
| canPage(page, sec)    | frontend-only: me.pages                                                           |
| canRoute(r)           | frontend-only: me.pages, me.tenants and me.warehouse against the record's owner    |
| homeRoute()           | endpoint: /api/auth/me (home)                                                     |
| tenants()             | reference: TENANTS                                                                |
| allowedTenants()      | endpoint: /api/auth/me (tenants)                                                  |
| tenantFilter, setTenantFilter, setBackendTheme, SIGNIN_DOMAIN | frontend-only: view state (sent as tenant_filter) |
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import policy
from di.auth import Principal, load_context, principal
from di.cases import store
from di.db import get_session
from di.reads.common import STARTING_CONFLICTS, STARTING_FAILED_WORKFLOWS, inbox_requests
from di.reads.workspace import aome_items
from di.screens.analytics import call_context, vis_cases_filtered
from di.screens.reference import lists

router = APIRouter(prefix="/api/screens/nav", tags=["screens: nav"])

# sources with an issue: stale or unavailable, and the connector states the screens show as stale
ISSUE_SQL = "SELECT count(*) FROM source_system WHERE status IN ('stale', 'unavailable', 'failing', 'auth_expired')"


def cc_layout(a: policy.Account, cc_mode: str) -> dict | None:
    """The demo's ccLayout: the Command Center layout for the role (an Admin's senior view is the Executive's)."""
    lay = lists()["CC_LAYOUT"]
    if a.role == "Admin" and cc_mode == "senior":
        return lay["Executive"]
    return lay.get(a.role)


def cc_sec_ok(lay: dict | None, k: str) -> bool:
    """The demo's ccSecOK: does the layout show this Command Center section?"""
    if not lay:
        return False
    row = lay.get("row") or []
    return {
        "kpis": True,
        "exceptions": bool(lay.get("senior") or lay.get("exceptions")),
        "aome": bool(lay.get("aome")),
        "handed": bool(lay.get("handed")),
        "approvals": bool(lay.get("inbox")),
        "outcomes": bool(lay.get("outcomes")),
        "actions": bool(lay.get("actions")),
        "signals": any(x != "value" for x in row),
        "health": lay.get("health") == "full",
    }.get(k, False)


def navigation(p: Principal, cases: list[dict], cc_mode: str = "operational", last_asset: str | None = None) -> list[dict]:
    """nav.ts navigation(): NAV filtered by the demo's frVisible and navKids, with each link as navHref builds it."""
    a = p.account
    lay = cc_layout(a, cc_mode)
    mine = [c for c in cases if p.tenant_ok(c["owner"]) and p.location_ok(c["location"])]  # the demo's myCases
    last = next((c for c in cases if c["id"] == last_asset), None)
    asset = last["id"] if last and p.tenant_ok(last["owner"]) else (mine[0]["id"] if mine else "RT-1048")  # rbLastAsset

    def kids_of(g: dict) -> list[list]:
        return [k for k in g["kids"] if policy.can_page(a, g["id"], k[0]) and (g["id"] != "command" or cc_sec_ok(lay, k[0]))]

    def href(g: dict, k: str) -> str:
        return "#/" + g["id"] + ("/asset/" + asset if g["id"] == "product" and k == "asset" else "/" + k if k else "")

    out = []
    for g in lists()["NAV"]:
        if not policy.can_page(a, g["id"]):
            continue
        kids = [] if g.get("leaf") else kids_of(g)
        if not g.get("leaf") and not kids:
            continue
        first = ("received" if any(k[0] == "received" for k in kids) else (kids[0][0] if kids else "")) if g.get("mode") else ""
        out.append({
            "id": g["id"], "label": g["label"], "sub": g["sub"], "icon": g["icon"], "section": g.get("sec") or "",
            "leaf": bool(g.get("leaf")), "href": "#/" + g["id"] if g.get("leaf") else href(g, first),
            "kids": [
                {"id": k[0], "label": k[1], "sub": k[2], "href": href(g, k[0])} | ({"badge": k[3]} if len(k) > 3 else {})
                for k in kids
            ],
        })  # fmt: skip
    return out


def badges(p: Principal, session: Session, tenant_filter: str = "All") -> dict:
    """nav.ts navBadges()."""
    ctx = call_context(p, session)
    conf = sum(1 for c in STARTING_CONFLICTS if c["status"] == "open")
    srcissue = session.execute(text(ISSUE_SQL)).scalar()
    wffail = len(STARTING_FAILED_WORKFLOWS)
    inbox = len(inbox_requests(ctx))
    awaiting = sum(1 for c in vis_cases_filtered(ctx, tenant_filter) if c["stage"] == "awaiting_approval")
    return {
        "awaiting": awaiting,
        "inbox": inbox if policy.can_page(p.account, "command", "approvals") else 0,
        "integration": conf if policy.can_page(p.account, "integration", "conflicts") else 0,
        "sections": {"conf": conf, "srcissue": srcissue, "wffail": wffail, "inbox": inbox},
    }


@router.get("")
def nav(
    cc_mode: str = "operational",
    last_asset: str | None = None,
    tenant_filter: str = "All",
    p: Principal = Depends(principal),
    session: Session = Depends(get_session),
):
    cases = store.all_cases(session)
    return {
        "groups": navigation(p, cases, cc_mode, last_asset),
        "badges": badges(p, session, tenant_filter),
        "tasks": len(aome_items(call_context(p, session))),
    }


@router.get("/accounts")
def accounts(session: Session = Depends(get_session)):
    """The demo accounts, as the identity mapping has them now, with the sign-in email (shown before sign-in)."""
    return [a.__dict__ | {"email": policy.sign_in_email(a)} for a in policy.accounts(load_context(session))]
