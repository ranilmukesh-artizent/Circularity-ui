"""The standard valuer (plan 9, P9-1.9; registry entry I-21: `VALUERS["standard"]`). It prices every route of a pack from
the pack's own value lines, so a new pack needs no engine code (story X-01; B section 7.4).

The pack's `valuer.params` (validated when the pack is parsed, `pack.check_standard`) holds:
- `lines`: `{route, type: "v" | "c" | "h", label, basis, amount, when?: [Cond], kind?}`. `amount` is the grammar of
  `amount.py`; `when` conditions are the gates' (`fact`, `op`, `value`) and a line whose conditions fail is left out.
- `requires`: `{route, requires: [Cond], why}`. A route whose requirement is false is not ok, with `why`.
- `routes` (P9-12.1): `{route, eligible_if?: Cond, ineligible_reason?}`. `Cond` is `{"all": [Cond]}`, `{"any": [Cond]}`,
  `{"not": Cond}` or `{"fact", "op": eq|ne|lt|le|gt|ge|in|exists, "value"}`; a false `eligible_if` makes the route not ok with
  the reason. Amounts are rounded to cents. `validate_valuer(pack)` lists unknown params, tables, condition keys and routes.
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

from di.services.engine.jsmath import js_round, js_sum
from di.services.modeler.carbon import co2_avoided
from di.services.modeler.gates import Cond, _fact, _holds
from di.services.modeler.pack import Pack
from di.services.modeler.valuers import amount
from di.services.modeler.valuers.amount import AmountError
from di.services.modeler.valuers.tool_fleet import Decision, PathValue, Rule, ValueLine, apply_rules

_LEAF_OPS = {"eq": "eq", "ne": "ne", "lt": "lt", "gt": "gt", "le": "lte", "ge": "gte", "in": "in", "exists": "exists"}
DEFAULT_KIND = {"v": "sale", "c": "prep", "h": "fees"}  # a line's term kind when the pack names none


def _holds_all(conds: Sequence[Mapping[str, Any]], case: Mapping[str, Any], pack: Pack) -> bool:
    return all(_holds(c := Cond.model_validate(x), _fact(case, pack, c.fact)) for x in conds)


def _cond_error(c: Any, at: str) -> str | None:
    """The first thing wrong with an `eligible_if` condition, None when it is well formed."""
    if not isinstance(c, Mapping):
        return f"{at} is a condition object"
    if set(c) in ({"all"}, {"any"}):
        k = next(iter(c))
        if not isinstance(c[k], list) or not c[k]:
            return f"{at}.{k} is a list of conditions"
        return next((e for i, x in enumerate(c[k]) if (e := _cond_error(x, f"{at}.{k}[{i}]"))), None)
    if set(c) == {"not"}:
        return _cond_error(c["not"], f"{at}.not")
    if isinstance(c.get("fact"), str) and c.get("op") in _LEAF_OPS and set(c) <= {"fact", "op", "value"}:
        return None
    unknown = sorted(set(c) - {"fact", "op", "value"}) or [str(c.get("op"))]
    return f"{at} has an unknown condition key or operator: {unknown[0]}"


def _eligible(c: Mapping[str, Any], case: Mapping[str, Any], pack: Pack) -> bool:
    if "all" in c:
        return all(_eligible(x, case, pack) for x in c["all"])
    if "any" in c:
        return any(_eligible(x, case, pack) for x in c["any"])
    if "not" in c:
        return not _eligible(c["not"], case, pack)
    leaf = Cond(fact=c["fact"], op=_LEAF_OPS[c["op"]], value=c.get("value"))
    return _holds(leaf, _fact(case, pack, leaf.fact))


def _walk_amounts(expr: Any, params: Mapping[str, Any], tables: Mapping[str, Any], at: str, out: list[str]) -> None:
    if not isinstance(expr, Mapping):
        return
    for k, v in expr.items():
        if k == "param" and v not in params:
            out.append(f"{at} uses the unknown param {v}")
        elif k == "table" and v not in tables:
            out.append(f"{at} uses the unknown table {v}")
        elif k == "decay" and isinstance(v, Mapping):
            for part in v.values():
                _walk_amounts(part, params, tables, f"{at}.decay", out)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                _walk_amounts(x, params, tables, f"{at}.{k}[{i}]", out)
        elif isinstance(v, Mapping):
            _walk_amounts(v, params, tables, f"{at}.{k}", out)


def validate_valuer(pack: Pack) -> list[str]:
    """Everything wrong with a standard pack's valuer data that the parse leaves to here: unknown params and tables in
    amounts, malformed or unknown keys in `eligible_if`, and `routes` entries for routes the pack does not have."""
    p = pack.valuer.params
    msgs: list[str] = []
    for i, ln in enumerate(p.get("lines") or []):
        _walk_amounts(ln.get("amount"), p.get("params") or {}, p.get("tables") or {}, f"lines[{i}].amount", msgs)
    ids = {r.id for r in pack.routes}
    for i, r in enumerate(p.get("routes") or []):
        if r.get("route") not in ids:
            msgs.append(f"routes[{i}] names the route {r.get('route')}, which the pack does not have")
        if r.get("eligible_if") is not None and (e := _cond_error(r["eligible_if"], f"routes[{i}].eligible_if")):
            msgs.append(e)
    return msgs


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
            {"type": ln["type"], "label": ln["label"], "basis": ln.get("basis", ""), "amt": js_round(amt * 100) / 100,
             "kind": ln.get("kind") or DEFAULT_KIND[ln["type"]]}
        )  # fmt: skip
    total = {t: js_sum(x["amt"] for x in lines if x["type"] == t) for t in ("v", "c", "h")}
    if not why and not lines:
        why = f"The pack has no value lines for {route}"
    ok = not why
    for r in params.get("requires") or []:
        if ok and r["route"] == route and not _holds_all(r["requires"], case, pack):
            ok, why = False, r["why"]
    for r in params.get("routes") or []:
        if ok and r.get("route") == route and r.get("eligible_if") and not _eligible(r["eligible_if"], case, pack):
            ok, why = False, r.get("ineligible_reason") or f"{route} is not eligible"
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
