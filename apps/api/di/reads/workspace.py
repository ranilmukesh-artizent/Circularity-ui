"""Workspace reads (B11): inbox.get, receiving.plan, access.lookup, kpi.explain.

Ports of the demo's read actions (index.html, `defAction('inbox.get', ...)`, `'receiving.plan'`, `'access.lookup'` and
`'kpi.explain'`) and the helpers they call: the role briefing (afBriefing), Actions on me (aomeItems), the
Command Center's scope and exceptions (ccScope, ccExList, ccExRows) and the analytics totals (metrics). Browser-memory
state they read (notifications, requests, approval limits, workflows) is the demo's starting state, in common.py.
"""

import math
import re
from functools import cache, cmp_to_key

from sqlalchemy import text

from di import golden, policy
from di.actions.registry import PERM_ALIAS, implement
from di.cases import store
from di.engine.jsmath import js_round, js_sum
from di.reads.common import (
    AS_OF,
    CLASSES,
    CO2S,
    DAY_MS,
    EMB,
    REQ_KIND,
    SOURCES,
    STARTING_CONFLICTS,
    STARTING_FAILED_WORKFLOWS,
    STARTING_MAPPINGS,
    WORLD,
    Case,
    account,
    active_step,
    as_hex,
    decisions_delegated,
    ex_app,
    ex_clock,
    ex_ts,
    exp_vis,
    fmt_n,
    inbox_requests,
    kfmt,
    limit_for,
    money,
    ms,
    notes,
    step_owner,
    ti_conf,
    to_fixed,
    vis_cases,
)

ROUTES = WORLD["routes"]


# ---------------------------------------------------------------- closed decisions (the demo's ROWS)
def _rows() -> list[dict]:
    return golden.load("decisions")


def vis_rows(ctx) -> list[dict]:
    """The demo's visRows: the closed decisions in the account's tenants (the on-screen tenant filter is 'All')."""
    a = account(ctx)
    return [r for r in _rows() if a is None or policy.tenant_ok(a, r["tenant"], ctx.actor.ctx)]


def _median(a: list[float]) -> float:
    """The demo's med."""
    if not a:
        return 0
    s, m = sorted(a), len(a) >> 1
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def metrics(rows: list[dict]) -> dict:
    """The demo's metrics, the parts the reads use: reconciled decisions, actual net and avoided spend."""
    rc = [r for r in rows if r["status"] == "reconciled"]
    return {"rc": rc, "act": js_sum(r["actual"] for r in rc), "avoided": js_sum(r["avoided"] for r in rc)}


def route_name(route_id: str) -> str:
    """The demo's rid(r).name."""
    return next((r["name"] for r in ROUTES if r["id"] == route_id), route_id)


# ---------------------------------------------------------------- the Command Center's scope (ccScope)
CC_REASONS = ["Delayed approval", "Condition deterioration", "Missing evidence", "Market price decline", "Capacity constraints"]
CC_DECAY = {"motor": 0.012, "pump": 0.014, "control": 0.03, "drill": 0.025, "batch": 0.03, "it": 0.05}
CC_CAP = {"Repair centre": 45, "Warehouse 1": 60, "Warehouse 2": 60, "Inspection queue": 30, "In execution": 40}
EX_OWNER = {"value": "approver", "evidence": "engineer", "integration": "developer"}
EX_WH_ORDER = ["Warehouse 1", "Warehouse 2", "Repair centre"]
SEV_MULT = {"High": 1.5, "Medium": 1, "Low": 0.6}
# the kind of exception each risk reason raises (the rest are "value")
EX_TYPE = {"Missing evidence": "evidence", "Condition deterioration": "evidence", "Capacity constraints": "bottleneck"}


@cache
def cc_est_per_unit() -> dict[str, float]:
    """The demo's CC_EST: per class, the median predicted net per unit of closed decisions (not exits, P50 > 0)."""
    return {
        k: _median([r["p50"] / r["q"] for r in _rows() if r["cls"] == k and r["route"] != "exit" and r["p50"] > 0])
        for k in CLASSES
    }


def cc_stage(c: Case) -> str:
    """The demo's ccStage: the Command Center's lifecycle bucket."""
    if c.get("assessment") == "Pending":
        return "await_insp"
    st = {"awaiting_approval": "approval", "approved": "approved", "executing": "exec", "reeval": "reeval"}.get(c["stage"])
    if st:
        return st
    return "need" if c.get("assessment") in ("Review", "Partial") else "noroute"


def cc_net(c: Case) -> float:
    r = c.get("recommendation")
    return r["net"] if r else 0


def cc_est(c: Case) -> float:
    """The demo's ccEst: the recommended net, or an estimate from similar closed decisions."""
    if c.get("recommendation"):
        return cc_net(c)
    return js_round((cc_est_per_unit().get(c["cls"]) or 0) * c["qty"] * 0.8)


def cc_left(c: Case) -> int:
    """The demo's ccLeft: days left in the decision window (from the evidence snapshot, else the receipt)."""
    a = (c.get("snapshot") or {}).get("takenAt") or c["received"]
    w = 14 if c.get("recommendation") else 10
    return js_round(w - (AS_OF - ms(a)) / DAY_MS)


def cc_util(vis: list[Case]) -> dict[str, int]:
    """The demo's ccUtil: load per facility and queue."""

    def at(loc: str) -> int:
        return sum(1 for c in vis if c["location"] == loc)

    return {
        "Repair centre": at("Repair centre"),
        "Warehouse 1": at("Warehouse 1"),
        "Warehouse 2": at("Warehouse 2"),
        "Inspection queue": sum(1 for c in vis if cc_stage(c) == "await_insp"),
        "In execution": sum(1 for c in vis if c["stage"] in ("executing", "approved")),
    }


def cc_risk(c: Case, util: dict[str, int]) -> dict[str, float]:
    """The demo's ccRisk: the value each risk reason puts at stake on this case over the next 30 days (key order as
    the demo inserts them; only positive amounts kept)."""
    st, r = cc_stage(c), {}
    if st in ("approval", "reeval"):
        n, left = cc_net(c), cc_left(c)
        r["Condition deterioration"] = n * (CC_DECAY.get(c["cls"]) or 0.02) * 3
        r["Delayed approval"] = n * (0.25 if left < 5 else 0.1 if left < 8 else 0.03)
        rec = c.get("recommendation")
        if rec and rec["id"] == "resale" and SOURCES.get("mkt", {}).get("status") == "stale":
            r["Market price decline"] = n * 0.06
        if c["location"] == "Repair centre" and util["Repair centre"] / CC_CAP["Repair centre"] >= 0.75:
            r["Capacity constraints"] = n * 0.05
    elif st in ("need", "await_insp", "noroute"):
        r["Missing evidence"] = cc_est(c) * 0.3
    return {k: v for k, v in r.items() if v > 0}


def cc_scope(ctx) -> dict:
    """The demo's ccScope with the Command Center filters cleared: the visible cases, each annotated with its stage
    (_st), risks (_risk), value at risk (_var) and estimated value (_val)."""
    vis = vis_cases(ctx, store.all_cases(ctx.session))
    util = cc_util(vis)
    for c in vis:
        c["_st"] = cc_stage(c)
        c["_risk"] = cc_risk(c, util)
        c["_var"] = js_sum(c["_risk"].values())
        c["_val"] = cc_est(c)
    return {"all": vis, "util": util}


def _cc_series(fn, rows: list[dict]) -> list[float]:
    o = [0] * 12
    for r in rows:
        o[r["mi"]] = o[r["mi"]] + fn(r)
    return o


def _prev_grade(c: Case) -> bool:
    """The demo's prevGrade (truthy): graded lower than at the last inspection."""
    return bool(c.get("grade") and c["grade"] != "A" and as_hex(c, "pg") % 11 == 0)


def cc_ex_list(sc: dict, ctx) -> list[dict]:
    """The demo's ccExList: exceptions ranked by value × urgency."""
    out: list[dict] = []
    a = account(ctx)
    wh = a.warehouse if a else None
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
                "type": EX_TYPE.get(k, "value"),
                "loc": "Repair centre" if k == "Capacity constraints" else None,
                "title": "Value at risk: " + k.lower(),
                "value": js_round(o["v"]),
                "ids": o["ids"],
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
                    "ids": [c["id"] for c in here],
                    "sev": "High" if p >= 1 else "Medium",
                    "urg": p,
                }
            )
    if not wh:
        rows = vis_rows(ctx)
        series = [
            ("net recovery", lambda r: r["actual"] if r["status"] == "reconciled" else 0),
            ("uplift vs baseline", lambda r: r["actual"] - r["baseline"] if r["status"] == "reconciled" else 0),
            ("closed decisions", lambda r: 1),
        ]
        for name, fn in series:
            s = _cc_series(fn, rows)
            last, prev = s[10], s[9]
            if prev > 0 and last / prev - 1 < -0.05:
                out.append(
                    {
                        "id": "kpi:" + name,
                        "type": "value",
                        "loc": None,
                        "title": "Declining metric: " + name,
                        "value": js_round(max(0, prev - last)),
                        "ids": [],
                        "sev": "High" if last / prev - 1 < -0.15 else "Medium",
                        "urg": 0.6,
                        "go": "analytics",
                    }
                )
    det = [c for c in sc["all"] if _prev_grade(c)]
    if det:
        out.append(
            {
                "id": "cond",
                "type": "evidence",
                "loc": None,
                "title": "Deteriorating condition",
                "value": js_round(js_sum(c.get("_val") or 0 for c in det)),
                "ids": [c["id"] for c in det],
                "sev": "Medium" if len(det) > 6 else "Low",
                "urg": 0.5,
            }
        )
    for x in out:
        x["score"] = x["value"] * x["urg"] * SEV_MULT[x["sev"]]
    return sorted(out, key=lambda x: -x["score"])


def cc_ex_rows(sc: dict, ctx) -> list[dict]:
    """The demo's ccExRows: each ranked exception split by the warehouse its items are in; the parts still add up to
    the ranked value (the remainder goes to the largest part)."""
    rows: list[dict] = []
    by_id = {c["id"]: c for c in sc["all"]}
    for x in cc_ex_list(sc, ctx):
        if not x["ids"]:
            rows.append({**x, "base": x["id"], "wh": "Portfolio", "items": []})
            continue
        k = x["id"][4:] if x["id"].startswith("var:") else None

        def iv(c: Case, k=k) -> float:
            return c["_risk"].get(k, 0) if k else (c.get("_val") or 0)

        g: dict[str, list[dict]] = {}
        for cid in x["ids"]:
            c = by_id.get(cid)
            if c is None:
                continue
            w = x["loc"] if x["id"].startswith("cap:") else c["location"]
            g.setdefault(w, []).append({"c": c, "v": iv(c)})
        ws = list(g)
        raw = [js_sum(i["v"] for i in g[w]) for w in ws]
        tot = js_sum(raw)
        vals = [js_round(x["value"] * v / tot) if tot else 0 for v in raw]
        if vals:
            vals[raw.index(max(raw))] += x["value"] - js_sum(vals)
        for w, val in zip(ws, vals, strict=True):
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
                    "ids": [i["c"]["id"] for i in items],
                    "items": items,
                }
            )
    tot_by: dict[str, float] = {}
    for r in rows:
        tot_by[r["wh"]] = tot_by.get(r["wh"], 0) + r["value"]

    def gk(w: str) -> float:
        return -1 if w == "Portfolio" else tot_by[w]

    def order(w: str) -> int:
        return EX_WH_ORDER.index(w) if w in EX_WH_ORDER else -1

    def cmp(a: dict, b: dict) -> float:
        if a["wh"] == b["wh"]:
            return b["value"] - a["value"]
        return (gk(b["wh"]) - gk(a["wh"])) or (order(a["wh"]) - order(b["wh"]))

    return sorted(rows, key=cmp_to_key(cmp))


def ex_owner(x: dict) -> str:
    """The demo's exOwner: the account an exception goes to."""
    if x["type"] == "bottleneck":
        return "wm-2" if x["loc"] == "Warehouse 2" else "wm-1" if x["loc"] == "Warehouse 1" else "engineer"
    return EX_OWNER.get(x["type"]) or "approver"


def ex_owner_label(x: dict, ctx) -> str:
    a = policy.account(ex_owner(x), ctx.actor.ctx)
    return a.label if a else "Approver"


def _sees_exceptions(ctx) -> bool:
    return policy.can_page(account(ctx), "command", "exceptions")


# ---------------------------------------------------------------- inbox.get
def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def briefing(ctx) -> list[dict]:
    """The demo's afBriefing: the briefing lines for the signed-in role, each linked to its object."""
    a = account(ctx)
    if a is None:
        return []
    role, cs = a.role, vis_cases(ctx, store.all_cases(ctx.session))
    out: list[dict] = []

    def add(t: str, go: str, n: int) -> None:
        out.append({"text": t, "go": go, "n": n})

    def m() -> dict:
        return metrics(vis_rows(ctx))

    sub = [c for c in cs if c["stage"] == "awaiting_approval" and c.get("submitted")]
    prep = [c for c in cs if c["stage"] == "awaiting_approval" and not c.get("submitted") and c.get("recommendation")]
    gaps = [c for c in cs if c.get("blocked")]
    outs = [c for c in cs if c["stage"] == "closed" and not c.get("outcome")]
    re_ = [c for c in cs if c["stage"] == "reeval"]

    def top(lst: list[Case]) -> Case:
        return sorted(lst, key=lambda c: -(c.get("recommendation") or {"net": 0})["net"])[0]

    if role in ("Planner", "Admin"):
        if prep:
            t, n = top(prep), len(prep)
            add(
                f"{n} decision{'s' if n > 1 else ''} ready to submit; the largest is {t['id']} at "
                f"{money(t['recommendation']['net'])}.",
                f"product/{t['id']}?step=5",
                n,
            )
        if gaps:
            unrequested = sum(1 for c in gaps if not c.get("requested"))
            n = len(gaps)
            add(
                f"{n} case{'s are' if n > 1 else ' is'} missing evidence; {unrequested} not yet requested.",
                "product/received",
                n,
            )
        if re_:
            n = len(re_)
            add(f"{n} case{'s need' if n > 1 else ' needs'} re-evaluation.", f"product/{re_[0]['id']}?step=5", n)
    if role in ("Approver", "Admin"):
        v = js_sum(c["recommendation"]["net"] for c in sub)
        low = [
            c for c in sub if ti_conf(c, c["recommendation"]) == "Low" or c["recommendation"].get("demandStatus") != "confirmed"
        ]
        n = len(sub)
        if n:
            tail = f"; {len(low)} with forecast demand or low confidence" if low else ""
            text_ = f"{n} approval{'s' if n > 1 else ''} waiting, {money(v)} in total{tail}."
        else:
            text_ = "No submitted decision is waiting for approval."
        add(text_, "command/approvals", n)
        rq = len(inbox_requests(ctx))
        if rq:
            s = "s" if rq > 1 else ""
            add(f"{rq} access request{s} or MCP proposal{s} to decide.", "command/approvals", rq)
    if role in ("Engineer", "Admin"):
        due = [c for c in cs if c.get("assessment") == "Pending"]
        req = [c for c in cs if c.get("blocked") and c.get("requested")]
        fg = [c for c in cs if c["routes"] and not c.get("recommendation")]
        tail = f"; {len(req)} requested and waiting for your result" if req else ""
        add(f"{len(due)} inspection{_plural(len(due), '', 's')} due{tail}.", "product/received", len(due))
        if fg:
            add(f"{len(fg)} case{'s' if len(fg) > 1 else ''} where every route failed a gate.", f"product/{fg[0]['id']}", len(fg))
    if role in ("Finance", "Admin"):
        n = len(outs)
        add(
            f"{n} outcome{'s' if n > 1 else ''} reported and waiting for you to confirm."
            if n
            else "No outcome waits for confirmation.",
            "command/outcomes",
            n,
        )
        mm = m()
        add(_recovered_line(mm), "analytics", len(mm["rc"]))
    if role in ("Executive", "Admin"):
        if role == "Executive":
            mm = m()
            add(_recovered_line(mm), "command/kpis", len(mm["rc"]))
        ex = cc_ex_rows(cc_scope(ctx), ctx)[:2] if _sees_exceptions(ctx) else []
        for x in ex:
            add(f"{x['wh']} · {x['title']}: {kfmt(x['value'])} at risk; owner {ex_owner_label(x, ctx)}.", "command/exceptions", 1)
    if role == "Warehouse Manager":
        inb = exp_vis(ctx)
        hand = [c for c in cs if (s := active_step(c)) and s["sys"].startswith("WMS")]
        add(f"{len(inb)} return{_plural(len(inb), '', 's')} expected at {a.warehouse}.", "product/expected", len(inb))
        add(f"{len(hand)} handed-off item{_plural(len(hand), '', 's')} waiting on WMS.", "command/handed", len(hand))
        add(f"{len(cs)} returned asset{_plural(len(cs), '', 's')} at {a.warehouse} now.", "product/received", len(cs))
    if role in ("Developer", "Admin"):
        srcs = list(SOURCES.values())
        st = [s for s in srcs if s["status"] in ("stale", "unavailable")]
        gp = [s for s in srcs if s["status"] != "unavailable" and not STARTING_MAPPINGS.get(s["id"])]
        wf = STARTING_FAILED_WORKFLOWS
        cf = [c for c in STARTING_CONFLICTS if c["status"] == "open"]
        names = (": " + ", ".join(s["name"] for s in st)) if st else ""
        add(f"{len(st)} source{_plural(len(st), '', 's')} stale or not connected{names}.", "integration/map", len(st))
        if wf:
            add(
                f"{len(wf)} workflow{'s' if len(wf) > 1 else ''} failed on the last run: {', '.join(wf[:2])}.",
                "integration/studio",
                len(wf),
            )
        if cf:
            add(f"{len(cf)} open source conflict{'s' if len(cf) > 1 else ''}.", "integration/conflicts", len(cf))
        if gp:
            add(f"{len(gp)} source{'s have' if len(gp) > 1 else ' has'} no field mapping.", "integration/map", len(gp))
    if role == "Admin":
        # AF.journal: the agent-layer journal; the backend's is action_journal, where `preparer` names the agent
        ag = ctx.session.execute(text("SELECT count(*) FROM action_journal WHERE preparer IS NOT NULL")).scalar_one()
        add(
            f"{ag} change{_plural(ag, '', 's')} prepared by agents so far; every one shows who confirmed it.",
            "audit/log",
            ag,
        )
    return out[: 6 if role == "Admin" else 5]


def _recovered_line(m: dict) -> str:
    return f"{money(m['act'])} recovered on {len(m['rc'])} reconciled decisions; {money(m['avoided'])} of new purchases avoided."


def _op_scoped(ctx, a: policy.Account) -> list[Case]:
    """The demo's opScoped: Planners and Engineers start at their home site (warehouse or site); a Warehouse Manager
    is locked to theirs. The demo's widen-to-all-locations toggle is a screen setting, so the read uses the default."""
    home = a.warehouse or a.site
    return [c for c in vis_cases(ctx, store.all_cases(ctx.session)) if not home or c["location"] == home]


def aome_items(ctx) -> list[dict]:
    """The demo's aomeItems: everything whose next step belongs to this account, each with one button."""
    a = account(ctx)
    if a is None:
        return []
    role, out = a.role, []
    cs = _op_scoped(ctx, a)

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
    # Approvals and outcomes are listed across every visible case, not only the home site
    vis = vis_cases(ctx, store.all_cases(ctx.session)) if role in ("Approver", "Finance") else []
    if role == "Approver":
        for c in vis:
            if c["stage"] == "awaiting_approval" and c.get("submitted"):
                d = f"Submitted by {c['submitted']['by']} · {money(c['recommendation']['net'])}"
                out.append({"t": c["id"] + " · approve or decline", "d": d, "btn": "Decide", "go": st5(c["id"])})
    if role == "Finance":
        for c in vis:
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
            d = f"{e['product']} · {e['customer']} · {e['prob']}% likely to return"
            out.append(
                {"t": f"{e['contract']} · inbound {e['window']}", "d": d, "btn": "Plan receiving", "go": "product/expected"}
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


@implement("inbox.get")
def inbox_get(i, ctx):
    br = briefing(ctx)
    items = []
    for x in aome_items(ctx):
        m = re.match(r"^(RT-\d{4})", x["t"])
        items.append(
            {
                "title": x["t"],
                "detail": x["d"],
                "btn": x["btn"],
                "act": x.get("act"),
                "arg": x.get("arg"),
                "go": x.get("go"),
                "case_id": m[1] if m else None,
            }
        )
    return {"items": items, "total": len(items), "briefing": br}


# ---------------------------------------------------------------- receiving.plan
@implement("receiving.plan")
def receiving_plan(i, ctx):
    """Expected returns per warehouse and return window against receiving capacity (8 a window; Warehouse 2: 6,
    the Repair centre: 4)."""
    expected = exp_vis(ctx)
    by: dict[str, dict] = {}
    for e in expected:
        wh, wk = e["wh"], e["window"] or "Next week"
        row = by.setdefault(f"{wh}|{wk}", {"wh": wh, "week": wk, "n": 0})
        row["n"] += 1
    rows = []
    for x in by.values():
        cap = 6 if x["wh"] == "Warehouse 2" else 4 if x["wh"] == "Repair centre" else 8
        rows.append({**x, "cap": cap, "load": js_round(x["n"] / cap * 100)})
    rows.sort(key=lambda x: -x["load"])
    return {"total": len(expected), "rows": rows, "over": [f"{x['wh']} {x['week']}" for x in rows if x["load"] > 100]}


# ---------------------------------------------------------------- access.lookup
def _limit_out(v: float) -> float | None:
    """An approval limit as JSON: the demo's Infinity (no limit) has no JSON number, so it goes out as null, which is
    also what the demo's own JSON.stringify writes for it."""
    return None if math.isinf(v) else v


@implement("access.lookup")
def access_lookup(i, ctx):
    perm, amount = i["perm"], i.get("amount")
    want = PERM_ALIAS.get(perm, perm)
    roles = policy.roles()
    rows = []
    for a in policy.accounts(ctx.actor.ctx):
        p = roles.get(a.role)
        if not p or not (p.get("all") or want in (p.get("perms") or [])):
            continue
        if a.role == "Approver" and perm == "approve" and not decisions_delegated(ctx):
            continue
        lim = limit_for(a, ctx.actor.ctx)
        if amount and not lim > amount:
            continue
        how = "Master role" if a.role == "Admin" else "Delegated by Admin" if a.role == "Approver" else "Granted by Admin"
        rows.append({"id": a.id, "label": a.label, "role": a.role, "limit": _limit_out(lim), "how": how})
    return {"perm": perm, "amount": amount or 0, "rows": rows}


# ---------------------------------------------------------------- kpi.explain
AF_KPI = {
    "assets": "Assets in scope",
    "potential": "Potential recovery value",
    "risk": "Value at risk",
    "co2": "CO₂e avoided opportunity",
    "recovery": "Net recovery",
    "avoided": "New purchases avoided",
    "variance": "Predicted against actual",
}


def _signed_k(n: float) -> str:
    """ "+$4k" / "−$36k": kfmt with an explicit sign."""
    return ("−" if n < 0 else "+") + kfmt(abs(n)).replace("−", "", 1)


@implement("kpi.explain")
def kpi_explain(i, ctx):
    k = i["kpi"] if i["kpi"] in AF_KPI else "recovery"
    sc = cc_scope(ctx)
    m = metrics(vis_rows(ctx))
    o = {"kpi": k, "label": AF_KPI[k]}
    if k == "assets":
        by: dict[str, int] = {}
        for c in sc["all"]:
            by[c["location"]] = by.get(c["location"], 0) + 1
        n = len(sc["all"])
        o |= {
            "value": n,
            "value_text": fmt_n(n) + " returned assets",
            "definition": "Returned assets in your scope that match the Command Center filters.",
            "calc": "Count of live returned-asset cases visible to you, after tenant, warehouse and filter scope.",
            "top_label": "Location",
            "top": [{"label": loc, "value": v, "value_text": fmt_n(v)} for loc, v in by.items()],
            "go": "product/received",
        }
    elif k == "potential":
        open_ = [c for c in sc["all"] if c["_st"] in ("approval", "reeval")]
        v = js_sum(cc_net(c) for c in open_)
        largest = sorted(open_, key=lambda c: -cc_net(c))[:5]
        o |= {
            "value": v,
            "value_text": f"{kfmt(v)} across {len(open_)} open decisions",
            "definition": "Predicted net recovery of decisions that still need a person: awaiting approval plus re-evaluation.",
            "calc": "Sum of the recommended route's predicted net for each open decision.",
            "top_label": "Largest open decisions",
            "top": [
                {"label": f"{c['id']} · {c['recommendation']['plan']}", "value": cc_net(c), "go": "product/" + c["id"]}
                for c in largest
            ],
        }
    elif k == "risk":
        v = js_sum(c["_var"] for c in sc["all"])
        by_reason = dict.fromkeys(CC_REASONS, 0)
        for c in sc["all"]:
            for x, amt in c["_risk"].items():
                by_reason[x] = by_reason[x] + amt
        a = account(ctx)
        ex = cc_ex_rows(sc, ctx)[:5] if _sees_exceptions(ctx) or (a and policy.policy(a).get("all")) else []
        if ex:
            top = [
                {
                    "label": f"{x['wh']} · {x['title']}",
                    "value": x["value"],
                    "owner": ex_owner_label(x, ctx),
                    "go": "command/exceptions",
                }
                for x in ex
            ]
        else:
            top = [{"label": r, "value": js_round(n)} for r, n in sorted(by_reason.items(), key=lambda e: -e[1])]
        o |= {
            "value": v,
            "value_text": kfmt(v) + " at risk over the next 30 days",
            "definition": "Predicted value exposed over the next 30 days if no action is taken: decisions whose window "
            "closes, value decay while waiting, missing evidence, stale market data and capacity.",
            "calc": "Sum over cases of the value each risk reason puts at stake; reasons: " + ", ".join(CC_REASONS).lower() + ".",
            "top_label": "Top exceptions" if ex else "Reason",
            "top": top,
        }
    elif k == "co2":
        v = (
            js_sum(
                (EMB.get(c["cls"]) or 0) * c["qty"] * (CO2S.get(c["recommendation"]["id"]) or 0)
                for c in sc["all"]
                if c.get("recommendation")
            )
            / 1000
        )
        o |= {
            "value": v,
            "value_text": to_fixed(v, 1) + " t CO₂e (estimated)",
            "definition": "Embodied carbon the recommended routes would avoid, estimated from factors; "
            "measured values are in Analytics.",
            "calc": "Embodied-carbon factor by asset class × quantity × the share avoided by the recommended route.",
            "top": [],
        }
    elif k == "avoided":
        o |= {
            "value": m["avoided"],
            "value_text": f"{kfmt(m['avoided'])} on {len(m['rc'])} reconciled decisions",
            "definition": "New purchases avoided by redeploying assets or using recovered parts, "
            "confirmed on reconciled decisions.",
            "calc": "Sum of confirmed avoided spend on reconciled redeploy and internal-parts decisions.",
            "top": [],
            "go": "analytics",
        }
    elif k == "variance":
        # the demo's REC(): every reconciled decision, not only the account's tenants
        rc = [r for r in _rows() if r["status"] == "reconciled" and r["route"] != "exit"]
        by_route: dict[str, float] = {}
        for r in rc:
            by_route[r["route"]] = by_route.get(r["route"], 0) + (r["actual"] - r["p50"])
        v = js_sum(r["actual"] - r["p50"] for r in rc)
        o |= {
            "value": v,
            "value_text": _signed_k(v) + " actual against predicted",
            "definition": "How far actual outcomes landed from the predicted value (P50) on reconciled decisions.",
            "calc": "Sum of actual minus predicted, by route; negative means the model was optimistic.",
            "top_label": "Route",
            "top": [
                {"label": route_name(r), "value": n, "value_text": _signed_k(n)}
                for r, n in sorted(by_route.items(), key=lambda e: e[1])
            ],
            "go": "analytics",
        }
    else:
        per_route = [{"label": t["name"], "value": js_sum(r["actual"] for r in m["rc"] if r["route"] == t["id"])} for t in ROUTES]
        o |= {
            "value": m["act"],
            "value_text": f"{kfmt(m['act'])} on {len(m['rc'])} reconciled decisions",
            "definition": "Actual net recovery on closed, reconciled decisions in your tenants.",
            "calc": "Sum of actual net on reconciled decisions; pending, cancelled and expired ones are excluded.",
            "top_label": "Route",
            "top": sorted([x for x in per_route if x["value"]], key=lambda x: -x["value"]),
            "go": "analytics",
        }
    return o
