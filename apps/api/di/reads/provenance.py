"""Provenance of a case's evidence (the demo's PMAP, provFor, fetchTimeOf and snapTime): one map, read by the Case
and Audit screens and the case.evidence read.

- `PMAP`: per kind of evidence, the source system, table, column, record prefix, request, value, where the value is
  used and how it was processed; motors and pumps trace their inspection and photos to the repair system
  (`REPAIR_PMAP`, the demo's later override of provFor).
- `prov_for(c, e)`: one evidence item's provenance (times ISO), or why it is unavailable.
- `fetch_time(c, e)`: when an evidence item was fetched (epoch ms); `snap_time(c)`: the evidence snapshot's time.
- `ordered_spec(c)`: the case's specification in the demo's per-class order (the database's JSON type sorts keys).
"""

import re
from typing import Any
from urllib.parse import quote

from di.engine.jsmath import js_round
from di.reads.common import AS_OF, SOURCES, Case, add_days, fmt_dy, hash_id, iso, money

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


def ordered_spec(c: Case) -> dict:
    spec = c.get("spec") or {}
    order = SPEC_ORDER.get(c["cls"], [])
    return {k: spec[k] for k in order if k in spec} | {k: v for k, v in sorted(spec.items()) if k not in order}


def js_text(v: Any) -> str:
    """JavaScript's String(v) for the values a case's specification holds."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return str(int(v)) if float(v).is_integer() else repr(v)
    return str(v)


def src(sid: str | None) -> dict | None:
    """The demo's SRC: a source system by id."""
    return SOURCES.get(sid) if sid else None


def _mkt_val(c: Case) -> str:
    r = next((x for x in c["routes"] if x["id"] == "resale" and x["terms"]), None)
    if not r:
        return "Comparable set retrieved"
    return f"{14 + int(hash_id(c['id'] + 'm'), 16) % 40} comparable sales · expected {money(r['terms'][0]['amt'])}"


def _cost_val(c: Case) -> str:
    t = next((t for r in c["routes"] for t in [next((x for x in r["terms"] if x["kind"] == "purchase"), None)] if t), None)
    return f"Planned purchase {money(t['amt'])}" if t else "Cost basis retrieved"


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
        "val": lambda c: "Reuse permitted · policy POL-3.2",  # noqa: ARG005 - every field value takes the case
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


def pmap(c: Case, k: str) -> dict | None:
    """PMAP[k] for this case, with the repair system's override for motors and pumps."""
    m = PMAP.get(k)
    if m and c["cls"] in ("motor", "pump") and k in REPAIR_PMAP and src("repair"):
        m = m | REPAIR_PMAP[k]
    return m


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
    m = pmap(c, e["k"])
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
