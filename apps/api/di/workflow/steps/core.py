"""The shapes every workflow step shares, and the helpers they use (plan 6, task C4).

- `Rec`: one record moving through a workflow (a source record, before or after mapping to facts).
- `Reject`: a record a step refused, with the field, the rule it broke, the value and a reason a person can read.
- `StepCtx`: what a step may know about its run (the session, the workflow and node, the clock, dry or not, a logger).
- `StepResult`: the records that go on (`out`), the ones refused (`rejected`) and anything else for the engine (`side`:
  counts, branch outputs, the time to resume …).

Helpers: `get`/`put` read and write a dotted field path; `compile_expr` is the one expression language every block uses
(x_expr, x_filter, x_branch, x_wait, x_val rule `expr`): field references, numbers, strings, true/false/null,
+ - * /, comparisons, and/or/not and parentheses. It is a small parser that builds a tree and walks it; nothing is ever
passed to `eval`, and anything outside the grammar raises `ExprError`. `rule_ok` checks one rule (the x_val rules and
the condition rows of x_filter / x_branch).
"""

import copy
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from di.canonical.store import Fact


@dataclass
class Rec:
    ext_id: str
    resource: str
    data: dict
    facts: list[Fact] | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class Reject:
    rec: Rec
    field: str | None
    rule: str
    value: Any
    reason: str


@dataclass
class StepCtx:
    s: Any  # a Session, or None for pure use (x_fx then uses the fixed demo rates)
    run_id: Any
    wf: dict
    node: dict
    source_id: str | None
    now: datetime
    dry: bool
    log: Callable[[str], None] | None = None
    resumed: bool = False  # x_wait: the run came back for the records this step parked (di/workflow/waits.py)


@dataclass
class StepResult:
    out: list[Rec]
    rejected: list[Reject] = field(default_factory=list)
    side: dict = field(default_factory=dict)


Step = Callable[[list[Rec], dict, StepCtx], StepResult]


class StepError(ValueError):
    """A setting the step cannot use (an unknown unit pair, a rate table that does not exist …): the step fails."""


def clone(r: Rec) -> Rec:
    """A copy a step may change: steps never change the records they are given (dry runs show before and after)."""
    return Rec(r.ext_id, r.resource, copy.deepcopy(r.data), list(r.facts) if r.facts is not None else None, copy.deepcopy(r.meta))


def opt(cfg: dict | None, key: str, default: Any = None) -> Any:
    """A setting, or its default when it is missing or empty."""
    v = (cfg or {}).get(key)
    return default if v is None or v == "" else v


def as_list(v: Any) -> list:
    if v is None or v == "":
        return []
    if isinstance(v, str):
        return [p.strip() for p in v.split(",") if p.strip()]
    return list(v)


# ------------------------------------------------------------------ field paths
_MISSING = object()


def get(r: Rec, path: str, default: Any = None) -> Any:
    """A dotted path into the record's data ("line.tax"); for a mapped record also "model.field" of one of its facts."""
    cur: Any = r.data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            cur = _MISSING
            break
    if cur is not _MISSING:
        return cur
    if r.facts and "." in path:
        model, _, fname = path.partition(".")
        for f in r.facts:
            if f.model == model and f.field == fname:
                return f.value
    return default


def put(r: Rec, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = r.data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = cur[part] = {}
        cur = nxt
    cur[parts[-1]] = value


def keep_source(r: Rec, path: str, value: Any) -> None:
    """Keep the value a step replaced in meta.source (the blocks promise the source value is kept alongside)."""
    r.meta.setdefault("source", {}).setdefault(path, value)


def digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


# ------------------------------------------------------------------ values
def num(v: Any) -> float | None:
    """A number, from a number or a numeric string; None otherwise (booleans are not numbers)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, str):
        try:
            return float(Decimal(v.strip()))
        except (InvalidOperation, ValueError):
            return None
    return None


def parse_ts(v: Any) -> datetime | None:
    """A time from an ISO 8601 string, a datetime or a date; naive values are taken as UTC."""
    if isinstance(v, datetime):
        d = v
    elif isinstance(v, date):
        d = datetime(v.year, v.month, v.day, tzinfo=UTC)
    elif isinstance(v, str) and v.strip():
        try:
            d = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def iso_z(d: datetime) -> str:
    return d.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def too_old(recs: list[Rec], time_field: str, window: float) -> tuple[dict[int, datetime], datetime | None]:
    """The records (by position) whose `time_field` is more than `window` minutes before the newest such time in the
    batch, and that newest time. Records without a readable time are never too old. Synced records carry no arrival
    time, so this is how x_late's late window and x_evt's replay window apply to them: relative to the newest record
    of the same run (not the run's clock, so replaying old data does not reject all of it)."""
    if not time_field or not window:
        return {}, None
    times = {i: t for i, r in enumerate(recs) if (t := parse_ts(get(r, time_field))) is not None}
    if not times:
        return {}, None
    newest = max(times.values())
    return {i: t for i, t in times.items() if newest - t > timedelta(minutes=window)}, newest


def zone(name: str | None):
    """A time zone from "UTC", "+05:30" / "-04:00" or an IANA name ("Asia/Kolkata")."""
    if not name or name.upper() in ("UTC", "Z", "GMT"):
        return UTC
    m = re.fullmatch(r"([+-])(\d{1,2}):?(\d{2})?", name.strip())
    if m:
        delta = timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0))
        return timezone(delta if m.group(1) == "+" else -delta)
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError as e:  # pragma: no cover
        raise StepError(f"unknown time zone {name}") from e
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise StepError(f"unknown time zone {name}") from e


# ------------------------------------------------------------------ expressions
class ExprError(StepError):
    """An expression outside the grammar."""


MAX_EXPR = 500
_TOKEN = re.compile(
    r"""\s*(?:
      (?P<num>\d+(?:\.\d+)?)
    | (?P<str>'[^'\\]*'|"[^"\\]*")
    | (?P<op>==|!=|<=|>=|<|>|\+|-|\*|/|\(|\))
    | (?P<ref>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)
    )""",
    re.VERBOSE,
)
_WORDS = {"and", "or", "not", "true", "false", "null"}
_CMP = {"==", "!=", "<", "<=", ">", ">="}


def _tokens(src: str) -> list[tuple[str, str]]:
    if len(src) > MAX_EXPR:
        raise ExprError(f"expression longer than {MAX_EXPR} characters")
    out, pos = [], 0
    while pos < len(src):
        if src[pos:].strip() == "":
            break
        m = _TOKEN.match(src, pos)
        if not m or m.end() == pos:
            raise ExprError(f"unexpected {src[pos:].strip()[:1]!r} at {pos}")
        kind = m.lastgroup or ""
        val = m.group(kind)
        if kind == "ref":
            if any(p.startswith("__") for p in val.split(".")):
                raise ExprError(f"field {val!r} is not allowed")
            if val in _WORDS:
                kind = "word"
        out.append((kind, val))
        pos = m.end()
    return out


class _Parser:
    def __init__(self, toks: list[tuple[str, str]]):
        self.t, self.i = toks, 0

    def peek(self) -> tuple[str, str] | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self, kind: str, val: str | None = None) -> bool:
        p = self.peek()
        if p and p[0] == kind and (val is None or p[1] == val):
            self.i += 1
            return True
        return False

    def parse(self):
        node = self.or_()
        if (p := self.peek()) is not None:
            raise ExprError(f"unexpected {p[1]!r}")
        return node

    def or_(self):
        node = self.and_()
        while self.take("word", "or"):
            node = ("or", node, self.and_())
        return node

    def and_(self):
        node = self.not_()
        while self.take("word", "and"):
            node = ("and", node, self.not_())
        return node

    def not_(self):
        if self.take("word", "not"):
            return ("not", self.not_())
        return self.cmp()

    def cmp(self):
        node = self.sum()
        p = self.peek()
        if p and p[0] == "op" and p[1] in _CMP:
            self.i += 1
            node = (p[1], node, self.sum())
        return node

    def sum(self):
        node = self.term()
        while (p := self.peek()) and p[0] == "op" and p[1] in "+-":
            self.i += 1
            node = (p[1], node, self.term())
        return node

    def term(self):
        node = self.unary()
        while (p := self.peek()) and p[0] == "op" and p[1] in "*/":
            self.i += 1
            node = (p[1], node, self.unary())
        return node

    def unary(self):
        if self.take("op", "-"):
            return ("neg", self.unary())
        return self.atom()

    def atom(self):
        p = self.peek()
        if p is None:
            raise ExprError("expression ends too early")
        kind, val = p
        self.i += 1
        if kind == "num":
            return ("lit", float(val) if "." in val else int(val))
        if kind == "str":
            return ("lit", val[1:-1])
        if kind == "word" and val in ("true", "false", "null"):
            return ("lit", {"true": True, "false": False, "null": None}[val])
        if kind == "ref":
            return ("ref", val)
        if kind == "op" and val == "(":
            node = self.or_()
            if not self.take("op", ")"):
                raise ExprError("missing )")
            return node
        raise ExprError(f"unexpected {val!r}")


def _is_num(v: Any) -> bool:
    return isinstance(v, int | float | Decimal) and not isinstance(v, bool)


def _cmp(op: str, a: Any, b: Any) -> bool:
    if op in ("==", "!="):
        eq = a == b
        if not eq and _is_num(a) != _is_num(b) and not isinstance(a, bool) and not isinstance(b, bool):
            na, nb = num(a), num(b)  # 5 == "5": a number against a numeric string compares as numbers
            eq = na is not None and na == nb
        return eq if op == "==" else not eq
    if a is None or b is None:
        return False
    na, nb = num(a), num(b)
    if na is not None and nb is not None:
        a, b = na, nb
    else:
        ta, tb = parse_ts(a), parse_ts(b)
        if ta is not None and tb is not None:
            a, b = ta, tb
        else:
            a, b = str(a), str(b)
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def _eval(node, r: Rec) -> Any:
    op = node[0]
    if op == "lit":
        return node[1]
    if op == "ref":
        return get(r, node[1])
    if op == "not":
        return not _eval(node[1], r)
    if op == "and":
        return bool(_eval(node[1], r)) and bool(_eval(node[2], r))
    if op == "or":
        return bool(_eval(node[1], r)) or bool(_eval(node[2], r))
    if op == "neg":
        v = num(_eval(node[1], r))
        return None if v is None else _tidy(-v)
    a, b = _eval(node[1], r), _eval(node[2], r)
    if op in _CMP:
        return _cmp(op, a, b)
    if op == "+" and isinstance(a, str) and isinstance(b, str) and num(a) is None:
        return a + b
    na, nb = num(a), num(b)
    if na is None or nb is None:
        return None
    if op == "+":
        return _tidy(na + nb)
    if op == "-":
        return _tidy(na - nb)
    if op == "*":
        return _tidy(na * nb)
    return None if nb == 0 else _tidy(na / nb)


def _tidy(v: float) -> float | int:
    v = round(v, 10)
    return int(v) if v == int(v) and abs(v) < 1e15 else v


class Expr:
    def __init__(self, src: str):
        self.src = src
        self.tree = _Parser(_tokens(src)).parse()

    def __call__(self, r: Rec) -> Any:
        return _eval(self.tree, r)


def compile_expr(src: str) -> Expr:
    if not isinstance(src, str) or not src.strip():
        raise ExprError("empty expression")
    return Expr(src)


# ------------------------------------------------------------------ rules and conditions
TYPES = {"text", "string", "number", "int", "integer", "date", "datetime", "bool", "boolean", "list", "object"}


def _is_type(v: Any, t: str) -> bool:
    t = t.lower()
    if t in ("text", "string"):
        return isinstance(v, str)
    if t == "number":
        return isinstance(v, int | float | Decimal) and not isinstance(v, bool)
    if t in ("int", "integer"):
        return isinstance(v, int) and not isinstance(v, bool)
    if t in ("date", "datetime"):
        return parse_ts(v) is not None
    if t in ("bool", "boolean"):
        return isinstance(v, bool)
    if t == "list":
        return isinstance(v, list)
    if t == "object":
        return isinstance(v, dict)
    raise StepError(f"unknown type {t}")


_CMP_ARG = re.compile(r"\s*(>=|<=|!=|>|<|=)\s*(-?\d+(?:\.\d+)?)\s*")


def range_test(arg: Any) -> tuple[Callable[[float], bool], str]:
    """A range setting -> (test, text). The forms of blocks.py: "min..max" (either side may be left out) or one
    comparison ">0", ">=0", "<5", "<=5", "=3", "!=3"; also {min, max} or [min, max]."""
    if isinstance(arg, str) and (m := _CMP_ARG.fullmatch(arg)):
        op, b = m.group(1), float(m.group(2))
        tests = {">": b.__lt__, ">=": b.__le__, "<": b.__gt__, "<=": b.__ge__, "=": b.__eq__, "!=": b.__ne__}
        return tests[op], f"{op}{m.group(2)}"
    if isinstance(arg, dict):
        lo, hi = num(arg.get("min")), num(arg.get("max"))
    elif isinstance(arg, list | tuple) and len(arg) == 2:
        lo, hi = num(arg[0]), num(arg[1])
    elif isinstance(arg, str) and ".." in arg:
        lo_s, _, hi_s = arg.partition("..")
        lo, hi = num(lo_s) if lo_s.strip() else None, num(hi_s) if hi_s.strip() else None
    else:
        raise StepError(f"range needs min..max or a comparison such as >0, not {arg!r}")
    if lo is None and hi is None:
        raise StepError(f"range needs min..max or a comparison such as >0, not {arg!r}")
    text = f"{'' if lo is None else _tidy(lo)}..{'' if hi is None else _tidy(hi)}"
    return (lambda n: (lo is None or n >= lo) and (hi is None or n <= hi)), text


def present(v: Any) -> bool:
    return v is not None and v != "" and v != [] and v != {}


def rule_ok(r: Rec, rule: dict | str) -> tuple[bool, str, str | None, Any, str]:
    """Check one rule on a record -> (ok, rule name, field, value, reason).

    A rule is an expression string, or {field, check, arg} with check present | type | regex | range | in | expr, or a
    condition row {field, op, value} with op == != < <= > >= contains. Checks other than `present` pass on a missing
    value (whether a field must be there is the `present` check's job, or x_val's required fields).
    """
    if isinstance(rule, str):
        return (bool(compile_expr(rule)(r)), "expr", None, None, f"{rule} is false")
    fname = rule.get("field")
    v = get(r, fname) if fname else None
    if "op" in rule and "check" not in rule:
        op, want = rule["op"], rule.get("value")
        if op == "contains":
            ok = v is not None and str(want) in (v if isinstance(v, list) else str(v))
        elif op in _CMP:
            ok = _cmp(op, v, want)
        else:
            raise StepError(f"unknown operator {op}")
        return ok, rule.get("name") or op, fname, v, f"{fname} {op} {want!r} is false (value {v!r})"
    check = rule.get("check") or "present"
    arg = rule.get("arg")
    name = rule.get("name") or check
    if check == "present":
        return present(v), name, fname, v, f"{fname} is missing"
    if check == "expr":
        return bool(compile_expr(str(arg))(r)), name, fname, v, f"{arg} is false"
    if v is None:
        return True, name, fname, v, ""
    if check == "type":
        return _is_type(v, str(arg or "text")), name, fname, v, f"{fname} is not a {arg} ({v!r})"
    if check == "regex":
        pat = str(arg or "")
        if len(pat) > 200:
            raise StepError("regex longer than 200 characters")
        try:
            ok = re.fullmatch(pat, str(v)) is not None
        except re.error as e:
            raise StepError(f"bad regex {pat!r}: {e}") from e
        return ok, name, fname, v, f"{fname} {v!r} does not match {pat}"
    if check == "range":
        test, txt = range_test(arg)
        n = num(v)
        return n is not None and test(n), name, fname, v, f"{fname} {v!r} is outside the range {txt}"
    if check == "in":
        allowed = [str(a) for a in as_list(arg)]
        return str(v) in allowed, name, fname, v, f"{fname} {v!r} is not one of {', '.join(allowed)}"
    raise StepError(f"unknown check {check}")


def condition(cond: Any) -> Callable[[Rec], bool]:
    """A condition setting -> a test: an expression string, or rule rows that must all hold; empty: always true."""
    if cond is None or cond == "" or cond == []:
        return lambda _r: True
    if isinstance(cond, str):
        e = compile_expr(cond)
        return lambda r: bool(e(r))
    rules = [cond] if isinstance(cond, dict) else list(cond)
    for rule in rules:  # compile expressions now: a bad one fails the step before any record
        if isinstance(rule, str):
            compile_expr(rule)
    return lambda r: all(rule_ok(r, rule)[0] for rule in rules)


def log(ctx: StepCtx, msg: str) -> None:
    if ctx.log is not None:
        ctx.log(msg)
