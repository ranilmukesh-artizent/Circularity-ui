"""Maximo `oslc.where` -> SQLAlchemy expression. User text never reaches SQL: values become bound parameters.

Supports what Maximo integration clients send:
  comparisons   status="APPR"   wopriority<=2   reportdate>="2026-01-01T00:00:00+05:30"   status!="CLOSE"
  like          description="%bearing%"   assetnum="MTR%"   (a % in a quoted value makes = / != a LIKE, case-insensitive)
  null checks   failurecode="*" (has a value)   failurecode!="*" (empty)
  lists         assetnum in ["MTR-2041","PMP-0320"]   status!=["CLOSE","CAN"] (not in)
  logic         ... and ...   ... or ...   parentheses
Attribute names may carry the OSLC prefix (spi:status). Values: "text" (\\" escapes a quote), numbers, null.
"""

import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, Numeric, and_, not_, or_
from sqlalchemy.sql import ColumnElement

IST = timezone(timedelta(hours=5, minutes=30))

_TOKEN = re.compile(
    r"""\s*(?:
      (?P<str>"(?:[^"\\]|\\.)*")
    | (?P<num>-?\d+(?:\.\d+)?)
    | (?P<op>>=|<=|!=|=|>|<|\(|\)|\[|\]|,)
    | (?P<word>[A-Za-z_][A-Za-z0-9_.:]*)
    )""",
    re.VERBOSE,
)


class WhereError(ValueError):
    pass


def parse_datetime(text: str) -> datetime:
    """ISO 8601 with or without offset (no offset = server time, +05:30), or a plain date."""
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.combine(date.fromisoformat(text), time(), IST)
        v = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as e:
        raise WhereError(f"Invalid date value {text!r}") from e
    return v if v.tzinfo else v.replace(tzinfo=IST)


def coerce(column, value: Any) -> Any:
    """A JSON / where value converted to the column's type."""
    if value is None:
        return None
    ctype = column.type
    try:
        if isinstance(ctype, DateTime):
            return parse_datetime(str(value))
        if isinstance(ctype, Boolean):
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("1", "true", "y")
        if isinstance(ctype, Integer):
            return int(Decimal(str(value)))
        if isinstance(ctype, Numeric):
            return Decimal(str(value))
    except (InvalidOperation, ValueError) as e:
        raise WhereError(f"Invalid value {value!r} for attribute {column.name}") from e
    return str(value)


class _Parser:
    def __init__(self, text: str, column: Callable[[str], Any]):
        self.tokens = self._lex(text)
        self.i = 0
        self.column = column

    @staticmethod
    def _lex(text: str) -> list[tuple[str, str]]:
        out, pos, text = [], 0, text.strip()
        while pos < len(text):
            m = _TOKEN.match(text, pos)
            if not m or m.end() == pos:
                raise WhereError(f"Invalid oslc.where at position {pos}")
            out.append((m.lastgroup, m.group(m.lastgroup)))
            pos = m.end()
        return out

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self, value: str | None = None) -> tuple[str, str]:
        t = self.peek()
        if t is None or (value is not None and t[1].lower() != value):
            raise WhereError(f"Expected {value or 'a value'} in oslc.where")
        self.i += 1
        return t

    def is_word(self, *words: str) -> bool:
        t = self.peek()
        return t is not None and t[0] == "word" and t[1].lower() in words

    def parse(self) -> ColumnElement:
        if not self.tokens:
            raise WhereError("Empty oslc.where")
        e = self.or_expr()
        if self.peek() is not None:
            raise WhereError(f"Unexpected {self.peek()[1]!r} in oslc.where")
        return e

    def or_expr(self):
        e = self.and_expr()
        while self.is_word("or"):
            self.take()
            e = or_(e, self.and_expr())
        return e

    def and_expr(self):
        e = self.primary()
        while self.is_word("and"):
            self.take()
            e = and_(e, self.primary())
        return e

    def primary(self):
        t = self.peek()
        if t and t[1] == "(":
            self.take()
            e = self.or_expr()
            self.take(")")
            return e
        return self.condition()

    def value(self) -> Any:
        kind, val = self.take()
        if kind == "str":
            return re.sub(r"\\(.)", r"\1", val[1:-1])
        if kind == "num":
            return Decimal(val)
        if kind == "word" and val.lower() == "null":
            return None
        raise WhereError(f"Expected a value, found {val!r} in oslc.where")

    def values(self) -> list:
        self.take("[")
        out = [self.value()]
        while self.peek() and self.peek()[1] == ",":
            self.take()
            out.append(self.value())
        self.take("]")
        return out

    def condition(self):
        kind, name = self.take()
        if kind != "word":
            raise WhereError(f"Expected an attribute name, found {name!r} in oslc.where")
        col = self.column(name.split(":", 1)[-1].lower())
        if self.is_word("in"):
            self.take()
            return col.in_([coerce(col, v) for v in self.values()])
        t = self.peek()
        if t is None or t[0] != "op" or t[1] not in ("=", "!=", ">", ">=", "<", "<="):
            raise WhereError(f"Expected an operator after {name} in oslc.where")
        op = self.take()[1]
        if self.peek() and self.peek()[1] == "[":
            vals = [coerce(col, v) for v in self.values()]
            if op == "=":
                return col.in_(vals)
            if op == "!=":
                return not_(col.in_(vals))
            raise WhereError("A list needs = or != in oslc.where")
        raw = self.value()
        if raw is None:
            if op == "=":
                return col.is_(None)
            if op == "!=":
                return col.is_not(None)
            raise WhereError("null needs = or != in oslc.where")
        if isinstance(raw, str) and op in ("=", "!=") and raw == "*":
            return col.is_not(None) if op == "=" else col.is_(None)
        if isinstance(raw, str) and op in ("=", "!=") and "%" in raw:
            like = col.ilike(raw)
            return like if op == "=" else not_(like)
        v = coerce(col, raw)
        return {
            "=": col == v,
            "!=": col != v,
            ">": col > v,
            ">=": col >= v,
            "<": col < v,
            "<=": col <= v,
        }[op]


def parse_where(text: str, column: Callable[[str], Any]) -> ColumnElement:
    """`column(name)` returns the column for an attribute or raises WhereError."""
    return _Parser(text, column).parse()
