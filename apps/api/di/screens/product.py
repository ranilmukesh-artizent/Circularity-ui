"""Product screens (B14): Returned assets, Expected returns, the journey strip, Asset intelligence and the pools.

GET /api/screens/product/returned?tenant=All
    The returned assets in view (tenant, warehouse and the top-bar tenant filter), one row per case with what the
    queue, the KPI strip, the grouping and the case drawer read; the count on the Expected toggle; the account's open
    notifications.
GET /api/screens/product/expected?tenant=All
    The expected returns in view (from contract and lease expiry), each with its case-run marker; the count on the
    toggle; the Contract Management source (vendor, freshness).
GET /api/screens/product/journey/{id}
    The journey strip and guide for a case (Returned assets and Asset intelligence): visible to this account or not,
    the run's stage, and what steps 0 and 1 established. Not visible is an answer (200), not a refusal.
GET /api/screens/product/asset/{id}   (GET /api/screens/product/asset: the default asset)
    Asset intelligence for one case: identity, health, facts, life events, return history, parts and prices,
    catalogue, preparation cost and its build-up, life, demand, diagnostics, recertification, confidence, the order the
    value is committed against, value state, baseline, economics, eligibility, the lease trail, provenance, the
    snapshot time, closed decisions of the product, term methods; and, from the account's cases, the fleet of the same
    class (rows), the related assets, the units of the same product and customer, and the counts behind the SKU picker.
GET /api/screens/product/pools
    The pool optimiser (hidden while the demo's FEAT.pools is off, so 403 for every account today).

Case-scoped reads refuse as the case actions do (403 out_of_scope without the page, 404 not_found, 403 tenant_boundary).

Facade (apps/web/src/api/product.ts) → this API
| export | served by |
|---|---|
| visibleCases | /returned → cases (rows) |
| myCases | /asset/{id} → fleet (same class), units, related, models, customers; /returned with tenant=All |
| caseById | /asset/{id} → case; GET /api/screens/case/{id} → case |
| isCaseId | frontend-only (a case id the frontend has seen; else the case endpoints answer 404) |
| classInfo, routeInfo, facilities, gateNames | reference (CLASSES, ROUTES, FACILITIES, GATES) |
| tenantOK | frontend-only (session: the account's tenants) |
| lastAssetId | /asset (no id) → the default asset; the remembered one is view state |
| rememberAsset | frontend-only (view state S.lastAsset; the frontend passes the id) |
| routeAllowed, poolsEnabled, upliftEnabled, assetTabAllowed | reference / session (page access, FEAT) |
| signals | /returned → cases[].signals |
| expectedVisible | /expected → rows |
| expectedCount | /returned → expected_count (and /expected → count) |
| leaseSource | /expected → source |
| expectedStage | /expected → rows[].run_stage |
| classLabel | reference (CLASSES) |
| myOpenNotes | /returned → notes |
| demoCaseId | frontend-only (the presenter's demo case, S.dpCase, default RT-1048) |
| demoVisible | /journey/{id} → visible (also /asset/{id} → journey) |
| journeySteps, journeyHref, journeyNextText, journeyTitle, journeyLabel, continueLabel | reference (JSTEPS, JG, ...) |
| journeyProgress | /journey/{id} → progress |
| journeyEstablished | /journey/{id} → established[0], established[1] (the only steps these pages show) |
| journeyWaiting | never reached on these pages (the run is always past stage 4) |
| pool | /pools → pools; GET /api/screens/case/{id}/analysis → pool |
| asModel, asTitle, asSerial, asRev, asReceipt, asRMA, asSC, asLease | /asset/{id} → model, title, serial, rev, receipt, |
| | rma, sc, lease_ref; rows carry model and serial |
| asHex | frontend-only (a hash of the case id the asset page uses for illustrative figures) |
| assetHealth | /asset/{id} → health; rows → health (score) |
| assetFacts, assetEvents, assetRelated, skuUnits, returnHistory | /asset/{id} → facts, events, related, units, return_history |
| partsAvailability, partPrices, catalogueValue, prepCost, prepParts | /asset/{id} → parts, part_prices, catalogue, |
| | prep_cost, prep_parts |
| exFx, rateCardId, inr, addDays, locName | reference / frontend-only (₹83.5, RC-2026.2, formatting, dates, names) |
| learnVersion | /asset/{id} → learn_version (prep-cost-time, the one the page shows) |
| caseRul, caseDemand, caseDiag, recert, confidence | /asset/{id} → rul, demand, diag, recert, confidence |
| diagKind | reference (DIAG) |
| valueOrder, valueState, baseline | /asset/{id} → value_order, value_state, baseline |
| caseStageKey | rows → stage_key |
| termMethod | /asset/{id} → term_methods (per term of the recommendation; EX_MC labels are reference) |
| closedLastYear | /asset/{id} → closed_last_year |
| asMoney, localCurrency | frontend-only (formatting, the currency setting) |
| assetEcon | /asset/{id} → econ (its `r` is the case's recommendation) |
| assetEligibility | /asset/{id} → eligibility (rows; its `route` is the recommendation, else the first route) |
| leaseTrail | /asset/{id} → lease_trail |
| badgeTip | reference (AF_BADGE_TIP) |
| provenance, snapshotTime | /asset/{id} → provenance, snapshot_time (ISO; the frontend formats it as isoT) |

Summary: 80 exports → 50 served by the endpoints, 20 reference (or session), 10 frontend-only.

Notes for the switch-over (B17): `null` also stands for the demo's `undefined`; times are ISO strings; the facade's
helpers that take a Case now read the fields above; the per-case figures do not depend on the account, the lists do.
"""

import re

from fastapi import APIRouter
from sqlalchemy.orm import Session

from di import policy
from di.auth import Principal
from di.cases import store
from di.deps import CurrentPrincipal, DbSession
from di.engine.jsmath import js_round, js_sum
from di.execution import as_sc, ex_prep_parts, ex_trace
from di.execution.plan import value_order
from di.execution.trace import learn_ver
from di.reads.asset import (
    as_lease,
    as_serial,
    as_title,
    asset_facts,
    case_diag,
    catalogue,
    health,
    part_prices,
    parts_availability,
)
from di.reads.case_detail import af_lease, as_rma, case_record, pool_of, prep_cost, recert, with_times
from di.reads.common import (
    AS_OF,
    CLASSES,
    SOURCES,
    Case,
    add_days,
    as_hex,
    as_model,
    case_demand,
    case_rul,
    fmt_dy,
    iso,
    ms,
    notes,
    run,
    ti_conf,
)
from di.reads.context import call_ctx, can_see_case, load_case, visible_cases
from di.reads.decisions import all_rows, median
from di.reads.expected import expected_for
from di.reads.provenance import ordered_spec, prov_for, snap_time
from di.reads.workspace import cc_stage

router = APIRouter(prefix="/api/screens/product", tags=["screens: product"])

TENANTS = ["Customer A", "Customer B", "Customer C"]
FACILITIES = ["Warehouse 1", "Warehouse 2", "Repair centre"]
GRADE_F = {"A": 1, "B": 0.86, "C": 0.64, "D": 0.38}
MONTHS = ["Oct 25", "Nov 25", "Dec 25", "Jan 26", "Feb 26", "Mar 26", "Apr 26", "May 26", "Jun 26", "Jul 26", "Aug 26", "Sep 26"]
_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"]  # en-GB, as Node writes it
PAST_DEC = {
    "redeploy": "Reused at another site",
    "resale": "Sold whole",
    "intparts": "Parts recovered for internal use",
    "relase": "Leased again",
    "material": "Material recovered",
    "extparts": "Parts sold",
    "exit": "Responsible exit",
}
# the demo's CC_EST: the median predicted value per unit of each class over the closed decisions (not exits)
CC_EST = {
    k: median([r["p50"] / r["q"] for r in all_rows() if r["cls"] == k and r["route"] != "exit" and r["p50"] > 0]) for k in CLASSES
}
ROW_KEYS = (
    "id",
    "assetId",
    "product",
    "cls",
    "owner",
    "received",
    "location",
    "condition",
    "assessment",
    "stage",
    "qty",
    "grade",
    "age",
    "mfr",
    "engLife",
    "hero",
    "spec",
    "evidence",
    "blocked",
)


# ---------------------------------------------------------------- one case, as the lists show it
def signals(c: Case) -> list[list[str]]:
    """The demo's sigOf: received, diagnostics, certification and economic path, each done, partial, waiting or blocked."""
    ins = next((x["state"] for x in c.get("evidence") or [] if x["k"] == "insp"), None)
    rec = bool(c.get("recommendation"))
    if rec or (c.get("assessment") != "Pending" and ins == "ready" and c.get("grade")):
        diag = "done"
    else:
        diag = "todo" if c.get("assessment") == "Pending" else "part"
    cert = "done" if rec or (diag == "done" and case_rul(c)) else "todo"
    econ = "done" if rec else "block" if c.get("blocked") else "todo"
    return [
        ["Received", "WMS receipt and RMA", "done"],
        ["Diagnostics", "MRO inspection", diag],
        ["Certification", "QMS certified period", cert],
        ["Economic path", "Circularity", econ],
    ]


def _brief(r: dict | None) -> dict | None:
    return {"id": r["id"], "plan": r["plan"], "net": r["net"]} if r else None


def row(c: Case) -> dict:
    """One case as the queue, the fleet, related assets and compare read it."""
    out = {k: c[k] for k in ROW_KEYS if k in c}
    out["spec"] = ordered_spec(c)
    return out | {
        "recommendation": _brief(c.get("recommendation")),
        "chosen": _brief(c.get("chosen")),
        "model": as_model(c),
        "serial": as_serial(c),
        "stage_key": cc_stage(c),
        "health": health(c)["score"],
        "signals": signals(c),
    }


# ---------------------------------------------------------------- Returned assets
@router.get("/returned")
def returned(p: CurrentPrincipal, session: DbSession, tenant: str = "All"):
    """Returned assets: the queue, the KPI strip, the Expected toggle's count and the account's open notifications."""
    p.require_page("product", "received")
    a = p.account
    return {
        "cases": [row(c) for c in visible_cases(call_ctx(p, session), tenant)],
        "expected_count": len(expected_for(a, p.ctx)),
        "notes": [n for n in notes(session) if n.get("to") == a.id and n.get("status") == "open"],
    }


# ---------------------------------------------------------------- Expected returns (the demo's EXPECTED: di.reads.expected)


@router.get("/expected")
def expected(p: CurrentPrincipal, session: DbSession, tenant: str = "All"):  # noqa: ARG001 - unused dependency left in place (C1 changes no behaviour)
    """Expected returns: the account's (tenant, warehouse, top-bar filter), the toggle's count and the source."""
    p.require_page("product", "expected")
    ok = expected_for(p.account, p.ctx)
    return {
        "rows": [e for e in ok if tenant == "All" or e["owner"] == tenant],
        "count": len(ok),
        "source": SOURCES.get("lease") or {"vendor": "Contract Management", "freshMin": 0},
    }


# ---------------------------------------------------------------- the journey strip
def return_history(c: Case) -> list[dict]:
    """The demo's asReturnHistory: earlier returns of this asset (closed decisions), else derived ones."""
    past = sorted((x for x in all_rows() if x["assetId"] == c["assetId"]), key=lambda x: -ms(x["date"]))
    if past:
        return [
            {
                "cust": x["tenant"],
                "at": iso(x["date"]),
                "dec": PAST_DEC.get(x["route"]) or x["route"],
                "grade": x["grade"],
                "site": x["site"],
                "ref": "Closed decision " + x["id"],
                "der": False,
            }
            for x in past
        ]
    n = 1 + as_hex(c, "rh") % 2
    span = max(1, c["age"]) * 365
    out = []
    for i in range(n):
        at = add_days(c["received"], -js_round(span * (i + 1) / (n + 1.4)))
        h = as_hex(c, f"rh{i}")
        out.append(
            {
                "cust": c["owner"] if i == 0 else TENANTS[h % len(TENANTS)],
                "at": iso(at),
                "dec": ["Refurbished and leased again", f"Reused at Site {1 + h % 8}", "Repaired, back in service"][h % 3],
                "grade": "ABC"[h % 3],
                "site": FACILITIES[h % len(FACILITIES)],
                "ref": f"Lease LS-{4200 + h % 700}",
                "der": True,
            }
        )
    return out


def dp_visible(p: Principal, c: Case | None) -> bool:
    """The demo's dpVisible: the case's journey can be walked by this account (tenant, warehouse, case and asset pages)."""
    a = p.account
    return bool(
        c and can_see_case(a, p.ctx, c) and policy.can_page(a, "product", "case") and policy.can_page(a, "product", "asset")
    )


@router.get("/journey/{case_id}")
def journey(case_id: str, p: CurrentPrincipal, session: DbSession):
    """The journey strip and guide on Returned assets (step 0) and Asset intelligence (step 1)."""
    c = store.get(session, case_id)
    if c is None or not dp_visible(p, c):
        return {"visible": False}
    R = case_rul(c)
    k = len(return_history(c))
    miss = sum(1 for e in c.get("evidence") or [] if e["state"] != "ready")
    if c.get("grade"):
        graded = f"Grade {c['grade']} from " + ("the MRO workshop" if c["cls"] in ("motor", "pump") else "inspection")
    else:
        graded = "Not graded yet"
    cert = f", certified for {R['certMonths']} months ({R['certRef']})" if R else ""
    times = "once" if k == 1 else "twice" if k == 2 else f"{k} times"
    tail = f"; {miss} evidence item{'s' if miss > 1 else ''} not complete yet" if miss else ""
    ctx = call_ctx(p, session)
    return {
        "visible": True,
        "progress": run(c, ctx)["stage"],
        "established": [
            f"{len(visible_cases(ctx))} returned assets in your view. {c['id']} is selected: {as_model(c)}, {c['owner']}, "
            f"{c['location']}.",
            f"{graded}{cert}, received at {c['location']}, returned {times} before{tail}.",
        ],
    }


# ---------------------------------------------------------------- Asset intelligence


def _mon(t: int) -> str:
    d = iso(t)
    return f"{_MON[int(d[5:7]) - 1]} {d[:4]}"


def asset_events(c: Case) -> list[dict]:
    """The demo's asEvents: manufactured, commissioned, deployed, service, returned, assessment and decision."""
    rec = ms(c["received"])
    mfg = add_days(rec, -js_round(c["age"] * 365))
    com = add_days(mfg, 45 + as_hex(c, "cm") % 76)
    dep = add_days(com, 20 + as_hex(c, "dp") % 40)
    svc_end = add_days(rec, -20 - as_hex(c, "se") % 40)
    n = max(1, js_round(c["age"] * 1.4) + as_hex(c, "wo") % 3)
    ins = None if c.get("assessment") == "Pending" else add_days(rec, 1 + as_hex(c, "ins") % 3)
    st = c["stage"]
    dec_done = st in ("executing", "approved")
    ready = c.get("assessment") == "Ready"
    r = c.get("recommendation")
    lease = f" under lease {as_lease(c)}" if (c.get("demand") or {}).get("lease") else ""
    return [
        {
            "k": "mfg",
            "t": "Manufactured",
            "d": fmt_dy(mfg),
            "src": "PLM · ERP",
            "s": "done",
            "note": f"Built to Rev {'ABCDE'[as_hex(c, 'rv') % 5]} by {c['mfr']}",
        },
        {
            "k": "com",
            "t": "Commissioned",
            "d": fmt_dy(com),
            "src": "EAM",
            "s": "done",
            "note": "Asset registered in the maintenance system",
        },
        {
            "k": "dep",
            "t": "Deployed",
            "d": fmt_dy(dep),
            "src": "ERP · contract",
            "s": "done",
            "note": f"In service for {c['owner']}{lease}",
        },
        {
            "k": "svc",
            "t": "Service",
            "d": f"{n} work order{'s' if n > 1 else ''}",
            "sub": f"{_mon(add_days(dep, 60))} – {_mon(svc_end)}",
            "src": "EAM · FSM",
            "s": "done",
            "note": f"{n} maintenance events recorded",
        },
        {"k": "ret", "t": "Returned", "d": fmt_dy(rec), "src": "WMS", "s": "done", "note": f"Received at {c['location']}"},
        {
            "k": "ass",
            "t": "Condition assessment",
            "d": fmt_dy(ins) if ins else "Pending",
            "src": "Inspection",
            "s": "done" if ins and ready else "warn" if ins else "pending",
            "note": (f"Inspection complete, grade {c.get('grade') or '—'}" if ready else "Evidence still incomplete")
            if ins
            else "No inspection recorded yet",
        },
        {
            "k": "dec",
            "t": "Treatment decision",
            "d": "Handed off"
            if dec_done
            else "Awaiting approval"
            if st == "awaiting_approval"
            else "Re-evaluate"
            if st == "reeval"
            else "Pending",
            "src": "Circularity",
            "s": "done" if dec_done else "warn" if st in ("awaiting_approval", "reeval") else "pending",
            "note": f"Recommended: {r['plan']}" if r else "No route recommended yet",
        },
    ]


def related(c: Case, my: list[Case]) -> list[Case]:
    """The demo's assetRelated: three of the same class, same customer first, then same location, then by id."""
    pool = [x for x in my if x["id"] != c["id"] and x["cls"] == c["cls"]]
    return sorted(pool, key=lambda x: (x["owner"] != c["owner"], -1 if x["location"] == c["location"] else 1, x["id"]))[:3]


def value_state(c: Case) -> str:
    """The demo's asValState."""
    r = c.get("chosen") or c.get("recommendation")
    if not r:
        return "pending"
    if c.get("outcome"):
        return "actual"
    return "committed" if c.get("approval") and c.get("exec") and c["stage"] != "reeval" else "predicted"


def baseline(c: Case) -> float | None:
    """The demo's asBaseline: the best of selling, recycling or exiting."""
    b = [r["net"] for r in c.get("routes") or [] if r["id"] in ("resale", "exit", "material")]
    return max(b) if b else None


def asset_econ(c: Case) -> dict:
    """The facade's assetEcon (the demo's asEcon): recovery, cost, net, service history, resale demand and price."""
    r, K, q = c.get("recommendation"), CLASSES[c["cls"]], c["qty"]
    pos = js_sum(t["amt"] for t in r["terms"] if t["amt"] > 0) if r else js_round(CC_EST[c["cls"]] * q)
    neg = js_sum(t["amt"] for t in r["terms"] if t["amt"] < 0) if r else 0
    net = r["net"] if r else js_round(pos * 0.8)
    rg = js_round((r["p90"] - r["p10"]) / 2 / max(1, abs(net)) * 100) if r else None
    age = max(1, c["age"])
    mt = js_round(K["pnew"] * q * 0.018 * age * (0.8 + (as_hex(c, "mt") % 50) / 100))
    pr = js_round(mt * (0.4 + (as_hex(c, "pr") % 40) / 100))
    sv = js_round((mt + pr) * (0.9 + (as_hex(c, "sv") % 30) / 100))
    avg = js_round(sv / age)
    rs = [
        x
        for x in all_rows()
        if x["cls"] == c["cls"] and x["route"] == "resale" and x["status"] == "reconciled" and x["actual"] > 0
    ]
    by = [0] * 12
    for x in rs:
        by[x["mi"]] += 1

    def unit(a: list[dict]) -> float:
        return median([x["actual"] / x["q"] for x in a])

    last3 = [x for x in rs if x["mi"] >= 9]
    prev3 = [x for x in rs if 6 <= x["mi"] < 9]
    trend = (unit(last3) / unit(prev3) - 1) * 100 if prev3 and last3 else 0
    price = js_round(unit(rs) * q) if rs else 0
    bars = by[6:]
    dem = (bars[3] + bars[4] + bars[5]) / max(1, bars[0] + bars[1] + bars[2])
    demand = ["Strong", "ok"] if dem >= 1.1 else ["Steady", "warn"] if dem >= 0.9 else ["Softening", "bad"]
    return {
        "pos": pos,
        "neg": neg,
        "net": net,
        "rg": rg,
        "age": age,
        "mt": mt,
        "pr": pr,
        "sv": sv,
        "avg": avg,
        "bars": bars,
        "mx": max(1, *bars),
        "months": MONTHS[6:],
        "demand": demand,
        "trend": trend,
        "price": price,
    }


def asset_eligibility(c: Case) -> list[list[str]]:
    """The facade's assetEligibility (the demo's asElig): ownership, contract, warranty, safety and environment."""
    d, spec = c.get("demand") or {}, c.get("spec") or {}
    yr = int(iso(c["received"])[:4]) - max(0, js_round(c["age"])) + min(6, js_round(CLASSES[c["cls"]]["tau"] / 2))
    warr = yr >= int(iso(AS_OF)[:4])
    sil = "SIL" in (spec.get("Safety rating") or "")
    lith = c["cls"] in ("drill", "batch", "it")
    erase = c["cls"] == "it" and spec.get("Data erasure") == "Pending"
    return [
        ["Ownership", c["owner"], "Eligible for all treatments", "ok"],
        [
            "Contract terms",
            f"Lease {as_lease(c)} ended, no restriction on reuse" if d.get("lease") else "No contract restriction on file",
            "Verified" if d.get("lease") else "Not on file",
            "ok" if d.get("lease") else "line",
        ],
        ["Warranty", f"Active until {yr}" if warr else f"Expired ({yr})", "Active" if warr else "—", "ok" if warr else "line"],
        [
            "Safety and regulatory",
            f"Safety-rated unit ({spec['Safety rating']})" if sil else "No open safety alerts",
            "Review" if sil else "Compliant",
            "warn" if sil else "ok",
        ],
        [
            "Environmental",
            "Data erasure certificate pending"
            if erase
            else "Lithium battery handling required"
            if lith
            else "No special handling",
            "Follow guidelines" if erase or lith else "Compliant",
            "warn" if erase or lith else "ok",
        ],
    ]


def closed_last_year(c: Case) -> int:
    """Closed decisions of this product for this customer in the last 12 months (the demo's skuStrip)."""
    m, cut = as_model(c), add_days(AS_OF, -365)
    return sum(
        1 for r in all_rows() if re.sub(r"s$", "", str(r["equip"])) == m and r["tenant"] == c["owner"] and ms(r["date"]) >= cut
    )


def _count(items: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k in items:
        out[k] = out.get(k, 0) + 1
    return out


def default_asset(p: Principal, session: Session) -> str:
    """The demo's rbLastAsset without a remembered asset: the first of the account's cases (RT-1048 when none)."""
    my = visible_cases(call_ctx(p, session))
    return my[0]["id"] if my else "RT-1048"


@router.get("/asset")
def asset_default(p: CurrentPrincipal, session: DbSession):
    """Asset intelligence for the default asset (the frontend passes the remembered one to /asset/{id})."""
    return asset(default_asset(p, session), p, session)


@router.get("/asset/{case_id}")
def asset(case_id: str, p: CurrentPrincipal, session: DbSession):
    """Asset intelligence for one case."""
    c = load_case(p, session, case_id, "product", "asset")
    h = health(c)
    r = c.get("chosen") or c.get("recommendation")
    rec = c.get("recommendation")
    my = visible_cases(call_ctx(p, session))
    m = as_model(c)
    return {
        "case": case_record(c, session),
        "title": as_title(c),
        "serial": as_serial(c),
        "rev": "Rev " + "ABCDE"[as_hex(c, "rv") % 5],
        "receipt": f"GR-{100000 + as_hex(c, 'gr') % 900000}",
        "rma": as_rma(c),
        "sc": as_sc(c),
        "lease_ref": as_lease(c),
        "model": m,
        "health": h,
        "facts": asset_facts(c),
        "events": asset_events(c),
        "return_history": return_history(c),
        "parts": parts_availability(c, h),
        "part_prices": part_prices(c, h),
        "catalogue": catalogue(c),
        "prep_cost": prep_cost(c),
        "prep_parts": ex_prep_parts(c, r) if r else None,
        "learn_version": learn_ver(c, "prep-cost-time"),
        "rul": case_rul(c),
        "demand": case_demand(c),
        "diag": case_diag(c, h),
        "recert": recert(c, r),
        "confidence": ti_conf(c, r) if r else None,
        "value_order": value_order(c),
        "value_state": value_state(c),
        "baseline": baseline(c),
        "econ": asset_econ(c),
        "eligibility": asset_eligibility(c),
        "lease_trail": with_times(af_lease(c)),
        "provenance": [prov_for(c, e) for e in c["evidence"]],
        "snapshot_time": snap_time(c),
        "closed_last_year": closed_last_year(c),
        "term_methods": [ex_trace(c, rec, t)["method"] for t in rec["terms"]] if rec else [],
        # from the account's cases
        "fleet": [row(x) for x in my if x["cls"] == c["cls"]],
        "related": [x["id"] for x in related(c, my)],
        "units": [
            x["id"] for x in sorted((x for x in my if as_model(x) == m and x["owner"] == c["owner"]), key=lambda x: x["id"])
        ],
        "models": _count([as_model(x) for x in my]),
        "customers": _count([x["owner"] for x in my if as_model(x) == m]),
        "journey": dp_visible(p, c),
    }


# ---------------------------------------------------------------- pools
@router.get("/pools")
def pools(p: CurrentPrincipal, session: DbSession):
    """The pool optimiser: the two pools in the account's tenants, solved. Hidden while pools are off (the demo's
    FEAT.pools), as canPage('product', 'pools') hides it."""
    p.require_page("product", "pools")
    out = {}
    for cid in ("RT-1048", "RT-1052"):
        c = store.get(session, cid)
        if c and policy.tenant_ok(p.account, c["owner"], p.ctx):
            out[cid] = pool_of(session, cid)
    return {"pools": out}
