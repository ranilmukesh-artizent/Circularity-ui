"""Tool fleet valuer: a port of the PO prototype's Recover engine (docs/reference/po-modeler/recover-app-prototype.html).

Line numbers below cite that file. What is ported:

- `value(c, k, p)` (928-1008): one path's net value for one returned tool, with its value lines and destination.
- `applyRules` (1035-1043, through the shared `di.services.modeler.apply.apply_rules`), `decide1` (1107-1114),
  `decide` (1102-1106) and the queue plan `planQueue` (1065-1101): an open return competes with the other open
  returns for the same named orders and for the repair center's slots.
- The sample world: the 33 cases `CASES` (1117-1138, `mkCase`/`mkDemand`, random draws from `rng(26110)`), the 168
  history cases that only consume draws (1141-1150) and the 3 waiting returns `INBOX` (1153). The goldens
  (fixtures/golden/po/equip_cases.json, equip_decisions.json) were dumped from the prototype in that state.
- `fSim` for the equip template (2408-2410).

The prototype's globals become arguments: `liveCases()` is `queue` (None: the sample world, CASES then INBOX), and the
queue plan's blocked orders and owners (`VB`, `VOWN`) are passed down instead of swapped in and out. Pure code: no
session, no I/O. Cases and rules are the prototype's JSON shapes (camelCase keys), as in the goldens.
"""

import copy
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, NotRequired, TypedDict

from di.services.engine.jsmath import js_round, js_sum
from di.services.engine.routes import Route
from di.services.modeler.apply import apply_rules as shared_apply_rules
from di.services.modeler.carbon import co2_avoided
from di.services.modeler.compile import CompiledRule
from di.services.modeler.pack import load_pack
from di.services.modeler.templates import load_template
from di.services.modeler.valuers.rng import mulberry32

Case = dict[str, Any]
Rule = dict[str, Any]
Params = dict[str, float]

NAME = "Tool fleet returns"  # TPL.equip.name (2374)

# The constants below are the pack's `valuer.params` (packs/tool_fleet.json), copied so a valuer never changes the
# cached pack. PATHS (799-806): name, executing application, lead days, owner.
_PARAMS: dict[str, Any] = copy.deepcopy(load_pack("tool_fleet").valuer.params)
PATHS: dict[str, dict[str, Any]] = _PARAMS["paths"]
PK = list(PATHS)
FUNCS: list[str] = _PARAMS["funcs"]  # 818
SITES: list[str] = _PARAMS["sites"]  # 819
SOURCES: dict[str, str] = _PARAMS["sources"]  # 820

# CLS (822-835) with `freight` (837).
CLS: dict[str, dict[str, Any]] = _PARAMS["classes"]
for _c in CLS.values():
    _c["freight"] = js_round(_c["newP"] * 0.015 + 12)
CK = list(CLS)

CUST: list[str] = _PARAMS["cust"]  # 840
DEALERS: list[str] = _PARAMS["dealers"]  # 841
TODAY = date(2026, 11, 1)  # 842: Date.UTC(2026, 10, 1)
TRANSIT = 2
GR = {"A": 0, "B": 1, "C": 2, "D": 3}
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

BASEP: Params = _PARAMS["basep"]  # 868
FIN: dict[str, float] = _PARAMS["fin"]  # 869
POOLK = frozenset(_PARAMS["poolk"])  # 916: the kinds of named order a queue plan hands to one return only

# liveRules() = compileEquip(PUB.equip) (1052-1061): the published flow's rules BR-01 and BR-02 (1019-1020).
LIVE_RULES: list[Rule] = [
    {
        "action": "exclude",
        "id": "BR-01",
        "path": "exit",
        "scope": {"cls": ["LSR", "DCD"]},
        "text": "construction lasers or core drill rigs: never recycle",
    },
    {
        "action": "prefer",
        "id": "BR-02",
        "path": "redeploy",
        "scope": {"ft": ["Repair center"], "grade": ["A", "B"]},
        "text": "Repair center returns, grade A/B: prefer tool pool",
    },
]


class ValueLine(TypedDict):
    type: str  # "v" value, "c" cost, "h" holding
    label: str
    basis: str
    amt: float
    kind: NotRequired[str]  # the term kind (routes_adapter) when the valuer names it; the standard valuer always does


class PathValue(TypedDict):
    k: str
    ok: bool
    gross: float
    cost: float
    hold: float
    net: float
    why: str
    lines: list[ValueLine]
    dest: dict[str, Any] | None
    misses: list[str]
    co2: float | None  # kg CO2e avoided, information only (carbon.co2_avoided); None without a factor or avoided figure
    co2Prov: dict[str, Any] | None  # the card's provenance (carbon.Co2.prov); None without a factor


class Decision(TypedDict, total=False):
    all: list[PathValue]
    best: PathValue
    dk: str
    dv: PathValue
    uplift: float
    second: PathValue | None
    rules: list[str]
    indep: PathValue  # open cases: the best path when the return is decided alone (no queue plan)
    blk: list[str]  # open cases: the orders (and "DEPOT") the queue plan keeps from this return


# A destination that is a confirmed named order on the demand line: its carbon d is 1, else the forecast (P9-1.12).
CONFIRMED_KINDS = frozenset({"lease", "so", "proj"})


# ---------------------------------------------------------------- helpers


def _dstr(n: int) -> str:  # 843
    d = TODAY + timedelta(days=n)
    return f"{d.day} {_MONTHS[d.month - 1]}"


def _money(n: float) -> str:  # 797, money(n, true)
    return ("−" if n < 0 else "") + "$" + f"{js_round(abs(n)):,}"


def _pct(v: float) -> str:
    return f"{js_round(v * 100)}%"


def _num(x: float) -> str:  # String(number) for the integers and decimals the prototype prints
    return str(int(x)) if float(x).is_integer() else repr(float(x))


def _grade(c: Case) -> str:
    return c.get("grade") or c["estGrade"]


def _timing(c: Case, d: dict[str, Any], lead: int) -> dict[str, int]:  # 866
    tr = TRANSIT if d.get("site") and d["site"] != c["site"] else 0
    ready = lead + tr
    return {"tr": tr, "ready": ready, "buffer": d["need"] - ready}


def _by_desc(items: list[Any], key: Callable[[Any], float]) -> list[Any]:
    """`items.sort((a, b) => key(b) - key(a))`: JavaScript's sort is stable, like Python's."""
    return sorted(items, key=lambda x: -key(x))


@dataclass
class _Ctx:
    """What value() reads besides the case: liveCases(), heldOrders(), and the queue plan's VB and VOWN."""

    live: Sequence[Case]
    held: dict[str, str]
    blk: frozenset[str] | set[str] = frozenset()
    own: dict[str, str] = field(default_factory=dict)


def _held_orders(live: Sequence[Case]) -> dict[str, str]:  # 920
    return {x["order"]: x["id"] for x in live if x["status"] in ("sent", "closed") and x.get("order")}


def _pool_for(c: Case, live: Sequence[Case]) -> dict[str, list[dict[str, Any]]]:  # 922-927
    dm = c["dem"]
    if c.get("hist"):
        return {"lease": dm["lease"], "so": dm["so"], "proj": [dm["proj"]] if dm["proj"] else []}
    out: dict[str, list[dict[str, Any]]] = {"lease": [], "so": [], "proj": []}
    seen: set[str] = set()

    def add(x: Case) -> None:
        for kind in ("lease", "so"):
            for d in x["dem"][kind]:
                if d["id"] not in seen:
                    seen.add(d["id"])
                    out[kind].append(d)
        pj = x["dem"]["proj"]
        if pj and pj["id"] not in seen:
            seen.add(pj["id"])
            out["proj"].append(pj)

    add(c)
    for x in live:
        if x is not c and x["cls"] == c["cls"]:
            add(x)
    return out


# ---------------------------------------------------------------- value (928-1008)


def _value(c: Case, k: str, p: Params, ctx: _Ctx) -> PathValue:
    C = CLS[c["cls"]]
    g = _grade(c)
    dm = c["dem"]
    pool = _pool_for(c, ctx.live)
    held: dict[str, str] = {} if c.get("hist") else ctx.held
    blk = ctx.blk
    taken: list[str] = []

    def avail(d: dict[str, Any]) -> bool:
        if held.get(d["id"]) and held[d["id"]] != c["id"]:
            taken.append(f"{d['id']} ({d['who']}) is already committed to {held[d['id']]}")
            return False
        if d["id"] in blk:
            taken.append(
                f"{d['id']} ({d['who']}) is planned for {ctx.own.get(d['id']) or 'another return'}"
                ", where it adds more across the queue"
            )
            return False
        return True

    L: list[ValueLine] = []

    def add(type_: str, label: str, basis: str, amt: float) -> None:
        L.append({"type": type_, "label": label, "basis": basis, "amt": amt})

    ok = True
    why = ""
    dest: dict[str, Any] | None = None
    misses: list[str] = []

    if k in ("release", "refurb"):
        lead = PATHS[k]["lead"]
        g_ok = g == "A" if k == "release" else (g in ("B", "C") and c["rul"] >= 40)
        blocked = k == "refurb" and "DEPOT" in blk
        cands = [d for d in pool["lease"] if avail(d)] + ([d for d in pool["so"] if avail(d)] if k == "refurb" else [])
        mr = FIN["rate"] / 12

        def lv(d: dict[str, Any]) -> dict[str, float]:
            n = d["term"]
            ann = (1 - math.pow(1 + mr, -n)) / mr
            inc = d["rate"] * p["lease"] * ann
            r0 = min(90, c["rul"] + FIN["refurbLife"]) if k == "refurb" else c["rul"]
            r1 = max(5, js_round(r0 - FIN["lifePerMonth"] * n))
            lf = 0.6 + 0.4 * r1 / 100
            resid = C["newP"] * C["res"]["B"] * p["market"] * lf
            rpv = resid / math.pow(1 + mr, n)
            svc = C["newP"] * FIN["svc"] * n / 12
            return {"n": n, "ann": ann, "inc": inc, "r0": r0, "r1": r1, "lf": lf, "resid": resid, "rpv": rpv, "svc": svc}

        def option(d: dict[str, Any]) -> dict[str, Any] | None:
            t = _timing(c, d, lead)
            if t["buffer"] < 0:
                unit = "a refurbished unit" if k == "refurb" else "this unit"
                misses.append(f"{d['id']} ({d['who']}) needs it by {_dstr(d['need'])}; {unit} is ready {_dstr(t['ready'])}")
                return None
            L0 = lv(d) if d["kind"] == "lease" else None
            inc = L0["inc"] + L0["rpv"] if L0 else d["price"]
            out = C["freight"] if t["tr"] else 0
            work = (
                C["refurb"] * p["labor"] * (1.35 if g == "C" else 1) + C["freight"] if k == "refurb" else C["newP"] * 0.02
            ) + (L0["svc"] if L0 else 0)
            return {"d": d, "t": t, "inc": inc, "L0": L0, "net": inc - work - out}

        opts = [] if blocked else [o for o in map(option, cands) if o]
        opt = _by_desc(opts, lambda o: o["net"])[0] if opts else None
        ok = g_ok and opt is not None and (k != "release" or p["lease"] > 0)
        if opt:
            d, t, L0 = opt["d"], opt["t"], opt["L0"]
            if d["kind"] == "lease":
                add(
                    "v",
                    ("Fleet renewal " if d["renew"] else "New fleet order ")
                    + f"{d['id']} · {d['who']}, {L0['n']} months in today's money",
                    f"${d['rate']:,} fleet fee a month × {L0['n']} months"
                    + (f" × {_pct(p['lease'])} fleet demand" if p["lease"] != 1 else "")
                    + f", discounted at {_pct(FIN['rate'])} a year",
                    L0["inc"],
                )
                add(
                    "v",
                    f"Value when the contract ends (month {L0['n']}), in today's money",
                    f"{_money(C['newP'])} new × {_pct(C['res']['B'])} grade B price"
                    + (f" × {_pct(p['market'])} market" if p["market"] != 1 else "")
                    + f" × {_pct(L0['lf'])} life factor at about {L0['r1']}% life left, discounted {L0['n']} months",
                    L0["rpv"],
                )
                add(
                    "c",
                    "Repairs covered during the contract",
                    f"{_pct(FIN['svc'])} of new price a year × {L0['n']} months",
                    L0["svc"],
                )
            else:
                add("v", f"Sales order {d['id']} · {d['who']}", "agreed price for 1 certified pre-owned tool", opt["inc"])
            if k == "refurb":
                add(
                    "c",
                    "Refurbish to certified condition",
                    f"{_money(C['refurb'])} standard × {_pct(p['labor'])} labor index"
                    + (" × 135% for grade C" if g == "C" else ""),
                    C["refurb"] * p["labor"] * (1.35 if g == "C" else 1),
                )
                add("c", "Inbound to repair center", "1.5% of new price + $12 handling", C["freight"])
            else:
                add("c", "Clean and inspect", f"2% of new price {_money(C['newP'])}", C["newP"] * 0.02)
            if t["tr"]:
                add("c", f"Ship to {d['site']}", "1.5% of new price + $12 handling", C["freight"])
            if d["kind"] == "lease":
                verb = f"issue to {d['who']} on fleet " + ("renewal " if d["renew"] else "order ") + d["id"]
            else:
                verb = f"sell to {d['who']} on {d['id']}"
            if k == "release":
                short = f"{d['who']} ({d['id']})"
            else:
                short = ("fleet · " if d["kind"] == "lease" else "sale · ") + d["who"]
            dest = {**d, **t, "verb": verb, "short": short}
        if ok and dest:
            why = ("Refurbish, then " + dest["verb"] if k == "refurb" else "Clean, inspect and issue to " + dest["who"]) + (
                f" ({dest['id']})" if dest["id"] not in dest["verb"] else ""
            )
        elif not g_ok:
            if k == "release":
                why = (
                    f"Grade {g} must be refurbished before it can be issued to a fleet (see Refurbish)"
                    if g in ("B", "C")
                    else f"Grade {g} cannot be issued to a fleet"
                )
            elif g == "A":
                why = "Grade A needs only a clean and inspect (priced under Re-issue and Pre-owned sale)"
            elif c["rul"] < 40:
                why = f"Remaining life {c['rul']}% is too short to justify refurbishment"
            else:
                why = "Grade D cannot be refurbished economically"
        elif blocked:
            why = "No repair center slot in the next two weeks: the queue plan gives the slots to refurbishments that add more"
        elif taken:
            why = taken[0]
        elif misses:
            why = misses[0]
        elif k == "refurb":
            why = "No fleet contract or sales order to refurbish against; refurbishing to stock is not recommended"
        else:
            why = "No open fleet renewal or order for this model"
    elif k == "redeploy":
        lead = PATHS["redeploy"]["lead"]
        pj = [{"d": d, "t": _timing(c, d, lead)} for d in pool["proj"] if avail(d)]
        pj_ok = _by_desc(
            [x for x in pj if x["t"]["buffer"] >= 0], lambda x: x["d"]["rental"] - (C["freight"] if x["t"]["tr"] else 0)
        )
        pk0 = pj_ok[0] if pj_ok else pj[0] if pj else None
        d = pk0["d"] if pk0 else None
        t = pk0["t"] if pk0 else None
        ok = d is not None and t is not None and g != "D" and c["rul"] >= 45 and t["buffer"] >= 0
        if d and t:
            add(
                "v",
                f"New pool unit avoided · {d['id']}",
                f"purchase requisition {d['quote']} for 1 new pool unit, net of its end-of-life value",
                d["rental"],
            )
            if t["tr"]:
                add("c", f"Ship to {d['site']}", "1.5% of new price + $12 handling", C["freight"])
            add("c", "Clean, test and tag for the pool", "4% of new price", C["newP"] * 0.04)
            dest = {**d, **t, "verb": f"place in the {d['site']} loaner pool ({d['id']})", "short": f"pool · {d['site']}"}
        if ok and d:
            why = f"Place in the {d['site']} loaner pool ({d['id']}), from {_dstr(d['need'])}"
        elif not d or not t:
            why = taken[0] if taken else "No service center pool is short of this model"
        elif t["buffer"] < 0:
            why = f"{d['id']} needs it by {_dstr(d['need'])}; unit ready {_dstr(t['ready'])}"
        else:
            why = "Condition too low for the loaner pool"
    elif k == "resell":
        ok = True
        bids = _by_desc([b for b in dm["bid"] if GR[g] <= GR[b["gmin"]]], lambda b: b["price"])
        b = bids[0] if bids else None
        if b:
            sale = b["price"]
            add(
                "v",
                f"Bid {b['id']} · {b['who']}",
                f"firm bid for grade {b['gmin']} or better, cleaned and tested, valid to {_dstr(b['exp'])}",
                sale,
            )
            dest = {
                **b,
                "need": b["exp"],
                "ready": 0,
                "buffer": b["exp"],
                "tr": 0,
                "verb": f"sell to {b['who']} ({b['id']})",
                "short": f"bid · {b['who']}",
                "committed": True,
            }
        else:
            lf = 0.6 + 0.4 * c["rul"] / 100
            sale = C["newP"] * C["res"][g] * p["market"] * lf
            add(
                "v",
                "Outlet sale (estimate)",
                f"{_money(C['newP'])} new × {_pct(C['res'][g])} grade {g} price × {_pct(p['market'])} market"
                f" × {_pct(lf)} life factor",
                sale,
            )
            dest = {
                "kind": "market",
                "id": "listing",
                "who": "pre-owned outlet",
                "need": 9,
                "ready": 9,
                "buffer": 0,
                "tr": 0,
                "verb": "list in the pre-owned outlet (no committed buyer yet)",
                "short": "outlet",
                "committed": False,
            }
        add("c", "Clean and test for sale", f"1.5% of new price {_money(C['newP'])}", C["newP"] * 0.015)
        add("c", "Channel fees", "8% of sale price", sale * 0.08)
        add("c", "Listing and handling", "flat", 15)
        why = (
            f"Clean, test and sell to {b['who']} on bid {b['id']}"
            if b
            else f"No live bid; outlet estimate for grade {g} at {c['rul']}% life"
        )
    elif k == "harvest":
        passed = 0
        wos: list[str] = []
        for j, pr in enumerate(c["partRul"]):
            pn, pv = C["parts"][j]
            w = dm["wo"][pn]
            if pr >= p["rulMin"] and w:
                passed += 1
                wos.append(w[0]["id"])
                add(
                    "v",
                    f"{pn} → {w[0]['id']} · {w[0]['who']}",
                    f"new part {_money(pv)} × 70% certified used value · {pr}% life ≥ {_num(p['rulMin'])}%",
                    pv * 0.7,
                )
                if w[0]["backorder"]:
                    add(
                        "v",
                        f"{pn}: customer wait avoided",
                        f"part is backordered; {w[0]['id']} not left waiting, loaner days and service-level cost saved",
                        p["downtime"],
                    )
                add("c", f"Test and certify {pn}", "flat per part", 12)
        add("v", "Residual material", f"60% of material value {_money(C['mat'])}", C["mat"] * 0.6)
        add("c", "Teardown", "4% of new price + $15", C["newP"] * 0.04 + 15)
        ok = passed > 0
        if ok:
            s = "s" if passed > 1 else ""
            dest = {
                "kind": "wo",
                "id": ", ".join(wos),
                "who": f"{passed} repair order{s}",
                "need": 14,
                "ready": 10,
                "buffer": 4,
                "tr": 0,
                "verb": f"harvest {passed} certified part{s} for repair orders {', '.join(wos)}",
                "short": f"{passed} repair order{s}",
                "wos": wos,
            }
        why = (
            "Certified parts issued to repair orders " + ", ".join(wos)
            if ok
            else f"No part both passes the {_num(p['rulMin'])}% life test and has an open repair order"
        )
    else:
        add("v", "Material credit", f"recycler quote {dm['rcq']}", C["mat"])
        add("c", "Recycling and certificate", "recycler fee", C["fee"])
        dest = {
            "kind": "exit",
            "id": dm["rcq"],
            "who": "certified recycler",
            "need": 6,
            "ready": 6,
            "buffer": 0,
            "tr": 0,
            "verb": f"send to the certified recycler (quote {dm['rcq']})",
            "short": "recycler",
        }
        why = f"Certified recycling on quote {dm['rcq']}"
    lead_k = PATHS[k]["lead"]
    add("h", "Holding until done", f"{_money(p['hold'])} a day × {lead_k} days to complete", p["hold"] * lead_k)
    gross = js_sum(x["amt"] for x in L if x["type"] == "v")
    cost = js_sum(x["amt"] for x in L if x["type"] == "c")
    hold = p["hold"] * lead_k
    net = gross - cost - hold
    confirmed = dest is not None and dest.get("kind") in CONFIRMED_KINDS
    cv = co2_avoided(load_pack("tool_fleet"), c["cls"], k, 1, confirmed=confirmed)
    return {
        "k": k,
        "ok": bool(ok),
        "gross": gross,
        "cost": cost,
        "hold": hold,
        "net": net,
        "why": why,
        "lines": L,
        "dest": dest,
        "misses": misses,
        "co2": cv.kg if cv else None,
        "co2Prov": cv.prov() if cv else None,
    }


# ---------------------------------------------------------------- rules (1027-1043)


def apply_rules(c: Case, values: list[PathValue], rules: Sequence[Rule]) -> dict[str, Any]:
    """applyRules (1035) through the shared `di.services.modeler.apply.apply_rules`: marks the paths the rules exclude
    (or a require rule leaves out) as not ok, in place. Returns `{ids, pref}`, or `{ids: [], pref: None, waived: True}`
    when the rules would leave no path (then nothing changes)."""
    routes: list[Route] = [
        {"id": v["k"], "excluded": not v["ok"], "failGate": -1, "failReason": v["why"], "gates": ["pass"] * 6} for v in values
    ]
    compiled = [CompiledRule(r["id"], r.get("scope") or {}, r["action"], r.get("path", ""), str(r.get("text"))) for r in rules]
    out = shared_apply_rules(c, routes, compiled, load_template("tool_fleet"))
    for v, r in zip(values, routes, strict=True):
        v["ok"], v["why"] = not r["excluded"], r["failReason"]
    if out.waived or not any(v["ok"] for v in values):
        return {"ids": [], "pref": None, "waived": True}
    return {"ids": out.ids, "pref": out.preferred}


# ---------------------------------------------------------------- decide (1102-1114, 872-879)


def _default_path(c: Case, ctx: _Ctx) -> str:  # 872
    g = _grade(c)

    def feasible(k: str) -> bool:
        return _value(c, k, BASEP, ctx)["ok"]

    if c["ft"] == "Fleet management":
        return "release" if g == "A" and feasible("release") else "resell"
    if c["ft"] == "Repair center":
        if g == "A" and feasible("release"):
            return "release"
        return "refurb" if g in ("B", "C") and feasible("refurb") else "exit"
    if c["ft"] == "Remarketing":
        return "resell"
    return "exit" if g == "D" else "resell"


def _decide1(c: Case, p: Params, rules: Sequence[Rule], ctx: _Ctx) -> Decision:  # 1107
    values = [_value(c, k, p, ctx) for k in PK]
    ap = apply_rules(c, values, rules)
    ok = _by_desc([v for v in values if v["ok"]], lambda v: v["net"])
    pv = next((v for v in ok if v["k"] == ap["pref"]), None) if ap["pref"] else None
    if pv and pv is not ok[0] and pv["net"] >= ok[0]["net"] - abs(ok[0]["net"]) * 0.15:
        ok = [pv] + [v for v in ok if v is not pv]
    best = ok[0]
    dk = _default_path(c, ctx)
    dv = next(v for v in values if v["k"] == dk)
    return {
        "all": values,
        "best": best,
        "dk": dk,
        "dv": dv,
        "uplift": best["net"] - dv["net"],
        "second": ok[1] if len(ok) > 1 else None,
        "rules": ap["ids"],
    }


def _pid(b: PathValue | None) -> str | None:
    return b["dest"]["id"] if b and b["dest"] and b["dest"].get("kind") in POOLK else None


class Plan(TypedDict):
    res: dict[str, Decision]
    blk: dict[str, set[str]]
    own: dict[str, str]
    why: dict[str, dict[str, Any]]
    total: float
    fcfs: float
    gain: float
    contested: list[str]
    indep: dict[str, PathValue]
    slots: int
    refurb_n: int


_PLANS: dict[str, Plan] = {}


def _plan_queue(p: Params, rules: Sequence[Rule], live: Sequence[Case], held: dict[str, str]) -> Plan:  # 1065-1101
    key = json.dumps([p, rules, live], sort_keys=True, default=str)
    if key in _PLANS:
        return _PLANS[key]
    open_ = [c for c in live if not c.get("hist") and c["status"] in ("new", "data")]
    slots = max(
        0,
        js_round(p["slots"] if p.get("slots") is not None else BASEP["slots"])
        - sum(1 for c in live if c["status"] == "sent" and c.get("path") == "refurb"),
    )
    blk: dict[str, set[str]] = {c["id"]: set() for c in open_}
    own: dict[str, str] = {}
    why: dict[str, dict[str, Any]] = {}
    res: dict[str, Decision] = {}

    def raw(c: Case, b: set[str] | frozenset[str], o: dict[str, str]) -> Decision:
        return _decide1(c, p, rules, _Ctx(live, held, b, o))

    def solve() -> None:
        res.clear()
        for c in open_:
            res[c["id"]] = raw(c, blk[c["id"]], own)

    def regret(c: Case, extra: list[str]) -> float:
        return res[c["id"]]["best"]["net"] - raw(c, blk[c["id"]] | set(extra), own)["best"]["net"]

    for _ in range(40):
        solve()
        changed = False
        claims: dict[str, list[Case]] = {}
        for c in open_:
            o = _pid(res[c["id"]]["best"])
            if o:
                claims.setdefault(o, []).append(c)
        for o, cs in claims.items():
            if len(cs) < 2:
                continue
            w = _by_desc([(c, regret(c, [o])) for c in cs], lambda x: x[1])
            for x in w[1:]:
                blk[x[0]["id"]].add(o)
            own[o] = w[0][0]["id"]
            why[o] = {"to": w[0][0]["id"], "gain": w[0][1], "others": [x[0]["id"] for x in w[1:]]}
            changed = True
        rf = [c for c in open_ if res[c["id"]]["best"]["k"] == "refurb"]
        if len(rf) > slots:
            w = _by_desc([(c, regret(c, ["DEPOT"])) for c in rf], lambda x: x[1])
            for x in w[slots:]:
                blk[x[0]["id"]].add("DEPOT")
            changed = True
        if not changed:
            break
    # free depot slots left by returns that moved to another path
    used = sum(1 for c in open_ if res[c["id"]]["best"]["k"] == "refurb")
    freed = []
    for c in open_:
        if "DEPOT" in blk[c["id"]]:
            s2 = blk[c["id"]] - {"DEPOT"}
            freed.append((c, raw(c, s2, own)["best"]["net"] - res[c["id"]]["best"]["net"], s2))
    for c, gain, s2 in _by_desc(freed, lambda x: x[1]):
        if used < slots and gain > 0:
            blk[c["id"]] = s2
            used += 1
    solve()
    # give orders nobody ended up using back to the return that gains most from them
    for _ in range(6):
        used_now = {o for o in (_pid(res[c["id"]]["best"]) for c in open_) if o}
        moved = False
        for o in [o for o in why if o not in used_now]:
            cands = []
            for c in open_:
                if o in blk[c["id"]]:
                    s2 = blk[c["id"]] - {o}
                    nb = raw(c, s2, own)["best"]
                    cands.append((c, nb["net"] - res[c["id"]]["best"]["net"], s2, _pid(nb)))
            best = next(iter(_by_desc([x for x in cands if x[1] > 0 and x[3] == o], lambda x: x[1])), None)
            if best:
                blk[best[0]["id"]] = best[2]
                why[o] = {"to": best[0]["id"], "gain": best[1], "others": []}
                moved = True
        if not moved:
            break
        solve()
    assign: dict[str, str] = {}
    total = 0.0
    refurb_n = 0
    for c in open_:
        b = res[c["id"]]["best"]
        total += b["net"]
        if b["k"] == "refurb":
            refurb_n += 1
        o = _pid(b)
        if o:
            assign[o] = c["id"]
    # baselines: each return decided alone (orders promised twice) and first come, first served (oldest return first)
    indep: dict[str, PathValue] = {}
    want: dict[str, list[str]] = {}
    for c in open_:
        b = raw(c, frozenset(), {})["best"]
        indep[c["id"]] = b
        o = _pid(b)
        if o:
            want.setdefault(o, []).append(c["id"])
    fcfs = 0.0
    dep = 0
    used_o: set[str] = set()
    for c in sorted(open_, key=lambda c: (-c["days"], c["id"])):
        s2 = set(used_o)
        if dep >= slots:
            s2.add("DEPOT")
        b = raw(c, s2, {})["best"]
        fcfs += b["net"]
        o = _pid(b)
        if o:
            used_o.add(o)
        if b["k"] == "refurb":
            dep += 1
    plan: Plan = {
        "res": res,
        "blk": blk,
        "own": assign,
        "why": why,
        "total": total,
        "fcfs": fcfs,
        "gain": total - fcfs,
        "contested": [o for o, ids in want.items() if len(ids) > 1],
        "indep": indep,
        "slots": slots,
        "refurb_n": refurb_n,
    }
    if len(_PLANS) >= 64:
        _PLANS.clear()
    _PLANS[key] = plan
    return plan


def _decide(c: Case, p: Params, rules: Sequence[Rule], live: Sequence[Case]) -> Decision:  # 1102
    held = _held_orders(live)
    if not c.get("hist") and c["status"] in ("sent", "closed") and c.get("order"):
        pl0 = _pool_for(c, live)
        blocked = {d["id"] for d in pl0["lease"] + pl0["so"] + pl0["proj"] if d["id"] != c["order"]}
        return _decide1(c, p, rules, _Ctx(live, held, blocked))
    if c.get("hist") or c["status"] not in ("new", "data") or all(x["id"] != c["id"] for x in live):
        return _decide1(c, p, rules, _Ctx(live, held))
    pl = _plan_queue(p, rules, live, held)
    return {**pl["res"][c["id"]], "indep": pl["indep"][c["id"]], "blk": sorted(pl["blk"][c["id"]])}


# ---------------------------------------------------------------- the sample world (791-793, 844-865, 1117-1153)


class _Gen:
    def __init__(self, seed: int) -> None:
        self.R = mulberry32(seed)
        self.seq = 112

    def pick(self, a: Sequence[Any]) -> Any:  # 793
        return a[math.floor(self.R() * len(a))]

    def rid(self, pre: str, n: int) -> str:  # 844
        return f"{pre}-{10 ** (n - 1) + math.floor(self.R() * 9 * 10 ** (n - 1))}"

    def demand(self, c: Case) -> dict[str, Any]:  # mkDemand (845-865)
        R, pick, rid = self.R, self.pick, self.rid
        C = CLS[c["cls"]]
        m = C["lease12"] / 12
        dm: dict[str, Any] = {"lease": [], "so": [], "bid": [], "proj": None, "wo": {}, "rcq": rid("RCQ", 4)}
        nl = (2 if R() < 0.35 else 1) if R() < 0.58 else 0
        for _ in range(nl):
            renew = R() < 0.55
            cust = pick(CUST)
            site = c["site"] if R() < 0.5 else pick(SITES)
            need = 6 + math.floor(R() * 28)
            id_ = rid("FC", 4) if renew else rid("FO", 4)
            rate = js_round(m * (0.92 + R() * 0.18) / 5) * 5
            term = pick([12, 12, 18, 24])
            what = (
                f"Fleet contract {id_} with {cust} renews {_dstr(need)}; customer confirmed one more unit of this model"
                if renew
                else f"New fleet order {id_} from {cust}, start {_dstr(need)}"
            )
            when = (
                "renewal confirmed " + _dstr(-1 - math.floor(R() * 6))
                if renew
                else "order entered " + _dstr(-math.floor(R() * 5))
            )
            dm["lease"].append(
                {
                    "kind": "lease",
                    "id": id_,
                    "renew": renew,
                    "who": cust,
                    "site": site,
                    "need": need,
                    "rate": rate,
                    "term": term,
                    "what": what,
                    "when": when,
                }
            )
        if R() < 0.45:
            cust = pick(CUST)
            need = 16 + math.floor(R() * 25)
            id_ = rid("SO", 5)
            site = pick(SITES)
            price = js_round(C["newP"] * C["rs"] * (0.94 + R() * 0.14) / 10) * 10
            what = f"Sales order {id_} from {cust}: 1 certified pre-owned tool, ship by {_dstr(need)}"
            when = "order booked " + _dstr(-math.floor(R() * 7))
            dm["so"].append(
                {"kind": "so", "id": id_, "who": cust, "site": site, "need": need, "price": price, "what": what, "when": when}
            )
        nb = (2 if R() < 0.3 else 1) if R() < 0.62 else 0
        for _ in range(nb):
            gmin = pick(["B", "C", "C"])
            who = pick(DEALERS)
            id_ = rid("BID", 5)
            exp = 3 + math.floor(R() * 8)
            price = js_round(C["newP"] * C["res"][gmin] * (1 + R() * 0.15) / 10) * 10
            what = f"Bid {id_} from {who} for grade {gmin} or better, cleaned and tested, valid to {_dstr(exp)}"
            when = "bid received " + _dstr(-math.floor(R() * 3))
            dm["bid"].append(
                {"kind": "bid", "id": id_, "who": who, "gmin": gmin, "exp": exp, "price": price, "what": what, "when": when}
            )
        if R() < 0.26:
            site = pick(SITES)
            need = 5 + math.floor(R() * 20)
            id_ = rid("TPR", 4)
            rental = js_round(C["newP"] * 0.42 / 10) * 10
            quote = rid("PR", 4)
            what = f"Tool pool request {id_}: {site} loaner pool is 1 unit short from {_dstr(need)}"
            when = "pool shortage raised " + _dstr(-math.floor(R() * 6))
            dm["proj"] = {
                "kind": "proj",
                "id": id_,
                "who": f"{site} tool pool",
                "site": site,
                "need": need,
                "rental": rental,
                "quote": quote,
                "what": what,
                "when": when,
            }
        for pn, _pv in C["parts"]:
            u = 1 + math.floor(R() * 3) if R() < 0.6 else 0
            bo = u > 0 and R() < 0.45
            dm["wo"][pn] = [{"id": rid("RO", 5), "who": pick(CUST), "backorder": bo} for _ in range(u)]
        return dm

    def case(self, over: Case | None = None) -> Case:  # mkCase (1118-1126)
        R, pick = self.R, self.pick
        over = over or {}
        cls = over.get("cls") or pick(CK)
        C = CLS[cls]
        ft = over.get("ft") or pick(FUNCS)
        grade = over["grade"] if "grade" in over else pick(["A", "B", "B", "C", "C", "D"])
        base = 75 if grade == "A" else 60 if grade == "B" else 46 if grade == "C" else 28
        rul = over.get("rul") or js_round(base + (R() - 0.5) * 22)
        id_ = f"RC-26{self.seq}"
        self.seq += 1
        site = over.get("site") or pick(SITES)
        est = grade or pick(["B", "C"])
        serial = f"{cls}-{10000 + math.floor(R() * 89999)}"
        age = 3 + math.floor(R() * 40)
        days = 1 + math.floor(R() * 9)
        part_rul = [max(5, min(98, js_round(rul + (R() - 0.4) * 40))) for _ in C["parts"]]
        c: Case = {
            "id": id_,
            "cls": cls,
            "ft": ft,
            "site": site,
            "src": SOURCES[ft],
            "grade": grade,
            "estGrade": est,
            "rul": rul,
            "serial": serial,
            "age": age,
            "days": days,
            "partRul": part_rul,
            "status": "new",
            "log": [],
        }
        c.update(over)
        c["grade"] = grade
        c["dem"] = self.demand(c)
        return c


def _build_world() -> tuple[list[Case], list[Case]]:
    """CASES (1127-1138) and INBOX (1153), drawn from rng(26110) in the prototype's order."""
    gen = _Gen(26110)
    cases = [gen.case() for _ in range(30)]
    cases.append(gen.case({"cls": "CMH", "ft": "Repair center", "grade": "C", "rul": 44, "site": "Houston"}))
    cases.append(gen.case({"cls": "CRH", "ft": "Remarketing", "grade": "A", "rul": 81, "site": "Houston"}))
    cases.append(gen.case({"cls": "BRK", "ft": "Tool pool", "grade": "B", "rul": 63, "site": "Atlanta"}))
    cases[30]["partRul"][0] = 72
    cases[30]["dem"]["lease"] = [
        {
            "kind": "lease",
            "id": "FC-2231",
            "renew": True,
            "who": "Brightline Mechanical",
            "site": "Houston",
            "need": 19,
            "rate": 55,
            "term": 12,
            "what": "Fleet contract FC-2231 with Brightline Mechanical renews 20 Nov; customer confirmed one more combihammer",
            "when": "renewal confirmed 29 Oct",
        }
    ]
    cases[30]["dem"]["so"] = [
        {
            "kind": "so",
            "id": "SO-88412",
            "who": "Westmark Supply",
            "site": "Atlanta",
            "need": 12,
            "price": 880,
            "what": "Sales order SO-88412 from Westmark Supply: 1 certified pre-owned combihammer, ship by 13 Nov",
            "when": "order booked 27 Oct",
        }
    ]
    for i in (3, 9, 15, 21):
        cases[i]["grade"] = None
        cases[i]["status"] = "data"
        cases[i]["estGrade"] = cases[i]["estGrade"] or "C"
    # INBOX is not yet initialised here (a `let` in its temporal dead zone), so liveCases() is CASES alone.
    for i in (1, 5, 8, 12, 17, 24, 27):
        cases[i]["status"] = "sent"
        b = _decide(cases[i], BASEP, LIVE_RULES, cases)["best"]
        cases[i]["path"] = b["k"]
        cases[i]["order"] = _pid(b)
        cases[i]["sentAt"] = "31 Oct"
    # sort: biggest uplift first (V8 sorts a copy, so every comparison sees the unsorted CASES)
    uplift = {c["id"]: _decide(c, BASEP, LIVE_RULES, cases)["uplift"] for c in cases}
    cases.sort(key=lambda c: -uplift[c["id"]])
    # HIST (1141-1150): 168 closed cases; only their draws matter here
    R = gen.R
    for _ in range(168):
        gen.case()
        for _ in range(3):  # noise
            R()
        ovr = R() < 0.07
        R()  # day
        R()  # hrs
        if ovr:
            gen.pick(["Customer commitment", "Known condition issue not in data", "Market knowledge"])
    gen.seq = 112 + 33
    inbox = [
        gen.case({"ft": "Fleet management", "cls": "CMH", "site": "Denver"}),
        gen.case({"ft": "Repair center", "cls": "DCD", "site": "Phoenix"}),
        gen.case({"ft": "Tool pool", "cls": "CRH", "site": "Atlanta"}),
    ]
    return cases, inbox


_WORLD: list[tuple[list[Case], list[Case]]] = []


def _world() -> tuple[list[Case], list[Case]]:
    if not _WORLD:
        _WORLD.append(_build_world())
    return _WORLD[0]


def _live(queue: Sequence[Case] | None) -> Sequence[Case]:
    if queue is not None:
        return queue
    cases, inbox = _world()
    return cases + inbox


def sample_cases() -> list[Case]:
    """Every case of the prototype's CASES (open and sent), in its order (golden equip_cases.json `cases`)."""
    return copy.deepcopy(_world()[0])


def sample_queue() -> list[Case]:
    """The open cases (openCases(), 1172): golden equip_cases.json `open_ids`."""
    return [c for c in sample_cases() if c["status"] in ("new", "data")]


def sample_live_cases() -> list[Case]:
    """liveCases() (919): CASES then the 3 waiting returns of INBOX; the queue the sample decisions are planned over."""
    cases, inbox = _world()
    return copy.deepcopy(cases + inbox)


# ---------------------------------------------------------------- public API


def value(case: Case, path: str, params: Params | None = None, *, queue: Sequence[Case] | None = None) -> PathValue:
    """value(c, k, p) outside a queue plan: no order blocked except those held by approved (sent) decisions.
    `queue` is liveCases() (the returns that share named orders); None means the sample world."""
    live = _live(queue)
    return copy.deepcopy(_value(case, path, params or BASEP, _Ctx(live, _held_orders(live))))


def decide(
    case: Case, params: Params | None = None, rules: Sequence[Rule] | None = None, *, queue: Sequence[Case] | None = None
) -> Decision:
    """decide(c, p, rs): an open case of the queue is decided within the queue plan; a sent case keeps its order;
    anything else is decided alone. `rules` defaults to the published flow's rules; `queue` to the sample world."""
    live = _live(queue)
    return copy.deepcopy(_decide(case, params or BASEP, LIVE_RULES if rules is None else rules, live))


def plan_queue(params: Params | None = None, rules: Sequence[Rule] | None = None, *, queue: Sequence[Case] | None = None) -> Plan:
    """planQueue(p, rs): every open return of the queue, one return per named order, refurbishment within the slots."""
    live = _live(queue)
    return copy.deepcopy(_plan_queue(params or BASEP, LIVE_RULES if rules is None else rules, live, _held_orders(live)))


def simulate(
    base_rules: Sequence[Rule],
    cand_rules: Sequence[Rule],
    params: Params | None = None,
    *,
    cases: Sequence[Case] | None = None,
    queue: Sequence[Case] | None = None,
) -> dict[str, Any]:
    """fSim for the equip template (2408-2410): the open cases decided under both rule sets; the cases whose best path
    changes (`flips`) and the change in total net (`dv`). `cases` defaults to the sample queue."""
    p = params or BASEP
    live = _live(queue)
    xs = cases if cases is not None else sample_queue()
    flips = []
    dv = 0.0
    for c in xs:
        b = _decide(c, p, base_rules, live)["best"]
        s = _decide(c, p, cand_rules, live)["best"]
        if b["k"] != s["k"]:
            flips.append({"id": c["id"], "from": b["k"], "to": s["k"], "from_net": b["net"], "to_net": s["net"]})
        dv = dv + s["net"] - b["net"]
    return {"kind": "equip", "n": len(xs), "flips": flips, "dv": dv}
