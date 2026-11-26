"""The live queue plan of an org's open tool returns (plan 9, P9-3.13, story TF-08; registry entry I-5).

    open_queue(s, org_unit_id) -> [valuer case]     every open tool-fleet return of the org, with its live named demand
    plan_of(s, org_unit_id) -> Plan                 the queue planned (a read, writes nothing)
    replan(s, org_unit_id) -> Plan                  the same, and every open case valued again with it
    refresh_actions(s, case) -> [ToolAction]        keep, swap or upgrade for each tool of a refresh case (P9-5.2)
    refresh_match(s, org_unit_id) -> {case: [row]}  the like-life unit of each swap of the org's open refresh cases (P9-5.3)

`open_queue` gives the valuer inputs of the org's tool-fleet cases that are not closed: the open ones (status new) and the
ones an approved or executing decision holds (status sent, which keep their order and their repair center slot), each
with its `dem` extended by the org's named demand of its class (the queue's tagged orders and the live renewals, sales
orders, bids, pool requests and repair orders of its sources). A case never competes with another org's returns.
`plan_of` runs the pack's planner (`engine.queue.planner_for`, the heuristic by default; the pack setting
`valuer.params["planner"]`) with `slots` the pack's repair center slots; the planner takes off the refurbishments in
progress (sent cases on the refurb path). `replan` also refreshes the stored routes and recommendation of every open case
whose result changed, with a journal row by `system` ("Re-planned: <old> -> <new>", di.services.cases.replan.on_opened).
The decision of a single case (`intake.tool_plan` over `intake.tool_queue`) is the same plan, so its result equals the plan's.

`refresh_match` (P9-5.3): the swaps of every open contract refresh of the org are matched together, so a unit is promised once.
First `like_life.match` over the refurbished stock (`unit_reservations.stock`, minus the units held). A swap left over joins
the returns queue as a named order of kind lease (id `<case>:<serial>`, needed by the contract's end, at the fee of its line):
the planner above gives each order to one return, so a return that is planned for a pool request or a renewal is not offered a
second time, and the swap it fills is the demand GR-02 asks of a refurbishment. Only a return with a workbench grade counts
(GR-C3). Matching proposes; reservations are written on approval (P9-5.5).

Owns: reading the queue and planning it. Never does: approve a case or move it to another stage, or call a language model.
"""

import calendar
import copy
from collections.abc import Mapping
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.repositories import market_tables as tables_repo
from di.repositories import plm, unit_reservations
from di.services.cases import intake, life_evidence, refresh_window, regrade
from di.services.cases import replan as replanner
from di.services.engine import like_life
from di.services.modeler.tables import JdmTable, ZenEvaluator
from di.services.modeler.valuers import contract_refresh, tool_fleet, tool_inputs
from di.services.modeler.valuers.tool_fleet import Plan

PACK, FLOW = (
    "tool_fleet",
    "service_desk",
)  # the pack and the flow whose market tables hold `refresh_tool_action` (as services.models.cost)

__all__ = ["Plan", "open_queue", "plan_of", "refresh_actions", "refresh_match", "replan"]


def _queue(s: Session, org_unit_id: str) -> tuple[intake.ToolQueue, list[dict[str, Any]]]:
    docs = intake.open_tool_cases(s, org_unit_id)
    return intake.queue_of(s, org_unit_id, [intake.tool_input(d) for d in docs]), docs


def open_queue(s: Session, org_unit_id: str) -> list[dict[str, Any]]:
    """The valuer cases of the org's open tool returns, with their live `dem` (module docstring)."""
    q, _ = _queue(s, org_unit_id)
    return [c | {"dem": tool_inputs.merge_demand(c["dem"], q.demand[c["id"]])} for c in q.cases]


def plan_of(s: Session, org_unit_id: str) -> Plan:
    """The org's open queue planned with the pack's planner; reads only."""
    q, docs = _queue(s, org_unit_id)
    rules = intake.case_rules(s, docs[0]) if docs else []
    return intake.tool_plan(q, rules)


def replan(s: Session, org_unit_id: str) -> Plan:
    """`plan_of`, and every open case of the org valued again with the queue as it is (journaled when it moved)."""
    plan = plan_of(s, org_unit_id)
    replanner.on_opened(s, org_unit_id)
    return plan


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def refresh_table(s: Session, c: Mapping[str, Any]) -> JdmTable | None:
    """The market's `refresh_tool_action` table in force today for the refresh case `c`; None without a market or a table."""
    market = (c.get("refresh") or {}).get("market")
    if not market:
        return None
    tables_repo.ensure_seeded(s, PACK)
    row = tables_repo.effective(s, c.get("owner"), PACK, FLOW, str(market), "refresh_tool_action", clock.now().date())
    return None if row is None else JdmTable.model_validate(row.body)


def refresh_actions(s: Session, c: Mapping[str, Any], table: JdmTable | None = None) -> list[contract_refresh.ToolAction]:
    """The action of each tool of the refresh case `c` (contract_refresh.tool_actions) with the life of its serial, PLM's end of
    parts and the market's table in force today (`table`: a copy of it with the what-if levers moved, P9-5.6); [] without a
    market, a term end, lines or the market's table."""
    r = c.get("refresh") or {}
    market, end, lines = r.get("market"), refresh_window.as_date(r.get("term_end")), list(r.get("lines") or [])
    if not market or end is None or not lines:
        return []
    org = c.get("owner")
    table = table or refresh_table(s, c)
    if table is None:
        return []
    life = {}
    for ln in lines:
        case = {"serial": ln["serial"], "owner": org, "cls": ln.get("cls")}
        res = tool_inputs.life_of(life_evidence.evidence(s, case), str(ln.get("cls") or ""), clock.now())
        if res is not None:
            life[str(ln["serial"])] = res
    eop = {k: plm.end_of_parts(s, org, k) for k in sorted({str(ln.get("cls")) for ln in lines if ln.get("cls")})}
    return contract_refresh.tool_actions(
        lines, life, eop, _add_months(end, int(r.get("term_months") or 0)), ZenEvaluator(), str(market), table,
    )  # fmt: skip


def _open_refresh(s: Session, org_unit_id: str) -> list[dict[str, Any]]:
    rows = s.execute(
        text("SELECT data FROM case_record WHERE owner = :o AND stage <> 'closed' AND data ->> 'flow' = :f ORDER BY id"),
        {"o": org_unit_id, "f": intake.REFRESH_FLOW},
    ).scalars()
    return sorted(rows, key=lambda d: str(d["id"]))


def _order(need: like_life.Need, line: Mapping[str, Any], days: int, customer: str) -> dict[str, Any]:
    """The swap as a named order of the returns queue (a renewal-shaped lease order, needed by the contract's end)."""
    return {"kind": "lease", "id": need.id, "renew": True, "who": customer or "Contract refresh", "site": tool_fleet.SITES[0],
            "need": days, "rate": float(line.get("fee") or 0), "term": 12, "what": f"Refresh swap {need.id}",
            "when": "contract refresh"}  # fmt: skip


def refresh_match(s: Session, org_unit_id: str, overlay: Mapping[str, JdmTable] | None = None) -> dict[str, list[dict[str, Any]]]:
    """The like-life unit of each swap of the org's open refresh cases, by case id (module docstring). A row is `{serial,
    need_id, cls, target, unit_id, rul, distance, source, why}`; `unit_id` is None when no unit fits and `why` says why.
    `overlay` (case id -> a copy of its table with the what-if levers moved, P9-5.6) changes what that case swaps; reads only."""
    cases = _open_refresh(s, org_unit_id)
    needs: list[like_life.Need] = []
    meta: dict[str, dict[str, Any]] = {}
    for c in cases:
        acts = refresh_actions(s, c, (overlay or {}).get(str(c["id"])))
        r = c.get("refresh") or {}
        lines = {str(ln["serial"]): ln for ln in r.get("lines") or []}
        end = refresh_window.as_date(r.get("term_end"))
        days = max(0, (end - clock.now().date()).days) if end else 0
        for n in contract_refresh.needs(c["id"], acts):
            serial = n.id.split(":", 1)[1]
            needs.append(n)
            meta[n.id] = {"serial": serial, "line": lines.get(serial, {}), "days": days, "customer": r.get("customer") or ""}
    units = [like_life.Unit(u["id"], u["cls"], u["rul"], "stock") for u in unit_reservations.stock(s)]
    res = like_life.match(needs, units, unit_reservations.held(s, org_unit_id))
    assign, why = dict(res.assign), dict(res.why)
    ruls = {u.id: u.rul for u in units}
    src = dict.fromkeys(assign, "stock")
    left = [n for n in needs if n.id not in assign]
    if left:
        docs = intake.open_tool_cases(s, org_unit_id)
        q = intake.queue_of(s, org_unit_id, [intake.tool_input(d) for d in docs]) if docs else None
        if q is not None:
            demand = copy.deepcopy(q.demand)
            for c in q.cases:
                orders = [
                    _order(n, meta[n.id]["line"], meta[n.id]["days"], meta[n.id]["customer"]) for n in left if n.cls == c["cls"]
                ]
                demand[c["id"]] = tool_inputs.merge_demand(demand[c["id"]], {"lease": orders})
            plan = intake.tool_plan(intake.ToolQueue(q.cases, demand), intake.case_rules(s, docs[0]))
            fills: dict[str, str] = {}  # named order id -> the return the plan gives it to
            for cid, d in plan["res"].items():
                dest = d["best"].get("dest")
                if dest:
                    fills[str(dest["id"])] = cid
            byid = {c["id"]: c for c in q.cases}
            for n in left:
                ret = fills.get(n.id)
                if ret is None:
                    taken = sorted(o for o, cid in fills.items() if byid[cid]["cls"] == n.cls and o not in meta)
                    other = f"; {fills[taken[0]]} is planned for {taken[0]}" if taken else ""
                    why[n.id] = f"no {n.cls} return is planned for it{other}"
                    continue
                graded = regrade.workbench_evidence(s, byid[ret].get("serial") or byid[ret].get("assetId"))
                if graded[tool_inputs.WORKBENCH] is None:
                    why[n.id] = f"{ret} has no workbench grade yet"
                    continue
                b = plan["res"][ret]["best"]
                rul = min(90, byid[ret]["rul"] + tool_fleet.FIN["refurbLife"]) if b["k"] == "refurb" else byid[ret]["rul"]
                assign[n.id], ruls[ret], src[n.id] = ret, rul, "return"
                why.pop(n.id, None)
    out: dict[str, list[dict[str, Any]]] = {c["id"]: [] for c in cases}
    for n in needs:
        u = assign.get(n.id)
        out[n.case_id].append(
            {"serial": meta[n.id]["serial"], "need_id": n.id, "cls": n.cls, "target": n.target, "unit_id": u,
             "rul": ruls.get(u) if u else None, "distance": abs(ruls[u] - n.target) if u else None,
             "source": src.get(n.id) if u else None, "why": None if u else why.get(n.id, "no like-life unit")}
        )  # fmt: skip
    return out
