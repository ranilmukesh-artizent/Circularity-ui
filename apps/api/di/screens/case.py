"""Case pages (B14): the Decision Workbench's ten stage pages, the case Overview and Full analysis, for one live case.

GET /api/screens/case/{id}
    The case as every case page draws it: the case record, the run (ten stages), each stage's tag and summary, where
    the case opens for this person, the next step, the active hand-off clock and the approval card's inputs.
GET /api/screens/case/{id}/analysis
    What the detail tabs and Full analysis are built from: evidence with provenance, every route's confidence and cost
    trace, the ranking, tie-break and what would flip it, demand and life, the pool, the execution plan, move and
    what-if guidance, the preparation build-up, the lease trail, the journal and events, and the evidence pack.

Both refuse as the case actions do: 403 out_of_scope when the account has no case pages, 404 not_found for an unknown
case, 403 tenant_boundary outside the account's tenants or warehouse (same messages as di.actions.pipeline).

The demo builds the detail tabs and Full analysis as HTML (stData's tabs, stFull, cxDrivers, tiResult, jsonHtml); the
API returns the data those blocks are made of, and the frontend draws them (B17). Formatting stays in the frontend;
sentences the demo writes as data (stage results and meanings, facts, tags) are returned as the demo writes them.

Facade (apps/web/src/api/case.ts) → this API
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

Notes for the switch-over (B17):
- `null` stands for the demo's `undefined` as well (JSON has no undefined); an unlimited approval limit is `null`.
- Times are ISO strings. The case record's `spec` is returned in the demo's per-class order (the database's JSON
  type does not keep key order).
- The journal comes from the action journal: `id` is the action, `by` the account's label, `prep` the agent that
  prepared it, `out` the stored output reference (the demo keeps the whole output).
"""

import math
import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import policy
from di.actions.decisions import draft_rationale
from di.actions.pipeline import Actor, CallContext
from di.auth import Principal, principal
from di.cases import store
from di.db import get_session
from di.engine.jsmath import js_round, js_sum
from di.engine.pool import solve_pool
from di.execution import ex_kg, ex_move, ex_plan, ex_prep_parts, ex_trace, ex_what_if, lane_cost, loc_name, steps_for
from di.execution.lanes import LOCS, RATE_CARD
from di.execution.plan import ex_delivered, value_order
from di.reads.cases import flips, tie_break, tie_text
from di.reads.common import (
    AS_OF,
    CLASSES,
    FAC_LOC,
    SITE_LOC,
    SOURCES,
    TENANT_SITES,
    Case,
    add_days,
    af_days,
    as_hex,
    as_model,
    base_rows,
    case_demand,
    case_events,
    case_rul,
    decisions_delegated,
    demand_order,
    ex_app,
    ex_clock,
    ex_ts,
    fmt_d,
    fmt_dy,
    hash_id,
    inr,
    iso,
    jg_lc,
    money,
    ms,
    next_step,
    run,
    ti_conf,
)
from di.reads.common import EX_FX as FX

router = APIRouter(prefix="/api/screens/case", tags=["screens: case"])


# ================================================================ shared by the product, case and orchestration screens
def screen_ctx(p: Principal, session: Session) -> CallContext:
    """The read context the action reads take (di.reads), for the signed-in account."""
    return CallContext(actor=Actor(account=p.account, ctx=p.ctx), session=session)


def load_case(p: Principal, session: Session, case_id: str, page: str, section: str) -> Case:
    """One live case for a page: the page must be open to the account, the case must exist and be inside the account's
    tenants and warehouse (the refusals and messages of the case actions, di.actions.pipeline)."""
    p.require_page(page, section)
    c = store.get(session, case_id)
    if c is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No live case {case_id}."})
    a = p.account
    if not policy.tenant_ok(a, c["owner"], p.ctx) or not policy.location_ok(a, c["location"]):
        msg = (
            f"{case_id} is at {c['location']}, outside your warehouse."
            if policy.policy(a).get("warehouseScoped")
            else f"{case_id} belongs to {c['owner']}, a tenant you cannot see. Request tenant access first."
        )
        raise HTTPException(403, {"code": "tenant_boundary", "message": msg})
    return c


def my_cases(p: Principal, session: Session) -> list[Case]:
    """The demo's myCases: every case in the account's tenants and warehouse."""
    return [
        c
        for c in store.all_cases(session)
        if policy.tenant_ok(p.account, c["owner"], p.ctx) and policy.location_ok(p.account, c["location"])
    ]


def vis_cases(p: Principal, session: Session, tenant: str = "All") -> list[Case]:
    """The demo's visCases: myCases narrowed by the top-bar tenant filter (S.tenant; "All" by default)."""
    return [c for c in my_cases(p, session) if tenant == "All" or c["owner"] == tenant]


# The demo lists a case's specification in a fixed order per class; the database's JSON type keeps keys sorted, so the
# order is restored here (the drawer shows the fields in it, and the configuration's provenance value uses the first three).
SPEC_ORDER = {
    "motor": ["Rated power", "IEC frame", "Efficiency class", "Voltage", "Speed"],
    "pump": ["Flow", "Head", "Pressure", "Drive", "Port"],
    "drill": ["Type", "Voltage", "Battery cycles", "Chuck"],
    "control": ["Family", "I/O points", "Firmware", "Supply", "Safety rating"],
    "it": ["Device", "CPU / RAM", "Storage", "Battery health", "Data erasure"],
    "batch": ["Tool type", "Cell chemistry", "Lot grade", "Calibration"],
}
BACKEND_ONLY = ("hazardousMaterial",)  # engine inputs the demo's case record does not carry


def ordered_spec(c: Case) -> dict:
    spec = c.get("spec") or {}
    order = SPEC_ORDER.get(c["cls"], [])
    return {k: spec[k] for k in order if k in spec} | {k: v for k, v in sorted(spec.items()) if k not in order}


def case_record(c: Case, session: Session) -> Case:
    """The case record as the pages read it (the demo's CASE_BY_ID entry). A pool's partner case carries the pool's
    result (the demo's poolResult)."""
    out = {k: v for k, v in c.items() if k not in BACKEND_ONLY}
    out["spec"] = ordered_spec(c)
    if POOL_HOME.get(c["id"], c["id"]) != c["id"]:
        out["poolResult"] = pool_of(session, c["id"])
    return out


TIMES = {"d0", "eta", "etd", "need", "repairAt", "readyAt", "t0", "due", "due2", "end", "auth", "pickup", "acq"}


def with_times(v: Any, key: str | None = None) -> Any:
    """Times kept as epoch milliseconds by the ports, as ISO strings (as the demo's Dates are sent)."""
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, int | float):
        return iso(v) if key in TIMES else v
    if isinstance(v, dict):
        return {k: with_times(x, k) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [with_times(x) for x in v]
    return v


def no_inf(v: float | None) -> float | None:
    """JSON has no Infinity: an unlimited amount is sent as null."""
    return None if v is None or math.isinf(v) else v


def src(sid: str | None) -> dict | None:
    """The demo's SRC: a source system by id."""
    return SOURCES.get(sid) if sid else None


def as_rma(c: Case) -> str:
    return f"RMA-{55800 + as_hex(c, 'rma') % 900}"


def ex_inbound(c: Case) -> dict:
    """The demo's exInbound: the inbound lane from the customer site to the receiving facility, as laneCost prices it."""
    ts = TENANT_SITES.get(c["owner"]) or TENANT_SITES["Customer A"]
    o = SITE_LOC[ts[int(c["id"][3:]) % len(ts)]]
    to = FAC_LOC.get(c["location"]) or "WH-PNQ-01"
    return {"from": o, "to": to, **lane_cost(o, to, max(150, ex_kg(c)))}


def af_lease(c: Case) -> dict:
    """The demo's afLease: stages 1-3 (lease end, return authorisation, pickup and transit), derived from the case id."""

    def h(k: str) -> int:
        return as_hex(c, "|af|" + k)

    rec = ms(c["received"])
    end = add_days(rec, -(16 + h("end") % 38))
    auth = add_days(end, 3 + h("ra") % 6)
    pk = add_days(auth, 2 + h("pk") % 5)
    eta = add_days(rec, -(h("eta") % 2))
    k = CLASSES[c["cls"]]
    book = js_round(k["pnew"] * c["qty"] * math.exp(-c["age"] / (k["tau"] * 1.6)) / 10) * 10
    if c["cls"] in ("motor", "pump"):
        usage = f"{9000 + h('u') % 26000} operating hours"
    elif c["cls"] == "it":
        usage = f"{h('u') % 4 + 2} years in service"
    else:
        usage = f"{h('u') % 900 + 300} cycles"
    lane = ex_inbound(c)
    return {
        "lease": f"LC-{4000 + h('lc') % 900}",
        "end": end,
        "intent": ["return at term", "return at term", "early return", "upgrade to a newer model"][h("in") % 4],
        "usage": usage,
        "rma": as_rma(c),
        "auth": auth,
        "fee": c["qty"] * (0 if h("fee") % 3 else 40 + h("f2") % 8 * 10),
        "repl": demand_order(c),
        "book": book,
        "acq": add_days(AS_OF, -js_round(c["age"] * 365.25)),
        "pickup": pk,
        "eta": eta,
        "carrier": ["Northline 3PL", "Velo Freight", "Coastal Haulage"][h("cr") % 3],
        "freight": js_round(lane["inr"] / FX),
        "lane": lane,
        "sim": True,
    }


# ---------------------------------------------------------------- provenance (the demo's PMAP and provFor)
def js_text(v: Any) -> str:
    """JavaScript's String(v) for the values a case's specification holds."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return str(int(v)) if float(v).is_integer() else repr(v)
    return str(v)


PMAP: dict[str, dict] = {
    "ret": {
        "s": "wms",
        "t": "movements",
        "col": "RCV_TS",
        "pre": "MV",
        "q": lambda c: f"GET /movements?return_id={c['id']}&asset_id={c['assetId']}",
        "val": lambda c: f"{fmt_dy(c['received'])} · received at {c['location']}",
        "use": ["Case creation", "Gate 1 Condition & life (identity of receipt)"],
        "proc": ["Normalised local time to UTC (MV_TS)", "Linked to asset identity"],
    },
    "id": {
        "s": "plm",
        "t": "BOM_HEADER",
        "col": "CFG_ID",
        "pre": "CFG",
        "q": lambda c: f"poll boms.csv · filter CFG_ID for {c['assetId']}",
        "val": lambda c: " · ".join(js_text(v) for v in list(ordered_spec(c).values())[:3]),
        "use": ["Gate 3 Policy & certification (compatibility)", "Demand matching (specification)"],
        "proc": ["Decoded configuration code", "Matched to approved alternates", "Linked to asset identity"],
    },
    "insp": {
        "s": "insp",
        "t": "inspections",
        "col": "GRADE_TXT",
        "pre": "INS",
        "q": lambda c: f"GET /inspections?asset_id={c['assetId']}&latest=true",
        "val": lambda c: f"Grade {c['grade']}" if c.get("grade") else c["condition"],
        "use": ["Gate 1 Condition & life", "Prediction: prep-cost-time v1.3", "Prediction: resale-price v1.3"],
        "proc": ["Mapped grade text through grade table v3", "Validated against condition schema v2.1"],
    },
    "svc": {
        "s": "eam",
        "t": "work_orders",
        "col": "LAST_SVC",
        "pre": "WO",
        "q": lambda c: f"GET /work-orders?asset_id={c['assetId']}&since=2023-01-01",
        "val": lambda c: f"Last service {fmt_dy(add_days(c['received'], -(30 + int(hash_id(c['id']), 16) % 200)))}",
        "use": ["Prediction: service-exposure v1.2", "Gate 2 Post-intervention"],
        "proc": ["Converted to UTC", "Aggregated failure history"],
    },
    "eng": {
        "s": "eng",
        "t": "assessments",
        "col": "RUL_MO",
        "pre": "ENG",
        "q": lambda c: f"GET /certificates?asset_id={c['assetId']}&type=life-assessment",
        "val": lambda c: f"Engineering life: {c['engLife']}",
        "use": ["Gate 1 Condition & life", "Economics: service exposure horizon"],
        "proc": ["Kept source assumptions and confidence", "Validated against policy POL-3.2"],
    },
    "photo": {
        "s": "insp",
        "t": "attachments",
        "col": "PHOTOS",
        "pre": "IMG",
        "q": lambda c: f"GET /inspections/attachments?asset_id={c['assetId']}",
        "val": lambda c: f"{6 + int(hash_id(c['id'] + 'p'), 16) % 10} images",
        "use": ["Condition validation"],
        "proc": ["Counted attachments", "Checksums recorded"],
    },
    "dem": {
        "s": "crm",
        "t": "opportunities",
        "col": "OPP_STG",
        "pre": "OPP",
        "q": lambda c: f"GET /opportunities?site={(c.get('demand') or {}).get('site') or 'any'}&spec_match={c['assetId']}",
        "val": lambda c: (
            f"{c['demand']['site']} requirement · qty {c['qty']} · {'confirmed' if c['demand'].get('confirmed') else 'forecast'}"
            if (c.get("demand") or {}).get("internal")
            else "No open internal requirement matched"
        ),
        "use": ["Gate 4 Demand fit", "Route candidates (redeploy, re-lease)"],
        "proc": ["Stage mapped to confirmed or forecast", "Specification matched via PLM"],
    },
    "mkt": {
        "s": "mkt",
        "t": "comparables",
        "col": "SOLD_PRC",
        "pre": "CMP",
        "q": lambda c: f"GET /comparables?class={c['cls']}&grade={c.get('grade') or 'any'}&age={js_round(c['age'])}y",
        "val": lambda c: _mkt_val(c),
        "use": ["Prediction: resale-price v1.3", "Economics: sale routes"],
        "proc": ["Currency and unit normalised", "Dealer grade mapped to grade table v3"],
    },
    "cost": {
        "s": "erp",
        "t": "costs",
        "col": "COST_AMT",
        "pre": "ERP",
        "q": lambda c: f"GET /purchase-plans?asset_class={c['cls']}&site={(c.get('demand') or {}).get('site') or 'any'}",
        "val": lambda c: _cost_val(c),
        "use": ["Economics: avoided purchase", "Baseline definition"],
        "proc": ["Currency converted to USD", "Cost basis aligned across routes"],
    },
    "pol": {
        "s": "qms",
        "t": "policies",
        "col": "REUSE",
        "pre": "POL",
        "q": lambda c: f"GET /policies?class={c['cls']}&owner={quote(c['owner'], safe='-_.!~*()' + chr(39))}",
        "val": lambda c: "Reuse permitted · policy POL-3.2",
        "use": ["Gate 3 Policy & certification"],
        "proc": ["Policy map v3.2 applied"],
    },
}
# Motors and pumps are inspected in the MRO workshop: their inspection report and photos come from the repair system
# (the demo's later override of provFor).
REPAIR_PMAP = {
    "insp": {
        "s": "repair",
        "t": "repair_inspections",
        "q": lambda c: f"GET /repair-orders?serial={c.get('serial') or c['assetId']}&task=receiving-inspection",
    },
    "photo": {
        "s": "repair",
        "t": "repair_attachments",
        "q": lambda c: f"GET /repair-orders/attachments?serial={c.get('serial') or c['assetId']}",
    },
}


def _mkt_val(c: Case) -> str:
    r = next((x for x in c["routes"] if x["id"] == "resale" and x["terms"]), None)
    if not r:
        return "Comparable set retrieved"
    return f"{14 + int(hash_id(c['id'] + 'm'), 16) % 40} comparable sales · expected {money(r['terms'][0]['amt'])}"


def _cost_val(c: Case) -> str:
    t = next((t for r in c["routes"] for t in [next((x for x in r["terms"] if x["kind"] == "purchase"), None)] if t), None)
    return f"Planned purchase {money(t['amt'])}" if t else "Cost basis retrieved"


def fetch_time(c: Case, e: dict) -> int:
    """The demo's fetchTimeOf: when an evidence item was fetched, from its freshness text (epoch ms)."""
    h = int(hash_id(c["id"] + e["k"]), 16)
    f = e.get("fresh") or ""
    if e["k"] == "mkt":
        return AS_OF - ((src("mkt") or {}).get("freshMin") or 1) * 60000 - (h % 50) * 1000
    if "just now" in f:
        return AS_OF - (h % 40) * 1000
    if m := re.search(r"(\d+) min", f):
        return AS_OF - (int(m[1]) * 60 + h % 50) * 1000
    if m := re.search(r"(\d+) h", f):
        return AS_OF - (int(m[1]) * 3600 + h % 1700) * 1000
    return AS_OF - (86400 + h % 28000) * 1000


def _ymd(t: int) -> str:
    return iso(t)[:10].replace("-", "")


def prov_for(c: Case, e: dict) -> dict:
    """The demo's provFor: where an evidence item came from (system, file, table, record, exact value, fetch time,
    request, checksum, processing) and what it is used in. Times are ISO strings."""
    m = PMAP.get(e["k"])
    if m and c["cls"] in ("motor", "pump") and e["k"] in REPAIR_PMAP and src("repair"):
        m = m | REPAIR_PMAP[e["k"]]
    pid = "PRV-" + hash_id(c["id"] + e["k"] + "p")[:6]
    if not m or e["state"] == "missing":
        s0 = src(m["s"]) if m else None
        reason = (
            (e.get("note") or "Evidence has not been supplied by the source system.")
            + " No fetch is recorded, so nothing is shown."
            if e["state"] == "missing"
            else "No provenance mapping exists for this item."
        )
        return {
            "id": pid,
            "status": "unavailable",
            "key": e["k"],
            "label": e["label"],
            "reason": reason,
            "sourceName": s0["name"] if s0 else e.get("source"),
            "usedIn": [],
        }
    s = src(m["s"])
    h = int(hash_id(c["id"] + e["k"] + "r"), 16)
    fa = fetch_time(c, e)
    via_api = bool(re.search(r"API|Events", s["mode"]))
    ext = "json" if via_api else "csv"
    hhmm = iso(fa)[11:16].replace(":", "")
    p = {
        "id": pid,
        "key": e["k"],
        "label": e["label"],
        "status": "available",
        "state": e["state"],
        "sourceName": s["name"],
        "vendor": s["vendor"],
        "mode": s["mode"],
        "auth": s["auth"],
        "file": f"landing/{m['s']}/{_ymd(fa)}/{m['t']}_{hhmm}.{ext}",
        "fileNote": "Staged API response (Connection Fabric)" if via_api else "Staged poll file (Connection Fabric)",
        "table": m["t"],
        "sheetKind": "resource" if via_api else "sheet",
        "column": m["col"],
        "record": f"{m['pre']}-{20000 + h % 80000}",
        "row": 1 + h % 4800,
        "rowsTotal": 2000 + h % 4000,
        "value": m["val"](c),
        "fetchedAt": iso(fa),
        "observedAt": iso(fa - (60 + h % 900) * 1000),
        "request": m["q"](c),
        "checksum": "sha256:" + hash_id(c["id"] + e["k"] + "x").lower() + hash_id(e["k"] + c["id"]).lower(),
        "processing": [
            f"Fetched via {s['vendor']} adapter ({s['auth']})",
            "Staged to landing file with checksum",
            *m["proc"],
            "Written to canonical model",
            f"Linked to {c['assetId']}",
        ],
        "usedIn": list(m["use"]),
        "notes": [],
    }
    if c.get("recommendation") and c.get("snapshot"):
        p["usedIn"].append(f"Decision DI-2026-{c['id'][3:]} · snapshot {c['snapshot']['id']}")
    if e["state"] == "stale":
        p["notes"].append("Source value is stale: " + (e.get("note") or "older than the freshness threshold"))
    if e["k"] == "mkt" and s.get("status") == "stale":
        p["notes"].append("Market feed is stale; last successful pull shown. Predictions carry a reduced-confidence flag.")
    if e["state"] == "partial":
        p["notes"].append(e.get("note") or "Partial evidence")
        p.update(status="partial", row=None, record=None)
        p["partialWhy"] = "Record references exist only for the units that were inspected; the remainder have no source record."
    if e["state"] == "conflict":
        p["status"] = "partial"
        p["notes"].append(e.get("note") or "Conflicting records")
        p.update(file=None, table=None, column=None, row=None, record=None)
        p["partialWhy"] = "The conflicting value comes from a physical label, which has no system record to trace."
    return p


def snap_time(c: Case) -> str:
    """The demo's snapTime: 90 s after the last evidence fetch (ISO)."""
    t = [fetch_time(c, e) for e in c["evidence"] if e["state"] != "missing"]
    return iso((max(t) if t else AS_OF) + 90000)


# ---------------------------------------------------------------- small demo helpers
def st_when(d: Any) -> str:
    """The demo's stWhen: "07 Oct 14:20" (the time only when it is not midnight UTC)."""
    if not d:
        return ""
    t = ms(d)
    hm = iso(t)[11:16]
    return fmt_d(t) + ("" if hm == "00:00" else " " + hm)


def same_route(a: dict | None, b: dict | None) -> bool:
    """`a === b` for routes (a stored case keeps copies; routes are told apart by plan, as di.execution does)."""
    return bool(a and b and a["plan"] == b["plan"] and a["id"] == b["id"])


def eligible(c: Case) -> list[dict]:
    return sorted((x for x in c["routes"] if not x["excluded"]), key=lambda x: -x["net"])


def steps_of(c: Case) -> list[dict]:
    """The demo's stepsOf: the instruction's steps, or the steps the route would send (by route id)."""
    if c.get("exec"):
        return c["exec"]["steps"]
    r = c.get("chosen") or c.get("recommendation") or {"id": "resale"}
    return steps_for({"id": r["id"]}, -1)


def default_spend(c: Case, r: dict) -> int:
    """The demo's defaultSpend: the preparation cost, as the spend the approval authorises."""
    return js_round(-js_sum(t["amt"] for t in r["terms"] if t["kind"] == "prep" and t["amt"] < 0))


def prep_cost(c: Case) -> float:
    """The demo's asPrepCost."""
    r = c.get("chosen") or c.get("recommendation")
    return -js_sum(t["amt"] for t in r["terms"] if t["kind"] == "prep" and t["amt"] < 0) if r else 0


def limit_of_role(role: str, p: Principal) -> float:
    return policy.limit_for(policy.Account(id="", role=role, label=role), p.ctx)


def instr_payload(c: Case) -> dict:
    """The demo's instrPayload: the instruction approval sends (times ISO)."""
    r = c.get("chosen") or c.get("recommendation")
    x, steps, M, mv = c.get("exec"), steps_of(c), case_demand(c) or {}, ex_move(c, r)
    pl = ex_plan(c, r, AS_OF)
    appr = c.get("approval") or {}
    legs = mv["legs"] if mv else []
    return {
        "decisionId": x["decisionId"] if x else "DI-2026-" + c["id"][3:],
        "approvalRef": x["ref"] if x else "(added on approval)",
        "instructionVersion": x.get("instruction") if x else 1,
        "destination": steps[0]["sys"],
        "targets": [s["sys"] for s in steps],
        "caseId": c["id"],
        "assetId": c["assetId"],
        "quantity": c["qty"],
        "action": r["id"],
        "plan": r["plan"],
        "targetSite": r.get("target") or M.get("site") or None,
        "order": M.get("order") or None,
        "orderLine": M.get("line") or None,
        "shipTo": M.get("shipTo") or None,
        "needBy": M.get("needBy") or None,
        "avoidedPurchase": M.get("avoidedPo") or None,
        "sourceLocation": FAC_LOC.get(c["location"]),
        "stagingWarehouse": mv["stage"]["code"] if mv and mv.get("stage") else None,
        "etd": iso(legs[0]["etd"]) if legs else None,
        "eta": iso(mv["eta"]) if mv and mv.get("eta") else None,
        "legs": [
            {
                "from": leg["from"],
                "to": leg["to"],
                "km": leg["km"],
                "etd": iso(leg["etd"]),
                "eta": iso(leg["eta"]),
                "carrier": leg["carrier"],
                "freightInr": leg["inr"],
            }
            for leg in legs
        ],
        "steps": [
            {
                "step": s["n"],
                "action": s["act"],
                "system": s["app"],
                "document": s["docs"][0],
                "owner": s["owner"],
                "timeLimit": s["lim"],
            }
            for s in pl
        ],
        "expectedNetUsd": r["net"],
        "spendAuthorityUsd": appr["spend"] if appr.get("spend") is not None else default_spend(c, r),
        "terms": appr.get("terms") or "As approved",
        "evidenceSnapshot": c["snapshot"]["id"],
        "policyVersion": "POL-3.2",
        "modelVersion": c.get("model"),
        "idempotencyKey": "idem-" + hash_id(c["id"] + (x["ref"] if x else "pending"))[:6].lower(),
    }


def case_journal(session: Session, case_id: str) -> list[dict]:
    """The demo's afCaseJournal: the recorded actions on the case (not undone), oldest first."""
    rows = session.execute(
        text(
            "SELECT seq, action, input, actor, preparer, run_id, output_ref, at FROM action_journal "
            "WHERE input->>'case_id' = :c AND NOT undone ORDER BY seq"
        ),
        {"c": case_id},
    ).all()
    out = []
    for r in rows:
        a = policy.account(r.actor)
        by = "Enterprise system adapter" if r.actor == "system" else (a.label if a else r.actor)
        out.append(
            {
                "seq": r.seq,
                "id": r.action,
                "by": by,
                "prep": r.preparer,
                "input": r.input,
                "out": r.output_ref,
                "at": iso(r.at.isoformat()),
                "run": r.run_id,
            }
        )
    return out


# ================================================================ the stage pages
def stage_tag(c: Case, n: int, rn: dict, p: Principal, deleg: bool) -> dict:
    """The demo's stState: a stage's tag (done, not reached, blocked, waiting on someone, current)."""
    s = rn["stages"][n - 1]
    x = c.get("exec")
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


def stage_data(c: Case, n: int, rn: dict, p: Principal, deleg: bool) -> dict:
    """The demo's stData without its detail tabs: what a stage established (res), its facts (each with the kind of
    provenance and the system behind it), documents, what it means, when and who."""
    L = af_lease(c)
    s = rn["stages"][n - 1]
    r = c.get("chosen") or c.get("recommendation")
    M, R, x = case_demand(c), case_rul(c), c.get("exec")
    st = x["steps"] if x else []
    ev = c.get("evidence") or []
    miss = [e for e in ev if e["state"] != "ready"]
    el = eligible(c)
    ex = [z for z in c["routes"] if z["excluded"]]
    nx = next((z for z in el if not same_route(z, r)), None) if r else None
    o: dict[str, Any] = {"res": "", "facts": [], "docs": [], "mean": "", "when": s.get("at"), "who": s.get("by") or ""}
    facts: list[dict] = o["facts"]

    def F(label: str, v: str, k: str, sys: str) -> None:
        facts.append({"l": label, "v": v, "k": k, "sys": sys})

    lane = L["lane"]
    blocked = c.get("blocked")
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
        code = FAC_LOC.get(c["location"])
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
        F("Grade", f"Grade {c['grade']}" if c.get("grade") else "Not graded", "ret", "MRO" if ws == "MRO" else "Inspection")
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
        pay = instr_payload(c) if r else None
        appr, sub = c.get("approval"), c.get("submitted")
        lim = None if appr else limit_of_role("Approver" if deleg else "Admin", p)
        apps = list(dict.fromkeys(ex_app(y) for y in steps_of(c))) if r else []
        apps = [a for a in apps if not re.match(r"^Circularity|^Planning", a)]
        if appr:
            o["res"] = (
                f"{'Override approved' if c.get('override') else 'Approved'} by {appr['by']} under {appr['ref']}: {r['plan']}."
            )
        elif sub:
            o["res"] = f"Submitted by {sub['by']} on {fmt_d(sub['at'])}; waiting for {'the Approver' if deleg else 'Admin'}."
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
        mv = ex_move(c, r) if r else None
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
        o9, last = c.get("outcome"), (st[-1] if st else None)
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
        o10 = c.get("outcome")

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


@router.get("/{case_id}")
def case_page(case_id: str, p: Principal = Depends(principal), session: Session = Depends(get_session)):
    """Everything the stage bar, the stage pages, the Overview and the approval card read, for one case."""
    c = load_case(p, session, case_id, "product", "case")
    ctx = screen_ctx(p, session)
    deleg = decisions_delegated(ctx)
    rn = run(c, ctx)
    return {
        "case": case_record(c, session),
        "model": as_model(c),
        "serial": "SN" + str(as_hex(c, "sn"))[:7].rjust(7, "0"),
        "run": rn,
        "tags": [stage_tag(c, n, rn, p, deleg) for n in range(1, 11)],
        "stages": [stage_data(c, n, rn, p, deleg) for n in range(1, 11)],
        "landing": landing(rn, p.account.role),
        "next": next_step(c, ctx),
        "clock": active_clock(c),
        "approval": {"role": "Approver" if deleg else "Admin", "limit": no_inf(policy.limit_for(p.account, p.ctx))},
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


@router.get("/{case_id}/analysis")
def case_analysis(case_id: str, p: Principal = Depends(principal), session: Session = Depends(get_session)):
    """The data behind the stage pages' detail tabs and Full analysis."""
    c = load_case(p, session, case_id, "product", "case")
    ctx = screen_ctx(p, session)
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
    }


# The demo's two pools: each is solved for its hero case, and its partner case shows the same result (POOLS, poolResult).
POOL_HOME = {"RT-1048": "RT-1048", "RT-1062": "RT-1048", "RT-1052": "RT-1052", "RT-1044": "RT-1052"}


def pool_of(session: Session, case_id: str) -> dict | None:
    """The pool a case belongs to, solved (the demo's solvePool, di.engine.pool)."""
    home = store.get(session, POOL_HOME[case_id]) if case_id in POOL_HOME else None
    return solve_pool(home["pool"]) if home and home.get("pool") else None


def recert(c: Case, r: dict | None) -> dict | None:
    """The demo's recert under the base assumptions: a redeployment or re-lease whose demand horizon outlasts the
    certified period needs recertification."""
    if not r or r["id"] not in ("redeploy", "relase"):
        return None
    R, D = case_rul(c), case_demand(c)
    if not R or not D:
        return None
    need = D["horizonMonths"]
    return {"need": need, "cert": R["certMonths"]} if need > R["certMonths"] else None
