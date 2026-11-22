"""One case as the case, product and orchestration pages and the reads read it (ported from the demo): the case
record (CASE_BY_ID, with the pool's result), the lease and return stages (afLease, exInbound), the instruction payload
(instrPayload, stepsOf, defaultSpend), the preparation cost (asPrepCost), the recertification, the pool a case belongs
to, the case's journal (afCaseJournal) and times as ISO strings (with_times)."""

import math
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy
from di.repositories.common import (
    AS_OF,
    CLASSES,
    FAC_LOC,
    SITE_LOC,
    TENANT_SITES,
    Case,
    add_days,
    as_hex,
    case_demand,
    case_rul,
    demand_order,
    hash_id,
    iso,
    ms,
)
from di.repositories.common import EX_FX as FX
from di.repositories.provenance import ordered_spec
from di.services.cases import store
from di.services.engine.jsmath import js_round, js_sum
from di.services.engine.pool import solve_pool
from di.services.execution import (
    ex_kg,
    ex_move,
    ex_plan,
    lane_cost,
    steps_for,
)

BACKEND_ONLY = ("hazardousMaterial",)  # engine inputs the demo's case record does not carry


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


def steps_of(c: Case) -> list[dict]:
    """The demo's stepsOf: the instruction's steps, or the steps the route would send (by route id)."""
    if c.get("exec"):
        return c["exec"]["steps"]
    r = c.get("chosen") or c.get("recommendation") or {"id": "resale"}
    return steps_for({"id": r["id"]}, -1)


def default_spend(c: Case, r: dict) -> int:  # noqa: ARG001 - the demo's defaultSpend(c, r)
    """The demo's defaultSpend: the preparation cost, as the spend the approval authorises."""
    return js_round(-js_sum(t["amt"] for t in r["terms"] if t["kind"] == "prep" and t["amt"] < 0))


def prep_cost(c: Case) -> float:
    """The demo's asPrepCost."""
    r = c.get("chosen") or c.get("recommendation")
    return -js_sum(t["amt"] for t in r["terms"] if t["kind"] == "prep" and t["amt"] < 0) if r else 0


def instr_payload(c: Case) -> dict:
    """The demo's instrPayload: the instruction approval sends (times ISO)."""
    r: Any = c.get("chosen") or c.get("recommendation")  # an instruction is built for a decided case
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


# The demo's two pools: each is solved for its hero case, and its partner case shows the same result (POOLS, poolResult).
POOL_HOME = {"RT-1048": "RT-1048", "RT-1062": "RT-1048", "RT-1052": "RT-1052", "RT-1044": "RT-1052"}


def pool_of(session: Session, case_id: str) -> dict | None:
    """The pool a case belongs to, solved (the demo's solvePool, di.services.engine.pool)."""
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
