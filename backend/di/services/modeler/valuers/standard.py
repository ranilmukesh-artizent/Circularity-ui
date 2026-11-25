"""The standard valuer (plan 9, P9-1.9; registry entry I-21: `VALUERS["standard"]`). It prices every route of a pack from
the pack's own value lines, so a new pack needs no engine code (story X-01; B section 7.4).

The pack's `valuer.params` (validated when the pack is parsed, `pack.check_standard`) holds:
- `lines`: `{route, type: "v" | "c" | "h", label, basis, amount, when?: [Cond], kind?}`. `amount` is the grammar of
  `amount.py`; `when` conditions are the gates' (`fact`, `op`, `value`) and a line whose conditions fail is left out.
- `requires`: `{route, requires: [Cond], why}`. A route whose requirement is false is not ok, with `why`.
- `tables` and `params`: the lookups and numbers the amounts read.

`value_routes(case, pack, as_of)` is the plug-in `decide_case` calls: one `PathValue` per pack route, in the pack's order.
`net = sum(v) - sum(c) - sum(h)`. A route that cannot be valued (no lines, or a case field a line needs is missing) is not
ok and says why; the fields it lacks are in `misses`. `decide(case, pack, rules)` is the tool fleet's `Decision` shape:
every route, the best by net among the ok ones, the shared business rules applied (`tool_fleet.apply_rules`).
CO2e comes from the pack's carbon set when it has factors for the route (information only, never changes a net).
Never does: read a session or the clock, write anything, or rank across the queue (that is `rank_routes`' job).
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from di.services.engine.jsmath import js_sum
from di.services.modeler.carbon import co2_avoided
from di.services.modeler.gates import Cond, _fact, _holds
from di.services.modeler.pack import Pack
from di.services.modeler.valuers import amount
from di.services.modeler.valuers.amount import AmountError
from di.services.modeler.valuers.tool_fleet import Decision, PathValue, Rule, ValueLine, apply_rules

DEFAULT_KIND = {"v": "sale", "c": "prep", "h": "fees"}  # a line's term kind when the pack names none


def _holds_all(conds: Sequence[Mapping[str, Any]], case: Mapping[str, Any], pack: Pack) -> bool:
    return all(_holds(c := Cond.model_validate(x), _fact(case, pack, c.fact)) for x in conds)


def _value(route: str, case: Mapping[str, Any], pack: Pack) -> PathValue:
    params = pack.valuer.params
    lines: list[ValueLine] = []
    misses: list[str] = []
    why = ""
    for i, ln in enumerate(params.get("lines") or []):
        if ln["route"] != route or not _holds_all(ln.get("when") or [], case, pack):
            continue
        try:
            amt = amount.evaluate(ln["amount"], case, pack, f"lines[{i}].amount")
        except AmountError as e:
            why = why or str(e)
            if e.field:
                misses.append(e.field)
            continue
        lines.append(
            {"type": ln["type"], "label": ln["label"], "basis": ln.get("basis", ""), "amt": amt,
             "kind": ln.get("kind") or DEFAULT_KIND[ln["type"]]}
        )  # fmt: skip
    total = {t: js_sum(x["amt"] for x in lines if x["type"] == t) for t in ("v", "c", "h")}
    if not why and not lines:
        why = f"The pack has no value lines for {route}"
    ok = not why
    for r in params.get("requires") or []:
        if ok and r["route"] == route and not _holds_all(r["requires"], case, pack):
            ok, why = False, r["why"]
    cv = co2_avoided(pack, case.get("cls"), route, float(case.get("qty") or 1), confirmed=False)
    return {
        "k": route, "ok": ok, "gross": total["v"], "cost": total["c"], "hold": total["h"],
        "net": total["v"] - total["c"] - total["h"], "why": why, "lines": lines, "dest": None, "misses": sorted(set(misses)),
        "co2": cv.kg if cv else None, "co2Prov": cv.prov() if cv else None,
    }  # fmt: skip


def value_routes(case: Mapping[str, Any], pack: Pack, _as_of: datetime | None = None) -> list[PathValue]:
    """The value of every route of the pack for the case (`_as_of` is for plug-ins that read evidence by time; unused here)."""
    return [_value(r.id, case, pack) for r in pack.routes]


def decide(case: Mapping[str, Any], pack: Pack, rules: Sequence[Rule]) -> Decision:
    """Every route valued, the rules applied, and the best ok route by net (a rule's preferred route first when it is ok;
    ties keep the pack's order). `best` is absent when no route is ok."""
    values = value_routes(case, pack)
    ap = apply_rules(dict(case), values, rules)
    ok = [v for v in values if v["ok"]]
    pref = next((v for v in ok if v["k"] == ap["pref"]), None) if ap["pref"] else None
    best = pref or max(ok, key=lambda v: v["net"], default=None)
    out: Decision = {"all": values, "rules": list(ap["ids"])}
    if best:
        out["best"] = best
    return out
