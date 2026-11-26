"""The amount grammar of the standard valuer (plan 9, P9-1.9; registry entry I-21). JSON only, never `eval`.

An amount is exactly one of:

    {"const": n}                        {"field": "dotted.path"}   a number of the case
    {"param": "name"}                   a pack parameter (`valuer.params.params`)
    {"table": "name", "by": ["f", ...]} a lookup in a pack table (`valuer.params.tables`) by case fields, one level each
    {"mul": [a, ...]}  {"add": [a, ...]}  {"min": [a, ...]}  {"max": [a, ...]}  {"sub": [a, b]}  {"round": a}
    {"div": [a, b]}     division (by zero raises `AmountError`)       {"fact": "model.field"}  an alias of `field`
    {"decay": {"start": a, "monthly": a, "months": a}}   start x (1 - monthly) ^ months (P9-12.1)

`evaluate(expr, case, pack) -> float` prices one amount; `check(expr)` is the static check `parse_pack` runs (an unknown
key is a `PackError` part 9). Errors raise `AmountError(path, message)` with the place in the pack's lines.
Owns: the grammar and its evaluation. Never does: read a session, the clock or a file; write anything. `round` is JS
rounding (`jsmath.js_round`), as every other valuer rounds.
"""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from di.services.engine.jsmath import js_round

if TYPE_CHECKING:
    from di.services.modeler.pack import Pack

OPS = ("const", "field", "fact", "param", "table", "mul", "add", "sub", "div", "min", "max", "round", "decay")
_DECAY = ("start", "monthly", "months")
_LISTS = ("mul", "add", "min", "max")


class AmountError(ValueError):
    """An amount that cannot be checked or priced. `path` is where it sits (`lines[2].amount.mul[1]`); `field` names the
    case field a missing-field error is about (the valuer lists it in the route's `misses`)."""

    def __init__(self, path: str, message: str, field: str | None = None) -> None:
        self.path, self.field = path, field
        super().__init__(message)


def _num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def check(expr: Any, path: str = "amount") -> None:
    """Raise `AmountError` when `expr` is not a well-formed amount; the shape only (fields, tables and params are looked
    up when the amount is priced)."""
    if not isinstance(expr, Mapping) or not expr:
        raise AmountError(path, f"An amount is an object with one operation at {path}")
    keys = set(expr)
    op = next((k for k in expr if k != "by"), None)
    if op is None or (op != "table" and len(keys) != 1) or (op == "table" and keys != {"table", "by"}):
        raise AmountError(path, f"An amount has exactly one operation at {path}")
    if op not in OPS:
        raise AmountError(path, f"Unknown amount {op} at {path}")
    v = expr[op]
    here = f"{path}.{op}"
    if op == "const":
        if not _num(v):
            raise AmountError(here, f"const is a number at {here}")
    elif op == "decay":
        if not isinstance(v, Mapping) or set(v) != set(_DECAY):
            raise AmountError(here, f"decay is {{start, monthly, months}} amounts at {here}")
        for k in _DECAY:
            check(v[k], f"{here}.{k}")
    elif op in ("field", "fact", "param"):
        if not isinstance(v, str) or not v:
            raise AmountError(here, f"{op} is a name at {here}")
    elif op == "table":
        by = expr["by"]
        if not isinstance(v, str) or not v or not isinstance(by, list) or not by or not all(isinstance(b, str) and b for b in by):
            raise AmountError(here, f"table is a name with a list of case fields (by) at {here}")
    elif op == "round":
        check(v, here)
    else:
        if not isinstance(v, list) or (op in ("sub", "div") and len(v) != 2) or (op in _LISTS and not v):
            raise AmountError(here, f"{op} takes {'two amounts' if op in ('sub', 'div') else 'a list of amounts'} at {here}")
        for i, x in enumerate(v):
            check(x, f"{here}[{i}]")


def lookup(case: Mapping[str, Any], path: str) -> Any:
    """The value at a dotted path of the case, None when any step is missing."""
    cur: Any = case
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _field(case: Mapping[str, Any], name: str, path: str) -> Any:
    v = lookup(case, name)
    if v is None:
        raise AmountError(path, f"The case has no {name} (needed at {path})", name)
    return v


def evaluate(expr: Mapping[str, Any], case: Mapping[str, Any], pack: "Pack", path: str = "amount") -> float:
    """The amount's value for the case, with the pack's parameters and tables. `AmountError` for an unknown key, a missing
    case field, a parameter or table row the pack lacks, or a value that is not a number."""
    check(expr, path)
    return _eval(expr, case, pack.valuer.params, path)


def _number(v: Any, what: str, path: str) -> float:
    if not _num(v):
        raise AmountError(path, f"{what} is not a number (at {path})")
    return float(v)


def _eval(expr: Mapping[str, Any], case: Mapping[str, Any], params: Mapping[str, Any], path: str) -> float:
    op = next(k for k in expr if k != "by")
    v = expr[op]
    here = f"{path}.{op}"
    if op == "const":
        return float(v)
    if op in ("field", "fact"):
        return _number(_field(case, v, path), f"The case's {v}", path)
    if op == "param":
        given = (params.get("params") or {}).get(v)
        if given is None:
            raise AmountError(path, f"The pack has no parameter {v} (needed at {path})")
        return _number(given, f"The parameter {v}", path)
    if op == "table":
        row: Any = (params.get("tables") or {}).get(v)
        if row is None:
            raise AmountError(path, f"The pack has no table {v} (needed at {path})")
        keys = [str(_field(case, f, path)) for f in expr["by"]]
        for k in keys:
            row = row.get(k) if isinstance(row, Mapping) else None
        if row is None:
            raise AmountError(path, f"The table {v} has no row for {' / '.join(keys)} (needed at {path})")
        return _number(row, f"The table {v} row", path)
    if op == "round":
        return float(js_round(_eval(v, case, params, here)))
    if op == "decay":
        a, m, n = (_eval(v[k], case, params, f"{here}.{k}") for k in _DECAY)
        return a * (1 - m) ** n
    xs = [_eval(x, case, params, f"{here}[{i}]") for i, x in enumerate(v)]
    if op == "mul":
        out = 1.0
        for x in xs:
            out *= x
        return out
    if op == "add":
        return sum(xs)
    if op == "sub":
        return xs[0] - xs[1]
    if op == "div":
        if xs[1] == 0:
            raise AmountError(path, f"Division by zero at {path}")
        return xs[0] / xs[1]
    return min(xs) if op == "min" else max(xs)
