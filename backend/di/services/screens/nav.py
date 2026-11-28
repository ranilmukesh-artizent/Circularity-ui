"""The menu and the signed-in session (docs/backend-steps.md, B14): what frontend/src/api/nav.ts and session.ts read.

    GET /api/screens/nav?cc_mode=operational&last_asset=&tenant_filter=All
        groups   the demo's NAV as the account sees it (nav.ts navigation()): the groups it may open, each with the
                 sections it may open, their links and badge keys. cc_mode is the Command Center view an Admin picked
                 ("operational" or "senior": the senior view has fewer sections); last_asset is the asset the user
                 last opened (the Asset intelligence link points at it when the account may see it, else at its first
                 visible case)
        badges   nav.ts navBadges(): cases awaiting approval, the approvals inbox, open conflicts, `mywork` (the length of
                 cases.process.items_for for the account, plan 9 P9-1.8), `mine` (the same list without the data
                 conflicts: the count beside My Tasks) and the per-section
                 counts keyed as in NAV (conf, srcissue, wffail, inbox)
        tasks    the open tasks count in the menu (the demo's frCounts().tasks: Actions on me)
    GET /api/screens/nav/scope   every case id with its owner and location ({id: [owner, location]}), so the frontend
                 can evaluate the demo's canRoute for record links (true, false, or "tenant" for a record outside the
                 account's tenants or warehouse) without a request per link; the tenant boundary itself is enforced
                 by every endpoint and action
    GET /api/screens/nav/accounts   the accounts as the identity mapping has them now, with their sign-in email: the
                 sign-in page lists them before anyone has signed in (the demo's ACCOUNTS)

The endpoints are in di.routes.screens.nav; this module builds what they return.

Where the counts come from:
- awaiting, inbox, tasks: the cases in the database and the workspace collections, as the reads compute them;
- conf (decided in B17, 20 Nov 2026): the connectors' real conflict table (B9), counting only the conflicts that
  hold up a decision: open or escalated conflicts on the asset of a case the account may see that has no decision yet
  or is awaiting approval. The full queue (hundreds after a sync) stays on the Connection Fabric's conflicts page;
- srcissue: the backend's source_system table (sources stale or unavailable), the real connector state, which gives
  the demo's count after a sync;
- wffail: the demo's starting failed workflows (di.repositories.common.STARTING_FAILED_WORKFLOWS), until workflows move.

Session: /api/auth/me (di/routes/auth.py) already returns the account, its email, description, home route, the
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

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy
from di.core.auth import Principal, load_context
from di.repositories.common import STARTING_FAILED_WORKFLOWS, inbox_requests
from di.repositories.context import call_ctx, can_see_case, visible_cases
from di.repositories.fabric import held_conflicts
from di.repositories.reference import lists
from di.repositories.workspace import aome_items
from di.services.cases import process, store

# sources with an issue: stale or unavailable, and the connector states the screens show as stale
ISSUE_SQL = "SELECT count(*) FROM source_system WHERE status IN ('stale', 'unavailable', 'failing', 'auth_expired')"
# Sections beyond the demo's NAV (plan 8; visible as policy.EXTRA_SECTIONS allows): [id, label, sub], after the golden ones
EXTRA_KIDS: dict[str, list[list[str]]] = {"access": [["orgs", "Organisation", "Groups, companies, sites and customers"]]}
# Pages beyond the demo's NAV (plan 8; visible as policy.EXTRA_PAGES allows): (the group or section it goes before, the entry)
EXTRA_NAV: list[tuple[str, dict]] = [
    # 28 Nov 2026 (decision log): Set up is its own entry after Home. My work is no longer in the menu: My Tasks is the one
    # page of what waits on a person (its route #/mywork still opens it).
    ("command", {"id": "setup", "label": "Set up", "sub": "Describe the business, connect systems, publish", "icon": "flag",
                 "leaf": True}),
    ("More", {"id": "modeler", "label": "Modeler", "sub": "Decision process and business rules", "icon": "branch",
              "sec": "Integration", "leaf": True}),
    ("orchestration", {"id": "agents", "label": "Agents", "sub": "Registry, runs, proposals and tools", "icon": "bot",
                       "sec": "More", "leaf": True}),
]  # fmt: skip


def nav_groups() -> list[dict]:
    """The demo's NAV with the EXTRA_NAV entries, each before the group it names, or the first group of the section
    it names (else last)."""
    out = list(lists()["NAV"])
    for before, g in EXTRA_NAV:
        out.insert(next((i for i, x in enumerate(out) if before in (x["id"], x.get("sec"))), len(out)), g)
    return out


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
    mine = [c for c in cases if can_see_case(a, p.ctx, c)]  # the demo's myCases
    last = next((c for c in cases if c["id"] == last_asset), None)
    asset = last["id"] if last and p.tenant_ok(last["owner"]) else (mine[0]["id"] if mine else "RT-1048")  # rbLastAsset

    def kids_of(g: dict) -> list[list]:
        kids = [*g["kids"], *EXTRA_KIDS.get(g["id"], [])]
        return [k for k in kids if policy.can_page(a, g["id"], k[0]) and (g["id"] != "command" or cc_sec_ok(lay, k[0]))]

    def href(g: dict, k: str) -> str:
        return "#/" + g["id"] + ("/asset/" + asset if g["id"] == "product" and k == "asset" else "/" + k if k else "")

    out = []
    for g in nav_groups():
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
    ctx = call_ctx(p, session)
    conf = held_conflicts(ctx, session)
    srcissue = session.execute(text(ISSUE_SQL)).scalar()
    wffail = len(STARTING_FAILED_WORKFLOWS)
    inbox = len(inbox_requests(ctx))
    awaiting = sum(1 for c in visible_cases(ctx, tenant_filter) if c["stage"] == "awaiting_approval")
    mine = process.items_for(session, ctx)
    return {
        "awaiting": awaiting,
        "inbox": inbox if policy.can_page(p.account, "command", "approvals") else 0,
        "integration": conf if policy.can_page(p.account, "integration", "conflicts") else 0,
        "mywork": len(mine),
        # the one count beside My Tasks: what waits on the person, without the data conflicts (counted on the Connection Fabric)
        "mine": sum(1 for w in mine if w.kind != "conflict"),
        "sections": {"conf": conf, "srcissue": srcissue, "wffail": wffail, "inbox": inbox},
    }


def page(
    p: Principal,
    session: Session,
    cc_mode: str = "operational",
    last_asset: str | None = None,
    tenant_filter: str = "All",
) -> dict:
    """GET /api/screens/nav: the menu as the account sees it, its badges and the open tasks count."""
    cases = store.all_cases(session)
    return {
        "groups": navigation(p, cases, cc_mode, last_asset),
        "badges": badges(p, session, tenant_filter),
        "tasks": len(aome_items(call_ctx(p, session))),
    }


def scope(session: Session) -> dict:
    """GET /api/screens/nav/scope: every case id with its owner and location."""
    rows = session.execute(text("SELECT id, owner, location FROM case_record ORDER BY id"))
    return {r.id: [r.owner, r.location] for r in rows}


def accounts(session: Session) -> list[dict]:
    """The demo accounts, as the identity mapping has them now, with the sign-in email (shown before sign-in)."""
    return [a.__dict__ | {"email": policy.sign_in_email(a)} for a in policy.accounts(load_context(session))]
