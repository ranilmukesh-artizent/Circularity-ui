"""Case pages (B14): the Decision Workbench's ten stage pages, the case Overview and Full analysis, for one live case.

GET /api/screens/case/{id}
    The case as every case page draws it: the case record, the run (ten stages), each stage's tag and summary, where
    the case opens for this person, the next step, the active hand-off clock and the approval card's inputs.
GET /api/screens/case/{id}/analysis
    What the detail tabs and Full analysis are built from: evidence with provenance, every route's confidence and cost
    trace, the ranking, tie-break and what would flip it, demand and life, the pool, the execution plan, move and
    what-if guidance, the preparation build-up, the lease trail, the journal and events, and the evidence pack.

A case opened from a received device (plan 9, P9-6.4) also carries `device` ({imei, sku, model, storageGb, declaredGrade, grade,
quote, partner, batch, received, ref, refSource, bulk, lines, quoteCheck}; the facade's `deviceView`; `quoteCheck` is the quote
against the lab's read, P9-6.5; `registry` the registry's check of the device and its exception, P9-6.6).

A template case with gates (plan 9, P9-1.2) also carries, inside `case`: `gates` (one row per gate result), `gateHold`
(held until evidence arrives), `requiredSteps` and `batch` ({ref, total, held, released} of its batch); the facade's
`CaseRec` types them and the Decide tab's Gates block draws them.

A tool-fleet case's page also has `plan` (plan 9, P9-1.4): its place in its org's queue plan, `{holds, contested, lost,
kinds}` (di.services.cases.replan.queue_plan; None for other templates). The Decide tab's "Queue plan" line draws it.

A template case also has `recordMatch` (plan 9, P9-1.10: whether the pack's system of record holds the asset, by
di.services.cases.record_match.view; None when the pack has none) and `custody` (the append-only list, oldest first). The
Overview's "System of record" line and Custody list draw them.

A template case also has `packStages` (plan 9, P9-1.13): its pack's stage agents with their autonomy, `[{key, label, agent,
autonomy}]` in stage order (None for the industrial demo's cases); the Overview's "Agents on this case" row draws it.
(`stages` is the ten stage pages.)

Both refuse as the case actions do: 403 out_of_scope when the account has no case pages, 404 not_found for an unknown
case, 403 tenant_boundary outside the account's tenants or warehouse (same messages as di.services.actions.pipeline).

The demo builds the detail tabs and Full analysis as HTML (stData's tabs, stFull, cxDrivers, tiResult, jsonHtml); the
API returns the data those blocks are made of, and the frontend draws them (B17). Formatting stays in the frontend;
sentences the demo writes as data (stage results and meanings, facts, tags) are returned as the demo writes them.

Facade (frontend/src/api/case.ts) → this API
| export | served by |
|---|---|
| caseById | GET /{id} → case (also /analysis) |
| caseVisible | GET /{id} answers 200 (visible) or 403 |
| syncEngineRoute | frontend-only (the engine's location; goes away with the engine) |
| stages, phases, phaseOf, stageTitle, stageWillHappen | reference (AF_STAGES, ST_PH, JSTEPS_AF) |
| runOf | GET /{id} → run |
| stageState | GET /{id} → tags[n-1] |
| stageSentence | frontend-only (a sentence over the tag; stWhen formatting) |
| stageData | GET /{id} → stages[n-1] (res, facts with provenance kind and system, docs, mean, when, who); tabs: /analysis |
| landing | GET /{id} → landing |
| nextStep | GET /{id} → next |
| when, lc, stageHref | frontend-only (formatting, routes) |
| stageLogosHtml, assetPhotoHtml, predictedVsActualHtml, badgeHtml, iconTileHtml | frontend-only (markup) |
| approverRole | GET /{id} → approval.role |
| activeClock | GET /{id} → clock (times ISO) |
| rememberedTab, rememberTab | frontend-only (view state S.stTabs) |
| assetModel, assetSerial | GET /{id} → model, serial |
| fullAnalysisHtml | frontend-only markup over GET /{id}/analysis |
| eligibleRoutes | frontend-only (filter and sort case.routes) |
| defaultSpend | GET /{id}/analysis → spend[route id] |
| draftRationale | case.packet.rationale when there is a packet, else GET /{id}/analysis → rationale (the draft) |
| approvalLimit | GET /{id} → approval.limit (null: unlimited) |
| instructionJsonHtml | GET /{id}/analysis → instruction (the payload; highlighting is frontend) |
| approvalTerms | frontend-only (wording over the route and case.timing) |
| simulateSystemAck, scheduleAutoAck | actions (adapter.acknowledge; the worker acknowledges, B13b) |
| evidencePack | GET /{id}/analysis → evidence_pack |
| scen, setScen, resetScen, scenAdj | frontend-only (the Explain view's assumptions, S.scen) |
| confidence | GET /{id}/analysis → routes[].conf |
| driversHtml | frontend-only markup over the recommended route's terms |
| scenarioImpactHtml | action case.whatIf (B10) with the assumptions, drawn in the frontend |
| snapshotItems | GET /{id}/analysis → provenance (one per evidence item) |
| snapshotFrozenAt | GET /{id}/analysis → snapshot_time |
| agentButton, actionDenied, runLegacyAct, refresh | frontend-only (the demo's HTML buttons; go with the HTML) |

Summary: 51 exports → 22 served (19 by the two endpoints, 3 by actions), 5 reference, 24 frontend-only.

B17 (done): the frontend draws the detail tabs, Full analysis, the Explain view and the drawers as React from these two
answers in both modes (the engine assembles the same documents). Added for that: GET /{id} → sources (the demo's
SOURCES: logos, provenance chips, the Systems tab); GET /{id}/analysis?tenant= → view: the hand-off steps (exApp,
exDocRef, stepOwner, hoKind, ackNote), exDelivered, valueOrder, exActual per outcome line, afStageLabel, the packet's
case.routes / case.evidence reads and afRisks, assetHealth, caseDiag, parts, part prices, catalogue, SC/RMA/receipt,
title, serial, assetFacts, the repair centre's load (ccUtil, tenant filter), FAC_LOC, LOCS (name, receiving window),
saved scenarios. The what-if (scenRoutes, tiRows, tieBreak, recert) is computed in the frontend from the routes and
the ranking, because its edge cases (critical part, new unit only, short certification, apply to one route) are not
inputs of case.whatIf.

Notes for the switch-over (B17):
- `null` stands for the demo's `undefined` as well (JSON has no undefined); an unlimited approval limit is `null`.
- Times are ISO strings. The case record's `spec` is returned in the demo's per-class order (the database's JSON
  type does not keep key order).
- The journal comes from the action journal: `id` is the action, `by` the account's label, `prep` the agent that
  prepared it, `out` the stored output reference (the demo keeps the whole output).

The endpoints are in di.routes.screens.case (parameters and access); this module builds what each returns.
"""

import math
import re
from typing import Any

from sqlalchemy.orm import Session

from di.core import policy
from di.core.auth import Principal
from di.repositories.case_detail import (
    af_lease,
    as_rma,
    case_journal,
    case_record,
    default_spend,
    instr_payload,
    pool_of,
    prep_cost,
    recert,
    steps_of,
    with_times,
)
from di.repositories.cases import flips, tie_break, tie_text
from di.repositories.common import (
    AS_OF,
    FAC_LOC,
    SOURCES,
    Case,
    af_days,
    as_hex,
    as_model,
    base_rows,
    case_demand,
    case_events,
    case_rul,
    decisions_delegated,
    ex_app,
    ex_clock,
    ex_ts,
    fmt_d,
    fmt_dy,
    inr,
    iso,
    jg_lc,
    money,
    ms,
    next_step,
    ooo_cover,
    run,
    stage_label,
    step_owner,
    ti_conf,
)
from di.repositories.context import call_ctx, load_case, visible_cases
from di.repositories.packs import active_pack
from di.repositories.provenance import prov_for, snap_time
from di.services.actions.decisions import draft_rationale
from di.services.actions.pipeline import CallContext
from di.services.cases import gate_hold, record_match, replan
from di.services.device import lock as device_lock
from di.services.device import payout as device_payout
from di.services.device import verify as device_verify
from di.services.device import wipe as device_wipe
from di.services.execution import (
    as_sc,
    ex_actual,
    ex_move,
    ex_plan,
    ex_prep_parts,
    ex_trace,
    ex_what_if,
    loc_name,
)
from di.services.execution.lanes import LOCS, RATE_CARD, loc_win
from di.services.execution.plan import ack_note, ex_delivered, value_order
from di.services.execution.steps import ex_doc_ref, ho_kind
from di.services.service_desk.intake import view as service_desk_view

# ================================================================ shared by the product, case and orchestration screens


def no_inf(v: float | None) -> float | None:
    """JSON has no Infinity: an unlimited amount is sent as null."""
    return None if v is None or math.isinf(v) else v


# ---------------------------------------------------------------- small demo helpers
def st_when(d: Any) -> str:
    """The demo's stWhen: "07 Oct 14:20" (the time only when it is not midnight UTC)."""
    if not d:
        return ""
    t = ms(d)
    hm = iso(t)[11:16]
    return fmt_d(t) + ("" if hm == "00:00" else " " + hm)


def same_route(a: dict | None, b: dict | None) -> bool:
    """`a === b` for routes (a stored case keeps copies; routes are told apart by plan, as di.services.execution does)."""
    return bool(a and b and a["plan"] == b["plan"] and a["id"] == b["id"])


def eligible(c: Case) -> list[dict]:
    return sorted((x for x in c["routes"] if not x["excluded"]), key=lambda x: -x["net"])


def limit_of_role(role: str, p: Principal) -> float:
    return policy.limit_for(policy.Account(id="", role=role, label=role), p.ctx)


# ================================================================ the stage pages
def stage_tag(c: Case, n: int, rn: dict, p: Principal, deleg: bool) -> dict:
    """The demo's stState: a stage's tag (done, not reached, blocked, waiting on someone, current)."""
    s = rn["stages"][n - 1]
    x: Any = c.get("exec")
    st = x["steps"] if x else []
    cur = rn["stage"] == n

    def wait(who: str, since: Any) -> dict:
        return {
            "k": "wait",
            "icon": "⏳",
            "word": "Waiting on " + ("you" if p.account.role == who else who),
            "who": who,
            "since": since,
        }

    state = s["state"]
    if state == "done":
        return {"k": "done", "icon": "✓", "word": "Done", "since": s.get("at") or None, "who": s.get("by") or ""}
    if state in ("queued", "skipped"):
        return {"k": "todo", "icon": "○", "word": "Not reached"}
    if state in ("warning", "failed"):
        b = s.get("blocked") or {}
        return {"k": "block", "icon": "!", "word": "Blocked", "who": b.get("owner") or "", "why": b.get("reason") or s["result"]}
    if n == 5 and state == "running":
        return wait(
            c["blocked"]["owner"] if c.get("blocked") else "Engineering", c["requested"]["at"] if c.get("requested") else None
        )
    if n == 7:
        if c.get("submitted"):
            return wait("Approver" if deleg else "Admin", c["submitted"]["at"])
        return wait("Planner", c["packet"]["at"] if c.get("packet") else None)
    if n == 8 or (n == 9 and state == "running"):
        i = next((k for k, y in enumerate(st) if y["state"] != "done"), -1)
        if i >= 0:
            prev = st[i - 1] if i > 0 else None
            since = (
                prev["ack"]["at"] if prev and prev.get("ack") else (x.get("approvedAt") or (c.get("approval") or {}).get("at"))
            )
            return wait(ex_app(st[i]), since)
        return {"k": "cur", "icon": "●", "word": "Current"}
    if n == 9 and state == "person":
        last = st[-1] if st else None
        return wait("Finance", last["ack"]["at"] if last and last.get("ack") else None)
    return {"k": "cur", "icon": "●", "word": "Current"} if cur else {"k": "todo", "icon": "○", "word": "Not reached"}


def landing(rn: dict, role: str) -> int | str:
    """The demo's stLand: where a case opens for the signed-in role."""
    n = min(rn["stage"], 10)
    if role == "Executive":
        return "overview"
    if role == "Engineer":
        return 5
    if role == "Finance":
        return n if n >= 9 else 9
    if role == "Warehouse Manager":
        return 8 if n >= 8 else 4
    return n


ST_SYS = {
    "Lease management": "lease",
    "CRM": "crm",
    "Customer portal": "crm",
    "ERP finance": "erp",
    "ERP": "erp",
    "Finance": "erp",
    "ERP procurement": "proc",
    "TMS / 3PL": "tms",
    "WMS": "wms",
    "Repair orders": "repair",
    "Repair": "repair",
    "MRO": "repair",
    "OMS": "oms",
    "TMS": "tms",
    "Inspection": "insp",
    "PLM": "plm",
    "EAM": "eam",
    "Remarketing": "dlr",
}
INSPECTION_WORD = {"ready": "Complete", "partial": "Partial", "stale": "Stale", "missing": "Missing", "conflict": "Conflict"}
DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def rc_story(o: dict) -> str:
    """The demo's rcStory: which cost line moved most, and which model learns from it."""
    ls = sorted((x for x in o["lines"] if x.get("act") != x.get("pred")), key=lambda x: -abs(x["act"] - x["pred"]))
    if not ls:
        return "Every line came in as predicted."
    ln = ls[0]
    x, cost = ln["act"] - ln["pred"], ln["pred"] < 0
    what = ("more" if x < 0 else "less") + " cost" if cost else ("less" if x < 0 else "more") + " value"
    return (
        f"The largest difference is {jg_lc(ln['label'])}: {money(abs(x))} {what} than predicted, so {ln['model']} {ln['ver']} "
        "learns most from this outcome."
    )


def stage_data(c: Case, n: int, rn: dict, p: Principal, deleg: bool, waiting: str | None = None) -> dict:
    """The demo's stData without its detail tabs: what a stage established (res), its facts (each with the kind of
    provenance and the system behind it), documents, what it means, when and who."""
    L = af_lease(c)
    s = rn["stages"][n - 1]
    r: Any = c.get("chosen") or c.get("recommendation")
    M: Any = case_demand(c)
    R: Any = case_rul(c)
    x: Any = c.get("exec")
    st = x["steps"] if x else []
    ev = c.get("evidence") or []
    miss = [e for e in ev if e["state"] != "ready"]
    el = eligible(c)
    ex = [z for z in c["routes"] if z["excluded"]]
    nx = next((z for z in el if not same_route(z, r)), None) if r else None
    o: dict[str, Any] = {"res": "", "facts": [], "docs": [], "mean": "", "when": s.get("at"), "who": s.get("by") or ""}
    facts: list[dict] = o["facts"]

    def F(label: str, v: str, k: str, sys: str, estimate: bool = False) -> None:
        facts.append({"l": label, "v": v, "k": k, "sys": sys} | ({"estimate": True} if estimate else {}))

    lane = L["lane"]
    blocked: Any = c.get("blocked")
    if n == 1:
        o["res"] = f"Lease {L['lease']} ended on {fmt_dy(L['end'])}; {c['owner']} chose to {L['intent']}."
        F("Lease contract", L["lease"], "ret", "Lease management")
        F("Ended", fmt_dy(L["end"]), "ret", "Lease management")
        F("Lessee", c["owner"], "ret", "CRM")
        F("Customer intent", L["intent"], "ret", "Customer portal")
        F("Usage", L["usage"], "ret", "Lease management")
        o["docs"], o["who"] = [L["lease"]], "Lease management"
        found = f"; {c['owner']}'s contract order {M['order']} is the demand it found" if M and M.get("order") else ""
        o["mean"] = f"A return is expected, so the agent opened {c['id']} and demand matching began{found}."
    elif n == 2:
        fee = f", with an early-return fee of {money(L['fee'])}" if L["fee"] else ", with no fee"
        o["res"] = f"Return authorised under {L['rma']} on {fmt_dy(L['auth'])}{fee}."
        F("Authorisation", L["rma"], "ret", "Lease management")
        F("Authorised", fmt_dy(L["auth"]), "ret", "Lease management")
        F("Fees", money(L["fee"]) if L["fee"] else "None", "ret", "ERP finance")
        F("Replacement order", L["repl"] or "None", "ret", "ERP")
        F("Book value", money(L["book"]), "ret", "ERP finance")
        o["docs"], o["who"] = [d for d in (L["rma"], L["repl"]) if d], "Lease management"
        pred = f"; the recommended {r['plan']} predicts {money(r['net'])}" if r else ""
        o["mean"] = f"Book value {money(L['book'])} is the baseline the decision must beat{pred}."
    elif n == 3:
        o["res"] = (
            f"Picked up on {fmt_d(L['pickup'])} at {loc_name(lane['from'])} by {L['carrier']}; arrived at {loc_name(lane['to'])} "
            f"on {fmt_d(L['eta'])}."
        )
        F("Picked up", fmt_dy(L["pickup"]), "ret", "TMS / 3PL")
        F("Carrier", L["carrier"], "ret", "TMS / 3PL")
        F("Arrived", fmt_dy(L["eta"]), "ret", "WMS")
        F("Freight", f"{money(L['freight'])} ({inr(lane['inr'])})", "ret", "TMS / 3PL")
        F("Lane", f"{lane['from']} → {lane['to']}", "rul", "Rate card " + RATE_CARD["id"])
        o["docs"], o["who"] = [RATE_CARD["id"]], L["carrier"]
        o["mean"] = (
            f"Freight of {money(L['freight'])} is already spent; from arrival the unit carries holding cost until a route "
            "moves it."
        )
    elif n == 4:
        hold = next((t for t in r["terms"] if re.search("holding", t["label"], re.I)), None) if r else None
        code: Any = FAC_LOC.get(c["location"])
        Lc = LOCS.get(code) or {}
        if miss:
            items = f"{len(miss)} evidence item{'s are' if len(miss) > 1 else ' is'} still missing"
        else:
            items = "every evidence item arrived"
        o["res"] = f"Received at {c['location']} on {fmt_dy(c['received'])}; {items}."
        F("Received", fmt_dy(c["received"]), "ret", "WMS")
        F("Warehouse", c["location"] + (f" · bin {Lc['bin']}" if Lc.get("bin") else ""), "ret", "WMS")
        F("Holding clock", f"{af_days(c['received'])} days", "rul", "Circularity")
        F("Evidence", f"{len(ev) - len(miss)} of {len(ev)} complete", "rul", "Evidence scoring")
        if hold:
            F("Holding and risk cost", money(hold["amt"]), "mod", "Prediction model")
        o["docs"], o["who"] = [as_rma(c)], "WMS"
        if miss:
            tail = f" holds back every route until {jg_lc(blocked['action'])}" if blocked else " narrows what can be priced"
            o["mean"] = f"Missing {', '.join(jg_lc(e['label']) for e in miss)}{tail}."
        else:
            o["mean"] = "Evidence is complete, so every route can be built and priced."
    elif n == 5:
        ws = "MRO" if c["cls"] in ("motor", "pump") else "Inspection"
        ins = next((e for e in ev if e["k"] == "insp"), None)
        prep = prep_cost(c)
        if s["state"] == "done":
            if c.get("grade"):
                cert = f"; certified for {R['certMonths']} months" if R else ""
                o["res"] = f"Graded {c['grade']} by {'MRO workshop inspection' if ws == 'MRO' else 'inspection'}{cert}."
            else:
                o["res"] = f"Assessed: {c.get('assessment')}."
        elif c.get("requested"):
            o["res"] = f"{blocked['action']} requested ({c['requested']['ref']}); waiting for {blocked['owner']}."
        else:
            o["res"] = f"{blocked['reason'] if blocked else 'Not inspected yet'}."
        F(
            "Grade",
            f"Grade {c['grade']}" if c.get("grade") else "Not graded",
            "ret",
            "MRO" if ws == "MRO" else "Inspection",
            estimate=bool(((c.get("vehicle") or {}).get("inspection") or {}).get("estimate")),
        )  # a car's estimated grade (P9-9.7)
        F("Condition", c["condition"], "ret", "Inspection")
        F("Inspection", (INSPECTION_WORD.get(ins["state"]) or ins["state"]) if ins else "—", "ret", "Inspection")
        if R:
            F("Certified period", f"{R['certMonths']} months · {R['certRef']}", "ret", "QMS")
        if c.get("engLife"):
            F("Engineering life", c["engLife"], "ret", "PLM")
        if prep:
            F("Repair estimate", money(prep), "mod", "Prediction model")
        o["docs"] = [d for d in (R["certRef"] if R else None, c["requested"]["ref"] if c.get("requested") else None) if d]
        if blocked and not c.get("recommendation"):
            o["mean"] = f"No route can be priced until {jg_lc(blocked['action'])}: {jg_lc(blocked['reason'])}."
        else:
            head = f"Grade {c['grade']}" if c.get("grade") else "The assessment"
            life = f" and a {R['certMonths']}-month certified life" if R else ""
            plans = f" ({', '.join(z['plan'] for z in el[:3])})" if el else ""
            held = "; ".join(f"{z['plan']} is withheld ({jg_lc(z.get('failReason') or 'a gate failed')})" for z in ex[:2])
            o["mean"] = (
                f"{head}{life} leave {len(el)} route{'' if len(el) == 1 else 's'} eligible{plans}{'; ' + held if ex else ''}."
            )
    elif n == 6:
        q = c.get("recommendation")
        if q:
            cf = ti_conf(c, q)
            passed = sum(1 for g in q["gates"] if g == "pass")
            o["res"] = f"Recommended: {q['plan']}, {money(q['net'])} predicted net."
            F("Predicted net", money(q["net"]), "mod", "Prediction model")
            F("Range (P10–P90)", f"{money(q['p10'])} to {money(q['p90'])} · confidence {cf.lower()}", "mod", "Prediction model")
            F("Gates", "All six passed" if passed == len(q["gates"]) else f"{passed} of six passed", "rul", "Gate engine")
            alt = [z for z in el if not same_route(z, q)][:3]
            if alt:
                F("Alternatives", " · ".join(f"{z['plan']} {money(z['net'])}" for z in alt), "mod", "Prediction model")
            if ex:
                F("Not eligible", ", ".join(z["plan"] for z in ex), "rul", "Gate engine")
            if c.get("flowVer") is not None:  # plan 8, MVP-3.4: evaluated with a stored decision flow
                rules = ", ".join(c.get("rulesApplied") or [])
                F("Decision flow", f"v{c['flowVer']}" + (f" · rules {rules}" if rules else ""), "rul", "Decision Modeler")
            o["docs"] = [
                d
                for d in (c["snapshot"]["id"] if c.get("snapshot") else None, f"Model {c['model']}" if c.get("model") else None)
                if d
            ]
            pk = c.get("packet")
            o["who"] = (f"Agent, for {pk['by']}" if pk.get("prep") else pk["by"]) if pk else "Decision engine"
            o["when"] = pk["at"] if pk else s.get("at")
            if nx:
                po = (
                    f" because it replaces the planned purchase {M['avoidedPo']}"
                    if q["id"] == "redeploy" and M and M.get("avoidedPo")
                    else ""
                )
                o["mean"] = f"{q['plan']} beats {nx['plan']} by {money(q['net'] - nx['net'])}{po}."
            else:
                o["mean"] = f"{q['plan']} is the only eligible route."
        else:
            o["res"] = s["result"] + "."
            F("Routes built", str(len(c["routes"])), "rul", "Gate engine")
            F("Eligible", str(len(el)), "rul", "Gate engine")
    elif n == 7:
        pay: Any = instr_payload(c) if r else None
        appr: Any = c.get("approval")
        sub: Any = c.get("submitted")
        lim: Any = None if appr else limit_of_role("Approver" if deleg else "Admin", p)
        apps = list(dict.fromkeys(ex_app(y) for y in steps_of(c))) if r else []
        apps = [a for a in apps if not re.match(r"^Circularity|^Planning", a)]
        if appr:
            who = f"{appr['delegate']} on behalf of {appr['onBehalfOf']}" if appr.get("onBehalfOf") else appr["by"]
            o["res"] = f"{'Override approved' if c.get('override') else 'Approved'} by {who} under {appr['ref']}: {r['plan']}."
        elif sub:
            waits = waiting or ("the Approver" if deleg else "Admin")  # waiting: an out-of-office delegate in force
            o["res"] = f"Submitted by {sub['by']} on {fmt_d(sub['at'])}; waiting for {waits}."
        elif r:
            o["res"] = "The decision packet is ready; it waits for the Planner to submit it."
        else:
            o["res"] = "Waits for a recommended route."
        if r:
            F("Route", f"{r['plan']} · {money(r['net'])}", "mod", "Prediction model")
            if sub:
                F("Submitted", f"{sub['by']} · {st_when(sub['at'])}", "rec", "Circularity")
            if appr:
                F("Approved", f"{appr['by']} · {st_when(appr['at'])}", "rec", "Circularity")
                spend = appr["spend"] if appr.get("spend") is not None else default_spend(c, r)
                F("Spend authority", money(spend), "rec", "Circularity")
            else:
                role = "Approver" if deleg else "Admin"
                F("Approval limit", f"Unlimited for the {role}" if math.isinf(lim) else money(lim), "rul", "Approval policy")
                ok = all(g == "pass" for g in r["gates"])
                snap = c["snapshot"]["id"] if c.get("snapshot") else "—"
                F(
                    "Pre-approval check",
                    f"All six gates passed; evidence snapshot {snap}" if ok else "Gate notes to read",
                    "rul",
                    "Gate engine",
                )
        o["docs"] = [d for d in (appr["ref"] if appr else None, pay["decisionId"] if pay else None) if d]
        o["when"] = appr["at"] if appr else sub["at"] if sub else None
        o["who"] = appr["by"] if appr else sub["by"] if sub else ""
        if r:
            alloc = (
                f", allocates the unit to {M['order']} line {M['line']}" if M and M.get("order") and r["id"] == "redeploy" else ""
            )
            o["mean"] = (
                f"Approval sends {len(steps_of(c))} instructions to {', '.join(apps)}{alloc} and commits up to "
                f"{money(pay['spendAuthorityUsd'])} of spend."
            )
    elif n == 8:
        mv: Any = ex_move(c, r) if r else None
        i = next((k for k, y in enumerate(st) if y["state"] != "done"), -1)
        a = st[i] if i >= 0 else None
        done = sum(1 for y in st if y["state"] == "done")
        if x:
            o["res"] = (
                f"{done} of {len(st)} instructions acknowledged; {jg_lc(a['label'])} is with {ex_app(a)}."
                if a
                else f"All {len(st)} instructions acknowledged."
            )
            F("Instruction", x["ref"], "rec", "Circularity")
            F("Acknowledged", f"{done} of {len(st)}", "ret", "ERP")
            if a:
                F("Running", f"{a['label']} · {ex_app(a)}", "ret", ST_SYS.get(a["sys"].split(" · ")[0]) or "ERP")
            if mv and mv.get("eta"):
                sl = mv.get("slack")
                tail = "" if sl is None else " · " + (f"{abs(sl)} days late" if sl < 0 else f"{sl} days early")
                F("Arrives", ex_ts(mv["eta"]) + tail, "rul", "Route planner")
            o["docs"] = [y["ack"]["ref"] for y in st if y.get("ack")]
            o["who"] = "Enterprise adapters"
            o["when"] = x.get("approvedAt") or (c.get("approval") or {}).get("at")
            if a:
                arr = f"; the unit arrives {ex_ts(mv['eta'])}" if mv and mv.get("eta") else ""
                o["mean"] = f"Step {i + 1} of {len(st)} is running{arr}."
            else:
                o["mean"] = "Every instruction is acknowledged; the outcome comes back next."
        else:
            o["res"] = "Instructions go out only after approval."
    elif n == 9:
        o9: Any = c.get("outcome")
        last: Any = st[-1] if st else None
        d = ex_delivered(c)
        mv = ex_move(c, r) if d else None
        ds = f"delivered to {loc_name(mv['to'])} against {M['order']} line {M['line']}" if d else ""

        def dl(v: float) -> str:
            return ("+" if v >= 0 else "−") + money(abs(v))

        if o9:
            o["res"] = f"Actual {money(o9['net'])} confirmed by {o9.get('by') or 'Finance'}{'; ' + ds if ds else ''}."
            F("Actual net", money(o9["net"]), "ret", "ERP finance")
            F("Predicted net", money(r["net"]), "mod", "Prediction model")
            F("Variance", dl(o9["net"] - r["net"]), "rul", "Reconciler")
            F(
                "Confirmed by",
                (o9.get("by") or "Finance") + (" · " + st_when(o9["at"]) if o9.get("at") else ""),
                "rec",
                "Circularity",
            )
        elif last and last.get("ack"):
            o["res"] = f"Outcome reported ({last['ack']['ref']}){'; ' + ds if ds else ''}; waiting for Finance to confirm it."
            F("Reported", f"{last['ack']['ref']} · {st_when(last['ack']['at'])}", "ret", "ERP finance")
            F("Predicted net", money(r["net"]), "mod", "Prediction model")
        else:
            o["res"] = "The outcome comes back once every instruction is acknowledged."
        vo = value_order(c)
        order = (o9 or {}).get("order") or (vo["ref"] if vo else None)
        if order:
            F("Order", order, "ret", "ERP")
        o["docs"] = [d for d in (last["ack"]["ref"] if last and last.get("ack") else None, (o9 or {}).get("order")) if d]
        if o9:
            if o9["net"] >= r["net"]:
                o["mean"] = f"The decision delivered {dl(o9['net'] - r['net'])} more than it promised."
            else:
                o["mean"] = (
                    f"The decision delivered {money(r['net'] - o9['net'])} less than the {money(r['net'])} it promised; stage 10 "
                    "shows which lines moved."
                )
    else:
        o10: Any = c.get("outcome")

        def dl(v: float) -> str:
            return "—" if v == 0 else ("+" if v > 0 else "−") + money(abs(v))

        if o10:
            o["res"] = f"Predicted {money(r['net'])}, actual {money(o10['net'])}: {dl(o10['net'] - r['net'])}."
            learned = [z for z in o10["lines"] if z.get("model")]
            F("Predicted", money(r["net"]), "mod", "Prediction model")
            F("Actual", money(o10["net"]), "ret", "ERP finance")
            F("Variance", dl(o10["net"] - r["net"]), "rul", "Reconciler")
            F("Lines reconciled", str(len(o10["lines"])), "rul", "Reconciler")
            F("Learning records", f"{len(learned)} · model {c.get('model') or '—'}", "rec", "Circularity")
            o["docs"] = [x["decisionId"]] if x and x.get("decisionId") else []
            o["who"] = "Reconciler"
            o["mean"] = rc_story(o10)
        else:
            o["res"] = "Reconciles once Finance confirms the outcome."
    return o


def active_clock(c: Case) -> dict | None:
    """The active instruction step's time-limit clock (exClock at the as-of time)."""
    a = next((y for y in (c.get("exec") or {}).get("steps") or [] if y["state"] == "active"), None)
    return with_times(ex_clock(c, a, AS_OF)) if a else None


def pack_stages(session: Session, c: Case) -> list[dict] | None:
    """The stage agents of the case's pack with their autonomy (plan 9, P9-1.13): [{key, label, agent, autonomy}] in stage
    order; None for a case with no template (the industrial demo's), whose page is unchanged."""
    if not c.get("template"):
        return None
    pack = active_pack(session, c["template"], c["owner"])
    return [{"key": s.key, "label": s.label, "agent": s.agent, "autonomy": s.autonomy} for s in pack.stages]


def device_block(c: Case, session: Session | None = None) -> dict | None:
    """The `device` block of a case opened from a received trade-in (plan 9, P9-6.4; facade `deviceView`): IMEI (none for a
    bulk lot), SKU, quote, partner, batch, received date and, for a lot, a line per device. None for any other case."""
    v = c.get("valuer") if c.get("template") == "device" else None
    if not isinstance(v, dict) or not (v.get("imei") or v.get("lines")):
        return None
    q = v.get("quote") or {}
    return {
        "imei": v.get("imei"), "sku": v.get("sku_key") or "", "brand": v.get("brand") or "", "model": v.get("model") or "",
        "storageGb": v.get("storage_gb"), "declaredGrade": v.get("declared_grade") or v["grade"], "grade": v["grade"],
        "graded": bool(v.get("graded")),
        "quote": {"amount": q["amount"], "currency": q.get("currency", "USD")} if q.get("amount") is not None else None,
        "partner": v.get("partner") or "", "batch": v.get("batch_id"), "received": v.get("received") or c["received"],
        "ref": v["ref"], "refSource": v.get("ref_source") or "quote", "bulk": not v.get("imei"),
        "lines": [
            {"imei": x["imei"], "model": x["model"], "storageGb": x["storage_gb"], "declaredGrade": x["declared_grade"],
             "grade": x["grade"], "quote": x.get("quote") or 0}
            for x in v.get("lines") or []
        ],
        "quoteCheck": device_verify.view(session, c) if session is not None else None,  # the quote against the read (P9-6.5)
        "registry": (
            device_lock.view(session, c, active_pack(session, c["template"], c["owner"])) if session is not None else None
        ),
        "wipe": device_wipe.view(session, c) if session is not None else None,  # the wipe certificate (P9-6.7)
        "payout": device_payout.view(session, c) if session is not None else None,  # the payout adjustment (P9-6.8)
    }  # fmt: skip


def case_page(session: Session, p: Principal, case_id: str) -> dict:
    """Everything the stage bar, the stage pages, the Overview and the approval card read, for one case."""
    c = load_case(p, session, case_id, "product", "case")
    ctx = call_ctx(p, session)
    deleg = decisions_delegated(ctx)
    cover = ooo_cover(ctx) if c.get("submitted") else None
    waiting = f"{cover['delegate']} (covering for the Approver)" if cover else None
    rn = run(c, ctx)
    rec = case_record(c, session)
    if rec.get("batchRef"):  # a lot opened in a batch: how many of its lots are released (plan 9, P9-1.2)
        rec["batch"] = {"ref": rec["batchRef"], **gate_hold.batch_status(session, rec["batchRef"])}
    if (dev := device_block(c, session)) is not None:  # a received device or a bulk lot (plan 9, P9-6.4)
        rec["device"] = dev
    if (sd := service_desk_view(session, c)) is not None:  # a service ticket or batch (plan 9, P9-4.3)
        rec["serviceDesk"] = sd
    return {
        "case": rec,
        "model": as_model(c),
        "serial": "SN" + str(as_hex(c, "sn"))[:7].rjust(7, "0"),
        "run": rn,
        "tags": [stage_tag(c, n, rn, p, deleg) for n in range(1, 11)],
        "stages": [stage_data(c, n, rn, p, deleg, waiting) for n in range(1, 11)],
        "landing": landing(rn, p.account.role),
        "next": next_step(c, ctx),
        "clock": active_clock(c),
        "approval": {"role": "Approver" if deleg else "Admin", "limit": no_inf(policy.limit_for(p.account, p.ctx))},
        "sources": case_sources(),
        "plan": replan.queue_plan(session, c),
        "recordMatch": record_match.view(c, active_pack(session, c["template"], c["owner"])) if c.get("template") else None,
        "custody": list(c.get("custody") or []),
        "packStages": pack_stages(session, c),
    }


def case_sources() -> dict:
    """The connected sources the stage pages name (logos, provenance chips, the Systems tab): the demo's SRC by id."""
    keys = ("id", "short", "name", "vendor", "mode", "status", "freshMin")
    return {k: {f: s.get(f) for f in keys} for k, s in SOURCES.items()}


def step_view(c: Case, s: dict) -> dict:
    """One instruction step as the hand-off blocks draw it: the vendor application, the document it creates, its owner,
    the kind of document the system returns and the acknowledgement note (exApp, exDocRef, stepOwner, hoKind, ackNote)."""
    return {
        "k": s.get("k"),
        "label": s["label"],
        "sys": s["sys"],
        "state": s["state"],
        "ack": s.get("ack"),
        "app": ex_app(s),
        "doc_ref": ex_doc_ref(c, s) if s.get("k") else None,
        "owner": step_owner(c, s),
        "doc": list(ho_kind(s)),
        "note": ack_note(s, c),
    }


def analysis_view(c: Case, p: Principal, session: Session, ctx: CallContext, tenant: str) -> dict:
    """What the detail tabs and Full analysis draw besides the analysis proper (B17): the hand-off steps, the delivery,
    the order the value is committed against, the actuals behind the outcome lines, the packet's reads and risks, the
    asset's health, diagnostics, parts and facts, and the repair centre's load (the demo's ccUtil, tenant filter)."""
    from di.repositories.asset import (
        as_serial,
        as_title,
        asset_facts,
        case_diag,
        catalogue,
        health,
        part_prices,
        parts_availability,
    )
    from di.repositories.cases import case_evidence, case_routes
    from di.repositories.workspace import af_risks
    from di.services.actions.decisions import saved_scenarios

    h = health(c)
    rt, ev = case_routes({"case_id": c["id"]}, ctx), case_evidence({"case_id": c["id"]}, ctx)
    o = c.get("outcome")
    return {
        "steps": [step_view(c, s) for s in steps_of(c)],
        "delivered": ex_delivered(c),
        "value_order": value_order(c),
        "actuals": [ex_actual(c, ln) for ln in o.get("lines") or []] if o else [],
        "stage_label": stage_label(c),
        "routes_read": rt,
        "evidence_read": ev,
        "risks": af_risks(c, rt, ev),
        "health": h,
        "diag": case_diag(c, h),
        "parts": parts_availability(c, h),
        "part_prices": part_prices(c, h),
        "catalogue": catalogue(c),
        "sc": as_sc(c),
        "rma": as_rma(c),
        "receipt": f"GR-{100000 + as_hex(c, 'gr') % 900000}",
        "title": as_title(c),
        "serial": as_serial(c),
        "facts": asset_facts(c),
        "repair_load": sum(1 for x in visible_cases(call_ctx(p, session), tenant) if x["location"] == "Repair centre"),
        "fac_code": FAC_LOC.get(c["location"]),
        "scenarios": saved_scenarios(session, c["id"]),
        "locs": {
            k: {"name": loc_name(k), "win": loc_win(k)} | {f: L.get(f) for f in ("city", "bin", "bay", "days")}
            for k, L in LOCS.items()
        },
    }


# ================================================================ full analysis
def evidence_pack(c: Case, rn: dict, session: Session) -> dict:
    """The demo's afEvidencePack: the case, its evidence, decision, instruction, plan, move, cost trace and events."""
    r = c.get("chosen") or c.get("recommendation")
    mv = ex_move(c, r) if r else None
    move = None
    if mv:
        move = {
            "stops": mv["stops"],
            "staging": mv["stage"],
            "legs": [
                {
                    "from": x["from"],
                    "to": x["to"],
                    "km": x["km"],
                    "etd": iso(x["etd"]),
                    "eta": iso(x["eta"]),
                    "carrier": x["carrier"],
                    "freight_inr": x["inr"],
                    "calc": x["calc"],
                }
                for x in mv["legs"]
            ],
            "need_by": iso(mv["need"])[:10] if mv.get("need") is not None else None,
            "slack_days": mv["slack"],
        }
    return {
        "generated_by": "Circularity",
        "generated_at": iso(AS_OF),
        "case": {"id": c["id"], "asset": c["assetId"], "product": as_model(c), "owner": c["owner"], "location": c["location"]},
        "snapshot": c.get("snapshot") or None,
        "evidence": [
            {"item": e["label"], "state": e["state"], "source": e.get("source"), "fresh": e.get("fresh")} for e in c["evidence"]
        ],
        "decision": {"route": r["plan"], "net": r["net"], "p10": r["p10"], "p90": r["p90"]} if r else None,
        "approval": c.get("approval") or None,
        "override": c.get("override") or None,
        "instructions": instr_payload(c) if c.get("exec") else None,
        "acknowledgements": [
            {"step": s["label"], "system": s["sys"], "state": s["state"], "ref": s["ack"]["ref"] if s.get("ack") else None}
            for s in (c["exec"]["steps"] if c.get("exec") else [])
        ],
        "execution_plan": [
            {
                "step": s["n"],
                "action": s["act"],
                "system": s["app"],
                "documents": s["docs"],
                "planned": s["planned"],
                "owner": s["owner"],
                "time_limit": s["lim"],
                "escalated_to": s["clock"]["to"] if s["clock"] and s["clock"]["level"] else None,
                "why": s["why"],
            }
            for s in (ex_plan(c, r, AS_OF) if r else [])
        ],
        "move": move,
        "cost_trace": with_times([ex_trace(c, r, t) for t in r["terms"]]) if r else [],
        "what_happens_if": ex_what_if(c, r) if r else [],
        "outcome": c.get("outcome") or None,
        "run": [{"stage": f"{s['n']} {s['t']}", "state": s["state"], "result": s["result"]} for s in rn["stages"]],
        "events": [
            {
                "ts": iso(e["ts"]),
                "type": e["type"],
                "by": e.get("by") or "",
                "prepared_by": e.get("prep") or None,
                "ack": e.get("ack"),
            }
            for e in case_events(session, c["id"])
        ],
    }


def case_analysis(session: Session, p: Principal, case_id: str, tenant: str) -> dict:
    """The data behind the stage pages' detail tabs and Full analysis (`tenant`: the top-bar filter, for the repair
    centre's load)."""
    c = load_case(p, session, case_id, "product", "case")
    ctx = call_ctx(p, session)
    r = c.get("chosen") or c.get("recommendation")
    rows = base_rows(c)
    tb = tie_break(c, rows)
    pool = pool_of(session, c["id"])
    return {
        "case_id": c["id"],
        "provenance": [prov_for(c, e) for e in c["evidence"]],
        "snapshot_time": snap_time(c),
        "routes": [
            {
                "id": x["id"],
                "plan": x["plan"],
                "conf": ti_conf(c, x),
                "terms": None if x["excluded"] else with_times([ex_trace(c, x, t) for t in x["terms"]]),
            }
            for x in c["routes"]
        ],
        "ranking": [
            {
                "route": x["r"]["id"],
                "plan": x["r"]["plan"],
                **{k: x[k] for k in ("gross", "cost", "net", "days", "prob", "life", "co2")},
            }
            for x in rows
        ],
        "tie": (
            {
                "gap": tb["gap"],
                "pct": tb["pct"],
                "text": tie_text(tb),
                "preferred": tb["preferred"]["r"]["plan"],
                "decided_by": tb["decidedBy"],
                "values": tb["values"],
            }
            if tb and tb["near"]
            else None
        ),
        "flips": flips(c),
        "rul": case_rul(c),
        "demand": case_demand(c),
        "recert": recert(c, r) if r else None,
        "pool": pool,
        "plan": with_times(ex_plan(c, r, AS_OF)) if r else [],
        "move": with_times(ex_move(c, r)) if r else None,
        "what_if": ex_what_if(c, r) if r else [],
        "prep_parts": ex_prep_parts(c, r) if r else None,
        "lease": with_times(af_lease(c)),
        "rationale": draft_rationale(c),
        "spend": {x["id"]: default_spend(c, x) for x in eligible(c)},
        "instruction": instr_payload(c) if r else None,
        "journal": case_journal(session, c["id"]),
        "events": case_events(session, c["id"]),
        "evidence_pack": evidence_pack(c, run(c, ctx), session),
        "view": analysis_view(c, p, session, ctx, tenant),
    }
