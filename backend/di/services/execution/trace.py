"""Where each number comes from (the demo's exTrace, N7/N8): every term of a route as cost lines, each with a method
(Retrieved, Contracted, Modelled), a source (system, record) and a why; and the actuals Finance confirms against them
(lineActuals, exActual).
"""

import re
from typing import Any

from di.repositories.common import AS_OF, CLASSES, WORLD, Case, as_model, case_demand, fmt_d, hash_id, inr, jg_lc
from di.services.engine.jsmath import js_round, js_sum
from di.services.engine.predictor import engine_class
from di.services.execution.lanes import RATE_CARD, ex_kg, ex_move_raw
from di.services.execution.prep import EX_BOM, EX_FX_AT, EX_SCOPE, as_sc, asset_health, ex_inr, ex_prep_parts, ex_svc
from di.services.execution.steps import ex_doc_num, ex_doc_ref
from di.services.execution.util import js_str

TMS = "Oracle Transportation Management"  # the demo's fictional "ShipLane TMS", replaced in B5b and in the demo (B17)
RATE = f"{RATE_CARD['id']} · {RATE_CARD['carrier']}"


def ex_trace(c: Case, r: dict, t: dict) -> dict:
    """The demo's exTrace: one term as cost lines that add up exactly to it (in rupees)."""
    B = ex_inr(t["amt"])
    M = case_demand(c)
    g = c.get("grade") or "C"
    m = re.search(r"(\d+) months", t["label"]) or re.search(r"(\d+)-month", c.get("horizon") or "")
    months = int(m[1]) if m else 30
    mod = as_model(c)
    o = {
        "label": t["label"], "kind": t["kind"], "usd": t["amt"], "inr": B, "lines": [], "why": "", "method": "Modelled",
        "sys": "", "rec": "", "asOf": EX_FX_AT,
    }  # fmt: skip

    def L(item, calc, v, method, sys, rec, why=""):
        o["lines"].append({"item": item, "calc": calc, "inr": v, "method": method, "sys": sys, "rec": rec, "why": why or ""})

    pos = next(iter(sorted((x for x in r["terms"] if x["amt"] > 0), key=lambda x: -x["amt"])), None)
    k = t["kind"]
    cls = CLASSES[engine_class(c)]
    P = ex_prep_parts(c, r) if k == "prep" else None
    if k == "purchase":
        po = M.get("avoidedPo") if M else None
        o.update(method="Contracted", sys="SAP Ariba", rec=po or f"Catalogue {ex_doc_num(c, 'order')}")
        L(
            "New " + mod + (f" × {js_str(c['qty'])}" if c["qty"] > 1 else ""),
            f"{js_str(c['qty'])} × {inr(B / c['qty'])} contract price",
            B, "Contracted", "SAP Ariba", f"Planned {po}" if po else "Contract catalogue",
        )  # fmt: skip
        o["why"] = (
            f"The purchase this redeployment avoids: planned {M['avoidedPo']} raised for {M['order']} line {M['line']}. "
            "Contract price, not list price."
            if M and M.get("order")
            else "Contract price of an equivalent new unit."
        )
    elif k == "prep" and P:
        sc = as_sc(c)
        wo = ex_doc_ref(c, {"k": "repair" if P["mode"] == "refurb" else "teardown"})
        o.update(method="Modelled", sys=f"Oracle Depot Repair · {TMS} · SAP Ariba", rec="Work order " + wo)
        comps = {x["n"]: x for x in asset_health(c)["comps"]} if c.get("grade") else {}
        for p in P["parts"]:
            rated = (comps.get(p["comp"]) or {"st": "replace on condition"})["st"].lower()
            why = (
                "In the repair scope: "
                + p["comp"].lower()
                + (" (workshop diagnosis)" if c["id"] in EX_SCOPE else f" rated {rated}")
            )
            L(
                f"{p['name']} · {p['pn']}",
                f"{js_str(p['qty'])} × {inr(p['unit'])}",
                p["qty"] * p["unit"],
                "Contracted",
                "SAP Ariba",
                sc,
                why,
            )
        L(
            "Labour · " + P["role"], f"{js_str(P['labH'])} h × {inr(P['rate'])}", P["lab"], "Modelled", "Oracle Depot Repair",
            "Operations on " + wo,
            f"Standard {js_str(P['std'])} h for the operations; hours solved last so the lines add up to the predicted {inr(B)}",
        )  # fmt: skip
        for x in P["ops"]:
            L(
                "Machine · " + x["name"], f"{js_str(x['h'])} h × {inr(x['rate'])}", x["inr"], "Contracted", "Oracle Depot Repair",
                "RC-HSR-01 machine rate", f"Required test or process for {cls['label'].lower()}s",
            )  # fmt: skip
        for x in P["legs"]:
            share = f" · shared load {js_round(x['share'] * 100)}%" if x["share"] < 1 else ""
            L(
                f"Transport leg {x['n']} · {x['from']} → {x['to']}",
                x["calc"] + share,
                x["inr"],
                "Contracted",
                TMS,
                RATE,
                "Contracted lane rate",
            )
        if P["pack"]:
            L(
                "Packing and handling", f"{cls['label']} crate, lashing and handling", P["pack"], "Contracted",
                "Manhattan Active WM", "Packing rate card", "Standard pack for the class",
            )  # fmt: skip
        if P["mode"] == "refurb":
            n = len(P["legs"])
            legs = f", {n} transport leg{'s' if n > 1 else ''} on {RATE_CARD['id']}" if n else ""
            o["why"] = (
                f"Refurbishment at RC-HSR-01 Hosur: {len(P['parts'])} parts at contract prices, {js_str(P['labH'])} labour "
                f"hours, {len(P['ops'])} machine operations{legs} and packing."
            )
        else:
            o["why"] = f"Teardown and part testing at RC-HSR-01: {js_str(P['labH'])} labour hours and the final test."
    elif k == "service":
        S = ex_svc(c, B, months)
        o.update(method="Modelled", sys="IBM Maximo · ServiceNow FSM", rec="service-exposure v1.2")
        for name, calc, v in S["lines"]:
            fl = name == "Field labour"
            L(
                name, calc, v, "Contracted" if fl else "Modelled", "ServiceNow Field Service Management" if fl else "IBM Maximo",
                "Field labour rate ₹1,100/h" if fl else "Failure history", "",
            )  # fmt: skip
        duty = "24/7" if c["id"] == "RT-1048" else "two-shift"
        o["why"] = (
            f"{js_str(S['n'])} expected interventions over {months} months at {inr(S['per'])} each. Failure rate from Maximo "
            f"history for {cls['plural'].lower()} at {duty} duty; field labour rate from ServiceNow FSM."
        )
    elif k == "residual":
        o.update(method="Modelled", sys="Circularity ML", rec="resale-price v1.3")
        L(
            f"End-of-horizon value at month {months}", f"grade {g} after {months} months of service", B, "Modelled",
            "Circularity ML", "resale-price v1.3",
        )  # fmt: skip
        o["why"] = "What the unit is still worth when the horizon ends, from the resale-price model."
    elif k == "risk":
        base = ex_inr(pos["amt"]) if pos else B
        p = js_round(B / max(1, base) * 1000) / 10
        o.update(method="Modelled", sys="Circularity ML", rec="repair-success v1.1")
        of = f" ({jg_lc(pos['label'])})" if pos else ""
        L(t["label"], f"{js_str(p)}% of {inr(base)}{of}", B, "Modelled", "Circularity ML", "Calibrated on past outcomes")
        o["why"] = "An allowance for the chance the demand, sale or repair does not land, calibrated on past outcomes."
    elif k == "sale":
        n = 14 + int(hash_id(c["id"] + "m"), 16) % 40
        o.update(method="Modelled", sys="Ritchie Bros. Market Data · Machinio", rec="resale-price v1.3")
        L(
            t["label"], f"median of {n} comparable sales · grade {g} · {js_str(c['age'])} years", B, "Modelled",
            "Ritchie Bros. Market Data", "Comparables " + fmt_d(AS_OF),
        )  # fmt: skip
        o["why"] = (
            "Comparable realised prices adjusted for grade and age; the market feed may be stale, and the prediction says so."
        )
    elif k == "fees" and t["label"] not in ("Collection", "Processing"):
        _fees(c, r, o, L, B, pos)
    elif k == "lease":
        ls = M.get("lease") if M else None
        o.update(method="Contracted", sys="Oracle Lease and Finance Management", rec=ls or "Lease quote")
        L(
            "Lease income", f"{months} months × {inr(B / months)} a month", B, "Contracted",
            "Oracle Lease and Finance Management", ls or "Quote",
        )  # fmt: skip
        o["why"] = "Quoted monthly rate from the lease opportunity, over the same horizon as every other route."
    elif k == "parts":
        h = asset_health(c) if c.get("grade") else None
        ok = [x["n"] for x in h["comps"] if x["cls"] == "ok"] if h else []
        bom = [p for p in EX_BOM[engine_class(c)] if not ok or p[2] in ok][:4]
        tw = js_sum(p[3] for p in bom) or 1
        left = B
        o.update(method="Modelled", sys="Aras Innovator BOM · Circularity ML", rec="resale-price v1.3")
        for i, p in enumerate(bom):
            v = left if i == len(bom) - 1 else js_round(B * p[3] / tw / 10) * 10
            left -= v
            L(
                f"{p[0]} · {p[1]}", f"recovered and tested · {js_round(p[3] / tw * 100)}% of the value", v, "Modelled",
                "Aras Innovator", "BOM revision C",
            )  # fmt: skip
        o["why"] = "Recovered components that pass test, valued at what they replace in service stock or fetch from buyers."
    elif k == "material":
        kg = ex_kg(c)
        cu = js_round(kg * (0.12 if c["cls"] == "motor" else 0.05))
        cu_v = min(B, cu * 650)
        o.update(method="Contracted", sys="Sims Lifecycle Services", rec="Partner rate sheet")
        if cu_v:
            L("Copper", f"{cu} kg × ₹650", cu_v, "Contracted", "Sims Lifecycle Services", "Partner rate sheet")
        L(
            "Steel and other metals",
            f"{kg - cu} kg at the partner rate",
            B - cu_v,
            "Contracted",
            "Sims Lifecycle Services",
            "Partner rate sheet",
        )
        o["why"] = "Weight by material at the recycler's contracted rates."
    else:
        na = k == "na"
        sys = "Approved vendor rate card" if k in ("credit", "fees") else "Disposal cost table" if k == "avoid" else "Circularity"
        o.update(method="Modelled" if na else "Contracted", sys=sys, rec="—" if na else "Rate card")
        L(t["label"], "route not viable" if na else "contracted rate", B, o["method"], o["sys"], o["rec"])
        o["why"] = "The route is not viable, so it carries no value." if na else "Contracted rate from the approved vendor."
    # whole rupees; any rounding left over goes to the last line, so the lines add up exactly to the term
    for x in o["lines"]:
        x["inr"] = js_round(x["inr"])
    d = B - js_sum(x["inr"] for x in o["lines"])
    if d and o["lines"]:
        o["lines"][-1]["inr"] += d
    o["sign"] = -1 if t["amt"] < 0 else 1
    return o


def _fees(c: Case, r: dict, o: dict, L, B: int, pos: dict | None) -> None:
    """Fees and freight: freight legs on the rate card (capped at 70% of the term), the rest the channel's fee."""
    rid: Any = r.get("id")
    mv = ex_move_raw(c, r)
    if not mv:
        legs = []
    elif rid == "resale":
        legs = [x for x in mv["legs"] if x["from"] == "RC-HSR-01" or "RC-HSR-01" not in mv["stops"]]
    else:
        legs = mv["legs"]
    fr = js_sum(x["inr"] for x in legs)
    cap = js_round(B * 0.7)
    s = cap / fr if fr > cap and fr else 1
    partner = "Sims Lifecycle Services" if rid == "material" else "SAP S/4HANA"
    o.update(method="Contracted", sys=f"{TMS} · {partner}", rec=RATE_CARD["id"])
    for x in legs:
        share = f" · shared load {js_round(s * 100)}%" if s < 1 else ""
        rec = f"{RATE_CARD['id']} · " + ("partner collection" if x["to"] == "PTN-MAA" else RATE_CARD["carrier"])
        L(
            f"Freight · {x['from']} → {x['to']}", x["calc"] + share, js_round(x["inr"] * s / 10) * 10, "Contracted", TMS, rec,
            "Same lane rate card as the inbound return",
        )  # fmt: skip
    rest = B - js_sum(x["inr"] for x in o["lines"])
    label = {
        "resale": "Channel fees (commission and listing)",
        "material": "Partner processing fee",
        "intparts": "Handling and internal transfer",
    }.get(rid, "Selling fees")
    if rest >= 0:
        pct = js_round(rest / max(1, ex_inr(pos["amt"]) if pos else B) * 1000) / 10
        calc = f"{js_str(pct)}% of " + (jg_lc(pos["label"]) if pos else "proceeds")
    else:
        calc = "credit"
    L(label, calc, rest, "Contracted", partner, "Channel agreement")
    o["why"] = (
        f"Freight from the {RATE_CARD['id']} lane rate card (one card for every move, inbound and outbound); the rest is "
        "the channel's contracted fee."
        if legs
        else "Contracted channel fee."
    )


# ---------------------------------------------------------------- actuals (step 10: reconcile and learn)
# The model that learns from each kind of cost line, and where a line without a model comes from
LEARN = {
    "prep": "prep-cost-time", "fees": "prep-cost-time", "sale": "resale-price", "parts": "resale-price",
    "material": "resale-price", "lease": "resale-price", "residual": "resale-price", "service": "service-exposure",
    "risk": "repair-success",
}  # fmt: skip
LEARN_RET = {"purchase": "ERP price (retrieved)", "avoid": "ERP price (retrieved)", "credit": "Vendor contract (retrieved)"}
# the demo record's preparation comes out 15% over estimate, so the story matches the review call (H8, assumed)
LEARN_PIN = {"RT-1048|prep": 0.15}
# exact per-line actuals where the seed has them (lines need not round to $10)
LINE_EXACT = {
    "RT-1049|Expected sale proceeds": 231,
    "RT-1049|Fees and freight": -36,
    "RT-1049|Unsold-risk allowance": -18,
    "RT-1049|Light refurbishment (chuck, brushes)": -57,
}
MODELS = WORLD["models"]


def learn_ver(c: Case, model: str) -> str:
    """The demo's learnVer: the model version that made the case's prediction (else the latest)."""
    p = next((x for x in c.get("predictions") or [] if x.get("model") == model), None)
    return p["ver"] if p else MODELS[-1]["v"]


def line_actuals(c: Case, r: dict) -> list[dict]:
    """The demo's lineActuals: an actual per cost line of the chosen route (deterministic per case and line, within
    ±25%), and the model that learns from it. A device case with a settlement (P9-6.12) takes the realised sale instead."""
    if c.get("template") == "device" and c.get("settlement"):
        from di.services.device import settle  # lazy: the device services read the case store

        return settle.lines(c, r)
    out = []
    for t in r["terms"]:
        m = LEARN.get(t["kind"])
        u = int(hash_id(f"{c['id']}|{t['label']}"), 16) % 2001 / 1000 - 1
        f = LEARN_PIN.get(f"{c['id']}|{t['kind']}", u * 0.25)
        exact = LINE_EXACT.get(f"{c['id']}|{t['label']}")
        act = exact if exact is not None else js_round(t["amt"] * (1 + f) / 10) * 10 if m else t["amt"]
        out.append({
            "label": t["label"], "kind": t["kind"], "pred": t["amt"], "act": act, "model": m,
            "ver": learn_ver(c, m) if m else None, "src": None if m else LEARN_RET.get(t["kind"]) or "Fixed amount (retrieved)",
        })  # fmt: skip
    return out


# RT-1048's preparation came in 15% over (LEARN_PIN), explained line by line
EX_ACT = {
    "RT-1048|prep": [
        ["Labour over standard", "+6 h × ₹850 on WO-47349", 5100, "Oracle Depot Repair", "Time confirmations on WO-47349"],
        ["Shaft repair sleeve, found worn at strip-down", "1 × ₹9,930 · VLT-SRS-250M", 9930, "Oracle Depot Repair · SAP Ariba",
         "Parts issue on WO-47349 · SC-7409"],
        ["Waiting charge at LOC-CHN-03", "75 min billable × $72/h = $90.00 at ₹83.5", 7515, "Reconcile · Northline 3PL bill",
         "Detention clause 7.2, checked against gate and release times"],
    ]
}  # fmt: skip


def ex_actual(c: Case, line: dict) -> list[list]:
    """The demo's exActual: what explains the difference between a confirmed actual and its prediction."""
    d = ex_inr(line["act"]) - ex_inr(line["pred"])
    if not d:
        return []
    k = f"{c['id']}|{line['kind']}"
    if k in EX_ACT:
        return EX_ACT[k]
    chosen: Any = c.get("chosen") or c.get("recommendation")
    P = ex_prep_parts(c, chosen) if line["kind"] == "prep" else None
    if P:
        hrs = js_str(js_round(abs(d) / P["rate"] * 10) / 10)
        return [
            [
                "Labour over standard" if d > 0 else "Labour under standard",
                f"{'+' if d > 0 else '−'}{hrs} h × {inr(P['rate'])}",
                d, "Oracle Depot Repair", "Time confirmations",
            ]
        ]  # fmt: skip
    src = "the outcome report" if line.get("model") else "the source system"
    return [
        [
            f"Difference reported by {src}", f"actual {inr(ex_inr(line['act']))} against {inr(ex_inr(line['pred']))}", d,
            "SAP S/4HANA", "Finance document " + ex_doc_ref(c, {"k": "finance"}),
        ]
    ]  # fmt: skip
