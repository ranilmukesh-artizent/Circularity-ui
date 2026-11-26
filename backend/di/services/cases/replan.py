"""A tool-fleet case's place in its org's queue plan, and planning the queue again when a return arrives (plan 9,
P9-1.4; registry entry I-5 through di.services.engine.queue).

    queue_plan(s, case) -> {holds, contested, lost, kinds} | None   what the Case page shows (screen field `plan`)
    on_opened(s, org_unit_id) -> [case ids]                         the job `case.replan {org_unit_id, template}`
    on_graded(s, case_id) -> bool                                   the job `case.reevaluate {case_id}` (P9-3.5)

- `holds`: the named order the plan gives this return, or None. `lost`: the orders this return wanted and the plan gave
  to another (`order`, `to` the winner's case id, `gain` what the winner gains from it). `contested`: the orders this
  return competes for. `kinds`: a short name for each of those orders ("lease renewal", "sales order" ...).
- An approved or executing case keeps its order: it holds what its recommendation names and loses nothing.
- `on_opened`: every open tool-fleet case of the org in stage `none` or `awaiting_approval` is valued again with the
  queue as it is now. A case whose recommended route changes gets a stage log row by `system`: "Re-planned: <old> ->
  <new>. <why>". Approved and executing cases are not touched, and no case changes stage.

Owns: the two functions. Never does: approve, or move a case to another stage; a person still decides.
"""

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.cases import intake, regrade, store

REPLANNED = ("none", "awaiting_approval")
_KIND = {"so": "sales order", "bid": "bid", "proj": "pool request"}


def _kind_of(item: Mapping[str, Any]) -> str:
    if item.get("kind") == "lease":
        return "lease renewal" if item.get("renew") else "fleet order"
    return _KIND.get(str(item.get("kind")), "order")


def _items(dem: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [*dem["lease"], *dem["so"], *dem.get("bid", []), *([dem["proj"]] if dem.get("proj") else [])]


def _kinds(q: intake.ToolQueue, orders: set[str]) -> dict[str, str]:
    """A short name for each order id, from the named orders of the queue's cases and the named demand."""
    out: dict[str, str] = {}
    for c in q.cases:
        for i in [*_items(c["dem"]), *_items(q.demand[c["id"]])]:
            if i["id"] in orders:
                out[i["id"]] = _kind_of(i)
    return out


def queue_plan(s: Session, case: Mapping[str, Any]) -> dict[str, Any] | None:
    """The case's place in the plan of its org's open queue (module docstring); None for a case of another template."""
    if case.get("template") != "tool_fleet" or intake.is_refresh(case):  # a contract refresh is in no queue (P9-5.1)
        return None
    if case.get("cls") == "BAT":  # a battery pack has its own valuer and is in no queue (P9-3.19)
        return None
    me = case["id"]
    if case["stage"] in ("approved", "executing"):
        rec = case.get("chosen") or case.get("recommendation") or {}  # an override takes the chosen route's order
        held = (rec.get("dest") or {}).get("id")
        return {"holds": held, "contested": [], "lost": [], "kinds": {}}
    q = intake.tool_queue(s, case["owner"], intake.valuer_input(case, "tool_fleet"))
    plan = intake.tool_plan(q, intake.case_rules(s, case))
    holds = next((o for o, who in sorted(plan["own"].items()) if who == me), None)
    lost = [{"order": o, "to": w["to"], "gain": w["gain"]} for o, w in sorted(plan["why"].items()) if me in w["others"]]
    contested = sorted(o for o, w in plan["why"].items() if me == w["to"] or me in w["others"])
    return {
        "holds": holds,
        "contested": contested,
        "lost": lost,
        "kinds": _kinds(q, set(contested) | ({holds} if holds else set())),
    }


def _why(s: Session, c: store.Case) -> str:
    plan = queue_plan(s, c)
    if plan and plan["lost"]:
        x = plan["lost"][0]
        return f"{x['order']} goes to {x['to']}, where it adds more across the queue."
    rec = c.get("recommendation")
    return str(rec["why"]) if rec and rec.get("why") else "The queue changed."


def on_opened(s: Session, org_unit_id: str) -> list[str]:
    """Value the org's other open tool-fleet cases again (module docstring); the ids of the cases that moved."""
    ids = s.execute(
        text(
            "SELECT id FROM case_record WHERE owner = :o AND stage = ANY(:st) AND data ->> 'template' = 'tool_fleet' ORDER BY id"
        ),
        {"o": org_unit_id, "st": list(REPLANNED)},
    ).scalars()
    moved = []
    for cid in list(ids):
        c = store.get(s, cid, for_update=True)
        if c is None or c["stage"] not in REPLANNED:
            continue
        old = c.get("recommendation")
        intake.revalue(s, c)
        store.save(s, c)
        new = c.get("recommendation")
        if (old or {}).get("id") != (new or {}).get("id"):
            was, now = (old or {}).get("plan", "no route"), (new or {}).get("plan", "no route")
            reason = f"Re-planned: {was} → {now}. {_why(s, c)}"
            p = {"c": cid, "st": c["stage"], "r": reason, "a": "system"}
            s.execute(
                text("INSERT INTO case_stage_log (case_id, from_stage, to_stage, reason, actor) VALUES (:c, :st, :st, :r, :a)"), p
            )
            s.execute(
                text("INSERT INTO domain_event (type, case_id, payload) VALUES ('case.replanned', :c, CAST(:p AS jsonb))"),
                {"c": cid, "p": json.dumps({"case_id": cid, "from": (old or {}).get("id"), "to": (new or {}).get("id")})},
            )
            moved.append(cid)
    return moved


def on_graded(s: Session, case_id: str) -> bool:
    """A workbench grade landed for the case's serial (canonical.store.apply, P9-3.5): the open case is valued again with
    the grade (di.services.cases.regrade) and, when its recommendation changed, planned with the queue. Only a case in
    stage `none` or `awaiting_approval` is touched, and no stage changes. True when the case was valued again."""
    c = store.get(s, case_id, for_update=True)
    if c is None or c.get("template") != "tool_fleet" or c["stage"] not in REPLANNED:
        return False
    old = c.get("recommendation")
    intake.revalue(s, c)
    store.save(s, c)
    ev = regrade.workbench_evidence(s, c.get("serial") or c.get("assetId"))["workbench_grade"]
    ref = ev.value.get("inspection_ref") if ev else None
    reason = f"Workbench grade {c['grade']}" + (f" from {ref}" if ref else "")
    was, now = (old or {}).get("plan", "no route"), (c.get("recommendation") or {}).get("plan", "no route")
    reason += f" is in: {was} -> {now}." if was != now else " is in; the recommendation stands."
    s.execute(
        text("INSERT INTO case_stage_log (case_id, from_stage, to_stage, reason, actor) VALUES (:c, :st, :st, :r, :a)"),
        {"c": case_id, "st": c["stage"], "r": reason, "a": "system"},
    )
    return True
