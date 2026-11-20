"""Process orchestration (B14): the cases behind the screen, and one case's run as the live board plays it.

GET /api/screens/orchestration/cases?tenant=All
    The cases the page can show (the account's cases; for an account without case pages, those in view with the
    top-bar tenant filter), each in brief, and the case shown first (RT-1048 when in scope, else the first).
GET /api/screens/orchestration/run/{id}?fail=
    One case's run: the ten stages with their activity lines (agent tool calls, people's steps, queued steps), when
    each stage and line plays (ms), the run's signature, the models each stage used, the next step for this person
    and the escalation it would draft, the case's journal, agent calls and events, and its trace id. `fail` is the
    presenter's failure drill (0-based stage index that times out; empty: off).

Refuses as the case actions do: 403 out_of_scope without the page, 404 not_found, 403 tenant_boundary.

Facade (apps/web/src/api/orchestration.ts) → this API
| export | served by |
|---|---|
| orCases | /cases → cases |
| orCase | /cases → default (the picked case is view state, S.or.case) |
| orCaseById | /cases → cases (by id) |
| setOrCase, failDrill | frontend-only (view state S.or; the drill is passed as ?fail=) |
| runModel | /run/{id} → model (run, st, cur) |
| runTimeline | /run/{id} → timeline (segs, total) |
| runSignature | /run/{id} → sig |
| LR_PACE | reference (the board's pacing constants) |
| runStates | reference (RUN_ST) |
| stageModels | /run/{id} → stage_models[n-1] (key, version, validation); algorithm, task and data are reference (LR_MODELS) |
| modelTag | /run/{id} → stage_models (key and version) with LR_MODELS[k].algo (reference) |
| nextStep | /run/{id} → next |
| runNext | action (the step's action through POST /api/actions) |
| escalationDraft | /run/{id} → escalation (with toLabel) |
| sendEscalation | action escalation.send |
| caseJournal | /run/{id} → journal |
| agentCalls | /run/{id} → agent_calls (the agent runs of this session; none on the server yet, see below) |
| caseEvents | /run/{id} → events |
| inputSummary, orT, orDur | frontend-only (formatting) |
| agents | /cases → agents (id, name, step, scopes, limit; AGENTS is not a reference list, MCP changes it) |
| stageAgent, handoffModel, poolsOn | reference (AF_STAGE_AGENT, HANDOFF_MODEL, FEAT) |
| traceId | /run/{id} → trace_id |

Summary: 27 exports → 16 served (14 by the two endpoints, 2 by actions), 6 reference, 5 frontend-only.

Notes for the switch-over (B17):
- `agent_calls`: the demo lists the tool calls of the agent runs started in this browser session (AF.ui.runs, empty at
  the start). The server has no agent runs yet (the agent layer moves to the server with MCP, B16), so it is always
  an empty list for now.
- The journal entries are the action journal's (see di.reads.case_detail.case_journal: `by` is the account's label,
  `out` the stored output reference).
"""

import re

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from di import policy
from di.auth import Principal, principal
from di.db import get_session
from di.engine.jsmath import js_round, js_sum
from di.engine.routes import GATES
from di.execution import ex_doc_ref, steps_for
from di.execution.trace import learn_ver
from di.reads.case_detail import af_lease, case_journal
from di.reads.common import (
    AS_OF,
    SOURCES,
    Case,
    af_days,
    case_demand,
    case_events,
    case_rul,
    ex_app,
    ex_clock,
    ex_ts,
    fmt_d,
    fmt_dy,
    fmt_n,
    hash_id,
    jg_lc,
    money,
    next_step,
    run,
    step_owner,
    to_fixed,
)
from di.reads.constants import AGENTS
from di.reads.context import call_ctx, load_case, visible_cases
from di.reads.decisions import reconciled
from di.reads.provenance import prov_for

router = APIRouter(prefix="/api/screens/orchestration", tags=["screens: orchestration"])

AGENT_NAMES = {a["id"]: a["name"] for a in AGENTS}
LR_MODEL_VERSIONS = {
    "condition-vision": "v2.1",
    "rul-survival": "v1.4",
    "demand-match": "v2.0",
    "resale-price": "v1.3",
    "prep-cost-time": "v1.3",
    "service-exposure": "v1.2",
    "repair-success": "v1.1",
}
LR_PACE = {"open": 400, "gap": 150, "settle": 300, "min": 900, "span": 500}
RATE_CARD_ID = "RC-2026.2"


def _js(v) -> str:
    """JavaScript's string concatenation of a value (null reads "null")."""
    return "null" if v is None else str(v)


# ---------------------------------------------------------------- the cases
def or_row(c: Case) -> dict:
    return {
        "id": c["id"],
        "product": c["product"],
        "owner": c["owner"],
        "stage": c["stage"],
        "approval": {"ref": c["approval"]["ref"], "by": c["approval"]["by"]} if c.get("approval") else None,
        "submitted": {"by": c["submitted"]["by"]} if c.get("submitted") else None,
        "exec": {"steps": [{"label": s["label"], "state": s["state"]} for s in c["exec"]["steps"]]} if c.get("exec") else None,
        "outcome": {"net": c["outcome"]["net"]} if c.get("outcome") else None,
    }


@router.get("/cases")
def cases(tenant: str = "All", p: Principal = Depends(principal), session: Session = Depends(get_session)):
    """The demo's orCases and orCase."""
    p.require_page("orchestration")
    ctx = call_ctx(p, session)
    cs = visible_cases(ctx) if policy.can_page(p.account, "product", "case") else visible_cases(ctx, tenant)
    default = next((c for c in cs if c["id"] == "RT-1048"), cs[0] if cs else None)
    return {
        "cases": [or_row(c) for c in cs],
        "default": default["id"] if default else None,
        "agents": [{k: a[k] for k in ("id", "name", "step", "scopes", "limit")} for a in AGENTS],
    }


# ---------------------------------------------------------------- the run's activity lines (the demo's afStageLines)
def lr_h(c: Case, k: str) -> int:
    return int(hash_id(c["id"] + "|lr|" + k), 16)


def lr_vendor(sid: str) -> str:
    s = SOURCES.get(sid)
    return s["vendor"] if s else sid


def lr_sys(sys: str | None) -> str:
    """The demo's lrSys: the vendor application behind a step's system."""
    return ex_app({"sys": sys})


def stage_lines(c: Case, n: int, rn: dict, session: Session) -> list[dict]:
    """The demo's afStageLines: what happened in a stage, as agent tool calls (A), people's steps (P) and queued steps (Q),
    done first, at most six."""
    s = rn["stages"][n - 1]
    L = af_lease(c)
    evs = c.get("evidence") or []
    r = c.get("recommendation")
    steps = c["exec"]["steps"] if c.get("exec") else []
    cevs = case_events(session, c["id"])

    def ev(k: str) -> dict | None:
        return next((e for e in evs if e["k"] == k), None)

    def ev_ids(f) -> list[str]:
        return ["AE-" + e["id"] for e in cevs if f(e)]

    def A(agent, tool, sys, verb, what, o=None) -> dict:
        x = {
            "agent": agent,
            "who": AGENT_NAMES.get(agent, agent),
            "tool": tool,
            "sys": sys,
            "verb": verb,
            "what": what or "",
            "ms": 40 + lr_h(c, f"{n}|{verb}") % 460,
            "audit": [],
            "st": "done",
            "model": None,
        }
        return x | (o or {})

    def P(who, verb, what, o=None) -> dict:
        x = {
            "agent": None,
            "who": who,
            "tool": None,
            "sys": who,
            "verb": verb,
            "what": what or "",
            "ms": 0,
            "audit": [],
            "st": "done",
            "model": None,
        }
        return x | (o or {})

    def Q(agent, tool, sys, verb, what=None) -> dict:
        return A(agent, tool, sys, verb, what, {"st": "queued"}) if agent else P(sys, verb, what, {"st": "queued"})

    def F(agent, k, verb, what=None, o=None) -> dict | None:
        e = ev(k)
        if not e:
            return None
        p = prov_for(c, e)
        if p["status"] == "unavailable":
            if o and o.get("need"):
                return A(
                    agent, "get_case_evidence", p["sourceName"], verb, "no record yet: " + e["label"].lower(), {"st": o["need"]}
                )
            return None
        tool = (o or {}).get("tool") or "get_case_evidence"
        what = (p["record"] + " · " if p.get("record") else "") + _js(what or p["value"])
        return A(agent, tool, p.get("vendor") or p["sourceName"], verb, what, {"audit": ["AU-" + p["id"]]})

    def M(agent, tool, k, verb, what, o=None) -> dict:
        return A(agent, tool, "Circularity ML", verb, what, {"model": k} | (o or {}))

    out: list = []
    if n == 1:
        usage = re.sub(r"^\d+", lambda m: fmt_n(int(m[0])), L["usage"])
        out = [
            A(
                "assembler",
                "get_case_evidence",
                lr_vendor("lease"),
                "Read lease contract",
                f"{L['lease']}, ended {fmt_dy(L['end'])}",
            ),
            A("assembler", "get_case_evidence", lr_vendor("crm"), "Read customer intent", L["intent"]),
            A("assembler", "get_case_evidence", lr_vendor("eam"), "Read usage", usage),
            F("assembler", "id", "Verified identity and configuration"),
            A(
                "briefer",
                "cases.list",
                "Circularity",
                "Opened case " + c["id"],
                "briefed the " + (c["owner"] + " Planner" if c.get("owner") else "Planner") + " on Home",
            ),
        ]
    elif n == 2:
        out = [
            A(
                "assembler",
                "get_case_evidence",
                lr_vendor("rl"),
                "Read return authorisation",
                f"{L['rma']} · authorised {fmt_d(L['auth'])}",
            ),
            A(
                "assembler",
                "get_case_evidence",
                lr_vendor("erp"),
                "Read book value and acquisition date",
                f"{money(L['book'])} · acquired {fmt_dy(L['acq'])}",
            ),
            A("finder", "find_demand", lr_vendor("erp"), "Linked replacement order", L["repl"]) if L["repl"] else None,
            A("assembler", "get_case_evidence", lr_vendor("lease"), "Read early-return fee", money(L["fee"]))
            if L["fee"]
            else None,
        ]
    elif n == 3:
        lane = L["lane"]
        out = [
            A("coordinator", "get_case_evidence", lr_vendor("rl"), "Tracked pickup", f"{fmt_d(L['pickup'])}, {L['carrier']}"),
            A("coordinator", "get_case_evidence", lr_vendor("rl"), "Confirmed arrival", fmt_d(L["eta"])),
            A(
                "assembler",
                "get_case_evidence",
                lr_vendor("tms"),
                "Read freight cost",
                f"{money(L['freight'])} · {lane['from']} → {lane['to']} · {RATE_CARD_ID}",
            ),
        ]
    elif n == 4:
        miss = [e for e in evs if e["state"] != "ready"]
        checked = f"{len(evs) - len(miss)} of {len(evs)} present"
        if miss:
            checked += (
                "; missing: "
                + ", ".join(e["label"].lower() for e in miss[:2])
                + (f" and {len(miss) - 2} more" if len(miss) > 2 else "")
            )
        out = [
            F("assembler", "ret", "Matched goods receipt", f"{c['location']}, {fmt_d(c['received'])}"),
            A("gap", "get_case_evidence", "Circularity", "Checked evidence", checked),
            A(
                "briefer",
                "inbox.get",
                "Circularity",
                "Started the holding-cost clock",
                f"{af_days(c['received'])} days so far; flagged on Home",
            ),
        ]
    elif n == 5:
        R = case_rul(c)
        need = "wait" if s["state"] == "running" else "fail" if s["state"] == "warning" else None
        o = {"need": need}
        ph = ev("photo")
        ph_ok = ph and ph["state"] != "missing" and c.get("grade")
        eng = ev("eng")
        if ph_ok:
            pp = prov_for(c, ph)
            conf = to_fixed(0.86 + (lr_h(c, "cv") % 11) / 100, 2)
            photo = M(
                "assembler",
                "get_case_evidence",
                "condition-vision",
                "Graded " + re.sub(r" images?", " photos", pp["value"], count=1),
                f"agrees with grade {c['grade']} · confidence {conf}",
                {"audit": ["AU-" + pp["id"]]},
            )
        else:
            photo = F("assembler", "photo", "Fetched photos", None, o)
        if R:
            audit = ["AU-" + prov_for(c, eng)["id"]] if eng and eng["state"] != "missing" else []
            life = M(
                "assembler",
                "get_case_evidence",
                "rul-survival",
                "Estimated remaining life",
                f"{R['estLow']}–{R['estHigh']} months (engineering: {c['engLife']})",
                {"audit": audit},
            )
        else:
            life = F("assembler", "eng", "Fetched life assessment", None, o)
        out = [
            F("assembler", "insp", "Fetched inspection report", f"grade {c['grade']}" if c.get("grade") else None, o),
            photo,
            F("assembler", "svc", "Fetched service history", None, o),
            life,
            F(
                "assembler",
                "pol",
                "Fetched certification records",
                f"{R['certRef']}, certified {R['certMonths']} months" if R else None,
                o,
            ),
        ]
        out = [x for x in out if x]
        if need:
            b, rq = c["blocked"], c.get("requested")
            out = [x for x in out if x["st"] == "done"][:3] + [x for x in out if x["st"] != "done"][:1]
            if rq:
                ids = ev_ids(lambda e: e.get("type") == "evidence.requested")
                out.append(
                    A(
                        "gap",
                        "request_missing_evidence",
                        b["owner"],
                        b["action"],
                        (rq["ref"] + " · " if rq.get("ref") else "") + "waiting for " + b["owner"],
                        {"st": "wait", "audit": ids},
                    )
                )
            else:
                out.append(
                    P("Gate engine", b["gateName"] + " gate held", f"{b['reason']} · {b['owner']} resolves it", {"st": "fail"})
                )
        else:
            ins = ev_ids(lambda e: e.get("type") == "inspection.result")
            if ins and out:
                out[0]["audit"] = out[0]["audit"] + ins
    elif n == 6:
        if s["state"] == "queued":
            out = [
                Q("finder", "find_demand", lr_vendor("crm"), "Will match demand"),
                Q("finder", "get_case_evidence", lr_vendor("mkt"), "Will fetch comparable sales"),
                Q("finder", "list_eligible_routes", "Gate engine", f"Will run {len(GATES)} gates on every route"),
                Q("finder", "predict_outcomes", "Circularity ML", "Will predict and rank the routes"),
            ]
        else:
            cd, dm = case_demand(c), ev("dem")
            n_ex = sum(1 for x in c["routes"] if x["excluded"])
            stale = (SOURCES.get("mkt") or {}).get("status") == "stale"
            if cd and dm and dm["state"] != "missing":
                pd = prov_for(c, dm)
                demand = M(
                    "finder",
                    "find_demand",
                    "demand-match",
                    "Matched demand",
                    f"{_js(cd['order'])} ({'confirmed' if cd['confirmed'] else 'forecast'}) · {_js(pd.get('record'))} in "
                    + lr_vendor("crm"),
                    {"audit": ["AU-" + pd["id"]]},
                )
            else:
                demand = A("finder", "find_demand", lr_vendor("crm"), "Checked demand", "no open internal requirement")
            nr = len(c["routes"])
            if s["state"] == "done":
                snap = f" · snapshot {c['snapshot']['id']}" if c.get("snapshot") else ""
                last = A(
                    "finder",
                    "optimize_pool",
                    "Circularity",
                    "Decided: recommend " + r["plan"],
                    f"{money(r['net'])} (P10–P90 {money(r['p10'])}–{money(r['p90'])}){snap}",
                )
            elif s["state"] == "failed":
                last = P(
                    "Gate engine",
                    "Every route failed a gate",
                    "human review needed; an agent cannot waive a gate",
                    {"st": "fail"},
                )
            else:
                last = P("Planner", "Re-evaluate", c.get("reevalReason") or "review triggered", {"st": "wait"})
            out = [
                demand,
                F("finder", "mkt", "Fetched comparable sales"),
                F("finder", "cost", "Fetched planned purchase cost"),
                A(
                    "finder",
                    "list_eligible_routes",
                    "Gate engine",
                    f"Ran {len(GATES)} gates on {nr} routes",
                    f"{n_ex} excluded, with the failing gate" if n_ex else "none excluded",
                ),
                M(
                    "finder",
                    "predict_outcomes",
                    "resale-price",
                    "Predicted every route",
                    f"P10–P90 for {nr} routes with resale-price, prep-cost-time and service-exposure",
                )
                if nr
                else None,
                last,
            ]
            if stale and out[1]:
                out[1]["what"] += " · last fresh data"
    elif n == 7:
        if s["state"] == "queued":
            out = [
                Q("auditor", "case.trace", "Circularity", "Will run the pre-approval check"),
                Q("coordinator", "request_approval", "Circularity", "Will draft the rationale"),
                Q(None, None, "Approver", "Will approve, edit or decline"),
            ]
        else:
            snap = f"snapshot {c['snapshot']['id']} · " if c.get("snapshot") else ""
            gates = f"{sum(1 for g in r['gates'] if g == 'pass')} of {len(GATES)} gates passed" if r else "gates"
            prov = sum(1 for e in evs if e["state"] != "missing")
            sub, appr = c.get("submitted"), c.get("approval")
            out = [
                A("auditor", "case.trace", "Circularity", "Pre-approval check", f"{snap}{gates} · {prov} provenance records"),
                A(
                    "coordinator",
                    "request_approval",
                    "Circularity",
                    "Drafted the rationale",
                    f"{r['plan']} · {money(r['net'])}" if r else "",
                ),
                P("Planner", "Submitted for review", "by " + sub["by"]) if sub else None,
                P("Approver", "Override approved" if c.get("override") else "Approved", f"{appr['ref']} · {appr['by']}")
                if s["state"] == "done"
                else P(
                    "Approver",
                    "Waiting for the Approver",
                    "submitted by " + sub["by"] if sub else "waiting for the Planner to submit",
                    {"st": "wait"},
                ),
            ]
    elif n == 8:
        if not c.get("exec") and not r:
            out = [
                Q("coordinator", "send_instruction", lr_vendor("oms"), "Will send the order instruction"),
                Q("coordinator", "send_instruction", lr_vendor("repair"), "Will send the repair order"),
                Q("coordinator", "send_instruction", lr_vendor("wms"), "Will send the stock movement"),
            ]
        elif not c.get("exec"):
            out = [
                Q(
                    "coordinator",
                    "send_instruction",
                    lr_sys(t["sys"]),
                    "Will send: " + t["label"].lower(),
                    f"{ex_doc_ref(c, t)} to be created · {step_owner(c, t)}",
                )
                for t in steps_for(r, -1)[:-1]
            ]
        else:
            for t in steps[:-1]:
                if t["state"] == "done":
                    ids = ev_ids(lambda e, t=t: e.get("dest") == t["sys"])
                    out.append(
                        A(
                            "coordinator",
                            "send_instruction",
                            lr_sys(t["sys"]),
                            t["label"] + " acknowledged",
                            (t["ack"]["ref"] + " · " if t.get("ack") else "") + step_owner(c, t),
                            {"audit": ids},
                        )
                    )
                elif t["state"] == "active":
                    k = ex_clock(c, t)
                    due = k["due"] if k else None
                    out.append(
                        A(
                            "coordinator",
                            "send_instruction",
                            lr_sys(t["sys"]),
                            t["label"] + " sent",
                            f"awaiting acknowledgement · {step_owner(c, t)} · due " + ex_ts(due if due is not None else AS_OF),
                            {"st": "wait"},
                        )
                    )
                else:
                    out.append(
                        Q(
                            "coordinator",
                            "send_instruction",
                            lr_sys(t["sys"]),
                            "Will send: " + t["label"].lower(),
                            f"{ex_doc_ref(c, t)} to be created",
                        )
                    )
            a = next((t for t in steps if t["state"] == "active"), None)
            k = ex_clock(c, a) if a else None
            if k and k["level"]:
                ids = ev_ids(lambda e: e.get("type") == "handoff.escalated")
                at = ex_ts(k["due2"] if k["level"] == 2 else k["due"])
                out.insert(
                    0,
                    P(
                        k["to"],
                        "Escalated: " + jg_lc(a["label"]),
                        f"{ex_app(a)} passed its {k['lim']} limit at {at} · owner {step_owner(c, a)}",
                        {"st": "wait", "audit": ids},
                    ),
                )
    elif n == 9:
        t = steps[-1] if steps else None
        o9 = c.get("outcome")
        if s["state"] == "queued":
            out = [
                Q("reconciler", "reconcile_outcome", lr_vendor("erp"), "Will collect the actual result"),
                Q(None, None, "Finance", "Will confirm the outcome"),
            ]
        else:
            if t and t.get("ack"):
                ids = ev_ids(lambda e: e.get("dest") == t["sys"])
                first = A(
                    "reconciler",
                    "reconcile_outcome",
                    lr_sys(t["sys"]),
                    "Collected the actual result",
                    t["ack"]["ref"] + (" · " + money(o9["net"]) if o9 else ""),
                    {"audit": ids},
                )
            else:
                first = A(
                    "reconciler",
                    "reconcile_outcome",
                    lr_sys(t["sys"] if t else "ERP"),
                    "Waiting for the actual result",
                    "",
                    {"st": "wait"},
                )
            out = [
                first,
                A(
                    "reconciler",
                    "reconcile_outcome",
                    "Circularity",
                    "Matched the result to the decision",
                    "DI-2026-" + c["id"][3:],
                )
                if o9
                else None,
                P("Finance", "Confirmed the outcome", f"{money(o9['net'])} · {o9.get('by') or 'Finance'}")
                if o9
                else P("Finance", "Waiting for Finance to confirm", "", {"st": "wait"})
                if t and t.get("ack")
                else None,
            ]
    else:
        o10 = c.get("outcome")
        if not o10:
            out = [
                Q("reconciler", "reconcile_outcome", "Circularity", "Will compare predicted and actual"),
                Q("analyst", "get_model_validation", "Circularity ML", "Will validate the models against the outcome"),
                Q("reconciler", "reconcile_outcome", "Circularity", "Will propose learning records"),
            ]
        else:
            ls, cd = o10.get("lines") or [], case_demand(c)
            lr = sum(1 for x in ls if x.get("model"))
            out = [
                A("reconciler", "reconcile_outcome", "Circularity", f"Compared {len(ls)} cost lines", "predicted against actual"),
                M(
                    "analyst",
                    "get_model_validation",
                    "resale-price",
                    "Validated the model",
                    "this outcome joins its validation set",
                ),
                A(
                    "reconciler",
                    "reconcile_outcome",
                    "Circularity",
                    f"Proposed {lr} learning records",
                    "queued for the next retraining, for review",
                ),
                A(
                    "finder",
                    "find_demand",
                    "Circularity",
                    "Carried forward open demand",
                    cd["order"] if cd and not cd["confirmed"] else "none open",
                ),
            ]
    out = [x for x in out if x]
    return ([x for x in out if x["st"] == "done"] + [x for x in out if x["st"] != "done"])[:6]


# ---------------------------------------------------------------- the live board (the demo's lrModel, lrTimeline, lrSig)
def lr_model(c: Case, rn: dict, fail: str, session: Session) -> dict:
    """The demo's lrModel: the ten stages with their lines; the failure drill times out one stage and queues the rest."""
    f = -1 if fail in ("", None) else int(fail)
    st = [
        {
            "n": i + 1,
            "t": s["t"],
            "state": s["state"],
            "result": s.get("result") or "",
            "by": s.get("by") or "",
            "at": s.get("at"),
            "blocked": s.get("blocked"),
            "lines": stage_lines(c, i + 1, rn, session),
        }
        for i, s in enumerate(rn["stages"])
    ]
    cur = min(rn["stage"], 10)
    if 0 <= f < cur:
        x = st[f]
        last = x["lines"][-1] if x["lines"] else None
        x["state"] = "failed"
        x["result"] = f"No response from {last['sys'] if last else 'the source'}; the stage timed out after 30 s"
        if last:
            last.update(st="fail", what="no response · timed out after 30 s", audit=[])
        for y in st[f + 1 :]:
            y["state"] = "queued"
            for ln in y["lines"]:
                ln["st"] = "queued"
        cur = f + 1
    return {"run": rn, "st": st, "cur": cur}


def lr_timeline(c: Case, m: dict) -> dict:
    """The demo's lrTimeline: when each stage opens and each line lands, in ms."""
    t, segs = 0, []
    for n in range(1, m["cur"] + 1):
        seg = {"n": n, "start": t, "lines": []}
        t += LR_PACE["open"]
        for i, _ in enumerate(m["st"][n - 1]["lines"]):
            d = LR_PACE["min"] + lr_h(c, f"t{n}|{i}") % LR_PACE["span"]
            seg["lines"].append({"start": t, "land": t + d})
            t += d + LR_PACE["gap"]
        seg["end"] = t
        if n < m["cur"]:
            t += LR_PACE["settle"]
        segs.append(seg)
    return {"segs": segs, "total": t}


def stage_models(c: Case, n: int, lines: list[dict]) -> list[dict]:
    """The demo's lrStageModels with lrModelVer: the models a stage used, and their versions."""
    ks = list(dict.fromkeys(ln["model"] for ln in lines if ln.get("model")))
    if n == 6 and "resale-price" in ks:
        extra = ["prep-cost-time", "service-exposure"] + (
            ["repair-success"] if any(x["id"] in ("resale", "intparts") for x in c["routes"]) else []
        )
        ks += [k for k in extra if k not in ks]
    out = []
    for k in ks:
        v = learn_ver(c, k) if k in ("resale-price", "prep-cost-time", "service-exposure") else LR_MODEL_VERSIONS[k]
        out.append({"key": k, "version": v, "validation": lr_validation(k, v)})
    return out


# The demo's LR_MODELS[k].val(v): the validation line on a model card (fixed figures, except resale-price's, which are
# measured on the reconciled decisions of that version).
LR_VALIDATION = {
    "condition-vision": "accuracy 94.2% · macro-F1 0.91",
    "rul-survival": "C-index 0.81 · MAE 3.9 months",
    "demand-match": "precision@3 0.92 · recall@10 0.88",
    "prep-cost-time": "MAE $214 · MAPE 7.9% · R² 0.86",
    "service-exposure": "MAE $186 · deviance explained 0.62",
    "repair-success": "AUC 0.88 · Brier 0.09",
}


def lr_validation(k: str, v: str) -> str:
    if k != "resale-price":
        return LR_VALIDATION[k]
    r = [x for x in reconciled() if x["model"] == v and x["route"] != "exit" and not x.get("override")]
    n = len(r)
    if not n:
        return "validation pending"
    mae = money(js_round(js_sum(abs(x["actual"] - x["p50"]) for x in r) / n))
    mape = to_fixed(js_sum(abs(x["actual"] - x["p50"]) / max(abs(x["p50"]), 1) for x in r) / n * 100, 1)
    cov = to_fixed(sum(1 for x in r if x["p10"] <= x["actual"] <= x["p90"]) / n * 100, 0)
    return f"MAE {mae} · MAPE {mape}% · P10–P90 coverage {cov}% · {n} reconciled decisions"


def escalation(c: Case, nx: dict, p: Principal) -> dict:
    """The demo's afEscalation (the draft) with the recipient's label."""
    b = c.get("blocked")
    owner = b["owner"] if b else nx.get("role") if nx and nx.get("role") else "Approver"
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
    blocker = b["reason"] if b else nx["label"] if nx else "Blocked"
    a = policy.account(to, p.ctx)
    return {
        "case_id": c["id"],
        "blocker": blocker,
        "owner": owner,
        "to": to,
        "msg": f"Please look at {c['id']}: {re.sub(r'[.]$', '', blocker)}.",
        "toLabel": a.label if a else to,
    }


@router.get("/run/{case_id}")
def case_run(case_id: str, fail: str = "", p: Principal = Depends(principal), session: Session = Depends(get_session)):
    """One case's run, as the live board, the run details and the trace read it."""
    c = load_case(p, session, case_id, "orchestration", "run")
    ctx = call_ctx(p, session)
    rn = run(c, ctx)
    m = lr_model(c, rn, fail, session)
    nx = next_step(c, ctx)
    return {
        "model": m,
        "timeline": lr_timeline(c, m),
        "sig": f"{c['id']}|{','.join(s['state'] for s in rn['stages'])}|{fail}",
        "stage_models": [stage_models(c, s["n"], s["lines"]) for s in m["st"]],
        "next": nx,
        "escalation": escalation(c, nx, p),
        "journal": case_journal(session, c["id"]),
        "agent_calls": [],
        "events": case_events(session, c["id"]),
        "trace_id": "trace-" + hash_id(c["id"]).lower(),
    }
