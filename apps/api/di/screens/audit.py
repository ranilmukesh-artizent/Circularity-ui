"""Audit & provenance (#/audit; docs/BACKEND_STEPS.md, B14): the log of evidence fetches and system events, the evidence
gaps, provenance records and comments.

    GET /api/screens/audit?tenant_filter=All
        entries   the demo's auditEntries() for the signed-in account: one "fetch" entry per evidence item of each
                  visible case (not missing), with its full provenance record (p), then one "event" entry per
                  instruction or event (ev) the account may see; the agent layer's additions (who acted, the agent
                  that prepared it, the run) are in `used` and `prep`. Case order, then the event log's order (newest
                  first); the page sorts and filters (search, source, kind, provenance, prepared by agent) itself.
        gaps      the demo's auditGaps(): {c: {id, assetId, evidence}, e: evidence item} for each missing item, with
                  its provenance record (p: status "unavailable" and the reason) for the data trace
        comments  the comments on the visible entries, keyed "au:<entry id>" (the demo's S.cm), oldest first
    GET /api/screens/audit/provenance?case_id=&key=   the demo's provenanceOf(caseId, key): {c, ev, p}
    GET /api/screens/audit/comments?key=              the comments under any record key (audit entries, sources ...)
    POST /api/actions/comment.add                     posting a comment (B12)

Where the data comes from:
- cases: the database (di.cases.store), scoped like the demo's visCases (tenants, a Warehouse Manager's warehouse,
  and the top bar's tenant filter);
- events: the workspace collection "events" (di.state), the demo's EVENTS with what actions have added since;
- comments: the workspace collection "comments" (written by comment.add);
- provenance: the demo's provFor, ported here in full (di.reads.cases.provenance ports only the fields its reads
  use). It describes each item by the demo's source catalogue (fixtures/golden/sources.json: name, vendor, access
  mode, authentication, status), which is what the page shows today. The connectors also keep a real HTTP fetch log
  (table fetch_log, GET /api/fetch-log, B9); it records the sync calls, not one fetch per evidence item, so it is
  not mixed into these entries. B17 can add it to the page as its own section.

Facade mapping (apps/web/src/api/audit.ts), for the switch-over (B17):

| export                         | served by                                                                    |
|--------------------------------|------------------------------------------------------------------------------|
| auditEntries()                 | endpoint: GET /api/screens/audit (entries; ts as ISO strings)                 |
| auditGaps()                    | endpoint: same answer (gaps)                                                  |
| comments(key)                  | endpoint: same answer (comments) for audit entries; /audit/comments?key=      |
| provenanceOf(caseId, key)      | endpoint: GET /api/screens/audit/provenance (also in entries[].p, gaps[].p)    |
| caseById(id)                   | endpoint: GET /api/screens/audit/provenance (c), or the case APIs             |
| postComment(key, text)         | action: comment.add (already served)                                          |
| isoT, eventJson, ackKind       | frontend-only: formatting                                                     |
"""

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from di import policy, state
from di.auth import Principal, principal
from di.cases import store
from di.db import get_session
from di.engine.jsmath import js_round
from di.reads.cases import _fetch_time
from di.reads.common import SOURCES, add_days, fmt_dy, hash_id, iso, money
from di.screens.analytics import call_context, vis_cases_filtered

router = APIRouter(prefix="/api/screens/audit", tags=["screens: audit"])
Case = dict[str, Any]

# The order of each class's specification fields in the demo (the cases are stored as JSON documents, whose keys the
# database sorts): the identity record shows the first three. Belongs with the case model (shared helper).
SPEC_ORDER = {
    "motor": ["Rated power", "IEC frame", "Efficiency class", "Voltage", "Speed"],
    "pump": ["Flow", "Head", "Pressure", "Drive", "Port"],
    "drill": ["Type", "Voltage", "Battery cycles", "Chuck"],
    "control": ["Family", "I/O points", "Firmware", "Supply", "Safety rating"],
    "it": ["Device", "CPU / RAM", "Storage", "Battery health", "Data erasure"],
    "batch": ["Tool type", "Cell chemistry", "Lot grade", "Calibration"],
}


def _spec_values(c: Case) -> list:
    spec = c.get("spec") or {}
    order = SPEC_ORDER.get(c["cls"], [])
    keys = [k for k in order if k in spec] + [k for k in spec if k not in order]
    return [spec[k] for k in keys]


def _site(c: Case) -> str:
    return (c.get("demand") or {}).get("site") or "any"


def _mkt_value(c: Case) -> str:
    r = next((x for x in c["routes"] if x["id"] == "resale" and x["terms"]), None)
    if not r:
        return "Comparable set retrieved"
    return f"{14 + int(hash_id(c['id'] + 'm'), 16) % 40} comparable sales · expected {money(r['terms'][0]['amt'])}"


def _cost_value(c: Case) -> str:
    t = next((t for r in c["routes"] if (t := next((x for x in r["terms"] if x["kind"] == "purchase"), None))), None)
    return f"Planned purchase {money(t['amt'])}" if t else "Cost basis retrieved"


def _dem_value(c: Case) -> str:
    d = c.get("demand")
    if d and d.get("internal"):
        return f"{d['site']} requirement · qty {c['qty']} · {'confirmed' if d.get('confirmed') else 'forecast'}"
    return "No open internal requirement matched"


# The demo's PMAP: per kind of evidence, the source system, table, column, record prefix, request, value, where the
# value is used and how it was processed.
PMAP: dict[str, dict] = {
    "ret": {
        "s": "wms", "t": "movements", "col": "RCV_TS", "pre": "MV",
        "q": lambda c: f"GET /movements?return_id={c['id']}&asset_id={c['assetId']}",
        "val": lambda c: f"{fmt_dy(c['received'])} · received at {c['location']}",
        "use": ["Case creation", "Gate 1 Condition & life (identity of receipt)"],
        "proc": ["Normalised local time to UTC (MV_TS)", "Linked to asset identity"],
    },
    "id": {
        "s": "plm", "t": "BOM_HEADER", "col": "CFG_ID", "pre": "CFG",
        "q": lambda c: f"poll boms.csv · filter CFG_ID for {c['assetId']}",
        "val": lambda c: " · ".join(str(v) for v in _spec_values(c)[:3]),
        "use": ["Gate 3 Policy & certification (compatibility)", "Demand matching (specification)"],
        "proc": ["Decoded configuration code", "Matched to approved alternates", "Linked to asset identity"],
    },
    "insp": {
        "s": "insp", "t": "inspections", "col": "GRADE_TXT", "pre": "INS",
        "q": lambda c: f"GET /inspections?asset_id={c['assetId']}&latest=true",
        "val": lambda c: f"Grade {c['grade']}" if c.get("grade") else c.get("condition"),
        "use": ["Gate 1 Condition & life", "Prediction: prep-cost-time v1.3", "Prediction: resale-price v1.3"],
        "proc": ["Mapped grade text through grade table v3", "Validated against condition schema v2.1"],
    },
    "svc": {
        "s": "eam", "t": "work_orders", "col": "LAST_SVC", "pre": "WO",
        "q": lambda c: f"GET /work-orders?asset_id={c['assetId']}&since=2023-01-01",
        "val": lambda c: f"Last service {fmt_dy(add_days(c['received'], -(30 + int(hash_id(c['id']), 16) % 200)))}",
        "use": ["Prediction: service-exposure v1.2", "Gate 2 Post-intervention"],
        "proc": ["Converted to UTC", "Aggregated failure history"],
    },
    "eng": {
        "s": "eng", "t": "assessments", "col": "RUL_MO", "pre": "ENG",
        "q": lambda c: f"GET /certificates?asset_id={c['assetId']}&type=life-assessment",
        "val": lambda c: f"Engineering life: {c.get('engLife')}",
        "use": ["Gate 1 Condition & life", "Economics: service exposure horizon"],
        "proc": ["Kept source assumptions and confidence", "Validated against policy POL-3.2"],
    },
    "photo": {
        "s": "insp", "t": "attachments", "col": "PHOTOS", "pre": "IMG",
        "q": lambda c: f"GET /inspections/attachments?asset_id={c['assetId']}",
        "val": lambda c: f"{6 + int(hash_id(c['id'] + 'p'), 16) % 10} images",
        "use": ["Condition validation"],
        "proc": ["Counted attachments", "Checksums recorded"],
    },
    "dem": {
        "s": "crm", "t": "opportunities", "col": "OPP_STG", "pre": "OPP",
        "q": lambda c: f"GET /opportunities?site={_site(c)}&spec_match={c['assetId']}",
        "val": _dem_value,
        "use": ["Gate 4 Demand fit", "Route candidates (redeploy, re-lease)"],
        "proc": ["Stage mapped to confirmed or forecast", "Specification matched via PLM"],
    },
    "mkt": {
        "s": "mkt", "t": "comparables", "col": "SOLD_PRC", "pre": "CMP",
        "q": lambda c: f"GET /comparables?class={c['cls']}&grade={c.get('grade') or 'any'}&age={js_round(c['age'])}y",
        "val": _mkt_value,
        "use": ["Prediction: resale-price v1.3", "Economics: sale routes"],
        "proc": ["Currency and unit normalised", "Dealer grade mapped to grade table v3"],
    },
    "cost": {
        "s": "erp", "t": "costs", "col": "COST_AMT", "pre": "ERP",
        "q": lambda c: f"GET /purchase-plans?asset_class={c['cls']}&site={_site(c)}",
        "val": _cost_value,
        "use": ["Economics: avoided purchase", "Baseline definition"],
        "proc": ["Currency converted to USD", "Cost basis aligned across routes"],
    },
    "pol": {
        "s": "qms", "t": "policies", "col": "REUSE", "pre": "POL",
        "q": lambda c: f"GET /policies?class={c['cls']}&owner={quote(c['owner'], safe=chr(39) + '-_.!~*()')}",
        "val": lambda c: "Reuse permitted · policy POL-3.2",
        "use": ["Gate 3 Policy & certification"],
        "proc": ["Policy map v3.2 applied"],
    },
}  # fmt: skip


def _pmap(c: Case, k: str) -> dict | None:
    """PMAP[k], with the demo's later override: motors and pumps are inspected in the MRO workshop, so their
    inspection and photo records trace to Oracle Depot Repair."""
    m = PMAP.get(k)
    if m and c["cls"] in ("motor", "pump") and k in ("insp", "photo") and "repair" in SOURCES:
        serial = c.get("serial") or c["assetId"]
        q = (
            f"GET /repair-orders?serial={serial}&task=receiving-inspection"
            if k == "insp"
            else f"GET /repair-orders/attachments?serial={serial}"
        )
        m = m | {"s": "repair", "t": "repair_inspections" if k == "insp" else "repair_attachments", "q": lambda _c: q}
    return m


def provenance(c: Case, e: dict) -> dict:
    """The demo's provFor(c, e): where an evidence item came from, record by record (or why that is unavailable)."""
    k = e["k"]
    m = _pmap(c, k)
    pid = "PRV-" + hash_id(c["id"] + k + "p")[:6]
    if not m or e["state"] == "missing":
        src = SOURCES.get(m["s"]) if m else None
        return {
            "id": pid,
            "status": "unavailable",
            "key": k,
            "label": e["label"],
            "reason": (
                (e.get("note") or "Evidence has not been supplied by the source system.")
                + " No fetch is recorded, so nothing is shown."
                if e["state"] == "missing"
                else "No provenance mapping exists for this item."
            ),
            "sourceName": src["name"] if src else e.get("source"),
            "usedIn": [],
        }
    s = SOURCES[m["s"]]
    h = int(hash_id(c["id"] + k + "r"), 16)
    fa = _fetch_time(c, e)
    fa_iso = iso(fa)
    via_api = "API" in s["mode"] or "Events" in s["mode"]
    p = {
        "id": pid,
        "key": k,
        "label": e["label"],
        "status": "available",
        "state": e["state"],
        "sourceName": s["name"],
        "vendor": s["vendor"],
        "mode": s["mode"],
        "auth": s["auth"],
        "file": f"landing/{m['s']}/{fa_iso[:10].replace('-', '')}/{m['t']}_{fa_iso[11:16].replace(':', '')}."
        + ("json" if via_api else "csv"),
        "fileNote": "Staged API response (Connection Fabric)" if via_api else "Staged poll file (Connection Fabric)",
        "table": m["t"],
        "sheetKind": "resource" if via_api else "sheet",
        "column": m["col"],
        "record": f"{m['pre']}-{20000 + h % 80000}",
        "row": 1 + h % 4800,
        "rowsTotal": 2000 + h % 4000,
        "value": m["val"](c),
        "fetchedAt": fa_iso,
        "observedAt": iso(fa - (60 + h % 900) * 1000),
        "request": m["q"](c),
        "checksum": "sha256:" + hash_id(c["id"] + k + "x").lower() + hash_id(k + c["id"]).lower(),
        "processing": [f"Fetched via {s['vendor']} adapter ({s['auth']})", "Staged to landing file with checksum"]
        + m["proc"]
        + ["Written to canonical model", "Linked to " + c["assetId"]],
        "usedIn": list(m["use"]),
        "notes": [],
    }
    if c.get("recommendation") and c.get("snapshot"):
        p["usedIn"].append(f"Decision DI-2026-{c['id'][3:]} · snapshot {c['snapshot']['id']}")
    if e["state"] == "stale":
        p["notes"].append("Source value is stale: " + (e.get("note") or "older than the freshness threshold"))
    if k == "mkt" and s.get("status") == "stale":
        p["notes"].append("Market feed is stale; last successful pull shown. Predictions carry a reduced-confidence flag.")
    if e["state"] == "partial":
        p["notes"].append(e.get("note") or "Partial evidence")
        p |= {"status": "partial", "row": None, "record": None}
        p["partialWhy"] = "Record references exist only for the units that were inspected; the remainder have no source record."
    if e["state"] == "conflict":
        p["status"] = "partial"
        p["notes"].append(e.get("note") or "Conflicting records")
        p |= {"file": None, "table": None, "column": None, "row": None, "record": None}
        p["partialWhy"] = "The conflicting value comes from a physical label, which has no system record to trace."
    return p


# ---------------------------------------------------------------- the log
def _event_used(ev: dict) -> str:
    if ev.get("decisionId"):
        used = f"Decision {ev['decisionId']}" + (f" · {ev['approval']}" if ev.get("approval") else "")
    elif ev.get("by"):
        used = "Access control · " + ev["by"]
    else:
        used = "Fabric housekeeping"
    # the agent layer's addition: who acted, the agent that prepared it, the run
    if ev.get("by") or ev.get("prep") or ev.get("run"):
        used += (
            (" · by " + ev["by"] if ev.get("by") else "")
            + (f" · prepared by agent ({ev['prep']})" if ev.get("prep") else "")
            + (" · " + ev["run"] if ev.get("run") else "")
        )
    return used


def entries(p: Principal, session: Session, tenant_filter: str = "All") -> list[dict]:
    """The demo's auditEntries() (with the agent layer's additions), for the signed-in account."""
    ctx = call_context(p, session)
    out: list[dict] = []
    for c in vis_cases_filtered(ctx, tenant_filter):
        for e in c.get("evidence") or []:
            if e["state"] == "missing":
                continue
            pv = provenance(c, e)
            out.append({
                "id": "AU-" + pv["id"], "kind": "fetch", "ts": pv["fetchedAt"], "source": pv["sourceName"],
                "caseId": c["id"], "asset": c["assetId"], "item": e["label"], "key": e["k"], "request": pv["request"],
                "result": "Partial record" if pv["status"] == "partial" else "1 record · " + (pv["table"] or "—"),
                "used": "; ".join(pv["usedIn"][:2]), "status": pv["status"], "prep": None, "p": pv,
            })  # fmt: skip
    by_id = {c["id"]: c for c in store.all_cases(session)}
    tenant_scoped = bool(policy.policy(p.account).get("tenantScoped"))
    for ev in state.items(session, "events", newest_first=True):
        c = by_id.get(ev.get("caseId")) if ev.get("caseId") else None
        if c is not None:
            if not p.tenant_ok(c["owner"]) or not p.location_ok(c["location"]):
                continue
            if tenant_filter != "All" and c["owner"] != tenant_filter:
                continue
        elif tenant_scoped:
            continue
        direction = "Outbound " if ev.get("dir") == "out" else "Inbound "
        key = ev.get("key")
        out.append({
            "id": "AE-" + ev["id"], "kind": "event", "ts": iso(ev["ts"]), "source": ev.get("dest"),
            "caseId": ev.get("caseId") or "—", "asset": c["assetId"] if c else "—", "item": ev.get("type"), "key": "event",
            "request": direction + str(ev.get("type")) + (" · " + key if key and key != "—" else ""),
            "result": ev.get("ack"), "used": _event_used(ev), "status": "recorded", "prep": ev.get("prep") or None, "ev": ev,
        })  # fmt: skip
    return out


def gaps(p: Principal, session: Session, tenant_filter: str = "All") -> list[dict]:
    """The demo's auditGaps(): each missing evidence item of the visible cases, with its (unavailable) provenance."""
    out = []
    for c in vis_cases_filtered(call_context(p, session), tenant_filter):
        lite = {"id": c["id"], "assetId": c["assetId"], "evidence": c.get("evidence") or []}
        for e in c.get("evidence") or []:
            if e["state"] == "missing":
                out.append({"c": lite, "e": e, "p": provenance(c, e)})
    return out


def comments_by_key(session: Session, keys: set[str] | None = None) -> dict[str, list[dict]]:
    """Comments (state collection "comments"), grouped by record key, oldest first, as the demo's S.cm."""
    out: dict[str, list[dict]] = {}
    for x in state.items(session, "comments"):
        if keys is None or x.get("key") in keys:
            out.setdefault(x["key"], []).append(
                {"by": x.get("by"), "at": x.get("at"), "text": x.get("text"), "prep": x.get("prep")}
            )
    return out


@router.get("")
def audit(tenant_filter: str = "All", p: Principal = Depends(principal), session: Session = Depends(get_session)):
    p.require_page("audit")
    es = entries(p, session, tenant_filter)
    return {
        "entries": es,
        "gaps": gaps(p, session, tenant_filter),
        "comments": comments_by_key(session, {"au:" + x["id"] for x in es}),
    }


@router.get("/provenance")
def provenance_of(case_id: str, key: str, p: Principal = Depends(principal), session: Session = Depends(get_session)):
    p.require_page("audit")
    c = store.get(session, case_id)
    if c is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No case {case_id}."})
    p.require_record(case_id, c["owner"], c["location"])
    ev = next((x for x in c.get("evidence") or [] if x["k"] == key), None)
    if ev is None:
        raise HTTPException(404, {"code": "not_found", "message": f"{case_id} has no evidence item {key}."})
    lite = {"id": c["id"], "assetId": c["assetId"], "evidence": c.get("evidence") or []}
    return {"c": lite, "ev": ev, "p": provenance(c, ev)}


@router.get("/comments")
def comments(key: str, p: Principal = Depends(principal), session: Session = Depends(get_session)):
    """Comments under one record key (an audit entry "au:<id>", a source "src:<id>" ...): everyone signed in reads."""
    return comments_by_key(session, {key}).get(key, [])
