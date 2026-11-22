"""OData v2 $filter → SQLAlchemy expression.

Supports what SAP clients send in practice:
  comparisons      Plant eq '1030'   NetPriceAmount gt 1000   Material ne null
  logic            ... and ...   ... or ...   not (...)   parentheses
  functions        substringof('MTR',Material)   startswith(Material,'MTR')   endswith(Material,'41')
                   (each may be compared with true/false, or used on its own)
  literals         'text' (with '' as an escaped quote), 12, 12.5, 12.5M, true, false, null,
                   datetime'2026-10-07T09:00:00', datetimeoffset'2026-10-07T09:00:00Z', guid'…'
Property names are mapped to columns by the caller; an unknown property raises FilterError.
"""

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, false, not_, or_, true
from sqlalchemy.sql import ColumnElement

_TOKEN = re.compile(
    r"""\s*(?:
      (?P<str>'(?:[^']|'')*')
    | (?P<typed>(?:datetimeoffset|datetime|guid|time)'[^']*')
    | (?P<num>-?\d+(?:\.\d+)?[MmDdLlFf]?)
    | (?P<op>\(|\)|,)
    | (?P<word>[A-Za-z_][A-Za-z0-9_/]*)
    )""",
    re.VERBOSE,
)

_CMP = {"eq", "ne", "gt", "ge", "lt", "le"}


class FilterError(ValueError):
    pass


class _BoolFn:
    """A string function (substringof, startswith, endswith): usable on its own or compared with true/false."""

    def __init__(self, expr: ColumnElement):
        self.expr = expr


class _Group(_BoolFn):
    """A parenthesised boolean expression."""


def _parse_datetime(text: str) -> datetime:
    v = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return v if v.tzinfo else v.replace(tzinfo=UTC)


class _Parser:
    def __init__(self, text: str, column: Callable[[str], Any]):
        self.tokens = self._lex(text)
        self.i = 0
        self.column = column

    @staticmethod
    def _lex(text: str) -> list[tuple[str, str]]:
        out, pos = [], 0
        text = text.strip()
        while pos < len(text):
            m = _TOKEN.match(text, pos)
            if not m or m.end() == pos:
                raise FilterError(f"Invalid token at position {pos} in $filter")
            kind = m.lastgroup
            out.append((kind, m.group(kind)))
            pos = m.end()
        return out

    def peek(self, k: int = 0) -> tuple[str, str] | None:
        j = self.i + k
        return self.tokens[j] if j < len(self.tokens) else None

    def take(self, value: str | None = None) -> tuple[str, str]:
        t = self.peek()
        if t is None or (value is not None and t[1].lower() != value):
            raise FilterError(f"Expected {value or 'a value'} in $filter")
        self.i += 1
        return t

    def word_is(self, *words: str) -> bool:
        t = self.peek()
        return t is not None and t[0] == "word" and t[1].lower() in words

    # expr := or_expr
    def parse(self) -> ColumnElement:
        e = self.or_expr()
        if self.peek() is not None:
            raise FilterError(f"Unexpected '{self.peek()[1]}' in $filter")
        return e

    def or_expr(self):
        e = self.and_expr()
        while self.word_is("or"):
            self.take()
            e = or_(e, self.and_expr())
        return e

    def and_expr(self):
        e = self.unary()
        while self.word_is("and"):
            self.take()
            e = and_(e, self.unary())
        return e

    def unary(self):
        if self.word_is("not"):
            self.take()
            return not_(self.unary())
        return self.comparison()

    def comparison(self):
        left = self.operand()
        if self.word_is(*_CMP):
            op = self.take()[1].lower()
            right = self.operand()
            return _compare(left, op, right)
        if isinstance(left, _BoolFn | _Group):
            return left.expr
        raise FilterError("Expected a comparison (eq, ne, gt, ge, lt, le) in $filter")

    def operand(self):
        t = self.peek()
        if t is None:
            raise FilterError("Unexpected end of $filter")
        kind, val = t
        if val == "(":
            self.take()
            e = self.or_expr()
            self.take(")")
            return _Group(e)
        if kind == "str":
            self.take()
            return val[1:-1].replace("''", "'")
        if kind == "typed":
            self.take()
            prefix, body = val.split("'", 1)
            body = body[:-1]
            return _parse_datetime(body) if prefix.startswith("datetime") else body
        if kind == "num":
            self.take()
            num = val.rstrip("MmDdLlFf")
            return Decimal(num) if "." in num or val[-1] in "MmDd" else int(num)
        if kind == "word":
            low = val.lower()
            if low in ("true", "false"):
                self.take()
                return low == "true"
            if low == "null":
                self.take()
                return None
            if low in ("substringof", "startswith", "endswith") and self.peek(1) == ("op", "("):
                return self.function(low)
            self.take()
            return self.column(val)
        raise FilterError(f"Unexpected '{val}' in $filter")

    def function(self, name: str):
        self.take()
        self.take("(")
        a = self.operand()
        self.take(",")
        b = self.operand()
        self.take(")")
        if name == "substringof":  # substringof('needle', Field)
            expr = _as_col(b).contains(_as_text(a), autoescape=True)
        elif name == "startswith":
            expr = _as_col(a).startswith(_as_text(b), autoescape=True)
        else:
            expr = _as_col(a).endswith(_as_text(b), autoescape=True)
        return _BoolFn(expr)


def _as_col(x):
    if not isinstance(x, ColumnElement):
        raise FilterError("String functions need a property as their field argument")
    return x


def _as_text(x):
    if not isinstance(x, str):
        raise FilterError("String functions need a quoted string")
    return x


def _compare(left, op: str, right):
    if isinstance(right, ColumnElement) and not isinstance(left, ColumnElement):
        left, right = right, left
        op = {"gt": "lt", "lt": "gt", "ge": "le", "le": "ge"}.get(op, op)
    if isinstance(left, _BoolFn):
        if not isinstance(right, bool) or op not in ("eq", "ne"):
            raise FilterError("A string function can only be compared with true or false")
        return left.expr if (right == (op == "eq")) else not_(left.expr)
    if not isinstance(left, ColumnElement):
        # constant comparison, e.g. 1 eq 1
        result = {"eq": left == right, "ne": left != right}.get(op)
        if result is None:
            raise FilterError("Comparisons need a property on one side")
        return true() if result else false()
    if right is None:
        if op == "eq":
            return left.is_(None)
        if op == "ne":
            return left.is_not(None)
        raise FilterError("null can only be compared with eq or ne")
    return {
        "eq": left == right,
        "ne": left != right,
        "gt": left > right,
        "ge": left >= right,
        "lt": left < right,
        "le": left <= right,
    }[op]


def parse_filter(text: str, columns: Mapping[str, Any]) -> ColumnElement:
    """Parse a $filter. `columns` maps OData property names to SQLAlchemy columns."""

    def column(name: str):
        if name not in columns:
            raise FilterError(f"Property '{name}' is invalid")
        return columns[name]

    return _Parser(text, column).parse()
