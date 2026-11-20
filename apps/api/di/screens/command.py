"""Command Center (#/command/<section>): the read endpoints behind apps/web/src/api/command.ts (B14).

Every figure is what the facade computes today from the demo's Command Center helpers (ccScope, ccRows, ccKpiSet,
ccSignals, ccExRows, aomeItems, handedRows, inboxReqs, afApprovalQueue, hhTotals ...), scoped to the signed-in account
and to the page's filters, which are query parameters:

    scope filters (S.tenant and S.cc): tenant (All | a tenant), site, cls, route, months (12 | 6 | 3)
    table filters (S.cc):              stage, due, reason, q
    view settings:                     mode (operational | senior: Admin's S.ccMode), all (S.opScope widened)

Parity: tests/test_screens_command.py against fixtures/golden/screens/command.json (scripts/golden/home_command.mjs).

Facade export (command.ts)            | served by
--------------------------------------|---------------------------------------------------------------------------
ccLayout, ccKeys, ccSecOK, ccSection  | GET /layout?mode=            -> {layout, keys, sections (open to the account)}
ccScope + kpiTiles, insights,         | GET /kpis?scope filters&mode= -> {tiles, insights, metrics, health, counts}
  ccRows + ccMetrics, healthStrip,    |
  visCaseCount, visRowCount, sourceCount, workflowCount
stageSlices, dueSlices, routeBars,    | GET /charts?scope filters    -> {stages, due, routes, var, combo, signals,
  varReasons, comboData, signals,     |                                  capacity}
  capacity                            |
oppRows, oppRow                       | GET /actions?scope+table filters -> {rows: [{case, trigger, action, cons, btn,
                                      |                                     conf, deadline, left}], total}
exRows, exOwner (+ the read-only      | GET /exceptions?scope filters -> {rows: [ExRow + owner], awaiting: [{id, plan,
  queue of OpsReadOnly)               |                                   net}] (awaiting approval, by net)}
aomeItems, opScopeInfo                | GET /aome?all=&tenant=       -> {items, scope}
handedRows, awaitingApproval          | GET /handed?all=&tenant=     -> {handed, awaiting, scope}
outcomesToConfirm                     | GET /outcomes?tenant=        -> {rows, done}
inboxRequests, inboxScope,            | GET /inbox?tenant=           -> {requests, scope, decisions_awaiting, cards,
  decisionsAwaiting, approvalCards,   |                                 limit (null: no limit)}
  approvalLimit, requestById          |   (requestById: a lookup in `requests`)
healthDetail                          | GET /health                  -> HealthDetail
SECTIONS, CC_STAGES, ccSecLabel,      | reference (/api/screens/reference: NAV, CC_DESC, CC_STAGES, CC_DUE, CLASSES,
  ccSecDesc, filterOptions,           |   ROUTES, FACILITIES, TENANTS, CLS_ICON, MONTHS, ACCOUNTS); filterOptions'
  classLabel, routeShort, clsIcon,    |   locked tenants come from the session's allowed tenants
  monthLabel, notifyRecipients, tenantAllowed
ccFilters, setCcFilters, clearCcFilters, | frontend-only: view settings (S.cc, S.tenant, S.ccMode, S.ccOps, S.opScope)
  ccPick, ccMode, setCcMode, ccOps,   |   passed to the endpoints as query parameters; formatting (kfmt, tFmt,
  setCcOps, toggleOpScope, clockText, |   the clock text); the route check is the session's (canRoute)
  rbPath, kfmt, tFmt, asModel         |
sendNotification, acknowledge,        | actions (POST /api/actions/notify.send, notify.acknowledge,
  decideRequest                       |   access.decideRequest)

Differences from the demo, by design:
- inbox.cards[].kinds: the step kinds of the route (STEP_TPL); cards[].steps labels them "<step> → <system>" (EX_STEP).
  The demo's facade mapped the kinds with `s[0] + ' → ' + s[1]`, which on its step kinds (strings) gave their first
  two letters ("o → r"); B17 fixed the facade to use these labels in both modes.
- kpis.counts.workflows: the demo counts its workflows only once a page has opened them (S.wf is created lazily);
  the server always counts the catalogue (35).
- Integration health (hhTotals) has no workflow runs in progress on the server; the demo has none at the start either.
"""

import re
from functools import cmp_to_key

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from di import policy
from di.auth import Principal, principal
from di.db import get_session
from di.engine.jsmath import js_round, js_sum
from di.execution.steps import EX_STEP, STEP_TPL, steps_for
from di.reads import cases as case_reads
from di.reads import workspace as ws
from di.reads.common import (
    AS_OF,
    DAY_MS,
    REQ_KIND,
    SOURCES,
    STARTING_CONFLICTS,
    Case,
    active_step,
    add_days,
    as_model,
    decisions_delegated,
    ex_app,
    ex_clock,
    ex_ts,
    exp_vis,
    fmt_d,
    fmt_n,
    inbox_requests,
    kfmt,
    limit_for,
    money,
    ms,
    notes,
    requests,
    step_owner,
    ti_conf,
    to_fixed,
)
from di.screens.home import (
    ROUTES,
    call_ctx,
    can_page,
    cc_net,
    hh,
    hh_totals,
    metrics,
    sm_exceptions,
    stale_sources,
    vis,
    vis_rows,
    wf_stat,
    workflows,
)

router = APIRouter(prefix="/api/screens/command", tags=["screens: command"])

FEAT_UPLIFT = False  # the demo's FEAT.uplift: the uplift figure is hidden
SECTIONS = ["kpis", "exceptions", "aome", "handed", "approvals", "outcomes", "charts", "actions", "signals", "value", "health"]
CC_STAGES = [
    ("await_insp", "Awaiting inspection", "var(--chart7)"),
    ("need", "Needs information", "var(--chart5)"),
    ("approval", "Awaiting approval", "var(--chart2)"),
    ("approved", "Approved · handing off", "var(--chart3)"),
    ("exec", "Handed off · awaiting outcome", "var(--chart1)"),
    ("reeval", "Re-evaluate", "var(--chart4)"),
    ("noroute", "No viable route", "var(--chart6)"),
]
CC_DUE = [
    ("d5", "< 5 days", "var(--bad)"),
    ("d7", "5–7 days", "#D4A800"),
    ("d10", "8–10 days", "var(--chart2)"),
    ("d11", "> 10 days", "var(--ok)"),
]
CAP_LBL = {"In execution": "Awaiting outcome from enterprise systems"}
CC_LAYOUT: dict[str, dict] = {
    "Planner": {
        "sub": "Prepare cases, close evidence gaps and submit decisions for review.",
        "kpis": ["aome", "scope", "awaiting", "gaps", "closing"],
        "aome": 1,
        "handed": 1,
        "charts": ["lifecycle", "due"],
        "actions": 1,
        "row": ["signals"],
        "ops": 1,
    },
    "Approver": {
        "sub": "Decide what is waiting for you: treatment decisions, spend and sale terms, and the requests Admin "
        "delegated to you.",
        "kpis": ["awaitVal", "potential", "risk", "closing", "inbox"],
        "aome": 1,
        "inbox": 1,
        "charts": ["var", "due"],
        "actions": 1,
        "row": ["capacity", "value"],
        "ops": 1,
    },
    "Engineer": {
        "sub": "Inspection queue, failed eligibility gates, condition and parts at risk.",
        "kpis": ["aome", "inspq", "gatefail", "graded", "parts"],
        "aome": 1,
        "handed": 1,
        "charts": ["lifecycle", "treat"],
        "actions": 1,
        "row": ["signals", "capacity"],
        "ops": 1,
        "health": "strip",
    },
    "Finance": {
        "sub": "Recovered value, avoided spend and outcomes waiting for confirmation.",
        "kpis": ["net", "uplift", "yield", "avoided", "co2m"],
        "aome": 1,
        "outcomes": 1,
        "charts": ["treat"],
        "row": ["value"],
        "fin": 1,
        "health": "strip",
    },
    "Developer": {
        "sub": "Health of connected systems, workflows, conflicts and MCP server proposals.",
        "kpis": ["ihealth", "srcattn", "wffail", "conf", "props"],
        "aome": 1,
        "health": "full",
    },
    "Executive": {
        "sub": "Value realised, portfolio health and the exceptions that need attention. Drill into the cases or "
        "notify the owner.",
        "kpis": ["net", "uplift", "yield", "avoided", "co2m"],
        "senior": 1,
        "charts": ["lifecycle", "treat"],
        "row": ["value"],
        "fin": 1,
    },
    "Warehouse Manager": {
        "sub": "Your warehouse: what is on you, inbound expected returns, and items with enterprise systems "
        "awaiting an outcome. WMS stays the system of record.",
        "kpis": ["aome", "whcases", "handed", "capwh"],
        "exceptions": 1,
        "aome": 1,
        "handed": 1,
        "charts": ["lifecycle", "due"],
        "row": ["capacity"],
    },
    "Admin": {
        "sub": "Identify, prioritise and act on lifecycle opportunities to maximise economic, operational and "
        "sustainability outcomes.",
        "kpis": ["inbox", "potential", "risk", "ihealth", "uplift"],
        "exceptions": 1,
        "aome": 1,
        "handed": 1,
        "inbox": 1,
        "outcomes": 1,
        "charts": ["lifecycle", "treat", "var", "due"],
        "actions": 1,
        "row": ["signals", "capacity", "value"],
        "ops": 1,
        "health": "full",
    },
}
SENIOR_SUB = "Senior view: value realised, portfolio health and exceptions. Switch to Operational for the queues."
DELEG = [("decisions", "Decisions and overrides"), ("mcp", "MCP server proposals"), ("tenantAccess", "Tenant access")]
REASONS = ws.CC_REASONS
CC_CAP = ws.CC_CAP


# ---------------------------------------------------------------- filters
class Filters:
    """The Command Center's filters (S.tenant and S.cc) from the query string."""

    def __init__(self, tenant="All", site="", cls="", route="", months=12, stage="", due="", reason="", q=""):
        self.tenant, self.site, self.cls, self.route, self.months = tenant or "All", site, cls, route, months
        self.stage, self.due, self.reason, self.q = stage, due, reason, q


def scope_filters(
    tenant: str = "All", site: str = "", cls: str = "", route: str = "", months: int = Query(12, ge=1, le=12)
) -> Filters:
    return Filters(tenant, site, cls, route, months)


def table_filters(f: Filters = Depends(scope_filters), stage: str = "", due: str = "", reason: str = "", q: str = "") -> Filters:
    f.stage, f.due, f.reason, f.q = stage, due, reason, q
    return f


def _f(f: Filters | dict) -> Filters:
    return Filters(**f) if isinstance(f, dict) else f


# ---------------------------------------------------------------- scope (the demo's ccScope and ccRows)
def due_key(left: int) -> str:
    """The demo's ccDueKey."""
    return "d5" if left < 5 else "d7" if left < 8 else "d10" if left < 11 else "d11"


def cc_scope(ctx, f: Filters | dict) -> dict:
    """The visible cases matching the filters, each annotated as the demo's ccScope does: stage bucket (_st), days left
    (_left), value at risk by reason (_risk, _var), estimated value (_val), due bucket (_due), rank score (_score) and,
    for those still needing a person (act), a priority (_pri)."""
    f = _f(f)
    v = vis(ctx, f.tenant)
    util = ws.cc_util(v)
    out = [
        c
        for c in v
        if (not f.site or c["location"] == f.site)
        and (not f.cls or c["cls"] == f.cls)
        and (not f.route or (c.get("recommendation") and c["recommendation"]["id"] == f.route))
    ]
    mx = max([1, *(ws.cc_est(c) for c in out)])
    for c in out:
        c["_st"] = ws.cc_stage(c)
        c["_left"] = ws.cc_left(c)
        c["_risk"] = ws.cc_risk(c, util)
        c["_var"] = js_sum(c["_risk"].values())
        c["_val"] = ws.cc_est(c)
        c["_due"] = due_key(c["_left"])
        c["_score"] = (c["_val"] / mx) * 60 + max(0, min(1, (10 - c["_left"]) / 10)) * 40
    act = sorted(
        (c for c in out if c["_st"] in ("approval", "reeval", "need", "await_insp", "noroute")), key=lambda c: -c["_score"]
    )
    for i, c in enumerate(act):
        c["_pri"] = "High" if i < len(act) * 0.3 else "Medium" if i < len(act) * 0.7 else "Low"
    return {"all": out, "act": act, "util": util, "net": js_sum(cc_net(c) for c in out)}


def cc_rows(ctx, f: Filters) -> list[dict]:
    """The demo's ccRows: the closed decisions in the filters and the time horizon."""
    return [
        r
        for r in vis_rows(ctx, f.tenant)
        if (not f.cls or r["cls"] == f.cls) and (not f.route or r["route"] == f.route) and r["mi"] >= 12 - f.months
    ]


def series(fn, rows: list[dict]) -> list[float]:
    """The demo's ccSeries: a figure per month over the closed decisions."""
    o = [0] * 12
    for r in rows:
        o[r["mi"]] = o[r["mi"]] + fn(r)
    return o


def cc_delta(s: list[float]) -> dict | None:
    """The demo's ccDelta: this month against the month before."""
    a, b = s[11], s[10]
    if not b:
        return None
    p = (a / b - 1) * 100
    up = p >= 0
    return {"txt": to_fixed(abs(p), 0) + "%", "arrow": "▲" if up else "▼", "cls": "ok" if up else "bad"}


def js_fixed(x: float, digits: int) -> str:
    """JavaScript's toFixed for any sign (a negative number keeps its minus, even when it rounds to zero)."""
    return ("-" if x < 0 else "") + to_fixed(abs(x), digits)


def _units(cs: list[Case]) -> str:
    return f"{sum(c['qty'] for c in cs):,}"


# ---------------------------------------------------------------- layout
def layout(a: policy.Account, mode: str) -> dict | None:
    """The demo's ccLayout: the role's key figures and panels (Admin can switch to the senior view)."""
    if a.role == "Admin" and mode == "senior":
        return {**CC_LAYOUT["Executive"], "sub": SENIOR_SUB}
    return CC_LAYOUT.get(a.role)


def keys(L: dict) -> list[str]:
    return [x for x in L["kpis"] if FEAT_UPLIFT or x != "uplift"]


def sec_ok(L: dict, k: str) -> bool:
    """The demo's ccSecOK."""
    row = L.get("row") or []
    return {
        "kpis": True,
        "exceptions": bool(L.get("senior") or L.get("exceptions")),
        "aome": bool(L.get("aome")),
        "handed": bool(L.get("handed")),
        "approvals": bool(L.get("inbox")),
        "outcomes": bool(L.get("outcomes")),
        "actions": bool(L.get("actions")),
        "signals": any(x != "value" for x in row),
        "health": L.get("health") == "full",
    }.get(k, False)


def sections(ctx, L: dict) -> list[str]:
    """The sections the account may open (the demo's ccSec: the layout has it and the access policy allows it)."""
    return [k for k in SECTIONS if k == "kpis" or (sec_ok(L, k) and can_page(ctx, "command", k))]


# ---------------------------------------------------------------- key figures (the demo's ccKpiSet)
def _parts_backorder(c: Case) -> bool:
    """The demo's asParts(c, assetHealth(c)): a component is on backorder when its stock draw is below 0.3."""
    from di.reads.common import as_hex

    comps = AS_COMPS[c["cls"]]
    return any((as_hex(c, "pt" + n) % 100) / 100 < 0.3 for n in comps)


AS_COMPS = {
    "motor": ["Stator winding", "Rotor and shaft", "Bearings", "Housing and frame", "Terminal box"],
    "pump": ["Pistons and barrel", "Shaft seal", "Bearings", "Housing", "Ports and fittings"],
    "control": ["Processor module", "I/O modules", "Power supply", "Connectors", "Firmware"],
    "drill": ["Motor", "Gearbox", "Chuck", "Housing", "Battery"],
    "batch": ["Drivers", "Battery packs", "Chucks", "Housings", "Chargers"],
    "it": ["Battery", "Display", "Keyboard", "Storage", "Chassis"],
}


def kpi_tiles(ctx, ks: list[str], sc: dict, rows: list[dict], f: Filters) -> list[dict]:
    a = ctx.actor.account
    m = metrics(rows)
    every = vis_rows(ctx, f.tenant)
    al = sc["all"]

    def st(x: str) -> list[Case]:
        return [c for c in al if c["_st"] == x]

    ap = st("approval")
    open_ = [c for c in al if c["_st"] in ("approval", "reeval")]
    pot, vr = js_sum(cc_net(c) for c in open_), js_sum(c["_var"] for c in al)
    cl = sum(1 for c in ap if c["_left"] < 5)
    gaps = sum(1 for c in al if c["_st"] in ("need", "await_insp"))
    yp = js_sum(r["p50"] for r in m["rc"])

    def s_cnt():
        return series(lambda r: 1, every)  # noqa: ARG005 - every counter takes the row

    def s_pred():
        return series(lambda r: max(0, r["p50"]), every)

    def s_up():
        return series(lambda r: r["actual"] - r["baseline"] if r["status"] == "reconciled" else 0, every)

    def s_act():
        return series(lambda r: r["actual"] if r["status"] == "reconciled" else 0, every)

    def pick(arg):
        return {"kind": "pick", "arg": arg}

    def go(to):
        return {"kind": "go", "to": to}

    def sec(x):
        return {"kind": "section", "sec": x}

    def k(key, cls, icon, label, val, sub, d, sp, act, tip):
        return {
            "key": key,
            "cls": cls,
            "icon": icon,
            "label": label,
            "val": val,
            "sub": sub,
            "delta": d,
            "spark": sp,
            "act": act,
            "tip": tip,
        }

    rest = js_sum(c["_val"] for c in al if c["_st"] in ("need", "await_insp", "noroute"))
    risk_pct = js_round(vr / max(1, pot + rest) * 100) if pot else 0
    ap_net = js_sum(cc_net(c) for c in ap)

    def inbox():
        n = len(inbox_requests(ctx))
        return k(
            "inbox",
            "y" if n else "ok",
            "access",
            "Requests waiting",
            fmt_n(n),
            "tenant access and MCP proposals",
            None,
            None,
            sec("approvals"),
            "Requests in the scopes you can decide. Select to open the Approvals inbox.",
        )

    def gatefail():
        n = sum(1 for c in al if c.get("blocked"))
        return k(
            "gatefail",
            "bad" if n else "ok",
            "flag",
            "Failed gates",
            fmt_n(n),
            "exceptions waiting for evidence",
            None,
            None,
            pick("stage:need"),
            "Cases where an eligibility gate failed or evidence is missing. No route is approvable until it passes.",
        )

    def graded():
        gr = [c for c in al if c.get("grade")]
        ab = sum(1 for c in gr if c["grade"] in ("A", "B"))
        return k(
            "graded",
            "ok",
            "check",
            "Graded A or B",
            f"{js_round(ab / len(gr) * 100) if gr else 0}%",
            f"{ab} of {len(gr)} graded assets",
            None,
            None,
            go("product/received"),
            "Share of inspected assets in the top two condition grades.",
        )

    def parts():
        n = sum(1 for c in al if _parts_backorder(c))
        return k(
            "parts",
            "bad" if n else "ok",
            "pump",
            "Parts on backorder",
            fmt_n(n),
            "assets with a part on backorder",
            None,
            None,
            go("product/received"),
            "Assets with at least one component on backorder.",
        )

    def uplift():
        pct = "+" + js_fixed((m["act"] / m["base"] - 1) * 100, 0) + "%" if m["base"] else "—"
        return k(
            "uplift",
            "y",
            "trend",
            "Uplift vs baseline",
            "+" + kfmt(m["uplift"]),
            f"closed decisions · {pct} vs sell-or-scrap",
            cc_delta(s_up()),
            s_up(),
            go("analytics"),
            "Additional net recovery on reconciled decisions compared with the sell-or-scrap baseline. Same number as Analytics.",
        )

    def ihealth():
        t = hh_totals()
        return k(
            "ihealth",
            "ok" if t["pct"] >= 95 else "bad",
            "integration",
            "Integration health",
            to_fixed(t["pct"], 1) + "%",
            "successful syncs and events · 24 h",
            None,
            None,
            go("integration/map"),
            "Share of syncs and events in the last 24 hours that succeeded.",
        )

    def srcattn():
        lst = stale_sources()
        return k(
            "srcattn",
            "bad" if lst else "ok",
            "flag",
            "Sources needing attention",
            fmt_n(len(lst)),
            ", ".join(s["name"] for s in lst) or "all sources fresh",
            None,
            None,
            go("integration/map"),
            "Sources that are stale or not connected.",
        )

    def wffail():
        n = sum(1 for w in workflows() if wf_stat(w) == "failing")
        return k(
            "wffail",
            "bad" if n else "ok",
            "play",
            "Failing workflows",
            fmt_n(n),
            "published, last run failed",
            None,
            None,
            go("integration/studio"),
            "Published workflows whose last run failed.",
        )

    def conf():
        n = sum(1 for c in STARTING_CONFLICTS if c["status"] == "open")
        return k(
            "conf",
            "bad" if n else "ok",
            "integration",
            "Open conflicts",
            fmt_n(n),
            "systems that disagree",
            None,
            None,
            go("integration/conflicts"),
            "Records where two systems disagree. Dependent routes stay held until resolved.",
        )

    def aome():
        n = len(aome_items(ctx, False, f.tenant))
        return k(
            "aome",
            "y" if n else "ok",
            "flag",
            "Actions on me",
            fmt_n(n),
            "items whose next step is yours",
            None,
            None,
            sec("aome"),
            "Everything waiting on you: notifications, requests, cases to submit, approve, inspect or confirm. "
            "Select to open Actions on me.",
        )

    def handed():
        n = sum(1 for c in al if c["stage"] in ("approved", "executing"))
        return k(
            "handed",
            "",
            "integration",
            "Handed off",
            fmt_n(n),
            "with enterprise systems · awaiting outcome",
            None,
            None,
            sec("handed"),
            "Approved instructions sent to ERP, EAM or WMS that have not reported an outcome yet.",
        )

    def capwh():
        w = a.warehouse or "Warehouse 1"
        cap = CC_CAP[w]
        u = sc["util"].get(w) or 0
        p = u / cap
        return k(
            "capwh",
            "bad" if p >= 0.85 else "ok",
            "flag",
            "Capacity used",
            f"{js_round(p * 100)}%",
            f"{u} of {cap} planned slots",
            None,
            None,
            sec("signals"),
            "Utilisation of your warehouse against its configured planning capacity.",
        )

    def props():
        lst = [r for r in requests(ctx.session) if r.get("byId") == a.id and r["kind"] == "mcp"]

        def n(s):
            return sum(1 for r in lst if r["status"] == s)

        return k(
            "props",
            "y",
            "mcp",
            "My MCP proposals",
            fmt_n(n("pending")) + " pending",
            f"{n('approved')} approved · {n('declined')} declined",
            None,
            None,
            go("mcp/proposals"),
            "Servers you proposed and their review status.",
        )

    D = {
        "scope": lambda: k(
            "scope",
            "",
            "batch",
            "Assets in scope",
            fmt_n(len(al)),
            _units(al) + " units · vs prior month",
            cc_delta(s_cnt()),
            s_cnt(),
            {"kind": "clear"},
            "Returned assets matching the filters. The change compares closed decisions this month with last month.",
        ),
        "awaiting": lambda: k(
            "awaiting",
            "y",
            "check",
            "Awaiting approval",
            fmt_n(len(ap)),
            kfmt(ap_net) + " predicted net · with an Approver",
            None,
            None,
            pick("stage:approval"),
            "Decisions you prepared that now wait for an Approver. Select to filter the table.",
        ),
        "awaitVal": lambda: k(
            "awaitVal",
            "ok",
            "check",
            "Awaiting approval",
            kfmt(ap_net),
            f"{len(ap)} decisions · predicted net",
            None,
            None,
            pick("stage:approval"),
            "Predicted net recovery of decisions waiting for your approval. Select to filter the table.",
        ),
        "gaps": lambda: k(
            "gaps",
            "bad",
            "audit",
            "Evidence gaps",
            fmt_n(gaps),
            "assets cannot be routed yet",
            None,
            None,
            pick("stage:need"),
            "Assets waiting for inspection or missing evidence. They cannot get a recommendation until it arrives.",
        ),
        "closing": lambda: k(
            "closing",
            "bad" if cl else "ok",
            "flag",
            "Closing within 5 days",
            fmt_n(cl),
            "decision windows · act first",
            None,
            None,
            pick("due:d5"),
            "Decisions awaiting approval whose window closes in under 5 days.",
        ),
        "potential": lambda: k(
            "potential",
            "ok",
            "analytics",
            "Potential recovery value",
            kfmt(pot),
            f"{len(open_)} decisions open · predicted net",
            cc_delta(s_pred()),
            s_pred(),
            pick("stage:approval"),
            "Predicted net recovery of decisions that still need a person: awaiting approval plus re-evaluation. "
            "Select to filter the table.",
        ),
        "risk": lambda: k(
            "risk",
            "bad",
            "flag",
            "Value at risk",
            kfmt(vr),
            f"{risk_pct}% of open value if no action",
            None,
            None,
            sec("kpis"),
            "Predicted recovery value on open returns that would be lost over the next 30 days if nobody acts: missing "
            "evidence, condition getting worse, delayed approval, falling market prices or capacity limits. Select to "
            "see the breakdown by reason.",
        ),
        "inbox": inbox,
        "inspq": lambda: k(
            "inspq",
            "",
            "audit",
            "Inspection queue",
            fmt_n(len(st("await_insp"))),
            "assets awaiting inspection",
            None,
            None,
            pick("stage:await_insp"),
            "Returned assets with no inspection yet. Select to filter the table.",
        ),
        "gatefail": gatefail,
        "graded": graded,
        "parts": parts,
        "net": lambda: k(
            "net",
            "ok",
            "analytics",
            "Net recovery",
            kfmt(m["act"]),
            f"{len(m['rc'])} reconciled decisions · {f.months} months",
            cc_delta(s_act()),
            s_act(),
            go("analytics/waterfall"),
            "Actual net recovery on reconciled decisions in the period. Same as Analytics when filters match.",
        ),
        "uplift": uplift,
        "yield": lambda: k(
            "yield",
            "",
            "check",
            "Recovery yield",
            f"{js_round(m['act'] / yp * 100) if yp else 0}%",
            "actual ÷ predicted on reconciled",
            None,
            None,
            go("analytics/predicted"),
            "Actual net recovery divided by the predicted P50 on the same reconciled decisions.",
        ),
        "avoided": lambda: k(
            "avoided",
            "ok",
            "export",
            "Avoided spend",
            kfmt(m["avoided"]),
            "ERP-confirmed purchases not made",
            None,
            None,
            go("analytics"),
            "Purchases avoided by redeploying assets or using recovered parts, confirmed in ERP.",
        ),
        "co2m": lambda: k(
            "co2m",
            "ok",
            "leaf",
            "CO₂e avoided",
            to_fixed(js_sum(r["co2e"] for r in m["rc"]) / 1000, 0) + " t",
            "estimated on reconciled decisions",
            None,
            None,
            go("analytics/sustain"),
            "Estimated embodied carbon avoided on reconciled decisions. Measured values are on Analytics.",
        ),
        "ihealth": ihealth,
        "srcattn": srcattn,
        "wffail": wffail,
        "conf": conf,
        "aome": aome,
        "whcases": lambda: k(
            "whcases",
            "",
            "batch",
            "Assets at " + (a.warehouse or "your site"),
            fmt_n(len(al)),
            _units(al) + " units · current location",
            None,
            None,
            go("product/received"),
            "Returned assets whose current location is your warehouse.",
        ),
        "handed": handed,
        "capwh": capwh,
        "props": props,
    }
    return [D[x]() for x in ks]


def insights(sc: dict) -> list[list[str]]:
    """The demo's ccInsightsHTML items: [filter, text], at most four."""
    al = sc["all"]
    o: list[list[str]] = []
    cl = sum(1 for c in al if c["_st"] == "approval" and c["_left"] < 5)
    ap = sum(1 for c in al if c["_st"] == "approval")
    if ap:
        o.append(["stage:approval", f"{ap} decisions await approval" + (f", {cl} close within 5 days" if cl else "")])
    by: dict[str, float] = {}
    for c in al:
        for k, v in c["_risk"].items():
            by[k] = by.get(k, 0) + v
    tot = js_sum(by.values())
    if by:
        top = sorted(by.items(), key=lambda e: -e[1])[0]
        o.append([f"reason:{top[0]}", f"{kfmt(tot)} at risk, mostly {top[0].lower()} ({js_round(top[1] / tot * 100)}%)"])
    if (SOURCES.get("mkt") or {}).get("status") == "stale":
        o.append(["route:resale", "Market feed is stale, so resale prices carry a warning"])
    ne = sum(1 for c in al if c["_st"] in ("need", "await_insp"))
    if ne:
        o.append(["stage:need", f"{ne} assets cannot be routed until evidence arrives"])
    return o[:4]


def cc_metrics(rows: list[dict]) -> dict:
    m = metrics(rows)
    return {
        "act": m["act"],
        "base": m["base"],
        "uplift": m["uplift"],
        "avoided": m["avoided"],
        "days": m["days"] or None,
        "rcCount": len(m["rc"]),
        "p50": js_sum(r["p50"] for r in m["rc"]),
        "co2e": js_sum(r["co2e"] for r in m["rc"]),
    }


def health_strip() -> dict:
    st = {"live": 0, "stale": 0, "manual": 0, "unavailable": 0}
    for s in SOURCES.values():
        st[s["status"]] += 1
    return {"pct": hh_totals()["pct"], **st}


# ---------------------------------------------------------------- charts
VAR_COL = {
    "Delayed approval": "var(--bad)",
    "Condition deterioration": "#D9651E",
    "Missing evidence": "#D4A800",
    "Market price decline": "var(--chart4)",
    "Capacity constraints": "var(--chart5)",
}
VAR_TIP = {
    "Delayed approval": "Decisions whose window is closing. The offer or demand can lapse.",
    "Condition deterioration": "Monthly value decay of the asset class while it waits.",
    "Missing evidence": "Value of assets that cannot be routed yet. Estimated from similar closed decisions.",
    "Market price decline": "Resale recommendations priced from stale market comparables.",
    "Capacity constraints": "Repair-centre load is above 75%, so prep may slip.",
}


def var_reasons(sc: dict) -> list[dict]:
    by = dict.fromkeys(REASONS, 0)
    for c in sc["all"]:
        for k, v in c["_risk"].items():
            by[k] = by[k] + v
    tot = js_sum(by.values()) or 1
    mx = max(1, *by.values())
    return [
        {
            "reason": r,
            "v": by[r],
            "pct": js_round(by[r] / tot * 100),
            "w": by[r] / mx * 100,
            "color": VAR_COL[r],
            "tip": VAR_TIP[r],
        }
        for r in REASONS
    ]


def combo(rows: list[dict], months: int) -> list[dict]:
    rc = [r for r in rows if r["status"] == "reconciled"]
    out = []
    for mi in range(12 - months, 12):
        p = js_sum(r["p50"] for r in rc if r["mi"] == mi)
        a = js_sum(r["actual"] for r in rc if r["mi"] == mi)
        out.append({"mi": mi, "p": p, "a": a, "y": a / p * 100 if p else 0})
    return out


def rb_path(ctx, p: str) -> bool:
    """The demo's rbPath for the routes a signal can open (a page and an optional section)."""
    h = p.split("/")
    return can_page(ctx, h[0]) and (len(h) < 2 or not policy.sections().get(h[0]) or can_page(ctx, h[0], h[1]))


def signals(ctx, sc: dict, f: Filters) -> list[dict]:
    """The demo's ccSignals, without the routes the account cannot open."""
    a, v = [], sc["all"]
    cl = [c for c in v if c["_st"] == "approval" and c["_left"] < 5]
    if cl:
        a.append(
            {
                "t": "Decision windows closing",
                "n": f"{len(cl)} assets",
                "note": "Approval needed within 5 days",
                "lvl": "bad",
                "act": "stage:approval",
                "ic": "flag",
            }
        )
    ev = [c for c in v if c["_st"] in ("need", "await_insp")]
    if ev:
        g: dict[str, int] = {}
        for c in ev:
            k = c["blocked"]["action"] if c.get("blocked") else "Request inspection"
            g[k] = g.get(k, 0) + 1
        top = sorted(g.items(), key=lambda e: -e[1])[0]
        a.append(
            {
                "t": "Evidence gaps",
                "n": f"{len(ev)} assets",
                "note": f"Most common: {top[0].lower()} ({top[1]})",
                "lvl": "warn",
                "act": "stage:need",
                "ic": "audit",
            }
        )
    mk = SOURCES.get("mkt")
    if mk and mk["status"] == "stale":
        n = sum(1 for c in v if c.get("recommendation") and c["recommendation"]["id"] == "resale")
        a.append(
            {
                "t": "Stale market feed",
                "n": f"{n} assets",
                "note": "Resale prices use last fresh comparables",
                "lvl": "bad",
                "act": "route:resale",
                "ic": "trend",
            }
        )
    rv = [c for c in v if c["_st"] == "reeval"]
    if rv:
        a.append(
            {
                "t": "Re-evaluation needed",
                "n": f"{len(rv)} assets",
                "note": rv[0].get("reevalReason") or "Conditions changed",
                "lvl": "warn",
                "act": "stage:reeval",
                "ic": "refresh",
            }
        )
    rr = vis_rows(ctx, f.tenant)
    h: dict[str, int] = {}
    pv: dict[str, int] = {}
    for r in rr:
        if r.get("ero", 0) > 0:
            k = f"{r['equip']} · {r['comp']}"
            if r["mi"] >= 9:
                h[k] = h.get(k, 0) + 1
            elif 6 <= r["mi"] < 9:
                pv[k] = pv.get(k, 0) + 1
    if h:
        top = sorted(h.items(), key=lambda e: -e[1])[0]
        p = pv.get(top[0], 0)
        tail = f" · {'▲' if top[1] >= p else '▼'} {abs(js_round((top[1] / p - 1) * 100))}% vs prior 3 months" if p else ""
        a.append(
            {
                "t": "Parts demand hotspot",
                "n": f"{top[1]} cases",
                "note": top[0] + tail,
                "lvl": "warn",
                "act": "go:analytics",
                "ic": "pump",
            }
        )
    from di.screens.home import ws_events

    late = sum(1 for e in ws_events(ctx) if re.search(r"late|out of order", e.get("ack") or ""))
    if late:
        a.append(
            {
                "t": "Late warehouse events",
                "n": f"{late} events",
                "note": "Reordered automatically; none lost",
                "lvl": "ok",
                "act": "go:integration",
                "ic": "integration",
            }
        )
    return [x for x in a[:5] if not x["act"].startswith("go:") or rb_path(ctx, x["act"][3:])]


def capacity(sc: dict) -> list[dict]:
    out = []
    for k, cap in CC_CAP.items():
        u = sc["util"].get(k) or 0
        p = u / cap
        out.append(
            {
                "k": k,
                "label": CAP_LBL.get(k, k),
                "u": u,
                "cap": cap,
                "p": p,
                "color": "var(--bad)" if p >= 0.9 else "#D4A800" if p >= 0.75 else "var(--ok)",
                "msg": "Over limit risk" if p >= 0.9 else "Tight" if p >= 0.75 else "Within limit",
            }
        )
    return out


def charts(ctx, f: Filters) -> dict:
    sc = cc_scope(ctx, f)
    al = sc["all"]
    routes = []
    for r in ROUTES:
        a = [c for c in al if c.get("recommendation") and c["recommendation"]["id"] == r["id"]]
        v = sum(c["qty"] for c in a)
        if v > 0:
            routes.append({"id": r["id"], "label": r["short"], "v": v, "net": js_sum(cc_net(c) for c in a), "color": r["color"]})
    return {
        "stages": [
            {"k": "stage:" + k, "label": label, "v": sum(1 for x in al if x["_st"] == k), "color": col}
            for k, label, col in CC_STAGES
        ],
        "due": [
            {"k": "due:" + k, "label": label, "v": sum(1 for x in sc["act"] if x["_due"] == k), "color": col}
            for k, label, col in CC_DUE
        ],
        "routes": routes,
        "var": var_reasons(sc),
        "combo": combo(cc_rows(ctx, f), f.months),
        "signals": signals(ctx, sc, f),
        "capacity": capacity(sc),
    }


# ---------------------------------------------------------------- the ranked table (actions to be prioritised)
def _cc_rec(r: dict | None) -> dict | None:
    if not r:
        return None
    o = {"id": r["id"], "net": r["net"], "p10": r["p10"], "p90": r["p90"], "plan": r["plan"]}
    if r.get("demandStatus") is not None:
        o["demandStatus"] = r["demandStatus"]
    return o


def cc_case(c: Case) -> dict:
    """The Command Center's case as the pages read it (the facade's CcCase)."""
    b = c.get("blocked")
    o = {
        "id": c["id"],
        "assetId": c["assetId"],
        "product": c["product"],
        "qty": c["qty"],
        "owner": c["owner"],
        "location": c["location"],
        "cls": c["cls"],
        "stage": c["stage"],
        "assessment": c.get("assessment"),
        "recommendation": _cc_rec(c.get("recommendation")),
        "chosen": _cc_rec(c.get("chosen")),
        "blocked": {"action": b["action"], "gateName": b["gateName"], "owner": b["owner"]} if b else None,
        "submitted": {"by": c["submitted"]["by"]} if c.get("submitted") else None,
        "_st": c["_st"],
        "_left": c["_left"],
        "_risk": c["_risk"],
        "_var": c["_var"],
        "_val": c["_val"],
        "_due": c["_due"],
        "_score": c["_score"],
    }
    for k in ("grade", "timing", "reevalReason", "_pri"):  # present in the demo's case only when set (null included)
        if k in c:
            o[k] = c[k]
    return o


def opp_rows(sc: dict, f: Filters) -> list[Case]:
    q = f.q.strip().lower()
    lst = sorted(sc["all"], key=lambda c: -c["_score"]) if f.stage in ("exec", "approved") else sc["act"]
    return [
        c
        for c in lst
        if (not f.stage or c["_st"] == f.stage)
        and (not f.due or c["_due"] == f.due)
        and (not f.reason or c["_risk"].get(f.reason, 0) > 0)
        and (not q or q in f"{c['id']} {c['assetId']} {c['product']} {c['owner']}".lower())
    ]


def opp_row(c: Case, sc: dict) -> dict:
    r, b, st = c.get("recommendation"), c.get("blocked"), c["_st"]
    if st == "approval":
        trigger = "Recommendation awaiting approval"
    elif st == "reeval":
        trigger = c.get("reevalReason") or "Conditions changed"
    elif st == "need":
        trigger = "Evidence gap: " + (b["gateName"] if b else "condition")
    else:
        trigger = {"await_insp": "Awaiting inspection", "noroute": "No route passed the gates"}.get(st, "In motion")
    action = (r["plan"] or ws.route_name(r["id"])) if r else b["action"] if b else "Request inspection"
    if b:
        cons = b["owner"] + " input needed"
    elif r and r.get("demandStatus") == "forecast":
        cons = "Forecast demand only"
    elif c["location"] == "Repair centre" and sc["util"]["Repair centre"] / CC_CAP["Repair centre"] >= 0.75:
        cons = "Repair capacity"
    else:
        cons = "None"
    btn = (
        "Review"
        if st == "approval"
        else "Re-evaluate"
        if st == "reeval"
        else "Track"
        if st in ("exec", "approved")
        else "Investigate"
    )
    conf = max(30, min(97, js_round((1 - (r["p90"] - r["p10"]) / (2 * max(abs(r["net"]), 1))) * 100))) if r else None
    return {
        "trigger": trigger,
        "action": action,
        "cons": cons,
        "btn": btn,
        "conf": conf,
        "deadline": fmt_d(add_days(AS_OF, c["_left"])),
        "left": c["_left"],
    }


# ---------------------------------------------------------------- exceptions (the demo's ccExList and ccExRows)
def _ex_list(ctx, sc: dict, f: Filters) -> list[dict]:
    """The demo's ccExList, with each exception's count and trend line, over the filtered scope."""
    out: list[dict] = []
    a = ctx.actor.account
    wh = a.warehouse
    by: dict[str, dict] = {}
    for c in sc["all"]:
        for k, v in c["_risk"].items():
            if v > 0:
                o = by.setdefault(k, {"v": 0, "ids": []})
                o["v"] = o["v"] + v
                o["ids"].append(c["id"])
    for k, o in by.items():
        out.append(
            {
                "id": "var:" + k,
                "type": ws.EX_TYPE.get(k, "value"),
                "loc": "Repair centre" if k == "Capacity constraints" else None,
                "title": "Value at risk: " + k.lower(),
                "value": js_round(o["v"]),
                "count": len(o["ids"]),
                "ids": o["ids"],
                "trend": "next 30 days if no action",
                "sev": "High" if o["v"] > 20000 else "Medium" if o["v"] > 5000 else "Low",
                "urg": 1 if k == "Delayed approval" else 0.8,
            }
        )
    for loc in ("Repair centre", "Warehouse 1", "Warehouse 2"):
        if wh and loc != wh:
            continue
        p = (sc["util"].get(loc) or 0) / CC_CAP[loc]
        if p >= 0.85:
            here = [c for c in sc["all"] if c["location"] == loc]
            out.append(
                {
                    "id": "cap:" + loc,
                    "type": "bottleneck",
                    "loc": loc,
                    "title": "Warehouse bottleneck: " + loc,
                    "value": js_round(js_sum(c.get("_val") or 0 for c in here)),
                    "count": len(here),
                    "ids": [c["id"] for c in here],
                    "trend": f"{js_round(p * 100)}% of planned capacity",
                    "sev": "High" if p >= 1 else "Medium",
                    "urg": p,
                }
            )
    if not wh:
        rows = vis_rows(ctx, f.tenant)
        for name, fn in (
            ("net recovery", lambda r: r["actual"] if r["status"] == "reconciled" else 0),
            ("uplift vs baseline", lambda r: r["actual"] - r["baseline"] if r["status"] == "reconciled" else 0),
            ("closed decisions", lambda r: 1),  # noqa: ARG005 - every counter takes the row
        ):
            s = series(fn, rows)
            last, prev = s[10], s[9]
            if prev > 0 and last / prev - 1 < -0.05:
                out.append(
                    {
                        "id": "kpi:" + name,
                        "type": "value",
                        "loc": None,
                        "title": "Declining metric: " + name,
                        "value": js_round(max(0, prev - last)),
                        "count": 0,
                        "ids": [],
                        "trend": f"▼ {abs(js_round((last / prev - 1) * 100))}% last full month vs the month before",
                        "sev": "High" if last / prev - 1 < -0.15 else "Medium",
                        "urg": 0.6,
                        "go": "analytics",
                    }
                )
    det = [c for c in sc["all"] if ws._prev_grade(c)]
    if det:
        out.append(
            {
                "id": "cond",
                "type": "evidence",
                "loc": None,
                "title": "Deteriorating condition",
                "value": js_round(js_sum(c.get("_val") or 0 for c in det)),
                "count": len(det),
                "ids": [c["id"] for c in det],
                "trend": f"{len(det)} graded lower than at the last inspection",
                "sev": "Medium" if len(det) > 6 else "Low",
                "urg": 0.5,
            }
        )
    for x in out:
        x["score"] = x["value"] * x["urg"] * ws.SEV_MULT[x["sev"]]
    return sorted(out, key=lambda x: -x["score"])


def ex_rows(ctx, sc: dict, f: Filters) -> list[dict]:
    """The demo's ccExRows as the facade's exRows: each exception split by warehouse, its items highest value first, the
    last notification sent about it and the account it goes to by default (exOwner)."""
    rows: list[dict] = []
    by_id = {c["id"]: c for c in sc["all"]}
    for x in _ex_list(ctx, sc, f):
        if not x["ids"]:
            rows.append({**x, "base": x["id"], "wh": "Portfolio", "items": []})
            continue
        k = x["id"][4:] if x["id"].startswith("var:") else None
        g: dict[str, list[dict]] = {}
        for cid in x["ids"]:
            c = by_id.get(cid)
            if c is None:
                continue
            w = x["loc"] if x["id"].startswith("cap:") else c["location"]
            g.setdefault(w, []).append({"c": c, "v": c["_risk"].get(k, 0) if k else (c.get("_val") or 0)})
        ws_ = list(g)
        raw = [js_sum(i["v"] for i in g[w]) for w in ws_]
        tot = js_sum(raw)
        vals = [js_round(x["value"] * v / tot) if tot else 0 for v in raw]
        if vals:
            vals[raw.index(max(raw))] += x["value"] - js_sum(vals)
        for w, val in zip(ws_, vals, strict=True):
            items = sorted(g[w], key=lambda i: -i["v"])
            rows.append(
                {
                    **x,
                    "id": x["id"] + "@" + w,
                    "base": x["id"],
                    "wh": w,
                    "loc": w,
                    "title": x["title"].replace(": " + w, "", 1),
                    "value": val,
                    "count": len(items),
                    "ids": [i["c"]["id"] for i in items],
                    "items": items,
                }
            )
    tot_by: dict[str, float] = {}
    for r in rows:
        tot_by[r["wh"]] = tot_by.get(r["wh"], 0) + r["value"]

    def cmp(a: dict, b: dict) -> float:
        if a["wh"] == b["wh"]:
            return b["value"] - a["value"]
        gk = lambda w: -1 if w == "Portfolio" else tot_by[w]  # noqa: E731
        order = lambda w: ws.EX_WH_ORDER.index(w) if w in ws.EX_WH_ORDER else -1  # noqa: E731
        return (gk(b["wh"]) - gk(a["wh"])) or (order(a["wh"]) - order(b["wh"]))

    rows.sort(key=cmp_to_key(cmp))
    ns = notes(ctx.session)
    out = []
    for x in rows:
        note = [n for n in ns if n.get("exId") in (x["id"], x["base"])]
        o = {
            "id": x["id"],
            "base": x["base"],
            "wh": x["wh"],
            "title": x["title"],
            "value": x["value"],
            "count": x["count"],
            "sev": x["sev"],
            "trend": x["trend"],
            "items": [{"id": i["c"]["id"], "model": as_model(i["c"]), "v": i["v"]} for i in x["items"]],
            "note": note[-1] if note else None,
            "owner": ws.ex_owner(x),
        }
        if x.get("go"):
            o["go"] = x["go"]
        out.append(o)
    return out


# ---------------------------------------------------------------- Actions on me, handed off, outcomes
def op_scope_info(ctx, widen: bool) -> dict:
    """The demo's opScope: Planners and Engineers start at their home site and may widen to every location; a Warehouse
    Manager is locked to theirs."""
    a = ctx.actor.account
    home = a.warehouse or a.site or ""
    scope = a.warehouse if a.warehouse else "" if widen else home
    return {"home": home, "scope": scope, "locked": bool(a.warehouse)}


def op_scoped(ctx, widen: bool, tenant: str = "All") -> list[Case]:
    s = op_scope_info(ctx, widen)["scope"]
    return [c for c in vis(ctx, tenant) if not s or c["location"] == s]


def aome_items(ctx, widen: bool = False, tenant: str = "All") -> list[dict]:
    """The demo's aomeItems with the tenant menu and the widened scope (di.reads.workspace.aome_items answers for the
    default scope and every tenant; this is the same port with those two settings)."""
    a = ctx.actor.account
    role, out = a.role, []
    cs = op_scoped(ctx, widen, tenant)

    def st5(cid: str) -> str:
        return f"product/{cid}?step=5"

    for n in notes(ctx.session):
        if n["to"] == a.id and n["status"] == "open":
            out.append(
                {
                    "t": n["title"],
                    "d": f"From {n['from']} · {n['sev']} · {n['msg']}",
                    "btn": "Acknowledge",
                    "act": "notifyAck",
                    "arg": n["id"],
                }
            )
    perms = policy.policy(a).get("perms") or []
    if role == "Admin" or any(p.startswith("approve.") for p in perms):
        for r in inbox_requests(ctx):
            out.append(
                {
                    "t": f"{REQ_KIND[r['kind']]} {r['id']}",
                    "d": "Requested by " + r["by"],
                    "btn": "Open inbox",
                    "go": "command/approvals",
                }
            )
    if role == "Engineer":
        for c in cs:
            if c.get("blocked") and c.get("requested"):
                b = c["blocked"]
                out.append(
                    {
                        "t": c["id"] + " · record the assessment result",
                        "d": f"{b['action']} · {b['gateName']} gate",
                        "btn": "Record result",
                        "go": st5(c["id"]),
                    }
                )
        for c in [c for c in cs if c.get("assessment") == "Pending"][:6]:
            out.append(
                {
                    "t": c["id"] + " · inspection due",
                    "d": f"{c['product']} at {c['location']}",
                    "btn": "Open asset",
                    "go": "product/asset/" + c["id"],
                }
            )
    if role == "Planner":
        for c in cs:
            if c["stage"] == "reeval":
                out.append(
                    {
                        "t": c["id"] + " · re-evaluate",
                        "d": c.get("reevalReason") or "Review triggered",
                        "btn": "Re-evaluate",
                        "go": st5(c["id"]),
                    }
                )
        ready = [c for c in cs if c["stage"] == "awaiting_approval" and not c.get("submitted") and c.get("recommendation")]
        for c in ready[:6]:
            r = c["recommendation"]
            out.append(
                {
                    "t": c["id"] + " · submit for review",
                    "d": f"{r['plan']} · {money(r['net'])}",
                    "btn": "Submit",
                    "go": st5(c["id"]),
                }
            )
    every = vis(ctx, tenant) if role in ("Approver", "Finance") else []
    if role == "Approver":
        for c in every:
            if c["stage"] == "awaiting_approval" and c.get("submitted"):
                d = f"Submitted by {c['submitted']['by']} · {money(c['recommendation']['net'])}"
                out.append({"t": c["id"] + " · approve or decline", "d": d, "btn": "Decide", "go": st5(c["id"])})
    if role == "Finance":
        for c in every:
            if c["stage"] == "closed" and not c.get("outcome"):
                out.append(
                    {
                        "t": c["id"] + " · confirm the outcome",
                        "d": "Reported by the enterprise systems",
                        "btn": "Confirm",
                        "go": st5(c["id"]),
                    }
                )
    if role == "Developer":
        for s in SOURCES.values():
            if s["status"] in ("stale", "unavailable"):
                out.append(
                    {"t": f"{s['name']} · {s['status']}", "d": s["vendor"], "btn": "Open Source map", "go": "integration/map"}
                )
    if role == "Warehouse Manager":
        for c in cs:
            s = active_step(c)
            if s and s["sys"].startswith("WMS"):
                out.append(
                    {
                        "t": f"{c['id']} · {s['label'].lower()}",
                        "d": "WMS acknowledgement pending · " + c["product"],
                        "btn": "Check",
                        "go": st5(c["id"]),
                    }
                )
        for e in exp_vis(ctx):
            if tenant == "All" or e["owner"] == tenant:
                out.append(
                    {
                        "t": f"{e['contract']} · inbound {e['window']}",
                        "d": f"{e['product']} · {e['customer']} · {e['prob']}% likely to return",
                        "btn": "Plan receiving",
                        "go": "product/expected",
                    }
                )
    if role in ("Approver", "Admin"):
        for c in cs:
            s = active_step(c)
            k = ex_clock(c, s) if s else None
            if k and k["level"] and (role == "Approver" or k["level"] == 2):
                at = ex_ts(k["due2"] if k["level"] == 2 else k["due"])
                out.append(
                    {
                        "t": f"{c['id']} · escalated: {s['label'].lower()}",
                        "d": f"{ex_app(s)} passed its {k['lim']} limit at {at} · owner {step_owner(c, s)}",
                        "btn": "Open handoff",
                        "go": st5(c["id"]),
                    }
                )
    return out


def handed_rows(ctx, widen: bool, tenant: str = "All") -> list[dict]:
    out = []
    for c in op_scoped(ctx, widen, tenant):
        if c["stage"] not in ("approved", "executing"):
            continue
        x = c.get("exec")
        st = x["steps"] if x else steps_for({"id": (c.get("chosen") or c.get("recommendation") or {"id": "resale"})["id"]}, -1)
        a = next((s for s in st if s["state"] == "active"), st[0])
        acked = [s for s in st if s.get("ack")]
        age = max(0, (AS_OF - ms(x["approvedAt"])) / DAY_MS) if x else 0
        out.append(
            {
                "id": c["id"],
                "label": a["label"],
                "sys": a["sys"],
                "ref": acked[-1]["ack"]["ref"] if acked else None,
                "age": age,
                "over": age > 2,
            }
        )
    return sorted(out, key=lambda r: -r["age"])


def awaiting_approval(ctx, widen: bool, tenant: str = "All") -> dict:
    ap = [c for c in op_scoped(ctx, widen, tenant) if c["stage"] == "awaiting_approval"]
    return {
        "decider": "Approver" if decisions_delegated(ctx) else "Admin",
        "rows": [
            {
                "id": c["id"],
                "location": c["location"],
                "plan": c["recommendation"]["plan"] if c.get("recommendation") else "—",
                "submitted": bool(c.get("submitted")),
            }
            for c in ap
        ],
    }


def outcomes(ctx, tenant: str = "All") -> dict:
    v = vis(ctx, tenant)
    rows = []
    for c in v:
        if c["stage"] == "closed" and not c.get("outcome"):
            r = c.get("chosen") or c.get("recommendation")
            rows.append(
                {
                    "id": c["id"],
                    "product": c["product"],
                    "assetId": c["assetId"],
                    "plan": r["plan"] if r else "—",
                    "net": r["net"] if r else None,
                }
            )
    return {"rows": rows, "done": sum(1 for c in v if c.get("outcome"))}


# ---------------------------------------------------------------- the Approvals inbox
def af_risks(c: Case, rt: dict, ev: dict) -> list[dict]:
    """The demo's afRisks: what to check before approving."""
    r = c.get("recommendation")
    if not r:
        return [
            {
                "level": "bad",
                "text": "No eligible route",
                "detail": c["blocked"]["reason"] if c.get("blocked") else "Every route failed a gate.",
            }
        ]
    items = []
    gw = [n for n in r.get("gateNotes") or [] if re.search(r"review|partial|warning|conditional", n, re.I)]
    items.append(
        {"level": "warn", "text": "Gate notes to read", "detail": "; ".join(gw)}
        if gw
        else {"level": "ok", "text": "All six gates passed", "detail": "Gate engine (rules)"}
    )
    st = [e for e in ev.get("items") or [] if e["state"] in ("stale", "partial")]
    items.append(
        {"level": "warn", "text": "Stale or partial evidence", "detail": "; ".join(e["label"] for e in st)}
        if st
        else {"level": "ok", "text": "Evidence current", "detail": f"{len(ev.get('items') or [])} items"}
    )
    mk = SOURCES.get("mkt")
    if mk and mk["status"] == "stale" and r["id"] in ("resale", "extparts"):
        items.append({"level": "warn", "text": "Market feed is stale", "detail": "Resale price uses the last fresh comparables"})
    items.append(
        {"level": "warn", "text": "Demand is a forecast", "detail": "A non-realisation allowance is included"}
        if r.get("demandStatus") != "confirmed"
        else {"level": "ok", "text": "Demand confirmed", "detail": r.get("demandLabel")}
    )
    cf = ti_conf(c, r)
    items.append(
        {"level": "bad", "text": "Low confidence", "detail": "Compare routes before approving"}
        if cf == "Low"
        else {
            "level": "warn" if cf == "Medium" else "ok",
            "text": cf + " confidence",
            "detail": f"P10–P90 {money(r['p10'])}–{money(r['p90'])}",
        }
    )
    if rt.get("tie"):
        items.append({"level": "warn", "text": "Near tie", "detail": rt["tie"]["text"]})
    cfl = [x for x in STARTING_CONFLICTS if x["status"] == "open" and x["asset"] == c["assetId"]]
    if cfl:
        items.append(
            {"level": "bad", "text": "Open source conflict", "detail": "; ".join(f"{x['kind']}: {x['impact']}" for x in cfl)}
        )
    return items


def approval_cards(ctx, tenant: str = "All") -> list[dict]:
    """The demo's afApprovalQueue as the facade's approvalCards: submitted decisions by value, then deadline, each with
    what to check before approving."""
    q = []
    for c in vis(ctx, tenant):
        if not (c["stage"] == "awaiting_approval" and c.get("submitted") and c.get("recommendation")):
            continue
        rt = case_reads.case_routes({"case_id": c["id"]}, ctx)
        ev = case_reads.case_evidence({"case_id": c["id"]}, ctx)
        risks = [x for x in af_risks(c, rt, ev) if x["level"] != "ok"]
        t = c.get("timing") or ""
        m = re.search(r"Day (\d+)", t) or re.search(r"(\d+) days", t)
        q.append({"c": c, "net": c["recommendation"]["net"], "days": int(m[1]) if m else 30, "risks": risks})
    q.sort(key=lambda x: (-x["net"], x["days"]))
    return [
        {
            "id": x["c"]["id"],
            "plan": x["c"]["recommendation"]["plan"],
            "net": x["net"],
            "model": as_model(x["c"]),
            "owner": x["c"]["owner"],
            "timing": x["c"].get("timing") or "",
            "submittedBy": x["c"]["submitted"]["by"],
            "risks": [r["text"] for r in x["risks"]],
            "kinds": list(STEP_TPL.get(x["c"]["recommendation"]["id"]) or []),
            "steps": [
                EX_STEP[k]["label"] + " → " + EX_STEP[k]["sys"] for k in STEP_TPL.get(x["c"]["recommendation"]["id"]) or []
            ],
        }
        for x in q
    ]


def inbox(ctx, tenant: str = "All") -> dict:
    a = ctx.actor.account
    lim = limit_for(a, ctx.actor.ctx)
    return {
        "requests": [{**r, "kindLabel": REQ_KIND[r["kind"]], "canDecide": True} for r in inbox_requests(ctx)],
        "scope": [label.lower().replace("mcp", "MCP") for k, label in DELEG if ctx.actor.ctx.delegations.get(k, True)]
        if a.role == "Approver"
        else None,
        "decisions_awaiting": sum(1 for c in vis(ctx, tenant) if c["stage"] == "awaiting_approval"),
        "cards": approval_cards(ctx, tenant),
        "limit": None if lim == float("inf") else lim,
    }


# ---------------------------------------------------------------- integration health (Developer and Admin)
def ack_kind(a: str) -> str:
    """The demo's ackKind."""
    if a == "acknowledged":
        return "ok"
    if re.search(r"conflict|stale|failed", a):
        return "bad"
    return "line" if "sent" in a else "warn"


def health_detail(ctx) -> dict:
    from di.screens.home import ws_events

    t, ex = hh_totals(), sm_exceptions()
    return {
        "ok": t["ok"],
        "warn": t["warn"],
        "bad": t["bad"],
        "run": t["run"],
        "pct": t["pct"],
        "hours": hh(),
        "exceptions": ex[:6],
        "exceptionCount": len(ex),
        "events": [
            {"id": e["id"], "ts": e["ts"], "dest": e["dest"], "type": e["type"], "ack": e["ack"], "kind": ack_kind(e["ack"])}
            for e in ws_events(ctx)[:6]
        ],
    }


# ---------------------------------------------------------------- endpoints
def _layout_or_kpis(p: Principal, mode: str) -> dict:
    return layout(p.account, mode) or {"kpis": []}


@router.get("/layout")
def get_layout(
    mode: str = Query("operational", pattern="^(operational|senior)$"),
    p: Principal = Depends(principal),
    session: Session = Depends(get_session),
) -> dict:
    """The role's Command Center layout, its key figures and the sections the account may open."""
    L = layout(p.account, mode)
    if L is None:
        return {"layout": None, "keys": [], "sections": []}
    return {"layout": L, "keys": keys(L), "sections": sections(call_ctx(p, session), L)}


@router.get("/kpis")
def get_kpis(
    mode: str = Query("operational", pattern="^(operational|senior)$"),
    f: Filters = Depends(scope_filters),
    p: Principal = Depends(principal),
    session: Session = Depends(get_session),
) -> dict:
    """Key figures: the layout's tiles, the "needs attention now" line, the totals and the health strip."""
    ctx = call_ctx(p, session)
    sc, rows = cc_scope(ctx, f), cc_rows(ctx, f)
    return {
        "tiles": kpi_tiles(ctx, keys(_layout_or_kpis(p, mode)), sc, rows, f),
        "insights": insights(sc),
        "metrics": cc_metrics(rows),
        "health": health_strip(),
        "counts": {
            "cases": len(vis(ctx, f.tenant)),
            "rows": len(vis_rows(ctx, f.tenant)),
            "sources": len(SOURCES),
            "workflows": len(workflows()),
        },
    }


@router.get("/charts")
def get_charts(
    f: Filters = Depends(scope_filters), p: Principal = Depends(principal), session: Session = Depends(get_session)
) -> dict:
    """The charts and panels: lifecycle stages, due windows, routes, value at risk, value realisation, signals and
    capacity."""
    return charts(call_ctx(p, session), f)


@router.get("/actions")
def get_actions(
    f: Filters = Depends(table_filters), p: Principal = Depends(principal), session: Session = Depends(get_session)
) -> dict:
    """The ranked table of actions to prioritise, with the table's view, due, reason and search filters."""
    ctx = call_ctx(p, session)
    sc = cc_scope(ctx, f)
    rows = [{"case": cc_case(c), **opp_row(c, sc)} for c in opp_rows(sc, f)]
    return {"rows": rows, "total": len(rows)}


@router.get("/exceptions")
def get_exceptions(
    f: Filters = Depends(scope_filters), p: Principal = Depends(principal), session: Session = Depends(get_session)
) -> dict:
    """Exceptions by warehouse, and the decisions awaiting approval (the senior view's read-only queue)."""
    ctx = call_ctx(p, session)
    sc = cc_scope(ctx, f)
    ap = sorted((c for c in sc["all"] if c["_st"] == "approval"), key=lambda c: -cc_net(c))
    return {
        "rows": ex_rows(ctx, sc, f),
        "awaiting": [
            {"id": c["id"], "plan": c["recommendation"]["plan"] if c.get("recommendation") else None, "net": cc_net(c)}
            for c in ap
        ],
    }


@router.get("/aome")
def get_aome(
    all: bool = False, tenant: str = "All", p: Principal = Depends(principal), session: Session = Depends(get_session)
) -> dict:
    """Actions on me, at the home site or (all=true) every location, in the tenant menu's tenant."""
    ctx = call_ctx(p, session)
    return {"items": aome_items(ctx, all, tenant), "scope": op_scope_info(ctx, all)}


@router.get("/handed")
def get_handed(
    all: bool = False, tenant: str = "All", p: Principal = Depends(principal), session: Session = Depends(get_session)
) -> dict:
    """Handed off and awaiting outcome, and waiting for approval, at the home site or (all=true) every location."""
    ctx = call_ctx(p, session)
    return {
        "handed": handed_rows(ctx, all, tenant),
        "awaiting": awaiting_approval(ctx, all, tenant),
        "scope": op_scope_info(ctx, all),
    }


@router.get("/outcomes")
def get_outcomes(tenant: str = "All", p: Principal = Depends(principal), session: Session = Depends(get_session)) -> dict:
    """Outcomes reported by the enterprise systems and waiting for Finance."""
    return outcomes(call_ctx(p, session), tenant)


@router.get("/inbox")
def get_inbox(tenant: str = "All", p: Principal = Depends(principal), session: Session = Depends(get_session)) -> dict:
    """The Approvals inbox: requests the account may decide, its delegated scope and the approval cards."""
    return inbox(call_ctx(p, session), tenant)


@router.get("/health")
def get_health(p: Principal = Depends(principal), session: Session = Depends(get_session)) -> dict:
    """Integration health for the Developer and Admin views."""
    return health_detail(call_ctx(p, session))
