"""Case reads (B11): cases.list, case.get, case.evidence, case.routes, case.trace, demand.find, asset.compare.

Ports of the demo's read actions (index.html, `defAction('cases.list', ...)` and the ones after it). The pipeline has
already checked the permission, the tenant boundary and the warehouse lock for the case-scoped ones.
"""

import re
from typing import Any

from di.actions.pipeline import CallContext
from di.actions.registry import ActionError, implement
from di.cases import store
from di.engine.jsmath import js_round, js_sum
from di.engine.routes import GATES
from di.engine.scenario import KIND_MULT
from di.reads.common import (
    SOURCES,
    Case,
    af_days,
    as_model,
    base_rows,
    case_demand,
    case_events,
    case_row,
    case_rul,
    esc,
    fmt_n,
    hash_id,
    iso,
    money,
    ms,
    next_step,
    priority,
    rec,
    run,
    stage_label,
)
from di.reads.context import visible_cases
from di.reads.provenance import fetch_time, pmap


def _case(ctx: CallContext, case_id: str) -> Case:
    c = store.get(ctx.session, case_id)
    if c is None:
        raise ActionError("not_found", f"No case {case_id}.")
    return c


# ---------------------------------------------------------------- cases.list
def _cases_in(i: dict, ctx: CallContext) -> list[Case]:
    """The demo's afCasesIn: the visible cases that match every filter given."""
    q = (i.get("q") or "").lower()
    product = (i.get("product") or "").lower()

    def keep(c: Case) -> bool:
        ev = c.get("evidence") or []
        not_ready = any(e["state"] != "ready" for e in ev)
        r = c.get("recommendation")
        return (
            (not i.get("location") or c["location"] == i["location"])
            and (not i.get("owner") or c["owner"] == i["owner"])
            and (not i.get("stage") or c["stage"] == i["stage"] or stage_label(c) == i["stage"])
            and (not i.get("cls") or c["cls"] == i["cls"])
            and (not product or product in as_model(c).lower() or product in c["product"].lower())
            and (i.get("missing") is None or (bool(c.get("blocked")) or not_ready) == i["missing"])
            and (not i.get("evidence") or any(e["k"] == i["evidence"] and e["state"] != "ready" for e in ev))
            and (not i.get("assessment") or c.get("assessment") == i["assessment"])
            and (not i.get("received_within_days") or af_days(c["received"]) <= i["received_within_days"])
            and (not i.get("route") or bool(r and r["id"] == i["route"]))
            and (i.get("submitted") is None or bool(c.get("submitted")) == i["submitted"])
            and (not q or q in f"{c['id']} {c['assetId']} {as_model(c)} {c['owner']} {c['location']}".lower())
        )

    return [c for c in visible_cases(ctx) if keep(c)]


@implement("cases.list")
def cases_list(i: dict[str, Any], ctx: CallContext):
    cases = _cases_in(i, ctx)
    sort = i.get("sort")
    if sort == "priority":
        scored = sorted(((c, priority(c)) for c in cases), key=lambda x: -x[1]["score"])
        rows = [case_row(c) | {"priority": p["score"], "why": p["why"]} for c, p in scored]
    else:
        if sort == "value":
            cases = sorted(cases, key=lambda c: -((c.get("recommendation") or {}).get("net") or 0))
        elif sort == "received":
            cases = sorted(cases, key=lambda c: ms(c["received"]))
        rows = [case_row(c) for c in cases]
    filters = [{"k": k, "v": v} for k, v in i.items() if v is not None and v != "" and k not in ("sort", "limit")]
    limit = int(i.get("limit") or 25)
    return {
        "rows": rows[:limit],
        "total": len(cases),
        "filters": filters,
        "value_total": js_sum(c["recommendation"]["net"] if c.get("recommendation") else 0 for c in cases),
    }


# ---------------------------------------------------------------- case.get
@implement("case.get")
def case_get(i: dict[str, Any], ctx: CallContext):
    c = _case(ctx, i["case_id"])
    rul = case_rul(c)
    out = None
    if c.get("outcome"):
        o, r = c["outcome"], c.get("chosen") or c["recommendation"]
        out = {
            "pred": r["net"],
            "act": o["net"],
            "variance": o["net"] - r["net"],
            "order": o.get("order") or None,
            "plan": r["plan"],
            "lines": [
                {"label": ln["label"], "pred": ln.get("pred"), "act": ln.get("act"), "model": ln.get("model") or None}
                for ln in o.get("lines") or []
            ],
        }
    return case_row(c) | {
        "age_years": c["age"],
        "mfr": c["mfr"],
        "life": c["engLife"],
        "cert_months": rul["certMonths"] if rul else None,
        "est_life": f"{rul['estLow']}–{rul['estHigh']} months" if rul else None,
        "timing": c.get("timing") or None,
        "outcome": out,
        "facts": list(c.get("facts") or []),
        "snapshot": c["snapshot"]["id"] if c.get("snapshot") else None,
        "priority": priority(c),
    }


# ---------------------------------------------------------------- case.evidence
def provenance(c: Case, e: dict) -> dict:
    """The demo's provFor (the shared PMAP, di.reads.provenance), the fields the reads use: the source system's name,
    the record and when it was fetched (motors and pumps trace their inspection and photos to the repair system)."""
    m = pmap(c, e["k"])
    if not m or e["state"] == "missing":
        src = SOURCES.get(m["s"]) if m else None
        return {"sourceName": src["name"] if src else e.get("source"), "record": None, "fetchedAt": None}
    h = int(hash_id(c["id"] + e["k"] + "r"), 16)
    record = None if e["state"] in ("partial", "conflict") else f"{m['pre']}-{20000 + h % 80000}"
    return {"sourceName": SOURCES[m["s"]]["name"], "record": record, "fetchedAt": fetch_time(c, e)}


@implement("case.evidence")
def case_evidence(i: dict[str, Any], ctx: CallContext):
    c = _case(ctx, i["case_id"])
    items = []
    for e in c.get("evidence") or []:
        p = provenance(c, e)
        item = {
            "k": e["k"],
            "label": e["label"],
            "state": e["state"],
            "source": e.get("source"),
            "system": p["sourceName"],
            "record": p["record"] or None,
            "fetched": iso(p["fetchedAt"]) if p["fetchedAt"] else None,
            "note": e.get("note") or "",
            "badge": "Retrieved",
        }
        if "fresh" in e:  # absent in the demo means undefined, which JSON leaves out
            item["fresh"] = e["fresh"]
        items.append(item)
    return {"case_id": c["id"], "items": items}


# ---------------------------------------------------------------- case.routes
TB_RULES = {
    "risk": "Risk / confidence",
    "demand": "Demand certainty",
    "cycle": "Cycle time",
    "rul": "Remaining useful life",
    "co2": "Carbon",
}


def tie_break(c: Case, rows: list[dict]) -> dict | None:
    """The demo's tieBreak: when the top two routes are within 5% or $250, the first secondary factor with a
    meaningful gap decides (risk, demand certainty, cycle time, remaining life, carbon)."""
    if not rows or len(rows) < 2:
        return None
    a, b = rows[0], rows[1]
    gap = a["net"] - b["net"]
    if gap > max(250, abs(a["net"]) * 0.05):
        return {"near": False, "gap": gap, "a": a, "b": b}
    rul = case_rul(c)

    def life(z):
        return rul["estMonths"] if rul and z["r"]["id"] in ("redeploy", "resale", "relase") else 0

    def dem(z):
        return 1 if z["r"].get("demandStatus") == "confirmed" else 0

    def higher(gap_ok):
        return lambda x, y: ("a" if x > y else "b") if gap_ok(x, y) else None

    factors = [
        ("risk", a["prob"], b["prob"], higher(lambda x, y: abs(x - y) >= 5), lambda v: f"{v}%"),
        ("demand", dem(a), dem(b), higher(lambda x, y: x != y), lambda v: "confirmed" if v else "forecast"),
        ("cycle", a["days"], b["days"], lambda x, y: ("a" if x < y else "b") if abs(x - y) >= 3 else None, lambda v: f"{v} days"),
        ("rul", life(a), life(b), higher(lambda x, y: abs(x - y) >= 6), lambda v: f"{v} months" if v else "none"),
        ("co2", a["co2"], b["co2"], higher(lambda x, y: abs(x - y) >= 0.1 * max(x, y, 1)), lambda v: fmt_n(v) + " kg"),
    ]
    values = [{"k": k, "label": TB_RULES[k], "a": fmt(x), "b": fmt(y), "w": win(x, y)} for k, x, y, win, fmt in factors]
    d = next((v for v in values if v["w"]), None)
    return {
        "near": True,
        "gap": gap,
        "pct": js_round(gap / max(1, abs(a["net"])) * 100),
        "a": a,
        "b": b,
        "decidedBy": d["k"] if d else None,
        "preferred": b if d and d["w"] == "b" else a,
        "values": values,
    }


def tie_text(t: dict | None) -> str:
    """The demo's tieText."""
    if not t or not t["near"]:
        return ""
    p = t["preferred"]
    v = next((x for x in t["values"] if x["k"] == t["decidedBy"]), None)
    me = "a" if p is t["a"] else "b"
    ot = "b" if me == "a" else "a"
    head = f"{t['a']['r']['plan']} and {t['b']['r']['plan']} are within {money(t['gap'])} ({t['pct']}%). "
    if v:
        return head + f"{p['r']['plan']} is preferred because {v['label'].lower()} decides: {v[me]} against {v[ot]}."
    return head + "No secondary factor separates them, so net value decides."


def flips(c: Case) -> list[dict]:
    """The demo's flips: what would have to change for the runner-up to win, smallest change first."""
    el = sorted((r for r in c["routes"] if not r["excluded"]), key=lambda r: -r["net"])
    if len(el) < 2 or not c.get("recommendation"):
        return []
    a, b = el[0], el[1]
    d = a["net"] - b["net"]
    out = []
    for t in a["terms"]:
        if not KIND_MULT.get(t["kind"]) or not t["amt"]:
            continue
        if t["amt"] > 0:
            out.append({"txt": f"{t['label']} falls below {money(t['amt'] - d)}", "pct": -d / t["amt"], "to": b["plan"]})
        else:
            out.append({"txt": f"{t['label']} rises above {money(-t['amt'] + d)}", "pct": d / -t["amt"], "to": b["plan"]})
    for t in b["terms"]:
        if t["amt"] > 0 and KIND_MULT.get(t["kind"]):
            txt = f"{esc(b['plan'])}: {t['label'].lower()} rises above {money(t['amt'] + d)}"
            out.append({"txt": txt, "pct": d / t["amt"], "to": b["plan"]})
    if a.get("demandStatus") == "confirmed" and a["id"] != "exit":
        out.append({"txt": f"Confirmed demand ({a['demandLabel'].split(' · ')[0]}) is cancelled", "pct": None, "to": b["plan"]})
    return sorted(out, key=lambda x: -1 if x["pct"] is None else abs(x["pct"]))[:4]


@implement("case.routes")
def case_routes(i: dict[str, Any], ctx: CallContext):
    c = _case(ctx, i["case_id"])
    el = sorted((r for r in c["routes"] if not r["excluded"]), key=lambda r: -r["net"])
    tb = tie_break(c, base_rows(c))
    b = c.get("blocked")

    def eligible(k: int, r: dict) -> dict:
        row = {
            "rank": k + 1,
            "plan": r["plan"],
            "route": r["id"],
            "net": r["net"],
            "behind": el[0]["net"] - r["net"],
            "p10": r["p10"],
            "p90": r["p90"],
            "demand_status": r.get("demandStatus"),
            "gates_passed": sum(1 for g in r["gates"] if g == "pass"),
            "terms": [{"label": t["label"], "amt": t["amt"], "kind": t["kind"]} for t in r["terms"]],
            "why": r.get("why") or "",
        }
        if "demandLabel" in r:  # absent in the demo means undefined, which JSON leaves out
            row["demand"] = r["demandLabel"]
        return row

    return {
        "case_id": c["id"],
        "recommended": rec(c),
        "blocked": {"gate": b["gateName"], "reason": b["reason"]} if b else None,
        "eligible": [eligible(k, r) for k, r in enumerate(el)],
        "excluded": [
            {
                "plan": r["plan"],
                "route": r["id"],
                "gate": GATES[r["failGate"]] if 0 <= r["failGate"] < len(GATES) else "Demand fit",
                "reason": r["failReason"],
            }
            for r in c["routes"]
            if r["excluded"]
        ],
        "tie": (
            {"gap": tb["gap"], "text": tie_text(tb), "preferred": tb["preferred"]["r"]["plan"], "decided_by": tb["decidedBy"]}
            if tb and tb["near"]
            else None
        ),
        "flips": [{"txt": f["txt"], "to": f["to"]} for f in flips(c)[:3]],
    }


# ---------------------------------------------------------------- case.trace
@implement("case.trace")
def case_trace(i: dict[str, Any], ctx: CallContext):
    c = _case(ctx, i["case_id"])
    events = [
        {"ts": iso(e["ts"]), "type": e["type"], "note": e.get("note") or "", "by": e.get("by") or "", "sim": bool(e.get("sim"))}
        for e in case_events(ctx.session, c["id"])[:12]
    ]
    return run(c, ctx) | {"next": next_step(c, ctx), "events": events}


# ---------------------------------------------------------------- demand.find
@implement("demand.find")
def demand_find(i: dict[str, Any], ctx: CallContext):
    c = _case(ctx, i["case_id"])
    m = case_demand(c)
    matched = (
        {"order": m["order"] or None, "site": m["site"] or None, "confirmed": m["confirmed"], "lease": m["lease"] or None}
        if m
        else None
    )
    demand = [
        {
            "route": r["id"],
            "plan": r["plan"],
            "demand": r["demandLabel"],
            "status": r.get("demandStatus"),
            "eligible": not r["excluded"],
        }
        for r in c["routes"]
        if r.get("demandLabel") and not re.search(r"^—|No ", r["demandLabel"])
    ]
    return {"case_id": c["id"], "matched": matched, "demand": demand}


# ---------------------------------------------------------------- asset.compare
@implement("asset.compare")
def asset_compare(i: dict[str, Any], ctx: CallContext):
    c = _case(ctx, i["case_id"])
    m = as_model(c)
    same = [x for x in visible_cases(ctx) if x["id"] != c["id"] and x["cls"] == c["cls"] and as_model(x) == m]
    rows = []
    for x in same[:10]:
        r = x.get("recommendation")
        rows.append({
            "id": x["id"],
            "owner": x["owner"],
            "location": x["location"],
            "grade": x.get("grade") or "—",
            "life": x["engLife"],
            "route": r["plan"] if r else "—",
            "net": r["net"] if r else None,
            "stage": stage_label(x),
        })  # fmt: skip
    return {"case_id": c["id"], "model": m, "total": len(same), "rows": rows}
