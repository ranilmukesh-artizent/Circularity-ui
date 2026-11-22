"""Reference data (docs/backend-steps.md, B14): the static lists every page reads, in one answer.

    GET /api/screens/reference              every list below, keyed by the demo's name
    GET /api/screens/reference?names=A,B    only those lists

The lists are the demo's constants after it has loaded (index.html): no account, case, decision, event or workspace
state goes into them, so they are the same for every account and never change while the stack runs. They are
configuration, read from the golden file `fixtures/golden/screens/reference.json` that
`frontend/scripts/golden/analytics_audit.mjs` dumps from the demo (as the access policy is read from policy.json, B7).
Signing in is not needed: the sign-in page reads ROLE_POLICY and RB_AV before anyone has signed in. The endpoint is
in di.routes.screens.reference; this module picks the lists.

What is here, by the facade file that reads it (frontend/src/api/*.ts):

| facade file      | lists                                                                                            |
|------------------|--------------------------------------------------------------------------------------------------|
| analytics.ts     | MONTHS ROUTES MODELS CLASSES CLS_ICON EQUIP COMPS JSTEPS JMAP (the demo's jmap(n), n = 0..12)     |
| session.ts       | ROLE_POLICY RB_AV TENANTS PERM_ALIAS RB_SECS (can / canPage are evaluated from /api/auth/me)      |
| access.ts        | AF_AUTO_TYPES AF_LEVELS AF_LV_RANK DELEG FACILITIES HARD_RULES HOME_LABEL IDP_ROLES ROLE_POLICY   |
| case.ts          | AF_STAGES JSTEPS_AF ST_PH                                                                        |
| command.ts       | AS_OF CAP_LBL CC_CAP CC_DESC CC_DUE CC_LAYOUT CC_REASONS CC_STAGES CLASSES CLS_ICON FACILITIES    |
|                  | FEAT MONTHS NAV REQ_KIND ROUTES STEP_TPL TENANTS                                                 |
| home.ts          | AF_AUTO_TYPES AF_INTENTS AF_LEVELS AF_STARTERS FR_AK FR_MODES FR_MODH FR_NOTIF FR_REP FR_ST FR_TG |
|                  | MONTHS NAV NOWF PAGES RG_CUR RG_LANG RG_TZ                                                       |
| integration.ts   | AUTH_OPTS CANON CANON_EX CANON_PFX CATALOG CONN_METHODS FACILITIES FR_AUTH FR_CATS FR_DEC         |
|                  | FR_INT_KIDS FR_INT_SUB FR_SAMPLE FR_XTYPES SAMPLE_CSV SRC_CATS SRC_CAT_NOTE SRC_TYPES TBL_AVAIL   |
|                  | TBL_MODELS TENANTS                                                                               |
| mcp.ts           | AF_EVALS HARD_RULES JSTEPS RISK_LABEL TENANTS TOOLS                                              |
| nav.ts           | NAV RG_CUR (the menu as the account sees it is /api/screens/nav)                                 |
| orchestration.ts | AF_STAGE_AGENT FEAT HANDOFF_MODEL LR_MODELS RUN_ST                                               |
| product.ts       | AF_BADGE_TIP AS_OF CC_EST CLASSES DIAG EX_FX EX_MC FACILITIES FEAT GATES JG JG_NEXT JSTEPS MONTHS |
|                  | RATE_CARD RG_CONT RG_CUR                                                                         |
| workflows.ts     | ACT_TYPES CH_ARR CH_DEL CH_ING DELIVER FR_CATOF FR_SRCG FR_ST FR_XF FXD MAP_TARGET NOWF SH        |
|                  | SRC_CATS TOOLS WF_STC WF_STL XF                                                                  |
| (world)          | SITES GATES                                                                                      |

CC_EST (estimated value per unit by class) is derived from the closed decisions, which are fixed, so it is a constant.
Functions in the demo's lists (AF_INTENTS matchers, AF_EVALS checks) are not data and are left out, as the dump drops
them; AF_INTENTS and AF_EVALS keep their ids, titles and questions.

Not here, because they are state or computed per account (each area's endpoints serve them): ACCOUNTS (the identity
mapping changes them; /api/screens/nav/accounts), AGENTS and CLIENT_SERVERS (MCP changes them), MAPPINGS, SOURCES,
CONFLICTS, EVENTS, CALLS, EXPECTED, POOLS, ROWS, CASE_BY_ID, ACTIONS (GET /api/actions), AF, S. Not here because they
are frontend assets: ICON, LOGO, LOGO_INK (bundle them with the app).
"""

from di.core.errors import ApiError
from di.repositories.reference import lists


def reference(names: str | None = None) -> dict:
    """Every list, or only the comma-separated `names` (404 naming any that does not exist)."""
    data = lists()
    if not names:
        return data
    want = [n.strip() for n in names.split(",") if n.strip()]
    missing = [n for n in want if n not in data]
    if missing:
        raise ApiError("not_found", "No reference list " + ", ".join(missing) + ".", 404)
    return {n: data[n] for n in want}
