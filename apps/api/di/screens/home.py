"""Home and the utility pages (My Tasks, Alerts, Reports): the read endpoints behind apps/web/src/api/home.ts (B14).

Each endpoint returns what the facade function returns today from the in-browser engine (the demo's afBriefing,
aomeItems, frAlerts, frKpis, frActivity, the facade's middlePanel and figures, FR_REP), scoped to the signed-in account.
Parity: tests/test_screens_home.py against fixtures/golden/screens/home.json (apps/web/scripts/golden/home_command.mjs).

Facade export (home.ts)        | served by
-------------------------------|--------------------------------------------------------------------------------
briefing                       | GET /api/screens/home/briefing                     -> [{text, go, n}]
taskItems, taskGroupOf         | GET /api/screens/home/tasks                        -> [{t, d, btn, act?, arg?, go?, group}]
alerts                         | GET /api/screens/home/alerts                       -> [Alert] (ack: see below)
kpis(role)                     | GET /api/screens/home/kpis                         -> [Kpi] for the signed-in role, delta parsed
activity(win)                  | GET /api/screens/home/activity?win=live|today|week -> [ActivityRow]
middlePanel(role)              | GET /api/screens/home/middle                       -> MiddlePanel for the signed-in role
figures(per)                   | GET /api/screens/home/figures?per=30|90|365        -> [Figure]
reports                        | GET /api/screens/home/reports                      -> [{id, t, ic, h, d}]
reportRows(id, tenant, period) | GET /api/screens/home/reports/{id}?tenant=&period= -> rows, header first
attention                      | frontend-only: composed from /alerts and /tasks (the facade's own rule)
role, canManageWorkflows,      | session and policy (the session area: the account, its role and permissions)
  roleDescription              |
status, taskGroups, alertKinds,| reference (/api/screens/reference: FR_ST, FR_TG, FR_AK, FR_MODES, AF_STARTERS,
  askModes, askStarters,       |   AF_INTENTS, NOWF, RG_*, FR_NOTIF, AF_AUTO_TYPES/AF_LEVELS, NAV and FR_MODH)
  askExamples, noWorkflowsMessage, regionOptions, notifTypes, autonomy, quickActions, modules, allModules
isTechnical, providerLabel,    | frontend-only: view settings and formatting (AF.ui, frLs, S.rg, localStorage,
  translate, greeting, homeUi, |   the presenter flag, the live-updates pause, kfmt, CSV, the as-of label)
  setHomeUi, frPref, setFrPref, watches, unwatch, kfmt, toCsv, asOfLabel, region, setRegion,
  presenterOn, setPresenter, livePaused, setLivePaused, alertAssignee
runTaskAct, acknowledgeAlert,  | actions (POST /api/actions/notify.acknowledge) and view state (S.frAck, S.frAssign,
  assignAlert, logReport*      |   the run-board log) that stay in the frontend until a server store exists
checks, checkOwner, checksRunAt, runChecks | the Data Checks page: GET /api/checks (another area)

Differences from the demo, by design (each documented where it is computed, and excluded only there in the tests):
- alerts: `ack` is always false. The demo keeps acknowledgements of derived alerts in browser memory (S.frAck); the
  frontend overlays its own until a server store exists. A failing workflow's `s` ends with the age of its last run,
  which the demo draws at random (rr) when it seeds its workflows; the server has no workflow runs yet, so `s` is the
  failure note alone.
- activity: the demo's synthetic workflow runs (wfSeedRuns: random times and record counts) and the agent's in-browser
  runs (AF.ui.runs) are not on the server; the rows are the agent-prepared journal entries and the hand-off events.
- reports/audit: the audit extract is the audit area's fetch log (auditEntries); this endpoint answers 404 for it.
- The workflow catalogue (names, statuses, the one failing ingest) is the demo's wfSeed without its random run data.
"""

import math
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import policy
from di.actions.pipeline import CallContext
from di.actions.registry import ACTIONS
from di.auth import Principal, principal
from di.cases import store
from di.db import get_session
from di.engine.jsmath import js_round, js_sum
from di.reads import workspace as ws
from di.reads.common import (
    AS_OF,
    DAY_MS,
    SOURCES,
    WORLD,
    Case,
    active_step,
    ex_app,
    ex_clock,
    fmt_n,
    iso,
    kfmt,
    limit_for,
    ms,
    notes,
    step_owner,
    to_fixed,
)
from di.reads.constants import ROUTES
from di.reads.context import call_ctx, can_page, visible_cases, visible_rows
from di.reads.decisions import metrics
from di.reads.expected import exp_vis
from di.reads.fabric import hh, hh_totals, open_conflicts, sm_exceptions, stale_sources, wf_stat, workflows, ws_events

router = APIRouter(prefix="/api/screens/home", tags=["screens: home"])

MONTHS: list[str] = WORLD["months"]


# ---------------------------------------------------------------- the call context and scope


def ago(ms_: float) -> str:
    """The demo's frAgo."""
    s = max(0, js_round(ms_ / 1000))
    if s < 60:
        return f"{s} sec ago"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 172800:
        return f"{s // 3600} h ago"
    return f"{s // 86400} days ago"


def delta(cur: float | None, prev: float | None, good_up: bool | None) -> dict | None:
    """The demo's frDelta, as the facade parses it: {cls, tip, text}, or None when there is no earlier figure."""
    if prev is None or not math.isfinite(prev) or prev == 0 or cur is None:
        return None
    p = (cur - prev) / abs(prev) * 100
    if not math.isfinite(p):
        return None
    up = p >= 0
    good = "" if good_up is None else "good" if up == good_up else "bad"
    pct = to_fixed(abs(p), 1) if abs(p) < 10 else to_fixed(abs(p), 0)
    return {"cls": good, "tip": "Against the same measure 30 days earlier", "text": f"{'▲' if up else '▼'} {pct}%"}


# ---------------------------------------------------------------- the workflow catalogue (the demo's wfSeed)
WF_FAILED_NOTE = "Validation & enrichment: 3 retries exhausted (connection reset)"


# ---------------------------------------------------------------- integration health (the demo's hhTotals)


# ---------------------------------------------------------------- tasks and alerts
def task_group(i: dict) -> str:
    """The demo's frTaskGroup."""
    t = f"{i['t']} {i['btn']} {i.get('go') or ''}".lower()
    if re.search(r"integration|source map|stale|unavailable", t):
        return "integration"
    if re.search(r"evidence|inspection|record|result|receiving|wms", t):
        return "evidence"
    if re.search(r"confirm|acknowledge|outcome|check", t):
        return "confirm"
    return "decide"


def _cred_days(s: dict) -> int:
    return js_round((s["credAt"] + s["credDays"] * DAY_MS - AS_OF) / DAY_MS)


def alerts(ctx: CallContext) -> list[dict]:
    """The demo's frAlerts: notifications, escalations, failing workflows, stale or unavailable sources, expiring
    credentials and open conflicts, most severe first."""
    a = ctx.actor.account
    out: list[dict] = []
    p_all = bool(policy.policy(a).get("all"))
    for n in notes(ctx.session):
        if n["status"] == "open" and (n["to"] == a.id or p_all):
            out.append(
                {
                    "id": n["id"],
                    "kind": "note",
                    "ic": "bell",
                    "h": "alert",
                    "t": n["title"],
                    "s": f"From {n['from']} · {n['sev']}",
                    "sev": 2 if n["sev"] == "High" else 1,
                    "go": "command/aome",
                    "ack": False,
                    "ref": n["id"],
                }
            )
    if can_page(ctx, "product", "case"):
        for c in visible_cases(ctx):
            s = active_step(c)
            k = ex_clock(c, s) if s else None
            if k and k["level"]:
                out.append(
                    {
                        "id": "esc:" + c["id"],
                        "kind": "esc",
                        "ic": "clock",
                        "h": "alert",
                        "t": f"{c['id']} · escalated: {s['label'].lower()}",
                        "s": f"{ex_app(s)} passed its {k['lim']} limit · owner {step_owner(c, s)}",
                        "sev": k["level"],
                        "go": f"product/{c['id']}?step=5",
                        "ack": False,
                    }
                )
    if can_page(ctx, "integration"):
        if can_page(ctx, "integration", "studio"):
            for w in workflows():
                if wf_stat(w) == "failing":
                    # the demo appends " · <age of the last run>", drawn at random when it seeds its workflows
                    out.append(
                        {
                            "id": "wf:" + w["id"],
                            "kind": "wf",
                            "ic": "workflow",
                            "h": "alert",
                            "t": w["name"] + " is failing",
                            "s": WF_FAILED_NOTE,
                            "sev": 2,
                            "go": "integration/studio/" + w["id"],
                            "ack": False,
                            "wf": w["id"],
                        }
                    )
        for s in stale_sources():
            stale = s["status"] == "stale"
            out.append(
                {
                    "id": "src:" + s["id"],
                    "kind": "src",
                    "ic": "clock" if stale else "unplug",
                    "h": "dec" if stale else "alert",
                    "t": s["name"] + " · " + ("feed is stale" if stale else "not connected"),
                    "s": s["vendor"] + (" · " + s["note"].split(".")[0] if s.get("note") else ""),
                    "sev": 2 if stale else 1,
                    "go": "integration/map",
                    "ack": False,
                    "src": s["id"],
                }
            )
        for s in SOURCES.values():
            if s["status"] == "live" and s.get("credAt") and _cred_days(s) <= 14:
                out.append(
                    {
                        "id": "cred:" + s["id"],
                        "kind": "cred",
                        "ic": "key",
                        "h": "dec",
                        "t": f"{s['name']} · credential expires in {_cred_days(s)} days",
                        "s": f"{s['vendor']} · {s['auth']}",
                        "sev": 1,
                        "go": "integration/map",
                        "ack": False,
                        "src": s["id"],
                    }
                )
        if can_page(ctx, "integration", "conflicts"):
            for c in open_conflicts():
                out.append(
                    {
                        "id": "cf:" + c["id"],
                        "kind": "conf",
                        "ic": "conflict",
                        "h": "dec",
                        "t": f"{c['id']} · {c['kind']} differs",
                        "s": f"{c['a']['src']} and {c['b']['src']} · {c['asset']}",
                        "sev": 1,
                        "go": "integration/conflicts",
                        "ack": False,
                    }
                )
    return sorted(out, key=lambda x: -x["sev"])  # the demo sorts unacknowledged first, then by severity (stable)


# ---------------------------------------------------------------- KPI tiles per role (the demo's frKpis)
def _monthly(rows: list[dict], f) -> list[float]:
    """The demo's frMonthly."""
    o = [0] * len(MONTHS)
    for x in rows:
        if x.get("mi") is not None and x["mi"] < len(o):
            o[x["mi"]] = o[x["mi"]] + (f(x) or 0)
    return o


def _wms_active(c: Case) -> bool:
    s = active_step(c)
    return bool(s and s["sys"].startswith("WMS"))


def kpis(ctx: CallContext) -> list[dict]:
    a = ctx.actor.account
    role, cs = a.role, visible_cases(ctx)
    T: list[dict] = []
    open_ = [c for c in cs if c["stage"] in ("awaiting_approval", "reeval")]
    pot = js_sum(ws.cc_net(c) for c in open_)
    rows = visible_rows(ctx)
    rec = _monthly(rows, lambda x: x["actual"] if x["status"] == "reconciled" else 0)
    r1, r0 = rec[-1], rec[-2]
    need = sum(1 for c in cs if c.get("blocked") or c.get("assessment") in ("Review", "Partial"))
    reev = sum(1 for c in cs if c["stage"] == "reeval")
    insp = sum(1 for c in cs if c.get("assessment") == "Pending")
    pot_t = {
        "ic": "dollar",
        "h": "money",
        "k": "potential",
        "v": kfmt(pot),
        "n": pot,
        "l": "Potential recovery",
        "sub": f"{len(open_)} decisions open",
        "go": "command/kpis",
    }

    def add(ic, h, k, v, n, label, go, sub=None, sp=None, d=None):
        o = {"ic": ic, "h": h, "k": k, "v": v, "n": n, "l": label}
        if sub is not None:
            o["sub"] = sub
        if sp is not None:
            o["sp"] = sp
        o["go"] = go
        if d is not None:
            o["delta"] = d
        T.append(o)

    if role == "Developer":
        fl = sum(1 for w in workflows() if wf_stat(w) == "failing")
        st, ex, cf, t = len(stale_sources()), len(sm_exceptions()), len(open_conflicts()), hh_totals()
        add("workflow", "alert", "wffail", fl, fl, "Failing workflows", "integration/studio")
        add("clock", "dec", "stale", st, st, "Stale sources", "integration/map")
        add("mapping", "insp", "mapx", ex, ex, "Mappings needing attention", "integration/map")
        add("conflict", "ev", "conf", cf, cf, "Conflicts open", "integration/conflicts")
        pct = to_fixed(t["pct"], 1)
        sp = [b["ok"] / ((b["ok"] + b["warn"] + b["bad"]) or 1) for b in hh()]
        add(
            "activity",
            "int",
            "health",
            pct + "%",
            float(pct),
            "Integration health",
            "integration/monitor",
            sub="last 24 hours",
            sp=sp,
        )
        return T
    if role == "Planner":
        rdy = sum(1 for c in cs if c["stage"] == "awaiting_approval" and not c.get("submitted") and c.get("recommendation"))
        wk = sum(1 for c in cs if (AS_OF - ms(c["received"])) / DAY_MS <= 7)
        add("clipboard", "dec", "ready", rdy, rdy, "Ready to submit", "product/received")
        add("search", "ev", "need", need, need, "Missing evidence", "product/received")
        add("rotate", "re", "reeval", reev, reev, "Re-evaluate", "product/received")
        add("box", "insp", "week", wk, wk, "Received this week", "product/received")
        T.append(pot_t)
        return T
    if role == "Approver":
        wait = [c for c in cs if c["stage"] == "awaiting_approval" and c.get("submitted")]
        lim = limit_for(a, ctx.actor.ctx)
        esc = sum(1 for x in alerts(ctx) if x["kind"] == "esc")

        def close_call(c: Case) -> bool:
            if c["stage"] != "awaiting_approval" or not c.get("routes") or len(c["routes"]) <= 1:
                return False
            n = sorted((r["net"] for r in c["routes"]), reverse=True)
            return n[0] > 0 and (n[0] - n[1]) / n[0] < 0.1

        close = sum(1 for c in cs if close_call(c))
        over = sum(
            1
            for c in cs
            if c["stage"] == "awaiting_approval" and c.get("recommendation") and abs(c["recommendation"]["net"]) > lim
        )
        wv = js_sum(ws.cc_net(c) for c in wait)
        add("tasks", "dec", "wait", len(wait), len(wait), "Waiting for me", "command/approvals")
        add("clock", "alert", "esc", esc, esc, "Escalations", "alerts")
        add("scale", "insp", "close", close, close, "Close calls", "product/received", sub="top two routes within 10%")
        add("shield", "ev", "over", over, over, "Over my limit", "product/received")
        add("dollar", "money", "potential", kfmt(wv), wv, "Value waiting", "command/approvals")
        return T
    if role == "Engineer":
        res = sum(1 for c in cs if c.get("blocked") and c.get("requested"))
        tst = sum(1 for c in cs if c.get("condition") == "Test required")
        cert = sum(1 for c in cs if c.get("blocked") and re.search(r"polic|certif", c["blocked"].get("gateName") or "", re.I))
        hold = sum(1 for c in cs if c.get("blocked"))
        add("cal", "insp", "insp", insp, insp, "Inspections due", "product/received")
        add("clipboard", "dec", "res", res, res, "Results to record", "command/aome")
        add("shield", "ev", "cert", cert, cert, "Certification holds", "product/received")
        add("rotate", "re", "retest", tst, tst, "Re-tests", "product/received", sub="test required")
        add("flag", "alert", "hold", hold, hold, "Gate holds", "product/received")
        return T
    if role == "Finance":
        conf = sum(1 for c in cs if c["stage"] == "closed" and not c.get("outcome"))
        vr = _monthly(rows, lambda x: x["actual"] - x["p50"] if x["status"] == "reconciled" else 0)
        v1 = vr[-1]
        rc = [x for x in rows if x["status"] == "reconciled" and x["mi"] == len(MONTHS) - 1]
        inb = sum(1 for x in rc if abs(x["actual"] - x["p50"]) <= abs(x["p50"]) * 0.1)
        bills = sum(1 for c in cs if c["stage"] in ("executing", "closed"))
        add("checks", "dec", "confirm", conf, conf, "Outcomes to confirm", "command/outcomes")
        add(
            "scale", "ev", "variance", kfmt(v1), v1, "Variance this month", "analytics/predicted", sub="actual against P50", sp=vr
        )
        pva = js_round(inb / len(rc) * 100) if rc else None
        add(
            "target",
            "re",
            "pva",
            f"{pva}%" if rc else "—",
            pva,
            "Predicted vs actual",
            "analytics/predicted",
            sub="within ±10% this month",
        )
        add("truck", "insp", "bills", bills, bills, "Carrier bills to check", "analytics")
        add(
            "dollar",
            "money",
            "recovery",
            kfmt(r1),
            r1,
            "Net recovery",
            "analytics/waterfall",
            sub=MONTHS[-1],
            sp=rec,
            d=delta(r1, r0, True),
        )
        return T
    if role == "Warehouse Manager":
        inb = len(exp_vis(ctx))
        wms = sum(1 for c in cs if _wms_active(c))
        esc = sum(1 for x in alerts(ctx) if x["kind"] == "esc")
        here = [c for c in cs if c["stage"] != "closed"]
        days = js_round(js_sum((AS_OF - ms(c["received"])) / DAY_MS for c in here) / len(here)) if here else 0
        add("truck", "insp", "inbound", inb, inb, "Inbound expected", "product/expected")
        add("warehouse", "dec", "wms", wms, wms, "Steps waiting on WMS", "command/handed")
        add("clock", "alert", "esc", esc, esc, "Escalations", "alerts")
        add("box", "re", "held", len(here), len(here), "Assets on hand", "product/received")
        add("cal", "money", "days", f"{days} d", days, "Average holding days", "product/received")
        return T
    if role == "Executive":
        sc = ws.cc_scope(ctx)
        co2 = _monthly(rows, lambda x: x["co2e"] if x["status"] == "reconciled" else 0)
        c1, c0 = co2[-1], co2[-2]
        risk = js_sum(c["_var"] for c in sc["all"])
        add(
            "dollar",
            "money",
            "recovery",
            kfmt(r1),
            r1,
            "Net recovery",
            "analytics/waterfall",
            sub=MONTHS[-1],
            sp=rec,
            d=delta(r1, r0, True),
        )
        T.append(pot_t)
        add("alert", "alert", "risk", kfmt(risk), risk, "Value at risk", "command/exceptions", sub="next 30 days if no action")
        add("tasks", "dec", "open", len(open_), len(open_), "Decisions open", "command/kpis")
        cr = js_round(c1)
        add(
            "leaf",
            "int",
            "co2",
            fmt_n(cr) + " kg",
            cr,
            "Carbon avoided",
            "analytics/sustain",
            sub=MONTHS[-1] + " · CO₂e",
            sp=co2,
            d=delta(c1, c0, True),
        )
        return T
    # Admin and anyone else: the decision pipeline
    rdy = sum(1 for c in cs if c["stage"] == "awaiting_approval")
    add("tasks", "dec", "ready", rdy, rdy, "Decisions ready", "product/received")
    add("search", "ev", "need", need, need, "Cases missing evidence", "product/received")
    add("rotate", "re", "reeval", reev, reev, "Require re-evaluation", "product/received")
    add("cal", "insp", "insp", insp, insp, "Inspections due", "product/received")
    T.append(pot_t)
    return T


# ---------------------------------------------------------------- activity (the demo's frActivity)
_ACT_LIM = {"live": 3600_000, "today": DAY_MS, "week": 7 * DAY_MS}
_ACT_EVENT = re.compile(r"^handoff\.|stock\.|outcome\.")


def activity(ctx: CallContext, win: str) -> list[dict]:
    now = AS_OF  # the demo's asOfNow(): the clock is pinned to the as-of time
    out: list[dict] = []
    jr = ctx.session.execute(
        text("SELECT action, actor, input, at FROM action_journal WHERE preparer IS NOT NULL AND NOT undone ORDER BY seq")
    ).all()
    for e in jr:
        a = ACTIONS.get(e.action)
        i = e.input or {}
        who = policy.account(e.actor, ctx.actor.ctx)
        cid = i.get("case_id")
        out.append(
            {
                "ts": ms(e.at.isoformat()),
                "ic": "bot",
                "h": "agent",
                "title": a.title if a else e.action,
                "badge": "Prepared by agent",
                "sub": f"{cid or i.get('source_id') or i.get('id') or ''} · by {who.label if who else e.actor}",
                "st": {"tone": "ok", "label": "Completed"},
                "links": [{"act": "trace", "arg": cid, "label": "Show trace"}] if cid else [],
            }
        )
    case_page = can_page(ctx, "product", "case")
    ids = {c["id"] for c in store.all_cases(ctx.session)}
    evs = [
        e for e in ws_events(ctx) if _ACT_EVENT.search(e["type"]) and (not e.get("caseId") or e["caseId"] not in ids or case_page)
    ][:10]
    for e in evs:
        esc = e["type"] == "handoff.escalated"
        out.append(
            {
                "ts": ms(e["ts"]),
                "ic": "clock" if esc else "send",
                "h": "alert" if esc else "money",
                "title": e["type"] + (" · " + e["caseId"] if e.get("caseId") else ""),
                "sub": f"{e.get('dest') or ''} · {e.get('ack') or ''}",
                "st": {"tone": "warn", "label": "Action required"} if esc else {"tone": "ok", "label": "Completed"},
                "links": [],
            }
        )
    lim = _ACT_LIM.get(win, DAY_MS)
    rows = [o for o in out if now - o["ts"] <= lim or win == "week"]
    rows.sort(key=lambda o: -o["ts"])
    rows = rows[: 6 if win == "live" else 10]
    for o in rows:
        o["ago"] = ago(now - o.pop("ts"))
    return rows


# ---------------------------------------------------------------- the middle panel (the facade's middlePanel)
def middle(ctx: CallContext) -> dict:
    r = ctx.actor.account.role
    if r in ("Developer", "Admin"):
        lst = workflows()
        c = {"published": 0, "failing": 0, "draft": 0, "paused": 0}
        for w in lst:
            c[wf_stat(w)] += 1
        src_n = len({w["src"] for w in lst if w["src"]})
        return {
            "id": "frWfHealth",
            "title": "Workflow health",
            "sub": f"Across {src_n} source systems",
            "link": {"go": "integration/studio", "label": "View all →"},
            "ring": {
                "segs": [
                    {"v": c["published"], "c": "var(--ok)", "l": "Published"},
                    {"v": c["failing"], "c": "var(--bad)", "l": "Failing"},
                    {"v": c["draft"] + c["paused"], "c": "var(--muted)", "l": "Draft or paused"},
                ],
                "center": to_fixed(c["published"] / (len(lst) or 1) * 100, 1) + "%",
                "sub": "Healthy",
                "label": "Workflow health",
            },
        }
    cs = visible_cases(ctx)
    if r == "Engineer":
        gr: dict[str, int] = {}
        for c in cs:
            k = (
                "Grade " + c["grade"]
                if c.get("grade")
                else "Not inspected"
                if c.get("assessment") == "Pending"
                else c.get("condition")
            )
            gr[k] = gr.get(k, 0) + 1
        cols = ["var(--ok)", "var(--h-money)", "var(--h-dec)", "var(--h-insp)", "var(--muted)", "var(--bad)"]
        segs = [{"v": v, "l": k, "c": cols[i % len(cols)]} for i, (k, v) in enumerate(gr.items())]
        return {
            "title": "Inspections by grade",
            "sub": "Every returned asset in your view",
            "ring": {"segs": segs, "center": str(len(cs)), "sub": "assets"},
        }
    if r == "Finance":
        rc = [x for x in visible_rows(ctx) if x["status"] == "reconciled"]
        inb = sum(1 for x in rc if abs(x["actual"] - x["p50"]) <= abs(x["p50"]) * 0.1)
        ab = sum(1 for x in rc if x["actual"] - x["p50"] > abs(x["p50"]) * 0.1)
        return {
            "title": "Predicted vs actual",
            "sub": f"{len(rc)} reconciled decisions",
            "link": {"go": "analytics/predicted", "label": "Analytics →"},
            "ring": {
                "segs": [
                    {"v": inb, "c": "var(--ok)", "l": "Within ±10%"},
                    {"v": ab, "c": "var(--h-money)", "l": "Above prediction"},
                    {"v": len(rc) - inb - ab, "c": "var(--bad)", "l": "Below prediction"},
                ],
                "center": to_fixed(inb / (len(rc) or 1) * 100, 0) + "%",
                "sub": "within ±10%",
            },
        }
    if r == "Warehouse Manager":
        u = ws.cc_util(cs)
        cols = ["var(--h-insp)", "var(--h-money)", "var(--h-dec)", "var(--h-re)", "var(--h-int)"]
        segs = [{"v": v, "l": k, "c": cols[i % 5]} for i, (k, v) in enumerate(u.items())]
        return {
            "title": "Receiving load",
            "sub": "Where assets are now",
            "ring": {"segs": segs, "center": str(sum(u.values())), "sub": "assets"},
        }
    if r == "Executive":
        m = metrics(visible_rows(ctx))
        mx = max(m["base"], m["act"], 1)

        def bar(label: str, v: float, c: str) -> dict:
            return {"l": label, "v": v, "c": c, "w": max(2, abs(v) / mx * 100)}

        return {
            "title": "Recovery waterfall",
            "sub": f"{len(m['rc'])} reconciled decisions",
            "link": {"go": "analytics/waterfall", "label": "Analytics →"},
            "bars": [
                bar("Baseline", m["base"], "var(--muted)"),
                bar("Circularity uplift", m["uplift"], "var(--yellow)"),
                bar("Net recovery", m["act"], "var(--ok)"),
            ],
        }
    names = {
        "approval": "Awaiting approval",
        "reeval": "Re-evaluate",
        "need": "Needs evidence",
        "await_insp": "Awaiting inspection",
        "approved": "Approved",
        "exec": "Handed off",
        "noroute": "Other",
    }
    cols = {
        "Awaiting approval": "var(--yellow)",
        "Re-evaluate": "var(--h-re)",
        "Needs evidence": "var(--h-ev)",
        "Awaiting inspection": "var(--h-insp)",
        "Approved": "var(--h-money)",
        "Handed off": "var(--ok)",
        "Other": "var(--muted)",
    }
    st: dict[str, int] = {}
    for c in cs:
        k = names[ws.cc_stage(c)]
        st[k] = st.get(k, 0) + 1
    segs = [{"v": v, "l": k, "c": cols[k]} for k, v in st.items()]
    return {
        "title": "Decisions by stage",
        "sub": "Every returned asset in your view",
        "ring": {"segs": segs, "center": str(len(cs)), "sub": "returned assets"},
    }


# ---------------------------------------------------------------- key figures (the facade's figures)
def figures(ctx: CallContext, per: str) -> list[dict]:
    n = 1 if per == "30" else 3 if per == "90" else 12
    mi0 = len(MONTHS) - n
    every = visible_rows(ctx)
    rc = [x for x in every if x["mi"] >= mi0 and x["status"] == "reconciled"]
    sc = ws.cc_scope(ctx)
    open_ = [c for c in sc["all"] if c["_st"] in ("approval", "reeval")]
    prev = [x for x in every if mi0 - n <= x["mi"] < mi0 and x["status"] == "reconciled"]

    def tot(rows: list[dict], f) -> float:
        return js_sum(f(x) for x in rows)

    def fig(k, ic, h, v, label, sub, d=None):
        o = {"k": k, "ic": ic, "h": h, "v": v, "l": label, "sub": sub}
        if d is not None:
            o["delta"] = d
        return o

    act, avo = tot(rc, lambda x: x["actual"]), tot(rc, lambda x: x["avoided"])
    return [
        fig("assets", "box", "insp", fmt_n(len(sc["all"])), "Assets in scope", "returned assets now"),
        fig(
            "potential",
            "dollar",
            "money",
            kfmt(js_sum(ws.cc_net(c) for c in open_)),
            "Potential recovery",
            f"{len(open_)} decisions open",
        ),
        fig("risk", "alert", "alert", kfmt(js_sum(c["_var"] for c in sc["all"])), "Value at risk", "next 30 days if no action"),
        fig(
            "recovery",
            "trend",
            "int",
            kfmt(act),
            "Net recovery",
            f"{len(rc)} reconciled",
            delta(act, tot(prev, lambda x: x["actual"]), True),
        ),
        fig(
            "avoided",
            "layers",
            "dec",
            kfmt(avo),
            "New purchases avoided",
            "confirmed avoided spend",
            delta(avo, tot(prev, lambda x: x["avoided"]), True),
        ),
        fig(
            "variance",
            "scale",
            "re",
            kfmt(tot(rc, lambda x: x["actual"] - x["p50"])),
            "Predicted against actual",
            "actual minus P50",
        ),
    ]


# ---------------------------------------------------------------- reports (the demo's FR_REP)
REPORTS = [
    (
        "pva",
        "Predicted vs actual",
        "target",
        "re",
        ("analytics", None),
        "Every reconciled decision: P50 prediction, actual net and the variance.",
    ),
    (
        "packs",
        "Evidence packs",
        "file",
        "ev",
        ("product", "case"),
        "Decisions with an evidence snapshot: route, value, approval and where the evidence came from.",
    ),
    (
        "waterfall",
        "Recovery waterfall",
        "analytics",
        "money",
        ("analytics", None),
        "Baseline, Circularity uplift and net recovery by month.",
    ),
    (
        "carbon",
        "Carbon avoided",
        "leaf",
        "int",
        ("analytics", None),
        "Estimated and measured CO₂e avoided by month; measured only where telemetry exists.",
    ),
    (
        "health",
        "Integration health",
        "activity",
        "int",
        ("integration", None),
        "Each connected system: status, freshness, completeness, confidence, records and last sync.",
    ),
    (
        "audit",
        "Audit extract",
        "audit",
        "re",
        ("audit", None),
        "The audit log in view: what was fetched or changed, from where, when and by whom.",
    ),
]


def _route(rid: str) -> dict:
    return next((r for r in ROUTES if r["id"] == rid), ROUTES[0])


def src_fresh(s: dict) -> int:
    """The demo's srcFresh: freshness in percent from the last sync against the source's interval."""
    if s.get("lastSync") is None:
        return 0
    if s["status"] == "manual":
        return 45
    w = s["interval"] * 2 if s.get("interval") else 30
    a = (AS_OF - s["lastSync"]) / 60000
    return max(4, js_round(100 - min(96, a / w * 100)))


def report_rows(ctx: CallContext, rid: str, tenant: str, period: str) -> list[list]:
    n = 1 if period == "30" else 3 if period == "90" else 12
    rows = [x for x in visible_rows(ctx) if x["mi"] >= len(MONTHS) - n and (tenant == "All" or x["tenant"] == tenant)]
    rc = [x for x in rows if x["status"] == "reconciled"]
    months = sorted({x["mi"] for x in rc})
    if rid == "pva":
        head = ["Case", "Month", "Tenant", "Route", "Predicted P50", "Actual", "Variance"]
        return [head] + [
            [
                x["id"],
                MONTHS[x["mi"]],
                x["tenant"],
                _route(x["route"])["name"],
                js_round(x["p50"]),
                js_round(x["actual"]),
                js_round(x["actual"] - x["p50"]),
            ]
            for x in rc
        ]
    if rid == "packs":
        head = ["Case", "Tenant", "Stage", "Route", "Net", "Approval ref", "Snapshot"]
        out = [head]
        for c in visible_cases(ctx):
            if c.get("recommendation") and (tenant == "All" or c["owner"] == tenant):
                r = c.get("chosen") or c["recommendation"]
                appr = c["approval"]["ref"] if c.get("approval") else ""
                out.append(
                    [
                        c["id"],
                        c["owner"],
                        c["stage"],
                        r["plan"],
                        js_round(r["net"]),
                        appr,
                        c["snapshot"]["id"] if c.get("snapshot") else "",
                    ]
                )
        return out
    if rid == "waterfall":
        out = [["Month", "Decisions", "Baseline", "Uplift", "Net recovery", "New purchases avoided"]]
        for i in months:
            q = [x for x in rc if x["mi"] == i]
            b, a = js_sum(x["baseline"] for x in q), js_sum(x["actual"] for x in q)
            out.append([MONTHS[i], len(q), js_round(b), js_round(a - b), js_round(a), js_round(js_sum(x["avoided"] for x in q))])
        return out
    if rid == "carbon":
        out = [["Month", "Decisions", "CO2e estimated (kg)", "CO2e measured (kg)"]]
        for i in months:
            q = [x for x in rc if x["mi"] == i]
            out.append(
                [
                    MONTHS[i],
                    len(q),
                    js_round(js_sum(x.get("co2e") or 0 for x in q)),
                    js_round(js_sum(x.get("co2m") or 0 for x in q)),
                ]
            )
        return out
    if rid == "health":
        head = ["System", "Vendor", "Status", "Freshness %", "Completeness %", "Confidence %", "Records", "Last sync"]
        return [head] + [
            [
                s["name"],
                s["vendor"],
                s["status"],
                src_fresh(s),
                s["compl"],
                s["conf"],
                s["records"],
                iso(s["lastSync"]) if s.get("lastSync") else "",
            ]
            for s in SOURCES.values()
        ]
    raise HTTPException(404, {"code": "not_found", "message": f"The {rid} report is served by its own page."})


def reports(ctx: CallContext) -> list[dict]:
    return [{"id": i, "t": t, "ic": ic, "h": h, "d": d} for i, t, ic, h, (pg, sec), d in REPORTS if can_page(ctx, pg, sec)]


# ---------------------------------------------------------------- endpoints
@router.get("/briefing")
def get_briefing(p: Principal = Depends(principal), session: Session = Depends(get_session)) -> list[dict]:
    """The briefing lines for the signed-in role (the demo's afBriefing)."""
    return ws.briefing(call_ctx(p, session))


@router.get("/tasks")
def get_tasks(p: Principal = Depends(principal), session: Session = Depends(get_session)) -> list[dict]:
    """Everything whose next step is the signed-in account's (the demo's aomeItems), each with its My Tasks group."""
    return [{**i, "group": task_group(i)} for i in ws.aome_items(call_ctx(p, session))]


@router.get("/alerts")
def get_alerts(p: Principal = Depends(principal), session: Session = Depends(get_session)) -> list[dict]:
    """Notifications, escalations and integration issues the account sees (the demo's frAlerts)."""
    return alerts(call_ctx(p, session))


@router.get("/kpis")
def get_kpis(p: Principal = Depends(principal), session: Session = Depends(get_session)) -> list[dict]:
    """Home's KPI tiles for the signed-in role (the demo's frKpis)."""
    return kpis(call_ctx(p, session))


@router.get("/activity")
def get_activity(
    win: str = Query("today", pattern="^(live|today|week)$"),
    p: Principal = Depends(principal),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Agent-prepared changes and hand-off events in the window (the demo's frActivity)."""
    return activity(call_ctx(p, session), win)


@router.get("/middle")
def get_middle(p: Principal = Depends(principal), session: Session = Depends(get_session)) -> dict:
    """Home's middle panel for the signed-in role."""
    return middle(call_ctx(p, session))


@router.get("/figures")
def get_figures(
    per: str = Query("30", pattern="^(30|90|365)$"), p: Principal = Depends(principal), session: Session = Depends(get_session)
) -> list[dict]:
    """Home's key figures for a period of 30, 90 or 365 days."""
    return figures(call_ctx(p, session), per)


@router.get("/reports")
def get_reports(p: Principal = Depends(principal), session: Session = Depends(get_session)) -> list[dict]:
    """The reports the account may open."""
    return reports(call_ctx(p, session))


@router.get("/reports/{report_id}")
def get_report_rows(
    report_id: str,
    tenant: str = "All",
    period: str = Query("90", pattern="^(30|90|365)$"),
    p: Principal = Depends(principal),
    session: Session = Depends(get_session),
) -> list[list]:
    """A report's rows (header first) for a tenant ('All' or one the account may see) and a period."""
    ctx = call_ctx(p, session)
    if report_id not in {r["id"] for r in reports(ctx)}:
        raise HTTPException(404, {"code": "not_found", "message": f"No report {report_id} for the {p.account.role} view."})
    if tenant != "All" and not p.tenant_ok(tenant):
        raise HTTPException(403, {"code": "tenant_boundary", "message": f"{tenant} is a tenant you cannot see."})
    return report_rows(ctx, report_id, tenant, period)
