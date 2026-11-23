"""The asset behind a case, as Asset intelligence and the case pages read it (ported from the demo): health
(assetHealth), diagnostics (caseDiag), parts and their prices, the catalogue price, title, serial, lease and facts."""

import math

from di.repositories.case_detail import as_rma, prep_cost
from di.repositories.common import (
    CLASSES,
    Case,
    as_hex,
    as_model,
    fmt_dy,
)
from di.services.engine.jsmath import js_round
from di.services.engine.predictor import engine_class
from di.services.execution import asset_health, ex_prep_parts

DIAG = {
    "motor": ("Winding insulation", "grade"),
    "pump": ("Seal and bearing wear", "wear"),
    "control": ("Controller self-test", "test"),
    "drill": ("Battery health", "pct"),
    "batch": ("Battery health", "pct"),
    "it": ("Battery health", "pct"),
}


def _clamp(v: float, a: float, b: float) -> float:
    return max(a, min(b, v))


def health(c: Case) -> dict:
    """The demo's assetHealth: score, components and the band counts."""
    h = asset_health(c)
    band: dict[str, int] = {}
    for x in h["comps"]:
        k = "Excellent" if x["h"] >= 0.9 else "Good" if x["h"] >= 0.75 else "Fair" if x["h"] >= 0.55 else "Poor"
        band[k] = band.get(k, 0) + 1
    return h | {"band": band}


def as_serial(c: Case) -> str:
    return "SN" + str(as_hex(c, "sn"))[:7].rjust(7, "0")


def as_title(c: Case) -> str:
    m = as_model(c)
    return m if str(c["mfr"]).split(" ")[0].lower() in m.lower() else f"{c['mfr']} {m}"


def as_lease(c: Case) -> str:
    return f"LS-{4900 + as_hex(c, 'cl') % 300}"


def asset_facts(c: Case) -> list[list[str]]:
    """The demo's assetFacts."""
    d = c.get("demand") or {}
    return [
        ["Asset ID", c["assetId"]],
        ["Serial number", as_serial(c)],
        ["Product", as_model(c)],
        ["Manufacturer", c["mfr"]],
        ["Revision", "Rev " + "ABCDE"[as_hex(c, "rv") % 5]],
        ["Ownership", c["owner"] + (f" · lease {as_lease(c)} (ended)" if d.get("lease") else "")],
        ["Location", c["location"]],
        [
            "Contract demand",
            f"{c['owner']} · {d['site']}" + (" · confirmed" if d.get("confirmed") else " · forecast")
            if d.get("site")
            else "None matched",
        ],
        ["Received", fmt_dy(c["received"])],
        ["Received under", f"GR-{100000 + as_hex(c, 'gr') % 900000} · WMS receipt"],
        ["Return authorisation", as_rma(c) + " · IBM Sterling OMS"],
        ["Age", f"{_num(c['age'])} years"],
        ["Engineering life", c["engLife"]],
        ["Next inspection", c["nextInspection"]],
    ]


def _num(v: float) -> str:
    """JavaScript's String(n)."""
    return str(int(v)) if float(v).is_integer() else repr(v)


def parts_availability(c: Case, h: dict) -> list[dict]:
    """The demo's asParts."""
    out = []
    for x in h["comps"]:
        v, q = (as_hex(c, "pt" + x["n"]) % 100) / 100, as_hex(c, "q" + x["n"])
        if v >= 0.6:
            out.append({"n": x["n"], "st": "In stock", "cls": "ok", "q": q % 24 + 3})
        elif v >= 0.3:
            out.append({"n": x["n"], "st": "Limited", "cls": "warn", "q": q % 4 + 1})
        else:
            out.append({"n": x["n"], "st": "Backorder", "cls": "bad", "q": 0})
    return out


def part_prices(c: Case, h: dict) -> list[dict]:
    """The demo's asPartPrices: the parts the preparation buys (from the build-up), else an estimate per worn part."""
    if not c.get("grade"):
        return []
    rr = c.get("chosen") or c.get("recommendation")
    PB = ex_prep_parts(c, rr) if rr else None
    if PB and PB["parts"]:
        return [
            {
                "n": x["name"],
                "st": x["comp"],
                "price": x["unit"] * x["qty"] / 83.5,
                "pn": x["pn"],
                "qty": x["qty"],
                "inr": x["unit"] * x["qty"],
            }
            for x in PB["parts"]
        ]
    sc = [x for x in h["comps"] if x["cls"] != "ok"]
    prep = prep_cost(c)
    base = prep * 0.55 if prep else CLASSES[engine_class(c)]["pnew"] * c["qty"] * 0.06
    if not sc:
        return []
    w = [1 + as_hex(c, "pw" + x["n"]) % 5 for x in sc]
    tw = sum(w)
    if prep and prep < 200:
        return [{"n": x["n"], "st": x["st"], "price": max(1, math.floor(base * w[i] / tw))} for i, x in enumerate(sc)]
    left, out = js_round(base / 10) * 10, []
    for i, x in enumerate(sc):
        v = left if i == len(sc) - 1 else js_round(base * w[i] / tw / 10) * 10
        left -= v
        out.append({"n": x["n"], "st": x["st"], "price": max(15, v + 5)})
    return out


def catalogue(c: Case) -> float:
    """The demo's asCatalogue: the planned purchase price, else the class's new price."""
    amts = [next((t["amt"] for t in r["terms"] if t["kind"] == "purchase"), None) for r in c.get("routes") or []]
    return next((a for a in amts if a), None) or js_round(CLASSES[engine_class(c)]["pnew"] * c["qty"])


def case_diag(c: Case, h: dict) -> dict | None:
    """The demo's caseDiag: the class's diagnostic measure."""
    if c.get("assessment") == "Pending" or (not c.get("grade") and c.get("assessment") != "Ready"):
        return None
    metric, kind = DIAG.get(c["cls"]) or ("Condition score", "pct")
    if kind == "grade":
        value = "Grade " + (c.get("grade") or "B")
    elif kind == "wear":
        value = f"{max(5, 100 - h['score'])}%"
    elif kind == "test":
        n = as_hex(c, "st") % 4
        value = ("Fail" if c.get("grade") == "C" or n > 2 else "Pass") + f" · {n} error{'' if n == 1 else 's'}"
    else:
        value = f"{_clamp(h['score'] - as_hex(c, 'bh') % 12, 35, 98)}%"
    ins = next((e for e in c.get("evidence") or [] if e["k"] == "insp"), None)
    source = "MRO · Depot repair" if c["cls"] in ("motor", "pump") else "Inspection"
    return {"metric": metric, "value": value, "source": source, "at": (ins.get("fresh") if ins else None) or "—"}
