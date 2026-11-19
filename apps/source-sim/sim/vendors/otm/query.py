"""OTM's `q` filter (REST API for Oracle Transportation Management, "Manage Collections"):

    locationXid sw "PHL"        not locationXid pr        refnums.shipmentRefnumValue eq "RT-1048"
    (a eq "1" or b ne "2") and updateDate gt "2026-10-07T09:00:00Z"        shipmentGid in ["A.B", "A.C"]

Operators eq ne co sw ew pr gt ge lt le in; and / or / not; parentheses. Values are quoted strings, numbers, true or
false. A dotted attribute walks into child collections (a match on any child item counts). Typed values (dateTimeType
{value, timezone}, currencyType {value, currency}, amountType {value, unit}) compare by their value: dates
chronologically, numbers numerically ("80 LB" compares as 80), anything else as strings (case-sensitive).
Filters are evaluated on the rendered resource, so a filter sees exactly what a GET returns.
"""

import re
from datetime import UTC, datetime
from typing import Any


class QueryError(ValueError):
    pass


_TOKEN = re.compile(r'\s*(?:(\()|(\))|(\[)|(\])|(,)|"((?:[^"\\]|\\.)*)"|([^\s()\[\],"]+))')
OPS = {"eq", "ne", "co", "sw", "ew", "pr", "gt", "ge", "lt", "le", "in"}


def _tokens(q: str) -> list[tuple[str, Any]]:
    out, pos = [], 0
    q = q.strip()
    while pos < len(q):
        m = _TOKEN.match(q, pos)
        if not m or m.end() == pos:
            raise QueryError(f"Invalid query near position {pos}: {q[pos : pos + 20]!r}")
        pos = m.end()
        lp, rp, lb, rb, comma, string, word = m.groups()
        if lp:
            out.append(("(", None))
        elif rp:
            out.append((")", None))
        elif lb:
            out.append(("[", None))
        elif rb:
            out.append(("]", None))
        elif comma:
            out.append((",", None))
        elif string is not None:
            out.append(("str", string.replace('\\"', '"')))
        elif word is not None:
            out.append(("word", word))
    return out


class _Parser:
    def __init__(self, q: str):
        self.t = _tokens(q)
        self.i = 0

    def peek(self, kind=None, value=None):
        if self.i >= len(self.t):
            return None
        k, v = self.t[self.i]
        if kind and k != kind:
            return None
        if value and (v or "").lower() != value:
            return None
        return self.t[self.i]

    def take(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def parse(self):
        node = self.expr()
        if self.i != len(self.t):
            raise QueryError(f"Unexpected {self.t[self.i][1] or self.t[self.i][0]!r} in query")
        return node

    def expr(self):
        node = self.term()
        while self.peek("word", "or"):
            self.take()
            node = ("or", node, self.term())
        return node

    def term(self):
        node = self.factor()
        while self.peek("word", "and"):
            self.take()
            node = ("and", node, self.factor())
        return node

    def factor(self):
        if self.peek("word", "not"):
            self.take()
            return ("not", self.factor())
        if self.peek("("):
            self.take()
            node = self.expr()
            if not self.peek(")"):
                raise QueryError("Missing ')' in query")
            self.take()
            return node
        if not self.peek("word"):
            raise QueryError("Expected an attribute name in query")
        attr = self.take()[1]
        if not self.peek("word") or self.t[self.i][1].lower() not in OPS:
            raise QueryError(f"Expected an operator after {attr!r} (eq, ne, co, sw, ew, pr, gt, ge, lt, le, in)")
        op = self.take()[1].lower()
        if op == "pr":
            return ("cmp", attr, op, None)
        if op == "in":
            if not self.peek("["):
                raise QueryError('The in operator takes a list: ["A", "B"]')
            self.take()
            values = []
            while not self.peek("]"):
                if self.i >= len(self.t):
                    raise QueryError("Missing ']' in query")
                k, v = self.take()
                if k in ("str", "word"):
                    values.append(v)
            self.take()
            return ("cmp", attr, op, values)
        if self.i >= len(self.t) or self.t[self.i][0] not in ("str", "word"):
            raise QueryError(f"Expected a value after {attr} {op}")
        k, v = self.take()
        return ("cmp", attr, op, _literal(k, v))


def _literal(kind: str, v: str):
    if kind == "str":
        return v
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        return float(v)
    except ValueError:
        return v


def parse(q: str | None):
    return _Parser(q).parse() if q and q.strip() else None


def _values(doc: Any, path: list[str]) -> list[Any]:
    if not path:
        return [doc]
    if isinstance(doc, list):
        return [v for x in doc for v in _values(x, path)]
    if not isinstance(doc, dict):
        return []
    v = doc.get(path[0])
    if isinstance(v, dict) and "items" in v and isinstance(v["items"], list):
        v = v["items"]
    if v is None:
        return []
    return _values(v, path[1:])


def _scalar(v):
    if isinstance(v, dict):
        return v.get("value")
    return v


def _as_date(v) -> datetime | None:
    if not isinstance(v, str) or not re.match(r"^\d{4}-\d{2}-\d{2}", v):
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _as_num(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)(?:\s+[A-Za-z]+)?\s*$", v)
        return float(m.group(1)) if m else None
    return None


def _compare(a, op: str, b) -> bool:
    if op == "pr":
        return a not in (None, "", [], {})
    if a is None:
        return op == "ne"
    if op in ("co", "sw", "ew"):
        a, b = str(a), str(b)
        return b in a if op == "co" else a.startswith(b) if op == "sw" else a.endswith(b)
    if isinstance(a, bool) or isinstance(b, bool):
        if op in ("gt", "ge", "lt", "le"):
            raise QueryError("Boolean attributes cannot be compared with gt, ge, lt or le")
        return (str(a).lower() == str(b).lower()) == (op == "eq")
    da, db = _as_date(a), _as_date(b)
    if da and db:
        a, b = da, db
    else:
        na, nb = _as_num(a), _as_num(b)
        if na is not None and nb is not None:
            a, b = na, nb
        else:
            a, b = str(a), str(b)
    return {
        "eq": a == b,
        "ne": a != b,
        "gt": a > b,
        "ge": a >= b,
        "lt": a < b,
        "le": a <= b,
    }[op]


def matches(node, doc: dict) -> bool:
    if node is None:
        return True
    kind = node[0]
    if kind == "and":
        return matches(node[1], doc) and matches(node[2], doc)
    if kind == "or":
        return matches(node[1], doc) or matches(node[2], doc)
    if kind == "not":
        return not matches(node[1], doc)
    _, attr, op, value = node
    vals = [_scalar(v) for v in _values(doc, attr.split("."))]
    if op == "in":
        return any(_compare(v, "eq", x) for v in vals for x in value)
    if op == "ne":
        return all(_compare(v, "ne", value) for v in vals) if vals else True
    if op == "pr":
        return any(_compare(v, "pr", None) for v in vals)
    return any(_compare(v, op, value) for v in vals)
