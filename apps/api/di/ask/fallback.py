"""The rule-based Ask: the demo's agent runtime (index.html, `afAsk` and `AF_INTENT_RUN`) on the server.

When no language model answers (no key, ASK_PROVIDER=none, Groq over its limit, failing or too slow), Ask answers as
the demo does without one: the question is parsed and matched to an intent (di.ask.intents), the intent's runner
reads through the action pipeline as the signed-in person (each read prepared by the demo's agent for that action,
AF_AGENT_OF), and the answer is the demo's text, typed cards and next steps, filled only from the action outputs.

The runners ported (the starters' and the data checks' intents whose actions have server handlers):
    briefing            inbox.get                   case.explain     case.get, case.evidence
    case.recommend      case.routes, case.evidence  case.compare     case.routes
    case.whynot         case.routes                 gate.waive       (refusal; no call)
    case.whatif         case.whatIf                 case.risk        case.get, case.routes, case.evidence
    case.submit         (plan card)                 case.approve     case.routes (approval card)
    case.record         (plan card)                 queue.filter     cases.list
    queue.triage        cases.list                  queue.prepare    cases.list, case.routes
    approvals.inbox     cases.list                  outcome.reconcile case.trace, case.get
    outcome.list        cases.list                  analytics.explain kpi.explain
    exceptions.top      kpi.explain                 access.who       access.lookup
    run.explain         case.trace                  expected.plan    receiving.plan
    wms.stuck           cases.list                  asset.compare    asset.compare
    analytics.accuracy  analytics.models
Not ported: the intents whose reads have no server handler yet (analytics.query, audit.search, sources.health,
sources.diagnose, conflict.suggest, event.explain, asset.summary) and the drafting intents that keep browser state
(mappings, table links, workflow drafts and edits, file cleaning, watches, the MCP proposal review, the pool
explanation, notifications). They are still recognised; the answer says the server cannot do that yet, as the demo
does for an intent without a runner.

Ask never writes. The demo's agent runs reads and drafts and stops every act or commit at a plan card the person
confirms; here even the drafts are skipped: an action that is not a read is never invoked, only recorded as skipped,
exactly as the demo's own eval mode does (afCallEval). Plan and approval cards point at the action; the person runs it.

`ask_rule` returns the demo's run: {intent, result, text, cards, next, calls}.
"""

import re
from collections.abc import Callable
from typing import Any

from di import golden, policy
from di.actions.decisions import draft_rationale
from di.actions.pipeline import CallContext, fail, invoke
from di.actions.registry import ACTIONS
from di.ask.intents import IGNORE_RULES, INTENT, STARTERS, match, parse
from di.cases import store
from di.engine.routes import GATES
from di.execution import ex_move, ex_plan, ex_trace, ex_what_if, loc_name
from di.reads.common import (
    AF_STAGES,
    AS_OF,
    SOURCES,
    as_model,
    can,
    case_demand,
    decisions_delegated,
    ex_ts,
    fmt_dy,
    inbox_requests,
    jg_lc,
    limit_for,
    money,
    next_step,
    priority,
    stage_label,
    ti_conf,
    vis_cases,
)
from di.screens.case import instr_payload
from di.screens.command import af_risks

WORLD = golden.load("world")
ROUTE_NAME = {r["id"]: r["name"] for r in WORLD["routes"]}
# the agent that prepares each action (the demo's AF_AGENT_OF, with its later analytics.models entry); briefer otherwise
AGENT_OF = {
    "case.get": "assembler",
    "case.evidence": "assembler",
    "case.trace": "auditor",
    "case.routes": "finder",
    "case.whatIf": "finder",
    "demand.find": "finder",
    "pool.optimize": "finder",
    "decision.prepare": "finder",
    "decision.submit": "coordinator",
    "evidence.request": "gap",
    "notify.send": "coordinator",
    "escalation.send": "coordinator",
    "outcome.confirm": "reconciler",
    "cases.list": "briefer",
    "inbox.get": "briefer",
    "analytics.query": "analyst",
    "kpi.explain": "analyst",
    "audit.search": "auditor",
    "sources.health": "integrator",
    "workflow.validate": "integrator",
    "access.lookup": "briefer",
    "asset.compare": "assembler",
    "analytics.models": "analyst",
}
CANT = "I can't do that yet. I can:"


class Run:
    """One request's calls (the demo's R.call), as the signed-in person; reads only."""

    def __init__(self, ctx: CallContext, ui: dict, inject: Callable[[str, dict], dict] | None = None):
        self.ctx, self.ui, self.inject = ctx, ui, inject
        self.calls: list[dict] = []
        self.outputs: list[Any] = []

    def call(self, action_id: str, i: dict) -> dict:
        a = ACTIONS.get(action_id)
        clean = {k: v for k, v in i.items() if v is not None and v != ""}
        if a is not None and a.risk != "read":  # Ask never writes: recorded as skipped, as the demo's eval mode does
            res = {"ok": True, "output": {}, "skipped": True}
        else:
            prev = self.ctx.preparer
            self.ctx.preparer = AGENT_OF.get(action_id, "briefer")
            try:
                res = invoke(action_id, clean, self.ctx)
            finally:
                self.ctx.preparer = prev
            if res["ok"] and self.inject:  # tests and data checks: record text planted in what a read returns
                res = {**res, "output": self.inject(action_id, res["output"])}
        self.outputs.append(res["output"] if res["ok"] else res["error"])
        self.calls.append(
            {
                "action": action_id,
                "input": clean,
                "ok": res["ok"],
                "code": None if res["ok"] else res["error"]["code"],
                "message": None if res["ok"] else res["error"]["message"],
                "skipped": bool(res.get("skipped")),
                "output": res["output"] if res["ok"] else None,
            }
        )
        return res

    @property
    def account(self) -> policy.Account:
        return self.ctx.actor.account

    def can(self, perm: str) -> bool:
        return can(self.ctx, perm)

    def all_policy(self) -> bool:
        return bool(policy.policy(self.account).get("all"))

    def case(self, cid: str | None) -> dict | None:
        return store.get(self.ctx.session, cid) if cid else None

    def in_scope(self, c: dict) -> bool:
        a, pctx = self.account, self.ctx.actor.ctx
        return policy.tenant_ok(a, c["owner"], pctx) and policy.location_ok(a, c["location"])


# ---------------------------------------------------------------- the demo's helpers
def err(code: str, message: str) -> dict:
    return fail(code, message)


def scope_err(R: Run, c: dict) -> dict:
    """The demo's afScopeErr."""
    if policy.policy(R.account).get("warehouseScoped"):
        return err("tenant_boundary", f"{c['id']} is at {c['location']}, outside your warehouse.")
    return err("tenant_boundary", f"{c['id']} belongs to {c['owner']}, a tenant you cannot see. Request tenant access first.")


def suggest(ui: dict) -> list[str]:
    """The demo's afSuggest: questions to ask instead (the page's object first, then the role's starters)."""
    role, o, out = ui.get("role") or "Planner", ui.get("object"), []
    if o and o.get("kind") == "case":
        out += [
            f"Explain {o['id']}",
            f"What should we do with {o['id']}, and why?",
            f"Anything risky before I approve {o['id']}?",
        ]
    if o and o.get("kind") == "source" and o.get("id") in SOURCES:
        name = SOURCES[o["id"]]["name"]
        out += [f"Diagnose {name}", f"Map the fields for {name}"]
    return (out + STARTERS.get(role, []))[:4]


def fail1(R: Run, res: dict, text: str | None = None) -> dict:
    """The demo's afFail1: a refusal as text and a can't-do card."""
    e = res["error"]
    sug = suggest(R.ui) if e["code"] in ("tenant_boundary", "out_of_scope") else []
    return {
        "text": text or e["message"],
        "cards": [{"type": "cantdo", "data": {"what": e["message"], "code": e["code"], "suggest": sug}}],
        "result": "refused",
    }


def next_for(R: Run, cid: str) -> list[dict]:
    """The demo's afNextFor: next steps offered under an answer (buttons that ask again, never free text)."""
    c = R.case(cid)
    if not c:
        return []
    st, out = next_step(c, R.ctx), []
    if st["kind"] == "act":
        out.append({"label": st["label"], "ask": f"Next step for {cid}"})
    if st["kind"] == "approve":
        out.append({"label": "Open the approval card", "approve": cid})
    if c.get("recommendation"):
        out += [
            {"label": "Compare the routes", "ask": f"Compare the routes for {cid}"},
            {"label": "Risks before approving", "ask": f"Anything risky before I approve {cid}?"},
        ]
    out.append({"label": "Explain this run", "ask": f"Explain the run for {cid}"})
    return out[:3]


def table_cases(title: str, o: dict, why: bool = False, appr: bool = False) -> dict:
    """The demo's afTableCases."""

    def cells(r: dict) -> list:
        rc = r.get("recommendation")
        if why:
            return [r["id"], r["product"], r["location"], "; ".join(r.get("why") or [])]
        if appr:
            return [
                r["id"],
                rc["plan"] if rc else "—",
                money(rc["net"]) if rc else "—",
                "by " + r["submitted"] if r.get("submitted") else "not yet",
            ]
        miss = f" · missing {len(r['missing'])}" if r["missing"] else ""
        return [r["id"], r["product"], f"{r['location']} · {r['owner']}", r["stage_label"] + miss]

    cols = (
        ["Case", "Product", "Where", "Why first"]
        if why
        else ["Case", "Route", "Value", "Submitted"]
        if appr
        else ["Case", "Product", "Where", "Stage"]
    )
    rows = [{"case_id": r["id"], "cells": cells(r), "open": {"go": "product/" + r["id"]}} for r in o["rows"]]
    return {
        "type": "table",
        "data": {"title": title, "cols": cols, "rows": rows, "total": o["total"], "filters": o.get("filters") or []},
    }


def plan(title: str, steps: list[dict]) -> dict:
    """The demo's afPlan: a plan the person confirms; Ask only shows it."""
    return {
        "type": "plan",
        "data": {"title": title, "steps": steps, "count": len(steps), "costs": sum(s.get("cost") or 0 for s in steps)},
    }


def escalation(c: dict, st: dict | None = None) -> dict:
    """The demo's afEscalation: a drafted message to whoever can unblock the case."""
    b = c.get("blocked")
    owner = b["owner"] if b else st["role"] if st and st.get("role") else "Approver"
    planner = "planner-b" if c["owner"] == "Customer B" else "planner-c" if c["owner"] == "Customer C" else "planner-a"
    to = {
        "Inspection": "engineer",
        "Engineering": "engineer",
        "EAM / PLM": "engineer",
        "Engineer": "engineer",
        "Planner": planner,
        "Approver": "approver",
        "Finance": "finance",
    }.get(owner) or "approver"
    blocker = b["reason"] if b else st["label"] if st else "Blocked"
    return {
        "type": "escalation",
        "data": {
            "case_id": c["id"],
            "blocker": blocker,
            "owner": owner,
            "to": to,
            "msg": f"Please look at {c['id']}: {re.sub(r'[.]$', '', blocker)}.",
        },
    }


def need_case(R: Run, p: dict, what: str) -> dict:
    """The demo's afNeedCase: ask which case, offering the three highest-priority ones in scope."""
    mine = vis_cases(R.ctx, store.all_cases(R.ctx.session))
    top = sorted(mine, key=lambda c: -priority(c)["score"])[:3]
    q = re.sub(r"\b(this|it|that)\b", "", p["raw"], count=1, flags=re.I)
    opts = [{"label": f"{c['id']} · {as_model(c)}", "ask": f"{q} {c['id']}"} for c in top]
    return {
        "result": "clarify",
        "text": "Which case?",
        "cards": [
            {"type": "clarify", "data": {"q": "Which case do you mean" + (f" for {what}" if what else "") + "?", "options": opts}}
        ],
    }


def packet(R: Run, c: dict, rt: dict, ev: dict | None, compact: bool = False) -> dict:
    """The demo's afPacketData: the decision packet for the recommended route."""
    r, M = c["recommendation"], case_demand(c)
    steps = [
        {
            "label": s["label"],
            "sys": s["sys"],
            "app": s["app"],
            "doc": s["docs"][0],
            "planned": s["planned"],
            "owner": s["owner"],
            "lim": s["lim"],
            "act": s["act"],
            "esc": s["clock"]["to"] if s.get("clock") and s["clock"].get("level") else None,
        }
        for s in ex_plan(c, r, AS_OF)
    ]
    mv = ex_move(c, r)
    pk = c.get("packet")
    return {
        "case_id": c["id"],
        "product": as_model(c),
        "owner": c["owner"],
        "location": c["location"],
        "stage": c["stage"],
        "stage_label": stage_label(c),
        "submitted": c["submitted"]["by"] if c.get("submitted") else None,
        "approval": c["approval"]["ref"] if c.get("approval") else None,
        "rec": {
            "plan": r["plan"],
            "route": r["id"],
            "net": r["net"],
            "p10": r["p10"],
            "p90": r["p90"],
            "conf": ti_conf(c, r),
            "demand": r.get("demandLabel"),
            "demand_status": r.get("demandStatus"),
        },
        "reason": re.sub(r"\.?$", ".", r["why"], count=1) if r.get("why") else "Highest predicted net among eligible routes.",
        "alts": [{"plan": x["plan"], "net": x["net"], "gap": r["net"] - x["net"]} for x in rt["eligible"][1:4]],
        "excluded": rt["excluded"][:4],
        "gates": [
            {
                "gate": g,
                "state": r["gates"][i],
                "note": (r.get("gateNotes") or [])[i] if i < len(r.get("gateNotes") or []) else "",
            }
            for i, g in enumerate(GATES)
        ],
        "evidence": [{"label": e["label"], "state": e["state"], "system": e.get("system")} for e in ev["items"][:10]]
        if ev
        else [],
        "risks": [x for x in af_risks(c, rt, ev) if x["level"] != "ok"] if ev else [],
        "decider": "Approver" if decisions_delegated(R.ctx) else "Admin",
        "matched": M["order"] if M and M.get("order") else None,
        "instructions": steps,
        "order": {
            "ref": M["order"],
            "line": M["line"],
            "customer": c["owner"],
            "site": loc_name(M["shipTo"]),
            "need": fmt_dy(M["needBy"]),
            "po": M["avoidedPo"],
        }
        if M and M.get("order") and r["id"] == "redeploy"
        else None,
        "move": {
            "stops": mv["stops"],
            "etd": ex_ts(mv["legs"][0]["etd"]),
            "eta": ex_ts(mv["eta"]),
            "slack": mv["slack"],
            "stage": mv["stage"]["why"] if mv.get("stage") else None,
        }
        if mv and mv["legs"]
        else None,
        "whatif": ex_what_if(c, r),
        "value": [{"label": t["label"], "amt": t["amt"], "method": ex_trace(c, r, t)["method"]} for t in r["terms"]],
        "route_ix": next((k for k, x in enumerate(c["routes"]) if x["id"] == r["id"]), -1),
        "tie": rt.get("tie"),
        "compact": compact,
        "draft": {"by": pk["by"], "prep": pk.get("prep"), "rationale": pk.get("rationale")} if pk else None,
        "snapshot": c["snapshot"]["id"] if c.get("snapshot") else None,
    }


def approval_data(R: Run, c: dict, rt: dict) -> dict:
    """The demo's afApprovalData: the approval card the person decides in (Ask never approves)."""
    r, pk = c["recommendation"], c.get("packet")
    lim = limit_for(R.account, R.ctx.actor.ctx)
    return {
        "case_id": c["id"],
        "plan": r["plan"],
        "net": r["net"],
        "p10": r["p10"],
        "p90": r["p90"],
        "payload": instr_payload(c),
        "limit": None if lim == float("inf") else lim,
        "rationale": pk["rationale"] if pk else draft_rationale(c),
        "snapshot": c["snapshot"]["id"] if c.get("snapshot") else None,
        "alts": [{"plan": x["plan"], "net": x["net"]} for x in rt["eligible"][1:4]],
    }


def clean_csv(text: str) -> dict | None:
    """The demo's afCleanCsv (the import.clean draft): normalisations and rejected rows with reasons. Every cell is
    data: a cell that reads like an instruction is just a value that fails the row's checks."""
    lines = [x for x in re.split(r"\r?\n", str(text or "").strip()) if x]
    if len(lines) < 2:
        return None
    hd = [x.strip().lower() for x in lines[0].split(",")]
    norm, rej, out = [], [], [lines[0]]
    for i, line in enumerate(lines[1:]):
        c = [x.strip() for x in line.split(",")]
        o = {h: c[k] if k < len(c) else "" for k, h in enumerate(hd)}
        row, why = i + 2, []
        if re.fullmatch(r"[ABCD]\+", o.get("condition_grade", "")):
            g = o["condition_grade"]
            norm.append({"row": row, "field": "condition_grade", "from": g, "to": g[0], "rule": "Grade table v3 (B+ → B)"})
            o["condition_grade"] = g[0]
        if re.fullmatch(r"\d{4}/\d{2}/\d{2}", o.get("received", "")):
            t = o["received"].replace("/", "-")
            norm.append({"row": row, "field": "received", "from": o["received"], "to": t, "rule": "Date format YYYY-MM-DD"})
            o["received"] = t
        if o.get("location") and o["location"] not in WORLD["facilities"]:
            why.append(f"unknown location “{o['location']}”")
        if not re.fullmatch(r"[1-9]\d*", o.get("qty") or ""):
            why.append("quantity missing or not a whole number")
        if o.get("owner") not in WORLD["tenants"]:
            why.append("owner is not a tenant on this account")
        if not re.fullmatch(r"(MTR|PMP|CTL|DRL|BAT|ITE)-\d{4}", o.get("asset_id") or ""):
            why.append("asset_id does not match a known class pattern")
        if why:
            rej.append({"row": row, "asset": o.get("asset_id"), "reasons": why})
        out.append(",".join(o[h] for h in hd))
    return {"norm": norm, "rejected": rej, "text": "\n".join(out), "rows": len(lines) - 1}


def js_num(n: float) -> str:
    """A number as JavaScript prints it (17.0 -> "17")."""
    return str(int(n)) if isinstance(n, float) and n.is_integer() else str(n)


# ---------------------------------------------------------------- the runners (AF_INTENT_RUN), in the demo's order
def r_briefing(R: Run, p: dict) -> dict:  # noqa: ARG001 - every runner takes (run, params)
    o = R.call("inbox.get", {})["output"]
    lines = o["briefing"]

    def row(i: dict) -> dict:
        go = {"go": i["go"]} if i.get("go") else {"go": "product/" + i["case_id"]} if i.get("case_id") else None
        prim = (
            {"label": i["btn"], "act": i["act"], "arg": i["arg"]}
            if i.get("act")
            else {"label": i["btn"], "go": i["go"]}
            if i.get("go")
            else None
        )
        return {"cells": [i["title"], i["detail"]], "open": go, "primary": prim}

    return {
        "text": f"Here is what needs you, {R.account.label}." if lines else "Nothing needs you right now.",
        "cards": [
            {"type": "briefing", "data": {"lines": lines, "role": R.account.role}},
            {
                "type": "table",
                "data": {
                    "title": "Needs you",
                    "cols": ["Item", "Detail"],
                    "rows": [row(i) for i in o["items"][:8]],
                    "total": o["total"],
                    "filters": [],
                },
            },
        ],
    }


def r_case_explain(R: Run, p: dict) -> dict:
    g = R.call("case.get", {"case_id": p["case"]})
    if not g["ok"]:
        return fail1(R, g)
    ev, c = R.call("case.evidence", {"case_id": p["case"]}), g["output"]
    t = f"{c['id']} is a {c['product']}" + (
        f" (×{c['qty']})" if c["qty"] > 1 else ""
    ) + f" from {c['owner']} at {c['location']}, " f"{c['stage_label'].lower()}. " + (
        f"Grade {c['grade']}" if c.get("grade") else "Not graded yet"
    ) + f"; evidence {c['evidence_ready']} of {c['evidence_total']}" + (
        f" (missing: {', '.join(jg_lc(x) for x in c['missing'])})" if c["missing"] else ""
    ) + "." + (
        f" Recommended: {c['recommendation']['plan']}, {money(c['recommendation']['net'])} predicted net."
        if c.get("recommendation")
        else f" {c['blocked']['reason']}"
        if c.get("blocked")
        else ""
    )
    data = {**c, "evidence": ev["output"]["items"] if ev["ok"] else []}
    return {"text": t, "cards": [{"type": "case", "data": data}], "next": next_for(R, c["id"])}


def r_case_recommend(R: Run, p: dict) -> dict:
    c = R.case(p["case"])
    if c and not R.in_scope(c):
        return fail1(R, scope_err(R, c))
    if c.get("blocked") or not c.get("recommendation"):
        R.call("case.get", {"case_id": p["case"]})
        t = (
            f"I cannot recommend a route for {c['id']} yet: {c['blocked']['reason']}"
            if c.get("blocked")
            else f"No route for {c['id']} passes every gate, so nothing can be recommended. Engineering and policy owners "
            "resolve failed gates; I cannot waive them."
        )
        return {"text": t, "cards": [escalation(c)], "next": next_for(R, c["id"]), "result": "blocked"}
    if R.can("submit") or R.all_policy():
        pr = R.call("decision.prepare", {"case_id": p["case"]})  # a draft: skipped, Ask never writes
        if not pr["ok"] and pr["error"]["code"] != "duplicate":
            return fail1(R, pr)
    rt, ev = R.call("case.routes", {"case_id": p["case"]}), R.call("case.evidence", {"case_id": p["case"]})
    pk = packet(R, c, rt["output"], ev["output"])
    el = rt["output"]["eligible"]
    nx = el[1] if len(el) > 1 else None
    ahead = f", {money(pk['rec']['net'] - nx['net'])} ahead of {nx['plan']}" if nx else ""
    t = f"Recommended for {c['id']}: {pk['rec']['plan']}, {money(pk['rec']['net'])} predicted net{ahead}. {pk['reason']}"
    return {"text": t, "cards": [{"type": "packet", "data": pk}], "next": next_for(R, c["id"])}


def r_queue_prepare(R: Run, p: dict) -> dict:
    days = p.get("days") or (None if re.search(r"top|first", p["t"]) else 7)
    li = R.call(
        "cases.list",
        {
            "received_within_days": days,
            "stage": "awaiting_approval",
            "location": p.get("location"),
            "owner": p.get("owner"),
            "cls": p.get("cls"),
            "sort": "priority",
            "limit": 5,
        },
    )
    if not li["ok"]:
        return fail1(R, li)
    rows = [r for r in li["output"]["rows"] if not r.get("submitted")]
    if not rows:
        empty = {"title": "Cases", "cols": ["Case"], "rows": [], "total": 0, "filters": li["output"]["filters"]}
        return {"text": "No case in that set waits for a decision packet.", "cards": [{"type": "table", "data": empty}]}
    cards = []
    for r in rows:
        c = R.case(r["id"])
        if R.can("submit") or R.all_policy():
            R.call("decision.prepare", {"case_id": r["id"]})  # skipped: the packets stay unsaved drafts
        rt = R.call("case.routes", {"case_id": r["id"]})
        if rt["ok"]:
            cards.append({"type": "packet", "data": packet(R, c, rt["output"], None, True)})
    n = len(cards)
    t = (
        f"I prepared {n} decision packet{'s' if n > 1 else ''} as drafts, highest priority first. "
        "Nothing is submitted until you press Submit."
    )
    return {"text": t, "cards": cards}


def r_case_compare(R: Run, p: dict) -> dict:
    rt = R.call("case.routes", {"case_id": p["case"]})
    if not rt["ok"]:
        return fail1(R, rt)
    o = rt["output"]
    el = o["eligible"]
    if not el:
        return {
            "text": f"No route for {o['case_id']} is eligible" + (f": {o['blocked']['reason']}" if o.get("blocked") else "."),
            "cards": [{"type": "routes", "data": o}],
        }
    n = len(el)
    ahead = f", {money(el[0]['net'] - el[1]['net'])} ahead of {el[1]['plan']}" if n > 1 else ""
    t = (
        f"{n} eligible route{'s' if n > 1 else ''} for {o['case_id']}; {el[0]['plan']} leads at {money(el[0]['net'])}{ahead}. "
        f"{len(o['excluded'])} excluded by a gate."
    )
    return {"text": t, "cards": [{"type": "routes", "data": o}], "next": next_for(R, o["case_id"])}


def _route_name(rid: str) -> str:
    return ROUTE_NAME.get(rid, rid)


def r_case_whynot(R: Run, p: dict) -> dict:
    rt = R.call("case.routes", {"case_id": p["case"]})
    if not rt["ok"]:
        return fail1(R, rt)
    o = rt["output"]
    want = next((x for x in p["routes"] if x != "hold"), None)
    gate_q, items = bool(re.search(r"gate", p["t"])), []
    el, b = o["eligible"], o.get("blocked")
    if b and (not want or gate_q):
        text = f"{o['case_id']} is held at the {b['gate']} gate: {b['reason']}"
        items.append({"term": b["gate"] + " gate", "detail": b["reason"], "cite": "Gate engine (rules)"})
    elif not want:
        r = el[0] if el else None
        if not r:
            text = f"No route is eligible for {o['case_id']}."
        else:
            n = el[1] if len(el) > 1 else None
            text = (
                f"{r['plan']} ranks first at {money(r['net'])}"
                + (f", {money(r['net'] - n['net'])} ahead of {n['plan']}" if n else "")
                + "."
                + (" " + o["tie"]["text"] if o.get("tie") else "")
                + (f" The ranking changes if {jg_lc(o['flips'][0]['txt'])}." if o.get("flips") else "")
            )
            for t in r["terms"]:
                sign = "−" if t["amt"] < 0 else "+"
                kind = "model" if t.get("kind") in ("purchase", "sale") else "rules"
                items.append(
                    {"term": t["label"], "detail": sign + money(abs(t["amt"])).replace("−", "", 1), "cite": f"Cost line ({kind})"}
                )
            if o.get("tie"):
                items.append({"term": "Tie-break", "detail": o["tie"]["text"], "cite": "Tie-break rules"})
    else:
        ex = next((x for x in o["excluded"] if x["route"] == want), None)
        hit = next((x for x in el if x["route"] == want), None)
        top = el[0] if el else None
        if ex:
            text = f"{ex['plan']} is not eligible for {o['case_id']}: the {ex['gate']} gate failed. {ex['reason']}."
            items.append({"term": ex["gate"] + " gate", "detail": ex["reason"], "cite": "Gate engine (rules)"})
        elif hit and top and hit["route"] == top["route"]:
            text = f"{hit['plan']} is already the recommendation, at {money(hit['net'])}."
        elif hit:
            gap = top["net"] - hit["net"]
            text = (
                f"{hit['plan']} is eligible but gives {money(hit['net'])}, "
                f"{money(gap)} below {top['plan']} ({money(top['net'])})."
                + (" " + o["tie"]["text"] if o.get("tie") and o["tie"].get("text") else "")
            )

            def tm(t: dict) -> float:
                return next((x for x in top["terms"] if x.get("kind") == t.get("kind")), {"amt": 0})["amt"]

            for t in hit["terms"]:
                items.append(
                    {
                        "term": t["label"],
                        "detail": f"{money(t['amt'])} here against {money(tm(t))} for {top['plan']}",
                        "cite": "Cost line",
                    }
                )
        else:
            text = f"No {_route_name(want).lower()} route was built for {o['case_id']}."
    title = "Why not " + _route_name(want).lower() if want else "Why this route"
    card = {"type": "explain", "data": {"case_id": o["case_id"], "title": title, "text": text, "items": items}}
    return {"text": text, "cards": [card], "next": next_for(R, o["case_id"])}


def r_gate_waive(R: Run, p: dict) -> dict:
    cid = p.get("case")
    sug = ([f"Why did {cid} fail the gate?", f"Who owns {cid}? Draft an escalation for {cid}"] if cid else []) + suggest(R.ui)
    return {
        "text": "I cannot waive a failed gate, and nobody can from here: failed gates are resolved by engineering and policy "
        "owners, then the case is re-evaluated. I can:",
        "result": "refused",
        "cards": [
            {
                "type": "cantdo",
                "data": {
                    "what": "Waive a failed gate or approve an excluded route (hard rule).",
                    "code": "out_of_scope",
                    "suggest": sug[:4],
                },
            }
        ],
    }


def r_case_whatif(R: Run, p: dict) -> dict:
    wi = p.get("whatif") or {}
    cid = p["case"]
    if not p.get("whatif") and not p.get("demandOff"):
        opts = [
            ("Repair costs 30% more", f"What if repair costs 30% more for {cid}"),
            ("Market price falls 20%", f"What if the market price falls 20% for {cid}"),
            ("Confirmed demand is cancelled", f"What if the confirmed demand is cancelled for {cid}"),
        ]
        return {
            "text": "Which assumption should change? For example: “what if repair costs 30% more”.",
            "result": "clarify",
            "cards": [
                {"type": "clarify", "data": {"q": "Which assumption?", "options": [{"label": a, "ask": b} for a, b in opts]}}
            ],
        }
    inp: dict[str, Any] = {"case_id": cid}
    if wi.get("factor"):
        inp[wi["factor"]] = wi["mult"]
    if p.get("demandOff"):
        inp["demandOff"] = True
    r = R.call("case.whatIf", inp)
    if not r["ok"]:
        return fail1(R, r)
    o = r["output"]
    lbl = {"cost": "prep and fees", "purchase": "purchase price", "service": "service", "market": "market price"}.get(
        wi.get("factor"), ""
    )
    head = f"With {lbl} {'+' if wi['pct'] > 0 else ''}{wi['pct']}%" if lbl else "With the confirmed demand cancelled"
    sim = f"{o['sim']['plan']} gives {money(o['sim']['net'])}" if o.get("sim") else "no route stays eligible"
    rank = f"; the ranking changes from {o['base']['plan']}" if o.get("rank_changed") else "; the ranking does not change"
    return {
        "text": f"{head}, {sim}{rank}. The approved decision is unchanged.",
        "cards": [{"type": "whatif", "data": o}],
        "next": next_for(R, o["case_id"]),
    }


def r_case_risk(R: Run, p: dict) -> dict:
    g = R.call("case.get", {"case_id": p["case"]})
    if not g["ok"]:
        return fail1(R, g)
    rt, ev = R.call("case.routes", {"case_id": p["case"]}), R.call("case.evidence", {"case_id": p["case"]})
    items = af_risks(R.case(p["case"]), rt["output"], ev["output"])
    n = sum(1 for i in items if i["level"] != "ok")
    t = (
        f"{n} thing{'s' if n > 1 else ''} to check before approving {p['case']}."
        if n
        else f"Nothing risky found for {p['case']}: gates pass, evidence is current and demand is confirmed."
    )
    return {
        "text": t,
        "cards": [{"type": "risk", "data": {"case_id": p["case"], "items": items}}],
        "next": next_for(R, p["case"]),
    }


def r_case_submit(R: Run, p: dict) -> dict:
    c = R.case(p["case"])
    if not R.in_scope(c):
        return fail1(R, scope_err(R, c))
    if not R.can("submit"):
        return fail1(
            R, err("out_of_scope", f"The {R.account.role} view cannot submit decisions. A Planner submits; an Approver decides.")
        )
    if c["stage"] != "awaiting_approval" or c.get("submitted"):
        t = (
            f"{c['id']} is already submitted, by {c['submitted']['by']}."
            if c.get("submitted")
            else f"{c['id']} is not awaiting a decision ({stage_label(c).lower()})."
        )
        return {"text": t, "cards": []}
    r = c["recommendation"]
    step = {
        "action": "decision.submit",
        "input": {"case_id": c["id"]},
        "label": f"Submit {c['id']} ({r['plan']}, {money(r['net'])}) to the Approver queue",
        "records": [c["id"]],
        "systems": ["Circularity"],
        "undo": "Can be undone until an Approver decides",
    }
    return {
        "text": "Here is the plan. Nothing happens until you confirm.",
        "cards": [plan(f"Submit {c['id']} for review", [step])],
    }


def r_case_approve(R: Run, p: dict) -> dict:
    c = R.case(p["case"])
    if not R.in_scope(c):
        return fail1(R, scope_err(R, c))
    if not R.can("approve"):
        who = "An Approver" if decisions_delegated(R.ctx) else "Admin"
        return fail1(R, err("out_of_scope", f"The {R.account.role} view cannot approve. {who} decides."))
    if c["stage"] != "awaiting_approval":
        return {"text": f"{c['id']} is not awaiting approval ({stage_label(c).lower()}).", "cards": []}
    rt = R.call("case.routes", {"case_id": c["id"]})
    return {
        "text": f"I do not approve anything from text. Here is the approval card for {c['id']}; you press the final button.",
        "cards": [{"type": "approval", "data": approval_data(R, c, rt["output"])}],
    }


def r_case_record(R: Run, p: dict) -> dict:
    c = R.case(p["case"])
    if not R.can("assess"):
        return fail1(R, err("out_of_scope", "Only the Engineer records inspection results."))
    if not c.get("blocked") and c.get("assessment") == "Ready":
        return {"text": f"{c['id']} is already assessed (grade {c.get('grade')}).", "cards": []}
    step = {
        "action": "evidence.recordResult",
        "input": {"case_id": c["id"]},
        "label": f"Record the inspection result for {c['id']} and rebuild its routes",
        "records": [c["id"]],
        "systems": ["Inspection"],
        "undo": "Can be undone until a decision is approved",
    }
    return {
        "text": "Here is the plan. Recording a result is a person-confirmed step.",
        "cards": [plan(f"Record the result for {c['id']}", [step])],
    }


def r_queue_filter(R: Run, p: dict) -> dict:
    t = p["t"]
    inp: dict[str, Any] = {
        "location": p.get("location"),
        "owner": p.get("owner"),
        "cls": p.get("cls"),
        "received_within_days": p.get("days"),
        "sort": "priority",
        "limit": 25,
    }
    if re.search(r"missing|without|not inspected|gap", t):
        inp["missing"] = True
    if p.get("evidence") and re.search(r"missing|without|not|no ", t):
        inp["evidence"] = p["evidence"]
    if re.search(r"awaiting approval", t):
        inp["stage"] = "awaiting_approval"
    r = R.call("cases.list", inp)
    if not r["ok"]:
        return fail1(R, r)
    o = r["output"]
    n = o["total"]
    nxt = (
        [{"label": "Request evidence for all of them", "ask": "Request evidence for all of them"}]
        if n and inp.get("missing")
        else []
    )
    return {
        "text": f"{n} case{'' if n == 1 else 's'} match{'es' if n == 1 else ''}.",
        "cards": [table_cases("Matching cases", o)],
        "next": nxt,
    }


def r_queue_triage(R: Run, p: dict) -> dict:
    r = R.call(
        "cases.list",
        {"location": p.get("location"), "owner": p.get("owner"), "cls": p.get("cls"), "sort": "priority", "limit": 8},
    )
    if not r["ok"]:
        return fail1(R, r)
    o = r["output"]
    rows = o["rows"]
    t = (
        f"Start with {rows[0]['id']}: {(rows[0].get('why') or ['highest priority'])[0] or 'highest priority'}. "
        f"Here are the top {len(rows)}, each with its reason."
        if rows
        else "Nothing in your scope needs attention."
    )
    return {"text": t, "cards": [table_cases("Look at these first", o, why=True)]}


def r_approvals_inbox(R: Run, p: dict) -> dict:  # noqa: ARG001 - every runner takes (run, params)
    s = R.call("cases.list", {"stage": "awaiting_approval", "submitted": True, "sort": "value", "limit": 25})
    if not s["ok"]:
        return fail1(R, s)
    u = R.call("cases.list", {"stage": "awaiting_approval", "submitted": False, "sort": "value", "limit": 12})
    rq = inbox_requests(R.ctx) if R.can("approve") or R.all_policy() else []
    sub, un = s["output"], u["output"]
    head = (
        f"{sub['total']} submitted decision{'s wait' if sub['total'] > 1 else ' waits'} for approval, "
        f"{money(sub['value_total'])} in total"
        if sub["total"]
        else "No submitted decision waits for approval"
    )
    more = f" {len(rq)} access request{'s' if len(rq) > 1 else ''} too." if rq else ""
    t = f"{head}; {un['total']} more are awaiting a Planner's submission.{more}"
    o = {
        "rows": (sub["rows"] + un["rows"])[:12],
        "total": sub["total"] + un["total"],
        "filters": [{"k": "stage", "v": "awaiting approval"}],
    }
    return {"text": t, "cards": [table_cases("Approvals, by value", o, appr=True)]}


def r_outcome_reconcile(R: Run, p: dict) -> dict:
    c = R.case(p["case"])
    if not R.in_scope(c):
        return fail1(R, scope_err(R, c))
    tr, g = R.call("case.trace", {"case_id": c["id"]}), R.call("case.get", {"case_id": c["id"]})
    oc = g["output"].get("outcome") if g["ok"] else None
    if not oc:
        st = tr["output"]["stage"]
        name = AF_STAGES[min(st, 10) - 1].lower() if 1 <= min(st, 10) <= 10 else ""
        return {
            "text": f"{c['id']} has no confirmed outcome yet; it is at stage {st}, {name}.",
            "cards": [{"type": "stages", "data": tr["output"]}],
        }
    sign = "+" if oc["variance"] >= 0 else "−"
    return {
        "text": f"Predicted {money(oc['pred'])}, actual {money(oc['act'])} for {c['id']} ({sign}{money(abs(oc['variance']))}).",
        "cards": [
            {
                "type": "reconcile",
                "data": {
                    "case_id": c["id"],
                    "plan": oc["plan"],
                    "pred": oc["pred"],
                    "act": oc["act"],
                    "order": oc["order"],
                    "lines": oc["lines"],
                },
            }
        ],
    }


def r_outcome_list(R: Run, p: dict) -> dict:  # noqa: ARG001 - every runner takes (run, params)
    r = R.call("cases.list", {"stage": "closed", "limit": 25})
    if not r["ok"]:
        return fail1(R, r)
    rows = [x for x in r["output"]["rows"] if not (R.case(x["id"]) or {}).get("outcome")]
    n = len(rows)
    t = (
        f"{n} outcome{'s are' if n > 1 else ' is'} reported and waiting for Finance to confirm."
        if n
        else "No reported outcome waits for confirmation."
    )
    o = {"rows": rows, "total": n, "filters": [{"k": "stage", "v": "outcome reported"}]}
    return {"text": t, "cards": [table_cases("Outcomes to confirm", o)]}


def r_analytics_explain(R: Run, p: dict) -> dict:
    obj = R.ui.get("object")
    k = (
        obj["id"]
        if obj and obj.get("kind") == "kpi"
        else "variance"
        if re.search(r"variance", p["t"])
        else "risk"
        if re.search(r"risk", p["t"])
        else "recovery"
    )
    r = R.call("kpi.explain", {"kpi": k})
    if not r["ok"]:
        return fail1(R, r)
    o = r["output"]
    return {"text": f"{o['label']}: {o['value_text']}. {o['definition']}", "cards": [{"type": "kpi", "data": o}]}


def r_exceptions_top(R: Run, p: dict) -> dict:  # noqa: ARG001 - every runner takes (run, params)
    r = R.call("kpi.explain", {"kpi": "risk"})
    if not r["ok"]:
        return fail1(R, r)
    o = r["output"]
    t = (o.get("top") or [None])[0]
    text = (
        f"The biggest value at risk is {t['label']}: {money(t['value'])}; owner {t['owner']}."
        if t
        else "No value at risk in your scope."
    )
    nxt = (
        [{"label": f"Draft a notification to {t['owner']}", "ask": f"Draft a notification to the owner of {t['label']}"}]
        if t and R.can("notify")
        else []
    )
    return {"text": text, "cards": [{"type": "kpi", "data": o}], "next": nxt}


def r_access_who(R: Run, p: dict) -> dict:
    amt = p.get("amount") or 0
    r = R.call("access.lookup", {"perm": "approve", "amount": amt})
    if not r["ok"]:
        return fail1(R, r)
    rows = r["output"]["rows"]

    def lim(x: dict) -> str:
        v = x.get("limit")
        return "Unlimited" if v is None else money(v)

    text = (
        ", ".join(x["label"] for x in rows) + " can approve " + (f"above {money(amt)}" if amt else "decisions") + "."
        if rows
        else f"Nobody can approve above {money(amt)} with the current limits."
    )
    data = {
        "title": "Who can approve" + (f" above {money(amt)}" if amt else ""),
        "cols": ["Account", "Role", "Approval limit", "How"],
        "rows": [{"cells": [x["label"], x["role"], lim(x), x["how"]]} for x in rows],
        "total": len(rows),
        "filters": [{"k": "amount", "v": money(amt) if amt else "any"}],
    }
    return {"text": text, "cards": [{"type": "table", "data": data}]}


def r_run_explain(R: Run, p: dict) -> dict:
    r = R.call("case.trace", {"case_id": p["case"]})
    if not r["ok"]:
        return fail1(R, r)
    o = r["output"]
    where = " (complete)" if o["stage"] > 10 else ", " + AF_STAGES[o["stage"] - 1].lower()
    return {
        "text": f"{o['id']} for {p['case']} is at stage {min(o['stage'], 10)}{where}. {o['next']['label']}.",
        "cards": [{"type": "stages", "data": o}],
        "next": next_for(R, p["case"]),
    }


def r_expected_plan(R: Run, p: dict) -> dict:  # noqa: ARG001 - every runner takes (run, params)
    r = R.call("receiving.plan", {})
    if not r["ok"]:
        return fail1(R, r)
    o = r["output"]
    over = "; over capacity in " + ", ".join(o["over"]) if o["over"] else "; no week is over capacity"
    rows = [
        {"cells": [x["wh"], x["week"], str(x["n"]), str(x["cap"]), f"{x['load']}%"], "warn": x["load"] > 100} for x in o["rows"]
    ]
    return {
        "text": f"{o['total']} return{'' if o['total'] == 1 else 's'} expected{over}. This is a draft plan; nothing is booked.",
        "cards": [
            {
                "type": "table",
                "data": {
                    "title": "Receiving plan (draft)",
                    "cols": ["Warehouse", "Week", "Expected", "Capacity", "Load"],
                    "rows": rows,
                    "total": len(o["rows"]),
                    "filters": [],
                },
            }
        ],
    }


def r_wms_stuck(R: Run, p: dict) -> dict:  # noqa: ARG001 - every runner takes (run, params)
    r = R.call("cases.list", {"stage": "executing", "limit": 50})
    if not r["ok"]:
        return fail1(R, r)

    def on_wms(x: dict) -> bool:
        c = R.case(x["id"]) or {}
        s = next((y for y in (c.get("exec") or {}).get("steps") or [] if y["state"] == "active"), None)
        return bool(s and re.match(r"WMS", s["sys"]))

    rows = [x for x in r["output"]["rows"] if on_wms(x)]
    n = len(rows)
    o = {"rows": rows, "total": n, "filters": [{"k": "waiting on", "v": "WMS"}]}
    return {
        "text": f"{n} handed-off item{' is' if n == 1 else 's are'} waiting on WMS.",
        "cards": [table_cases("Waiting on WMS", o)],
    }


def r_asset_compare(R: Run, p: dict) -> dict:
    r = R.call("asset.compare", {"case_id": p["case"]})
    if not r["ok"]:
        return fail1(R, r)
    o = r["output"]
    rows = [
        {
            "case_id": x["id"],
            "cells": [
                x["id"],
                f"{x['location']} · {x['owner']}",
                x["grade"],
                x["route"],
                "—" if x["net"] is None else money(x["net"]),
            ],
            "open": {"go": "product/asset/" + x["id"]},
        }
        for x in o["rows"]
    ]
    return {
        "text": f"{o['total']} other unit{'' if o['total'] == 1 else 's'} of {o['model']} in your scope.",
        "cards": [
            {
                "type": "table",
                "data": {
                    "title": "Similar assets · " + o["model"],
                    "cols": ["Case", "Where", "Grade", "Route", "Net"],
                    "rows": rows,
                    "total": o["total"],
                    "filters": [{"k": "model", "v": o["model"]}],
                },
            }
        ],
    }


def r_analytics_accuracy(R: Run, p: dict) -> dict:  # noqa: ARG001 - every runner takes (run, params)
    r = R.call("analytics.models", {})
    if not r["ok"]:
        return fail1(R, r)
    o = r["output"]
    a, b = o["versions"][0], o["versions"][-1]
    t = (
        "Every reconciled decision is scored against its prediction. "
        f"Error fell from {js_num(a['error_pct'])}% on {a['version']} to {js_num(b['error_pct'])}% on {b['version']}, "
        f"and {js_num(o['within_band_pct'])}% of {o['decisions']:,} decisions landed within ±{js_num(o['band_pct'])}%."
    )
    return {"text": t, "cards": [{"type": "cxacc", "data": o}]}


RUNNERS: dict[str, Callable[[Run, dict], dict]] = {
    "briefing": r_briefing,
    "case.explain": r_case_explain,
    "case.recommend": r_case_recommend,
    "queue.prepare": r_queue_prepare,
    "case.compare": r_case_compare,
    "case.whynot": r_case_whynot,
    "gate.waive": r_gate_waive,
    "case.whatif": r_case_whatif,
    "case.risk": r_case_risk,
    "case.submit": r_case_submit,
    "case.approve": r_case_approve,
    "case.record": r_case_record,
    "queue.filter": r_queue_filter,
    "queue.triage": r_queue_triage,
    "approvals.inbox": r_approvals_inbox,
    "outcome.reconcile": r_outcome_reconcile,
    "outcome.list": r_outcome_list,
    "analytics.explain": r_analytics_explain,
    "exceptions.top": r_exceptions_top,
    "access.who": r_access_who,
    "run.explain": r_run_explain,
    "expected.plan": r_expected_plan,
    "wms.stuck": r_wms_stuck,
    "asset.compare": r_asset_compare,
    "analytics.accuracy": r_analytics_accuracy,
}
assert set(RUNNERS) <= set(INTENT), "every runner belongs to an intent in the catalog"  # noqa: S101 - import-time check of the catalog


# ---------------------------------------------------------------- one request (afAsk)
def ask_rule(text: str, ctx: CallContext, ui: dict, inject: Callable[[str, dict], dict] | None = None) -> dict:
    """The demo's afAsk without a model: match, run reads through the pipeline, compose. `ui` is the page context:
    {page, role, object: {kind, id} | None}. `inject` (tests, data checks) may rewrite what a read returns."""
    R = Run(ctx, ui, inject)
    obj = ui.get("object")
    p = parse(text, obj, {c["id"] for c in store.all_cases(ctx.session)})
    hits = match(p, obj)
    intent, result = None, "ok"
    if IGNORE_RULES.search(str(text)):
        out = {
            "text": "I follow the product rules for every request; text that asks me to ignore them changes nothing. I can:",
            "cards": [{"type": "cantdo", "data": {"what": "Change my rules or skip an approval", "suggest": suggest(ui)}}],
        }
    elif not hits:
        result = "fallback"
        out = {"text": CANT, "cards": [{"type": "cantdo", "data": {"what": str(text)[:120], "suggest": suggest(ui)}}]}
    else:
        a, b = hits[0], hits[1] if len(hits) > 1 else None
        if (
            b
            and a.intent.area != b.intent.area
            and a.s - b.s < 0.25
            and not (a.intent.need == "case" and p.get("case") and b.intent.need != "case")
        ):
            result = "clarify"
            opts = [
                {"label": i.title, "ask": i.title + (" " + p["case"] if p.get("case") else ""), "intent": i.id}
                for i in (a.intent, b.intent)
            ]
            out = {
                "text": "Do you mean one of these?",
                "cards": [{"type": "clarify", "data": {"q": "Which did you mean?", "options": opts}}],
            }
        else:
            intent = a.intent.id
            if a.intent.need == "case" and not p.get("case"):
                out = need_case(R, p, a.intent.title.lower())
            elif intent in RUNNERS:
                out = RUNNERS[intent](R, p)
            else:
                out = {
                    "text": CANT,
                    "result": "fallback",
                    "cards": [
                        {
                            "type": "cantdo",
                            "data": {
                                "what": a.intent.title,
                                "suggest": suggest(ui),
                                "why": "This one runs in the browser demo; the server cannot do it yet.",
                            },
                        }
                    ],
                }
    return {
        "intent": intent,
        "result": out.get("result") or result,
        "text": out["text"],
        "cards": out.get("cards") or [],
        "next": out.get("next") or [],
        "calls": R.calls,
    }
