"""The execution plan for display, the packet and the payload (the demo's exPlan, N2/N4/N5), the what-if guidance
(exWhatIf, N3/K3), the delivery sentence (exDelivered, N6), the order the value is committed against (valueOrder) and
the note an acknowledgement carries (ackNote).

Routes are compared by plan name: the demo compares objects (`c.chosen === r`), and a stored case keeps copies.
"""

from di.repositories.common import (
    AS_OF,
    Case,
    add_days,
    case_demand,
    ex_app,
    ex_clock,
    ex_lim,
    ex_ts,
    fmt_dy,
    money,
    step_owner,
    ti_conf,
)
from di.services.execution.lanes import LOCS, RATE_CARD, loc_name
from di.services.execution.move import ex_move
from di.services.execution.prep import ex_prep_parts
from di.services.execution.steps import ACK_NOTE, EX_STEP, ex_doc_num, ex_doc_ref, ho_kind, steps_for
from di.services.execution.util import js_str


def _same(a: dict | None, b: dict | None) -> bool:
    return bool(a and b and a["plan"] == b["plan"])


def _lim(d: dict) -> str:
    """The demo's exLim, with no limit read as "on delivery"."""
    return "on delivery" if d["lim"] is None else ex_lim(d["lim"])


def ex_plan(c: Case, r: dict | None = None, now: int = AS_OF) -> list[dict]:
    """The demo's exPlan: one row per step, with the action, the documents, the owner and the time limit."""
    r = r or c.get("chosen") or c.get("recommendation")
    if not r:
        return []
    x = c.get("exec")
    st = x["steps"] if x and _same(c.get("chosen") or c.get("recommendation"), r) else steps_for(r, -1, c.get("template"))
    M, mv, P = case_demand(c), ex_move(c, r), ex_prep_parts(c, r)
    rows = []
    for i, s in enumerate(st):
        k, d = s["k"], EX_STEP.get(s["k"]) or {}
        ref = s["ack"]["ref"] if s.get("ack") else ex_doc_ref(c, s)
        act, docs, why = f"{s['label']}: {r['plan']}", [ref], d.get("why") or ""
        if k == "order" and M and M.get("order"):
            act = (
                f"Allocate {c['assetId']} to {M['order']} line {M['line']} for {c['owner']} at {loc_name(M['shipTo'])}; "
                f"cancel planned purchase {M['avoidedPo']}"
            )
            docs = [f"{ref} line {M['line']}", f"{M['avoidedPo']} cancelled"]
        elif k in ("repair", "teardown") and P:
            parts = f"{len(P['parts'])} parts, " if P["parts"] else ""
            ops = ", ".join(o["name"].lower() for o in P["ops"])
            verb = "Refurbish" if k == "repair" else "Tear down"
            act = f"{verb} at RC-HSR-01 Hosur: {parts}{js_str(P['labH'])} labour hours, {ops}"
        elif k in ("transport", "ship") and mv:
            n = len(mv["legs"])
            act = (
                f"{n} leg{'s' if n > 1 else ''} with {RATE_CARD['carrier']}: {' → '.join(mv['stops'])} · "
                f"first ETD {ex_ts(mv['legs'][0]['etd'])}"
            )
            why += f"; {RATE_CARD['carrier']} holds the {RATE_CARD['id']} lanes (K15, assumed)"
        elif k == "move" and mv:
            L0 = LOCS.get(mv["src"])
            stg = mv["stage"]
            via = f" → {stg['code']} bay {LOCS[stg['code']]['bay']}" if stg and stg["code"] else ""
            act = f"{mv['src']} bin {L0.get('bin') if L0 else '—'} → RC-HSR-01{via} → {mv['to']}"
            docs = [ref, f"OBD-{ex_doc_num(c, 'move') + 1}"]
        elif k == "pod" and M and M.get("order"):
            eta = f" · ETA {ex_ts(mv['eta'])}" if mv and mv["eta"] else ""
            act = f"Proof of delivery at {mv['to'] if mv else M['shipTo']} against {M['order']} line {M['line']}{eta}"
        elif k == "finance":
            act = f"Post actual parts, labour, machine and freight costs against DI-2026-{c['id'][3:]}"
        rows.append({
            "n": i + 1, "k": k, "label": s["label"], "sys": s["sys"], "app": ex_app(s), "act": act, "docs": docs,
            "planned": not s.get("ack"), "owner": step_owner(c, s), "lim": _lim(d) if d else "—", "state": s["state"],
            "clock": ex_clock(c, s, now), "why": why,
        })  # fmt: skip
    return rows


def ex_what_if(c: Case, r: dict | None = None) -> list[dict]:
    """The demo's exWhatIf: only the time limit is enforced; the rest is guidance."""
    r = r or c.get("chosen") or c.get("recommendation")
    if not r:
        return []
    M = case_demand(c)
    others = sorted((x for x in c["routes"] if not x["excluded"] and not _same(x, r)), key=lambda x: -x["net"])
    nx = others[0] if others else None
    cf = ti_conf(c, r)
    return [
        {
            "k": "limit", "t": "A step passes its time limit", "on": True,
            "d": "The step escalates to the Approver, then to Admin, with the reason and a log line in the audit trail.",
        },
        {
            "k": "conf", "t": "Confidence is low", "on": False,
            "d": "It is low now: compare the alternatives before approving."
            if cf == "Low"
            else f"Compare the alternatives first. Confidence is {cf.lower()} now.",
        },
        {
            "k": "expiry", "t": "Not approved by " + fmt_dy(add_days(AS_OF, 7)), "on": False,
            "d": "The decision is re-evaluated on fresh evidence; nothing is sent on a stale decision.",
        },
        {
            "k": "cancel", "on": False,
            "t": f"Order {M['order']} line {M['line']} is cancelled" if M and M.get("order") else "The demand is cancelled",
            "d": f"Next eligible route: {nx['plan']} at {money(nx['net'])}."
            if nx
            else "No other eligible route; the case goes back to the Planner.",
        },
        {
            "k": "gate", "t": "A gate fails after approval", "on": False,
            "d": "The existing exclusion applies: the route is withheld with the failing gate and the case returns to the "
            "Planner.",
        },
    ]  # fmt: skip


def ex_delivered(c: Case) -> str:
    """The demo's exDelivered: for a redeployment against an order line, where and when it is delivered."""
    r = c.get("chosen") or c.get("recommendation")
    M = case_demand(c)
    m = ex_move(c, r) if r else None
    if not r or r.get("id") != "redeploy" or not M or not M.get("order") or not m:
        return ""
    out = (
        f"delivered to {loc_name(m['to'])} for {c['owner']} against {M['order']} line {M['line']}, {' → '.join(m['stops'])}, "
        f"ETD {ex_ts(m['legs'][0]['etd'])}, ETA {ex_ts(m['eta'])}"
    )
    if m["slack"] is not None:
        out += f" ({abs(m['slack'])} days late)" if m["slack"] < 0 else f" ({m['slack']} days before the need-by date)"
    return out


def ack_note(s: dict, c: Case | None) -> str:
    """The demo's ackNote: what the system reports with its acknowledgement; delivery and finance carry the delivery."""
    d = EX_STEP.get(s.get("k", ""))
    if c and s.get("k") in ("pod", "finance"):
        t = ex_delivered(c)
        if t:
            return ("proof of delivery signed; " if s["k"] == "pod" else EX_STEP["finance"]["note"] + "; ") + t
    return d["note"] if d else ACK_NOTE.get(s["label"], "")


def value_order(c: Case) -> dict | None:
    """The demo's valueOrder: the enterprise order the value is committed against (a returned SO, lease or WO), else
    the matched sales order of a redeployment."""
    st = c["exec"]["steps"] if c.get("exec") else []
    r = c.get("chosen") or c.get("recommendation")
    M = case_demand(c)
    for k in ("SO", "LS", "WO"):
        for y in st:
            if y.get("ack") and y["ack"]["ref"].startswith(k + "-"):
                return {"ref": y["ack"]["ref"], "kind": ho_kind(y)[1], "sys": y["ack"]["by"], "ack": True}
    if r and r.get("id") == "redeploy" and M and M.get("order"):
        return {"ref": M["order"], "kind": "Sales order", "sys": "ERP", "ack": False}
    return None
