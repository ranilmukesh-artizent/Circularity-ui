"""The `Query` expression of Manhattan Active search endpoints, e.g.

    ItemId = 'MTR-2041' and FacilityId in ('WH01','WH02') and UpdatedTimestamp > '2026-10-07T09:00:00.000'

Supported: comparisons =, !=, <>, >, >=, <, <=, `in (...)`, `not in (...)`, `like` ('%' wildcard), `is null`,
`is not null`, joined by `and` / `or` (and binds tighter), parentheses. Values are single-quoted strings (with ''
for a quote), numbers, true/false and null. Field names may be dotted (OrderLine.ItemId). Timestamps compare as
strings, which is correct for Manhattan's fixed-width ISO format.
"""

import re
from collections.abc import Callable
from typing import Any

TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>-?\d+(?:\.\d+)?)|(?P<op><>|!=|>=|<=|=|>|<)|(?P<paren>[(),])|(?P<word>[A-Za-z_][\w.]*))"
)


class QueryError(ValueError):
    pass


def _tokens(q: str) -> list[tuple[str, Any]]:
    out, pos = [], 0
    q = q.rstrip()
    while pos < len(q):
        m = TOKEN.match(q, pos)
        if not m or m.end() == pos:
            raise QueryError(f"Invalid query near '{q[pos:pos + 20]}'")
        pos = m.end()
        if m["str"] is not None:
            out.append(("val", m["str"][1:-1].replace("''", "'")))
        elif m["num"] is not None:
            n = m["num"]
            out.append(("val", float(n) if "." in n else int(n)))
        elif m["op"]:
            out.append(("op", "!=" if m["op"] == "<>" else m["op"]))
        elif m["paren"]:
            out.append((m["paren"], m["paren"]))
        else:
            w = m["word"]
            lw = w.lower()
            if lw in ("and", "or", "in", "not", "like", "is"):
                out.append((lw, lw))
            elif lw in ("true", "false"):
                out.append(("val", lw == "true"))
            elif lw == "null":
                out.append(("val", None))
            else:
                out.append(("field", w))
    return out


def _get(doc: dict, path: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if isinstance(cur, list):
            return [_get(x, part) if isinstance(x, dict) else None for x in cur]
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _cmp(a: Any, op: str, b: Any) -> bool:
    if isinstance(a, list):  # a field of a list of children: any child matches
        return any(_cmp(x, op, b) for x in a)
    if op == "=":
        return a == b or (a is not None and b is not None and str(a) == str(b))
    if op == "!=":
        return not _cmp(a, "=", b)
    if a is None or b is None:
        return False
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    if isinstance(a, int | float) and isinstance(b, int | float):
        x, y = a, b
    else:
        x, y = str(a), str(b)
    return {">": x > y, ">=": x >= y, "<": x < y, "<=": x <= y}[op]


Pred = Callable[[dict], bool]


class _Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self, k=0):
        return self.t[self.i + k] if self.i + k < len(self.t) else (None, None)

    def take(self, kind=None):
        tok = self.peek()
        if tok[0] is None or (kind and tok[0] != kind):
            raise QueryError(f"Invalid query: expected {kind or 'more input'}")
        self.i += 1
        return tok

    def expr(self) -> Pred:
        left = self.term()
        while self.peek()[0] == "or":
            self.take()
            right = self.term()
            left = (lambda a, b: lambda d: a(d) or b(d))(left, right)
        return left

    def term(self) -> Pred:
        left = self.factor()
        while self.peek()[0] == "and":
            self.take()
            right = self.factor()
            left = (lambda a, b: lambda d: a(d) and b(d))(left, right)
        return left

    def factor(self) -> Pred:
        if self.peek()[0] == "(":
            self.take("(")
            p = self.expr()
            self.take(")")
            return p
        field = self.take("field")[1]
        kind = self.peek()[0]
        if kind == "op":
            op = self.take()[1]
            v = self.take("val")[1]
            return lambda d: _cmp(_get(d, field), op, v)
        neg = False
        if kind == "not":
            self.take()
            neg = True
            kind = self.peek()[0]
        if kind == "in":
            self.take()
            self.take("(")
            vals = [self.take("val")[1]]
            while self.peek()[0] == ",":
                self.take()
                vals.append(self.take("val")[1])
            self.take(")")
            return lambda d: any(_cmp(_get(d, field), "=", v) for v in vals) != neg
        if kind == "like":
            self.take()
            pat = re.compile("^" + ".*".join(re.escape(p) for p in str(self.take("val")[1]).split("%")) + "$", re.I)
            return lambda d: (bool(pat.match(str(_get(d, field) or "")))) != neg
        if kind == "is":
            self.take()
            isnot = self.peek()[0] == "not"
            if isnot:
                self.take()
            if self.take("val")[1] is not None:
                raise QueryError("Invalid query: 'is' takes null")
            return lambda d: (_get(d, field) is None) != isnot
        raise QueryError(f"Invalid query: no operator after {field}")


def parse_query(q: str | None) -> Pred:
    if not q or not q.strip():
        return lambda d: True  # noqa: ARG005 - every filter takes the document
    p = _Parser(_tokens(q))
    pred = p.expr()
    if p.i != len(p.t):
        raise QueryError("Invalid query: unexpected input at the end")
    return pred
