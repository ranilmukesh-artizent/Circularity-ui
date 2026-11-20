"""Shared pieces of the read actions (B11), ported from the demo (index.html) so the reads give its answers exactly.

- formatting: `money`, `inr`, `fmt_n`, `fmt_d`, `fmt_dy`, `iso`, and JavaScript's date arithmetic in epoch milliseconds
- the case as a list row: `case_row` (afCaseRow), `priority` (afPriority), `stage_label` (afStageLabel), `rec` (afRec)
- the ten-stage case run: `stage_states` (afStageStates), `run` (afRun), `run_of` (afRunOf), `next_step` (afNextStep)
- scope: `can` (can); what an account may see (visCases, visRows) is in di.reads.context
- facts derived from a case: `case_rul` (caseRul), `case_demand` (caseDemand), `ti_m` (tiM), `base_rows` (afBaseRows)

The demo's clock is pinned to its as-of time (`AS_OF`, from the golden world); `asOfNow()` and `new Date()` mean that.
"""

import math
import re
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text

from di import golden, policy, state
from di.actions.pipeline import CallContext
from di.engine.jsmath import js_round, js_sum
from di.engine.scenario import Assumptions, scenario_routes

Case = dict[str, Any]
DAY_MS = 86_400_000
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------- JavaScript dates, in epoch milliseconds
def ms(v: Any) -> int:
    """`new Date(v).getTime()` for an ISO string (date-only strings are UTC, as in JavaScript) or epoch ms."""
    if isinstance(v, int | float):
        return int(v)
    s = str(v)
    if len(s) == 10:
        s += "T00:00:00Z"
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return (d - _EPOCH) // timedelta(milliseconds=1)


def _dt(t: int) -> datetime:
    return _EPOCH + timedelta(milliseconds=t)


def iso(v: Any) -> str:
    """`new Date(v).toISOString()`."""
    t = ms(v)
    return _dt(t).strftime("%Y-%m-%dT%H:%M:%S") + f".{t % 1000:03d}Z"


AS_OF = ms(golden.load("world")["as_of"])
# en-GB short months as Node's ICU writes them ("Sept", not "Sep")
_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"]


def add_days(v: Any, n: float) -> int:
    return ms(v) + int(n * DAY_MS)


def fmt_d(v: Any) -> str:
    """The demo's fmtD: "03 Oct"."""
    d = _dt(ms(v))
    return f"{d.day:02d} {_MON[d.month - 1]}"


def fmt_dy(v: Any) -> str:
    """The demo's fmtDY: "03 Oct 2026"."""
    d = _dt(ms(v))
    return f"{d.day:02d} {_MON[d.month - 1]} {d.year}"


def af_days(a: Any, b: Any = None) -> int:
    """The demo's afDays: whole days from a to b (default: as-of), never negative."""
    return max(0, js_round((ms(b if b is not None else AS_OF) - ms(a)) / DAY_MS))


# ---------------------------------------------------------------- numbers and text
def fmt_n(n: float) -> str:
    """The demo's fmtN, `Number(n).toLocaleString('en-US')`: grouped, at most three decimals."""
    s = f"{n:,.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def money(n: float) -> str:
    """The demo's money(): "$9,600", "−$1,200" (U+2212 minus)."""
    return ("−" if n < 0 else "") + "$" + f"{abs(js_round(n)):,}"


def _en_in(n: int) -> str:
    """Indian digit grouping ("12,34,567"), as toLocaleString('en-IN')."""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([head, *groups, tail]) if head else ",".join([*groups, tail])


def inr(n: float) -> str:
    """The demo's inr(): "₹3,600"."""
    return ("−" if n < 0 else "") + "₹" + _en_in(abs(js_round(n)))


def ex_num(n: float) -> str:
    """The demo's exNum."""
    return ("-" if js_round(n) < 0 else "") + _en_in(abs(js_round(n)))


def esc(s: Any) -> str:
    """The demo's esc(): HTML-escape (some read texts carry it)."""
    rep = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}
    return "".join(rep.get(ch, ch) for ch in ("" if s is None else str(s)))


def jg_lc(t: str) -> str:
    """The demo's jgLc: first letter lower case."""
    return t[:1].lower() + t[1:] if t else t


def hash_id(s: str) -> str:
    """The demo's hashId: 32-bit FNV-1a over UTF-16 code units (first unit of each code point), 8 upper-case hex."""
    h = 2166136261
    for ch in s:
        code = ord(ch)
        if code > 0xFFFF:  # `for (const ch of s) ch.charCodeAt(0)` sees the high surrogate only
            code = 0xD800 + ((code - 0x10000) >> 10)
        h = ((h ^ code) * 16777619) & 0xFFFFFFFF
    return f"{h:08X}"


def as_hex(c: Case, k: str) -> int:
    """The demo's asHex: a stable number derived from the case id."""
    return int(hash_id(c["id"] + k), 16)


def ex_h(c: Case, k: str) -> int:
    """The demo's exH."""
    return int(hash_id(c["id"] + "|ex|" + k), 16)


# ---------------------------------------------------------------- reference data the demo keeps in code
WORLD = golden.load("world")
CLASSES = WORLD["classes"]
# The source systems' starting state (the demo's SOURCES). Their freshness changes only when the demo's simulator
# ticks, which the backend does not run; the connector state in the database does not carry these fields yet.
SOURCES = {s["id"]: s for s in golden.load("sources")["sources"]}
# The demo's EQUIP: the first model listed per class names the class's product ("Voltara V4 motors" -> "... motor")
EQUIP_FIRST = {
    "motor": "Voltara V4 motors",
    "pump": "Halden HX axial pumps",
    "control": "Orbis Series 7 PLC",
    "drill": "Tessen TX tools",
    "batch": "Brava 36 V fleet",
    "it": "Corvid C14 laptops",
}
AF_STAGE = {
    "awaiting_approval": "Awaiting approval",
    "approved": "Approved · handing off",
    "executing": "Handed off",
    "reeval": "Re-evaluate",
    "closed": "Closed",
    "none": "Needs evidence",
}
AF_STAGES = [
    "Lease ends",
    "Return authorised",
    "Pickup and transit",
    "Received",
    "Inspect and grade",
    "Decide",
    "Approve",
    "Execute",
    "Outcome",
    "Reconcile and learn",
]
RUN_ST = {
    "done": "Completed",
    "running": "Running",
    "waiting": "Waiting for approval",
    "person": "Waiting for a person",
    "warning": "Warning",
    "failed": "Failed",
    "queued": "Queued",
    "skipped": "Skipped",
}
BASE_DAYS = {"redeploy": 21, "resale": 34, "intparts": 28, "relase": 45, "material": 17, "extparts": 32, "exit": 12}
EMB = {"motor": 420, "pump": 260, "control": 90, "drill": 24, "batch": 18, "it": 230}
CO2S = {"redeploy": 0.7, "resale": 0.55, "intparts": 0.3, "relase": 0.65, "material": 0.08, "extparts": 0.25, "exit": 0}
EX_NEED = {"RT-1048": "2026-10-17"}
EX_FX = 83.5
# facilities and customer sites (the demo's LOCS): code -> (site, lat, lon)
LOCS = {
    "WH-PNQ-01": (None, 18.76, 73.86),
    "WH-MAA-02": (None, 12.97, 79.95),
    "RC-HSR-01": (None, 12.74, 77.83),
    "LOC-PNQ-01": ("Site 1", 18.63, 73.80),
    "LOC-HSR-02": ("Site 2", 12.72, 77.81),
    "LOC-CHN-03": ("Site 3", 13.10, 80.16),
    "LOC-NSK-04": ("Site 4", 19.99, 73.79),
    "LOC-VTZ-05": ("Site 5", 17.69, 83.22),
    "LOC-CBE-06": ("Site 6", 11.02, 76.96),
    "LOC-STV-07": ("Site 7", 21.17, 72.83),
    "LOC-IDR-08": ("Site 8", 22.72, 75.86),
    "EXT-BOM": (None, 19.30, 73.06),
    "EXT-BLR": (None, 12.97, 77.59),
    "PTN-MAA": (None, 13.40, 80.11),
}
FAC_LOC = {"Warehouse 1": "WH-PNQ-01", "Warehouse 2": "WH-MAA-02", "Repair centre": "RC-HSR-01"}
SITE_LOC = {site: code for code, (site, _, _) in LOCS.items() if site}
TENANT_SITES = {
    "Customer A": ["Site 1", "Site 3", "Site 2", "Site 4"],
    "Customer B": ["Site 6", "Site 7"],
    "Customer C": ["Site 8", "Site 5"],
}
LANE_KM = {"WH-PNQ-01|RC-HSR-01": 930, "RC-HSR-01|WH-MAA-02": 260, "WH-MAA-02|LOC-CHN-03": 34, "WH-PNQ-01|LOC-CHN-03": 1180}
RATE_CARD = {"perKm": 20, "load": 1200, "min": 3600}


# ---------------------------------------------------------------- scope
def account(ctx: CallContext) -> policy.Account | None:
    return None if ctx.actor.system else ctx.actor.account


def can(ctx: CallContext, perm: str) -> bool:
    """The demo's can() for the signed-in account (no account: nothing), including its later rule that a Planner may
    approve once Admin raises the Planner approval limit above $0 (policy.can)."""
    return policy.can(account(ctx), perm, ctx.actor.ctx)


def decisions_delegated(ctx: CallContext) -> bool:
    """The demo's S.deleg.decisions: Admin has delegated approving decisions to the Approver."""
    return ctx.actor.ctx.delegations.get("decisions", True)


# ---------------------------------------------------------------- facts derived from a case
def as_model(c: Case) -> str:
    """The demo's asModel: the product model of the case's class."""
    m = EQUIP_FIRST.get(c["cls"])
    return re.sub(r"s$", "", m) if m else c["product"]


def stage_label(c: Case) -> str:
    """The demo's afStageLabel."""
    if c["stage"] == "none":
        return "Needs evidence" if c.get("blocked") else "Needs review"
    stage: str = c["stage"]
    return AF_STAGE.get(stage, stage)


def case_rul(c: Case) -> dict | None:
    """The demo's caseRul: the estimated remaining life as a range, and the certified period (one firm figure)."""
    m = re.match(r"(\d+)\s*months", c.get("engLife") or "")
    if not m:
        return None
    est = int(m[1])
    wide = c.get("grade") == "C"
    lo = js_round(est * (0.75 if wide else 0.83))
    hi = max(est, js_round(est * (1.2 if wide else 1.11)))
    cert = (lo // 12) * 12 if lo >= 12 else max(6, (lo // 6) * 6)
    return {
        "estMonths": est,
        "estLow": min(lo, est),
        "estHigh": hi,
        "certMonths": min(cert, est),
        "basis": "Certified in QMS by the EAM diagnostic and quality process after "
        + (f"grade {c['grade']} inspection" if c.get("grade") else "inspection")
        + " and any part replacement",
        "certRef": f"QMS-{2400 + as_hex(c, 'qms') % 600}",
    }


def demand_order(c: Case) -> str | None:
    """The demo's demandOrder: the pending sales order matched to a case with internal demand."""
    d = c.get("demand") or {}
    if c["id"] == "RT-1048":
        return "SO-48102"
    return f"SO-{48000 + (int(c['id'][3:]) * 7) % 997}" if d.get("internal") else None


def case_demand(c: Case) -> dict | None:
    """The demo's caseDemand: the internal demand (order line, ship-to, need-by) or lease matched to a case."""
    d: Any = c.get("demand") or {}
    if not d.get("internal") and not d.get("lease"):
        return None
    n = int(c["id"][3:])
    r = case_rul(c)
    cert = r["certMonths"] if r else 24
    internal = bool(d.get("internal"))
    if c["id"] == "RT-1048":  # noqa: SIM108 - a nested conditional expression would read worse
        horizon = 24
    else:
        horizon = cert + 12 if as_hex(c, "hz") % 6 == 0 else min(cert, 24)
    need_by = None
    if internal:
        need_by = EX_NEED.get(c["id"]) or iso(AS_OF + (12 + ex_h(c, "nb") % 28) * DAY_MS)[:10]
    return {
        "order": demand_order(c),
        "site": d.get("site"),
        "lease": d.get("lease"),
        "confirmed": bool(d.get("confirmed")),
        "horizonMonths": horizon,
        "line": (10 if c["id"] == "RT-1048" else 10 * (1 + ex_h(c, "ln") % 4)) if internal else None,
        "shipTo": SITE_LOC.get(d.get("site")) if internal else None,
        "needBy": need_by,
        "avoidedPo": f"PO-{48000 + n}" if internal else None,
        "oms": "IBM Sterling OMS",
    }


def ti_m(c: Case, r: dict, sn: float) -> dict:
    """The demo's tiM: a route's turnaround days, confidence (prob, %) and carbon saved, for ranking and tie-breaks."""
    gross = js_sum(t["amt"] for t in r["terms"] if t["amt"] > 0)
    cost = js_sum(t["amt"] for t in r["terms"] if t["amt"] < 0)
    m = re.match(r"(\d+)\s*months", c.get("engLife") or "")
    base = (BASE_DAYS.get(r["id"]) or 25) * (1.25 if r.get("variant") == "refurb" else 1)
    days = max(3, js_round(base * (0.8 + as_hex(c, "d" + r["plan"]) % 35 / 100)))
    spread = abs((r["p90"] - r["p10"]) / 2 / max(1, abs(r["net"]))) * 60
    prob = js_round(max(55, min(98, 100 - spread)))
    life = f"{int(m[1]) / 12:.1f} yrs" if r["id"] in ("redeploy", "resale", "relase") and m else "—"
    co2 = js_round((EMB.get(c["cls"]) or 0) * c["qty"] * (CO2S.get(r["id"]) or 0))
    return {"gross": gross, "cost": cost, "net": sn, "days": days, "prob": prob, "life": life, "co2": co2}


def ti_conf(c: Case, r: dict) -> str:
    """The demo's tiConf."""
    p = ti_m(c, r, r["net"])["prob"]
    return "High" if p >= 85 else "Medium" if p >= 70 else "Low"


def base_rows(c: Case) -> list[dict]:
    """The demo's afBaseRows: the eligible routes ranked under the base assumptions (tiRows' fields; the weighted
    fit score is left out: it depends on the Workbench's sliders and no read returns it)."""
    _, el = scenario_routes(c, Assumptions())
    return [{"r": x["r"], **ti_m(c, x["r"], x["sn"])} for x in el]


def rec(c: Case) -> dict | None:
    """The demo's afRec: the chosen route (or the recommendation) in brief."""
    r = c.get("chosen") or c.get("recommendation")
    if not r:
        return None
    return {
        "plan": r["plan"],
        "route": r["id"],
        "net": r["net"],
        "p10": r["p10"],
        "p90": r["p90"],
        "conf": ti_conf(c, r),
        "demand": r.get("demandStatus"),
    }


def priority(c: Case) -> dict:
    """The demo's afPriority: why a case deserves attention first (value at stake, waiting time, missing evidence,
    a closing window), as a score and reasons."""
    r: Any = c.get("recommendation")
    why: list[str] = []
    s: float = 0
    age = af_days(c["received"])
    if r and c["stage"] == "awaiting_approval":
        s += r["net"]
        why.append(money(r["net"]) + " waiting for a decision")
    if c.get("blocked"):
        v = re.search(r"\$([\d,]+)–\$([\d,]+)", " ".join(c.get("facts") or []))
        s += int(v[1].replace(",", "")) if v else 500
        why.append("missing: " + jg_lc(re.sub(r"^Request ", "", c["blocked"]["action"])))
    if c["stage"] == "reeval":
        s += r["net"] * 0.6 if r else 300
        why.append("declined or changed: re-evaluate")
    if c.get("submitted"):
        why.append("submitted by " + c["submitted"]["by"])
    s *= 1 + min(age, 14) / 14
    if age >= 5:
        why.append(f"received {age} days ago")
    if r and r.get("demandStatus") == "confirmed" and c.get("timing") and "Day" in c["timing"]:
        s *= 1.15
        why.append("confirmed demand, " + c["timing"])
    return {"score": js_round(s), "why": why}


def case_row(c: Case) -> dict:
    """The demo's afCaseRow: one case as a list row."""
    ev = c.get("evidence") or []
    miss = [e for e in ev if e["state"] != "ready"]
    b = c.get("blocked")
    return {
        "id": c["id"],
        "asset": c["assetId"],
        "product": as_model(c),
        "cls": c["cls"],
        "qty": c["qty"],
        "owner": c["owner"],
        "location": c["location"],
        "stage": c["stage"],
        "stage_label": stage_label(c),
        "grade": c.get("grade"),
        "assessment": c.get("assessment"),
        "received": iso(c["received"])[:10],
        "evidence_ready": len(ev) - len(miss),
        "evidence_total": len(ev),
        "missing": [e["label"] for e in miss],
        "blocked": {"gate": b["gateName"], "reason": b["reason"], "action": b["action"], "owner": b["owner"]} if b else None,
        "recommendation": rec(c),
        "submitted": c["submitted"]["by"] if c.get("submitted") else None,
        "approval": c["approval"]["ref"] if c.get("approval") else None,
        "run": run_of(c),
    }


# ---------------------------------------------------------------- the case run: ten stages
def _journal_by(ctx: CallContext, case_id: str, actions: tuple[str, ...]) -> dict | None:
    """The last journal entry (not undone) of these actions on this case: who acted, which agent prepared it, when
    (the demo's afCaseJournal). The demo keeps the actor's label; the journal keeps the account id."""
    row = ctx.session.execute(
        text(
            "SELECT actor, preparer, at FROM action_journal WHERE input->>'case_id' = :c AND action = ANY(:a) AND NOT undone "
            "ORDER BY seq DESC LIMIT 1"
        ),
        {"c": case_id, "a": list(actions)},
    ).first()
    if row is None:
        return None
    a = policy.account(row.actor, ctx.actor.ctx)  # the label as the identity mapping has it now
    by = "Enterprise system adapter" if row.actor == "system" else (a.label if a else row.actor)
    return {"by": by, "prep": row.preparer, "at": iso(row.at.isoformat())}


def _states(c: Case) -> list[str]:
    """The states of stages 5-10 (stages 1-4 are always done once a case exists)."""
    st = (c.get("exec") or {}).get("steps") or []
    live = c["stage"] != "reeval"

    def ack(i: int) -> bool:
        return 0 <= i < len(st) and st[i]["state"] == "done"

    s5 = ("running" if c.get("requested") else "warning") if c.get("blocked") else "done"
    if s5 != "done":
        s6 = "queued"
    elif c["stage"] == "reeval":
        s6 = "warning"
    else:
        s6 = "done" if c.get("recommendation") else "failed" if c["routes"] else "queued"
    if s6 != "done":
        s7 = "queued"
    else:
        s7 = "done" if c.get("approval") and live else "waiting" if c["stage"] == "awaiting_approval" else "queued"
    if s7 != "done":  # noqa: SIM108 - a nested conditional expression would read worse
        s8 = "queued"
    else:
        s8 = "done" if st and all(s["state"] == "done" for s in st[:-1]) else "running"
    s9 = "queued" if s8 != "done" else "done" if c.get("outcome") else "person" if ack(len(st) - 1) else "running"
    s10 = "done" if c.get("outcome") else "queued"
    return ["done"] * 4 + [s5, s6, s7, s8, s9, s10]


def _lane_km(a: str, b: str) -> int:
    if a == b:
        return 0
    p = LANE_KM.get(f"{a}|{b}") or LANE_KM.get(f"{b}|{a}")
    if p:
        return p
    (_, alat, alon), (_, blat, blon) = LOCS[a], LOCS[b]
    r = math.pi / 180
    x = (blon - alon) * r * math.cos((alat + blat) / 2 * r)
    y = (blat - alat) * r
    return max(5, js_round(math.hypot(x, y) * 6371 * 1.25 / 5) * 5)


def ex_inbound(c: Case) -> dict:
    """The demo's exInbound and laneCost: the inbound lane from the customer site to the receiving facility.
    A return is always costed as a dedicated pickup: the demo prices it at max(150 kg, the unit's weight), and the
    dedicated rate applies from 150 kg."""
    ts = TENANT_SITES.get(c["owner"]) or TENANT_SITES["Customer A"]
    frm = SITE_LOC[ts[int(c["id"][3:]) % len(ts)]]
    to = FAC_LOC.get(c["location"]) or "WH-PNQ-01"
    km, rc = _lane_km(frm, to), RATE_CARD
    raw = km * rc["perKm"] + rc["load"]
    v = max(rc["min"], raw)
    calc = (
        f"{ex_num(km)} km · minimum charge {inr(rc['min'])}"
        if raw < rc["min"]
        else f"{ex_num(km)} km × ₹{rc['perKm']} + {inr(rc['load'])} loading"
    )
    return {"from": frm, "to": to, "km": km, "inr": v, "calc": calc}


def lease(c: Case) -> dict:
    """The demo's afLease: stages 1-3 (lease end, return authorisation, pickup), derived from the case id."""

    def h(k: str) -> int:
        return as_hex(c, "|af|" + k)

    rec_ms = ms(c["received"])
    end = add_days(rec_ms, -(16 + h("end") % 38))
    auth = add_days(end, 3 + h("ra") % 6)
    pk = add_days(auth, 2 + h("pk") % 5)
    eta = add_days(rec_ms, -(h("eta") % 2))
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
        "rma": f"RMA-{55800 + as_hex(c, 'rma') % 900}",
        "auth": auth,
        "fee": c["qty"] * (0 if h("fee") % 3 else 40 + h("f2") % 8 * 10),
        "repl": demand_order(c),
        "book": book,
        "pickup": pk,
        "eta": eta,
        "carrier": ["Northline 3PL", "Velo Freight", "Coastal Haulage"][h("cr") % 3],
        "freight": js_round(lane["inr"] / EX_FX),
        "lane": lane,
    }


def ex_delivered(c: Case) -> str:
    """The demo's exDelivered: the order line and delivery in one sentence, once the outcome is reported (di.execution;
    imported here, not at the top, because the execution package builds on this module)."""
    from di.execution.plan import ex_delivered as delivered

    return delivered(c)


def stage_states(c: Case, ctx: CallContext) -> list[dict]:
    """The demo's afStageStates: each of the ten stages with its state, result, who acted and when."""
    s5, s6, s7, s8, s9, s10 = _states(c)[4:]
    x = c.get("exec")
    st = (x or {}).get("steps") or []
    lz = lease(c)
    miss = [e for e in c.get("evidence") or [] if e["state"] != "ready"]
    deleg = decisions_delegated(ctx)
    last: Any = st[-1] if st else None
    last_acked = bool(last and last["state"] == "done")
    blocked: Any = c.get("blocked")
    r: Any = c.get("recommendation")

    def by(actions: tuple[str, ...]) -> dict | None:
        return _journal_by(ctx, c["id"], actions)

    fee = f", early-return fee {money(lz['fee'])}" if lz["fee"] else ", no fee"
    repl = f"; replacement order {lz['repl']}" if lz["repl"] else ""
    lane = lz["lane"]
    n_miss = len(miss)
    stages = [
        {
            "state": "done",
            "at": iso(lz["end"]),
            "by": "Lease management",
            "result": f"Lease {lz['lease']} ended {fmt_dy(lz['end'])}; customer intent: {lz['intent']}; {lz['usage']}",
        },
        {
            "state": "done",
            "at": iso(lz["auth"]),
            "by": "Lease management",
            "result": f"Return authorised {lz['rma']}{fee}{repl}; book value {money(lz['book'])}",
        },
        {
            "state": "done",
            "at": iso(lz["pickup"]),
            "by": lz["carrier"],
            "result": f"Picked up {fmt_d(lz['pickup'])} at {lane['from']} by {lz['carrier']}, arrived {fmt_d(lz['eta'])} at "
            f"{lane['to']}; freight {money(lz['freight'])} ({inr(lane['inr'])}, {lane['calc']})",
        },
        {
            "state": "done",
            "at": iso(c["received"]),
            "by": "WMS",
            "result": f"Received at {c['location']} on {fmt_d(c['received'])}; holding clock {af_days(c['received'])} days"
            + (f"; {n_miss} evidence item{'s' if n_miss > 1 else ''} missing" if n_miss else "; evidence complete"),
        },
    ]

    # stage 5: inspect and grade
    if s5 == "done":
        life = f" · life {c['engLife']}" if c.get("engLife") else ""
        res5 = f"Grade {c['grade']}{life}" if c.get("grade") else f"Assessed {c.get('assessment')}"
    elif c.get("requested"):
        res5 = f"{blocked['action']} requested ({c['requested']['ref']}); waiting for {blocked['owner']}"
    else:
        res5 = blocked["reason"]
    blocked5 = {"reason": blocked["reason"], "owner": blocked["owner"], "action": blocked["action"]} if s5 == "warning" else None
    by5 = by(("evidence.recordResult", "evidence.request")) or {"by": "Inspection" if c.get("grade") else ""}
    stages.append({"state": s5, "result": res5, "blocked": blocked5, **by5})

    # stage 6: decide
    if s6 == "done":
        res6 = f"{r['plan']} · {money(r['net'])} (P10–P90 {money(r['p10'])}–{money(r['p90'])})"
    elif s6 == "failed":
        res6 = "Every route failed a gate; human review needed"
    elif s6 == "warning":
        res6 = "Re-evaluate: " + (c.get("reevalReason") or "review triggered")
    else:
        res6 = "Waits for complete evidence"
    blocked6 = (
        {"reason": "No eligible route", "owner": "Engineering", "action": "Review the failed gates"}
        if s6 == "failed"
        else {"reason": c.get("reevalReason") or "Review triggered", "owner": "Planner", "action": "Re-evaluate"}
        if s6 == "warning"
        else None
    )
    stages.append(
        {
            "state": s6,
            "result": res6,
            "blocked": blocked6,
            **(by(("decision.prepare", "case.reevaluate", "decision.submit")) or {}),
        }
    )

    # stage 7: approve
    appr: Any = c.get("approval")
    if s7 == "done":
        res7 = ("Override approved" if c.get("override") else "Approved") + f" by {appr['by']} under {appr['ref']}"
    elif s7 == "waiting":
        res7 = (
            f"Submitted by {c['submitted']['by']}; waiting for {'an Approver' if deleg else 'Admin'}"
            if c.get("submitted")
            else "Waiting for the Planner to submit, then an Approver"
        )
    else:
        res7 = "After the decision"
    stages.append({
        "state": s7,
        "result": res7,
        "at": appr["at"] if appr else None,
        **({"by": appr["by"], "prep": appr.get("prep") or None} if appr else {}),
    })  # fmt: skip

    # stage 8: execute
    if x:
        parts = []
        for s in st[:-1]:
            tail = (
                f" {s['ack']['ref']}" if s.get("ack") else f" (with {s['sys'].split(' · ')[0]})" if s["state"] == "active" else ""
            )
            parts.append(s["label"] + tail)
        res8 = " · ".join(parts)
    else:
        res8 = "Instructions go out only after approval"
    prev = st[-2] if len(st) >= 2 else None
    stages.append({
        "state": s8,
        "result": res8,
        "at": prev["ack"]["at"] if prev and prev.get("ack") else None,
        "by": "Enterprise adapters" if x else "",
    })  # fmt: skip

    # stage 9: outcome
    out: Any = c.get("outcome")
    if out:
        res9 = f"Actual {money(out['net'])} confirmed by {out.get('by') or 'Finance'}"
    elif last_acked:
        dl = ex_delivered(c)
        res9 = f"Outcome reported ({last['ack']['ref']})" + (f"; {dl}" if dl else "") + "; waiting for Finance to confirm"
    else:
        res9 = "After execution"
    at9 = out["at"] if out else (last["ack"]["at"] if last and last.get("ack") else None)
    stages.append({"state": s9, "result": res9, "at": at9, "by": (out.get("by") or "Finance") if out else ""})

    # stage 10: reconcile and learn
    if out:
        rr = c.get("chosen") or r
        d = out["net"] - rr["net"]
        learned = len([ln for ln in out.get("lines") or [] if ln.get("model")])
        res10 = (
            f"Predicted {money(rr['net'])}, actual {money(out['net'])} ({'+' if d >= 0 else '−'}{money(abs(d))}); "
            f"{learned} learning records proposed"
        )
    else:
        res10 = "After the outcome is confirmed"
    stages.append({"state": s10, "result": res10, "at": out["at"] if out else None, "by": "Reconciler" if out else ""})
    return stages


def run_id(c: Case) -> str:
    """The demo's afRunId."""
    return "RUN-" + c["id"][3:]


def _current(states: list[str]) -> int:
    """The current stage number: the first stage not done (11 when all are)."""
    return next((i + 1 for i, s in enumerate(states) if s != "done"), 11)


def run(c: Case, ctx: CallContext) -> dict:
    """The demo's afRun: the case run through its ten stages."""
    stages = stage_states(c, ctx)
    cur = _current([s["state"] for s in stages])
    return {
        "id": run_id(c),
        "case_id": c["id"],
        "stage": cur,
        "stages": [{"n": i + 1, "t": AF_STAGES[i], "label": RUN_ST[s["state"]], **s} for i, s in enumerate(stages)],
        "done": cur == 11,
    }


def run_of(c: Case) -> dict:
    """The demo's afRunOf: where the run is, in brief (only the stage states are needed for it)."""
    states = _states(c)
    cur = _current(states)
    return {
        "id": run_id(c),
        "stage": min(cur, 10),
        "stage_label": "Complete" if cur > 10 else AF_STAGES[cur - 1],
        "done": cur == 11,
        "state": "done" if cur > 10 else states[cur - 1],
    }


def next_step(c: Case, ctx: CallContext) -> dict:
    """The demo's afNextStep: what Next does at the current stage, for this person: one action, a person-only step,
    or nothing."""
    states = _states(c)
    n = _current(states)
    if n > 10:
        return {"kind": "done", "n": n, "label": "Journey complete"}
    state, cid = states[n - 1], c["id"]

    def act(action: str, label: str) -> dict:
        return {"kind": "act", "n": n, "action": action, "input": {"case_id": cid}, "label": label}

    def wait(label: str, role: str | None = None) -> dict:
        return {"kind": "wait", "n": n, "label": label, **({"role": role} if role else {})}

    if n == 5:
        if state == "warning":
            if can(ctx, "request"):
                return act("evidence.request", c["blocked"]["action"])
            return wait(f"Waiting for {c['blocked']['owner']}; a Planner, Engineer or Warehouse Manager requests it", "Engineer")
        if can(ctx, "assess"):
            return act("evidence.recordResult", "Record the inspection result")
        return wait("Waiting for the Engineer to record the result", "Engineer")
    if n == 6:
        if state == "warning":
            return (
                act("case.reevaluate", f"Re-evaluate {cid}")
                if can(ctx, "reeval")
                else wait("Waiting for the Planner to re-evaluate", "Planner")
            )
        if state == "failed":
            label = "Every route failed a gate. Engineering and policy owners resolve failed gates; the agent cannot waive them."
            return {"kind": "blocked", "n": n, "label": label, "role": "Engineer"}
        return wait("Waiting for evidence")
    if n == 7:
        if can(ctx, "approve"):
            return {"kind": "approve", "n": n, "label": "Open the approval card"}
        if not c.get("submitted") and can(ctx, "submit"):
            return act("decision.submit", f"Submit {cid} for review")
        if c.get("submitted"):
            return wait("Waiting for " + ("an Approver" if decisions_delegated(ctx) else "Admin"), "Approver")
        return wait("Waiting for the Planner to submit it", "Planner")
    if n == 8 or (n == 9 and state == "running"):
        return (
            {"kind": "ack", "n": n, "label": "Check for the next acknowledgement"}
            if can(ctx, "execSim")
            else wait("Waiting for the enterprise systems")
        )
    if n == 9:
        return (
            act("outcome.confirm", "Confirm the outcome")
            if can(ctx, "confirm")
            else wait("Waiting for Finance to confirm the outcome", "Finance")
        )
    return wait("Waiting")


# ---------------------------------------------------------------- the demo's event log
# The demo's EVENTS (instructions, acknowledgements, escalations ...): the workspace collection "events" (di.state),
# seeded from the starting log. domain_event holds the backend's own events, in another shape. The demo's log is
# newest first (pushEvent unshifts); the collection keeps insertion order, so it is seeded oldest first.
STARTING_EVENTS: list[dict] = golden.load("events")["events"]
state.register("events", lambda: [(e["id"], e) for e in reversed(STARTING_EVENTS)])


def case_events(s, case_id: str) -> list[dict]:
    """The demo's EVENTS for one case, in log order (newest first)."""
    return [e for e in state.items(s, "events", newest_first=True) if e.get("caseId") == case_id]


# ---------------------------------------------------------------- more number formats
def to_fixed(x: float, digits: int) -> str:
    """JavaScript's `x.toFixed(digits)` for x >= 0: the exact binary value, an exact half rounded up (Python's format
    rounds exact halves to even)."""
    return str(Decimal(x).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def kfmt(n: float) -> str:
    """The demo's kfmt: "$2.43M", "$94k", "$261", "−$36k" (U+2212 minus)."""
    a, s = abs(n), "−" if n < 0 else ""
    if a >= 1e6:
        return f"{s}${to_fixed(a / 1e6, 2)}M"
    if a >= 1e3:
        return f"{s}${js_round(a / 1e3)}k"
    return f"{s}${js_round(a)}"


# ---------------------------------------------------------------- the demo's browser-memory state at the start
# These live only in the demo's browser memory and have no backend home yet. Each is the demo's starting value; the
# reads use it as is, since nothing on the server changes them yet. When their handlers move to the server (B12, B13)
# the state moves to the database and these become its seeds.

# S.notes: notifications sent from an exception to its owner (Actions on me), the workspace collection "notes"
# (di.state) seeded from these. One is open at the start.
STARTING_NOTES: list[dict] = [
    {
        "id": "NTF-101",
        "exId": "var:Delayed approval",
        "title": "Value at risk: delayed approval",
        "msg": "Decisions are close to their window. Please clear the oldest first.",
        "sev": "High",
        "to": "approver",
        "toLabel": "Approver",
        "from": "Executive",
        "at": iso(add_days(AS_OF, -0.2)),
        "status": "open",
        "ids": [],
    }
]
state.register("notes", lambda: [(n["id"], n) for n in STARTING_NOTES])


def notes(s) -> list[dict]:
    """The notifications, oldest first (the demo's S.notes)."""
    return state.items(s, "notes")


# S.reqs: tenant-access requests and MCP server proposals, decided by a delegated Approver or by Admin. The workspace
# collection "requests" (di.state), seeded from these; access.requestTenant and mcp.propose add to it and
# access.decideRequest decides. The demo's list is newest first (new requests are unshifted), so the collection is
# seeded oldest first and read newest first.
REQ_SCOPE = {"tenant": "tenantAccess", "mcp": "mcp"}
REQ_KIND = {"tenant": "Tenant access", "mcp": "MCP server proposal"}
STARTING_REQUESTS: list[dict] = [
    {
        "id": "REQ-304", "kind": "tenant", "status": "pending", "by": "Planner · Customer B", "byId": "planner-b",
        "at": iso(add_days(AS_OF, -0.4)), "tenant": "Customer A",
        "reason": "Customer A and Customer B share the Site 3 motor pool. I need to see Customer A returns to plan "
        "redeployment.",
    },
    {
        "id": "REQ-301", "kind": "mcp", "status": "pending", "by": "Developer", "byId": "developer",
        "at": iso(add_days(AS_OF, -1.2)),
        "server": {
            "name": "Fleet telematics MCP server", "owner": "TrackLine",
            "purpose": "Read operating hours and duty cycles so condition predictions can use measured duty instead of "
            "estimates.",
            "tools": ["telemetry.hours", "telemetry.duty_cycle"], "access": "read",
            "data": "Device telemetry for leased assets. No personal data.",
        },
    },
    {
        "id": "REQ-303", "kind": "mcp", "status": "declined", "by": "Developer", "byId": "developer",
        "at": iso(add_days(AS_OF, -6)), "decidedBy": "Admin", "decidedAt": iso(add_days(AS_OF, -5)),
        "note": "It books shipments without a human approval step. Resubmit with the approval gate.",
        "server": {
            "name": "Freight booking MCP server", "owner": "Oracle", "purpose": "Book and cancel transfers between sites.",
            "tools": ["shipment.book", "shipment.cancel"], "access": "write", "data": "Shipment orders between company sites.",
        },
    },
    {
        "id": "REQ-302", "kind": "mcp", "status": "approved", "by": "Developer", "byId": "developer",
        "at": iso(add_days(AS_OF, -9)), "decidedBy": "Approver", "decidedAt": iso(add_days(AS_OF, -8)),
        "note": "Read-only and limited to part prices.",
        "server": {
            "name": "Supplier catalogue MCP server", "owner": "PartsHub",
            "purpose": "Look up spare-part prices and lead times for repair and harvest routes.",
            "tools": ["part.search", "part.price"], "access": "read", "data": "Part numbers, prices and lead times.",
        },
    },
]  # fmt: skip
REQ_SEQ_START = 304  # the demo's REQ_SEQ: the next request is REQ-305
state.register("requests", lambda: [(r["id"], r) for r in reversed(STARTING_REQUESTS)])


def requests(s) -> list[dict]:
    """The requests, newest first (the demo's S.reqs)."""
    return state.items(s, "requests", newest_first=True)


# S.wf.list: the workflows whose last run failed. The demo seeds one run per published workflow and injects a
# validation failure into the Oracle Depot Repair ingest (wfSeed), so that is the only failed one at the start.
STARTING_FAILED_WORKFLOWS: list[str] = ["Ingest · Oracle Depot Repair"]

# CONFLICTS (source conflicts) and MAPPINGS (field mappings per source): the demo's starting values.
STARTING_CONFLICTS: list[dict] = golden.load("events")["conflicts"]
STARTING_MAPPINGS: dict[str, list] = golden.load("canonical")["mappings"]


def limit_for(a: policy.Account | None, pctx: policy.Context | None = None) -> float:
    """The demo's afLimitFor (policy.limit_for), with the stored limits when given the access context."""
    return policy.limit_for(a, pctx)


def inbox_requests(ctx: CallContext) -> list[dict]:
    """The demo's inboxReqs: the pending requests this account may decide."""
    return [r for r in requests(ctx.session) if r["status"] == "pending" and can(ctx, "approve." + REQ_SCOPE[r["kind"]])]


# ---------------------------------------------------------------- expected returns (the demo's EXPECTED)


# ---------------------------------------------------------------- hand-off clocks (the demo's EX_STEP limits)
# Per step kind: the working-hour limit before it escalates (None: no limit) and the step's owner.
EX_STEP: dict[str, tuple[int | None, str]] = {
    "order": (4, "Customer operations · order desk"),
    "repair": (4, "Repair centre lead (Engineer)"),
    "transport": (4, "Transport planner"),
    "move": (2, "Warehouse Manager"),
    "pod": (None, "Customer operations"),
    "finance": (16, "Finance"),
    "reserve": (2, "Warehouse Manager"),
    "sale": (8, "Sales operations"),
    "ship": (4, "Transport planner"),
    "fulfil": (None, "Customer operations"),
    "receipt": (16, "Finance"),
    "putaway": (2, "Warehouse Manager"),
    "lease": (16, "Lease administration"),
    "teardown": (4, "Repair centre lead (Engineer)"),
    "partsput": (2, "Warehouse Manager"),
    "partsxfer": (8, "Materials planner"),
    "resparts": (2, "Warehouse Manager"),
    "saletask": (8, "Sales operations"),
    "release": (2, "Warehouse Manager"),
    "collect": (24, "Exit partner"),
    "process": (40, "Exit partner"),
    "cert": (40, "Exit partner"),
    "custody": (40, "Exit partner"),
    "holdput": (2, "Warehouse Manager"),
    "holdrev": (16, "Planner"),
    "reeval": (16, "Planner"),
    "holdout": (16, "Finance"),
}
_HOUR_MS = 3_600_000


def work_add(t: int, h: float) -> int:
    """The demo's workAdd: epoch ms t plus h working hours (Mon–Sat 08:00–18:00, UTC)."""
    d, left = t, h * 60
    for _ in range(200):
        if left <= 0:
            break
        dt = _dt(d)
        m = dt.hour * 60 + dt.minute  # whole minutes, as getUTCHours()*60 + getUTCMinutes()
        midnight = ms(dt.strftime("%Y-%m-%d"))
        if dt.isoweekday() == 7 or m >= 1080:  # Sunday or after 18:00: next day 08:00
            d = midnight + DAY_MS + 8 * _HOUR_MS
        elif m < 480:  # before 08:00: 08:00 that day
            d = midnight + 8 * _HOUR_MS
        else:
            tk = min(left, 1080 - m)
            d += int(tk * 60_000)
            left -= tk
    return d


def ex_lim(lim: int) -> str:
    """The demo's exLim: "4 working h", "2 working days"."""
    return f"{fmt_n(lim / 8)} working days" if lim >= 16 else f"{lim} working h"


def ex_clock(c: Case, s: dict | None, now: int = AS_OF) -> dict | None:
    """The demo's exClock: an active step's due times, and how far it has escalated (1: to the Approver, 2: to
    Admin)."""
    d = EX_STEP.get(s["k"]) if s else None
    if not s or s["state"] != "active" or not d or d[0] is None or not c.get("exec"):
        return None
    t0 = ms(s.get("activeAt") or c["exec"]["approvedAt"])
    due = work_add(t0, d[0])
    due2 = work_add(due, d[0])
    level = 2 if now > due2 else 1 if now > due else 0
    to = "Admin" if level == 2 else "Approver" if level == 1 else None
    return {"t0": t0, "due": due, "due2": due2, "level": level, "to": to, "lim": ex_lim(d[0])}


def ex_hh(h: float) -> str:
    """The demo's exHH: hours as "16:00"."""
    return f"{math.floor(h):02d}:{js_round(h % 1 * 60):02d}"


def ex_ts(t: int) -> str:
    """The demo's exTs: "06 Oct 16:00"."""
    d = _dt(t)
    return f"{fmt_d(t)} {ex_hh(d.hour + d.minute / 60)}"


def ex_app(s: dict) -> str:
    """The demo's exApp: the vendor application behind a step's system ("MRO · Depot repair" -> Oracle Depot Repair)."""
    p = str(s.get("sys") or "").split(" · ")[0]
    src = next((x for x in SOURCES.values() if x.get("short") == p or x.get("name") == p), None)
    return src["vendor"] if src else p


def step_owner(c: Case, s: dict) -> str:
    """The demo's stepOwner: who owns a hand-off step, with the warehouse or repair centre where it applies."""
    d, k = EX_STEP.get(s["k"]), s["k"]
    if not d:
        return "Enterprise system"
    if k in ("move", "reserve", "release", "holdput", "partsput", "resparts"):
        wh = c["location"]
    elif k == "putaway":
        wh = "Warehouse 2" if c["location"] == "Repair centre" else c["location"]
    else:
        wh = None
    return d[1] + (f" · {wh}" if wh else " · RC-HSR-01" if k in ("repair", "teardown") else "")


def active_step(c: Case) -> dict | None:
    """The case's active hand-off step, if any."""
    x = c.get("exec")
    return next((s for s in x["steps"] if s["state"] == "active"), None) if x else None
