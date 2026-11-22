"""A SOQL subset → SQLAlchemy Core (never SQL text built from user input).

Supported:
    SELECT Id, Name, Account.Name ...    fields of the object, or of a parent one level up (single-target lookups)
    SELECT COUNT() ...                   totalSize only
    FROM <one object>
    WHERE   =  !=  <>  <  >  <=  >=  LIKE  IN (...)  NOT IN (...)  AND  OR  NOT  ( ... )
            mixing AND and OR at one level needs parentheses, as in Salesforce
    literals 'text' (backslash escapes), 12, 12.5, TRUE, FALSE, NULL, 2026-12-31, 2026-10-07T09:00:00Z,
             TODAY, YESTERDAY, TOMORROW, LAST_N_DAYS:n, NEXT_N_DAYS:n
    ORDER BY f [ASC|DESC] [NULLS FIRST|LAST], ...    LIMIT n    OFFSET n (at most 2000)
As in Salesforce: keywords, object and field names are case-insensitive, text = and LIKE are case-insensitive,
and an id may be given in its 15- or 18-character form.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, func, not_, or_, select
from sqlalchemy.sql import ColumnElement

from sim.vendors.salesforce.schema import BY_LOWER, OBJECTS, TABLES, Field, SObject, normalise_id

MAX_OFFSET = 2000


class SoqlError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _malformed(msg: str, pos: int | None = None) -> SoqlError:
    where = f"ERROR at Row:1:Column:{pos + 1}\n" if pos is not None else ""
    return SoqlError("MALFORMED_QUERY", where + msg)


# ------------------------------------------------------------------ tokens
_TOKEN = re.compile(
    r"""\s*(?:
      (?P<str>'(?:\\.|[^'\\])*')
    | (?P<datetime>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))
    | (?P<date>\d{4}-\d{2}-\d{2})
    | (?P<num>-?\d+(?:\.\d+)?)
    | (?P<op>!=|<>|<=|>=|=|<|>)
    | (?P<punct>[(),:])
    | (?P<ident>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)
    )""",
    re.VERBOSE,
)
_ESCAPES = {"'": "'", '"': '"', "\\": "\\", "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "%": "\\%", "_": "\\_"}


@dataclass(frozen=True)
class Tok:
    kind: str
    value: str
    pos: int

    def kw(self, *words: str) -> bool:
        return self.kind == "ident" and self.value.upper() in words


def tokenize(text: str) -> list[Tok]:
    out, pos = [], 0
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            start = len(text) - len(text[pos:].lstrip())
            raise _malformed(f"unexpected token: '{text[start : start + 10]}'", start)
        kind = m.lastgroup
        out.append(Tok(kind, m.group(kind), m.start(kind)))
        pos = m.end()
    return out


def _unescape(raw: str, pos: int) -> str:
    out, i = [], 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\":
            nxt = raw[i + 1] if i + 1 < len(raw) else ""
            if nxt not in _ESCAPES:
                raise _malformed(f"Invalid string literal '{raw}'. Illegal character sequence '\\{nxt}' in string literal.", pos)
            out.append(_ESCAPES[nxt])
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


# ------------------------------------------------------------------ syntax tree
@dataclass(frozen=True)
class Lit:
    kind: str  # string, number, bool, null, date, datetime, datefn
    value: Any
    pos: int


@dataclass(frozen=True)
class Cmp:
    path: str
    op: str  # = != < > <= >= like in notin
    value: Lit | list[Lit]
    pos: int


@dataclass(frozen=True)
class Logic:
    op: str  # AND, OR, NOT
    items: tuple


@dataclass
class Query:
    obj: str
    fields: list[tuple[str, int]] = field(default_factory=list)  # (path, pos)
    count: bool = False
    where: Any = None
    order: list[tuple[str, bool, bool | None, int]] = field(default_factory=list)  # path, desc, nulls_first, pos
    limit: int | None = None
    offset: int = 0


class _Parser:
    def __init__(self, text: str):
        self.toks = tokenize(text)
        self.i = 0
        self.end = len(text)

    def peek(self) -> Tok | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def next(self) -> Tok:
        t = self.peek()
        if t is None:
            raise _malformed("unexpected token: <EOF>", self.end)
        self.i += 1
        return t

    def unexpected(self, t: Tok | None) -> SoqlError:
        return _malformed(f"unexpected token: '{t.value}'", t.pos) if t else _malformed("unexpected token: <EOF>", self.end)

    def expect_kw(self, *words: str) -> Tok:
        t = self.peek()
        if not t or not t.kw(*words):
            raise self.unexpected(t)
        return self.next()

    def expect(self, kind: str, value: str | None = None) -> Tok:
        t = self.peek()
        if not t or t.kind != kind or (value is not None and t.value != value):
            raise self.unexpected(t)
        return self.next()

    def accept_kw(self, *words: str) -> Tok | None:
        t = self.peek()
        return self.next() if t and t.kw(*words) else None

    def accept(self, kind: str, value: str) -> bool:
        t = self.peek()
        if t and t.kind == kind and t.value == value:
            self.i += 1
            return True
        return False

    def ident(self) -> Tok:
        t = self.peek()
        if not t or t.kind != "ident" or t.kw("FROM", "WHERE", "ORDER", "LIMIT", "OFFSET", "AND", "OR", "NOT", "SELECT"):
            raise self.unexpected(t)
        return self.next()

    def integer(self) -> int:
        t = self.expect("num")
        if not re.fullmatch(r"\d+", t.value):
            raise self.unexpected(t)
        return int(t.value)

    # SELECT ... FROM ... [WHERE ...] [ORDER BY ...] [LIMIT n] [OFFSET n]
    def query(self) -> Query:
        self.expect_kw("SELECT")
        q = Query(obj="")
        t = self.peek()
        if t and t.kw("COUNT") and self.i + 1 < len(self.toks) and self.toks[self.i + 1].value == "(":
            self.next()
            self.expect("punct", "(")
            self.expect("punct", ")")
            q.count = True
        else:
            while True:
                if (t := self.peek()) and t.value == "(":
                    raise SoqlError("MALFORMED_QUERY", "Subqueries are not supported by this mock")
                f = self.ident()
                q.fields.append((f.value, f.pos))
                if not self.accept("punct", ","):
                    break
        self.expect_kw("FROM")
        q.obj = self.ident().value
        if self.accept_kw("WHERE"):
            q.where = self.condition()
        if self.accept_kw("ORDER"):
            self.expect_kw("BY")
            while True:
                f = self.ident()
                desc = bool(self.accept_kw("DESC"))
                if not desc:
                    self.accept_kw("ASC")
                nulls = None
                if self.accept_kw("NULLS"):
                    nulls = self.expect_kw("FIRST", "LAST").value.upper() == "FIRST"
                q.order.append((f.value, desc, nulls, f.pos))
                if not self.accept("punct", ","):
                    break
        if self.accept_kw("LIMIT"):
            q.limit = self.integer()
        if self.accept_kw("OFFSET"):
            q.offset = self.integer()
        if (t := self.peek()) is not None:
            raise self.unexpected(t)
        return q

    def condition(self):
        items, op = [self.unary()], None
        while (t := self.peek()) and t.kw("AND", "OR"):
            word = self.next().value.upper()
            if op and word != op:
                raise _malformed(f"unexpected token: '{t.value}'", t.pos)
            op = word
            items.append(self.unary())
        return items[0] if op is None else Logic(op, tuple(items))

    def unary(self):
        if self.accept_kw("NOT"):
            return Logic("NOT", (self.unary(),))
        if self.accept("punct", "("):
            c = self.condition()
            self.expect("punct", ")")
            return c
        f = self.ident()
        t = self.peek()
        if t and t.kw("NOT"):
            self.next()
            self.expect_kw("IN")
            return Cmp(f.value, "notin", self.values(), f.pos)
        if t and t.kw("IN"):
            self.next()
            return Cmp(f.value, "in", self.values(), f.pos)
        if t and t.kw("LIKE"):
            self.next()
            return Cmp(f.value, "like", self.literal(), f.pos)
        op = self.expect("op").value
        return Cmp(f.value, {"<>": "!="}.get(op, op), self.literal(), f.pos)

    def values(self) -> list[Lit]:
        self.expect("punct", "(")
        out = [self.literal()]
        while self.accept("punct", ","):
            out.append(self.literal())
        self.expect("punct", ")")
        return out

    def literal(self) -> Lit:
        t = self.next()
        try:
            if t.kind == "str":
                return Lit("string", _unescape(t.value[1:-1], t.pos), t.pos)
            if t.kind == "num":
                return Lit("number", Decimal(t.value), t.pos)
            if t.kind == "date":
                return Lit("date", date.fromisoformat(t.value), t.pos)
            if t.kind == "datetime":
                return Lit("datetime", datetime.fromisoformat(t.value), t.pos)
        except ValueError:
            raise _malformed(f"line 1:{t.pos} no viable alternative at character '{t.value}'", t.pos) from None
        if t.kind == "ident":
            word = t.value.upper()
            if word in ("TRUE", "FALSE"):
                return Lit("bool", word == "TRUE", t.pos)
            if word == "NULL":
                return Lit("null", None, t.pos)
            if word in ("TODAY", "YESTERDAY", "TOMORROW"):
                return Lit("datefn", (word, 0), t.pos)
            if word in ("LAST_N_DAYS", "NEXT_N_DAYS"):
                self.expect("punct", ":")
                return Lit("datefn", (word, self.integer()), t.pos)
        raise self.unexpected(t)


def parse(text: str) -> Query:
    if not text or not text.strip():
        raise SoqlError("MALFORMED_QUERY", "A query string has to be specified")
    return _Parser(text).query()


# ------------------------------------------------------------------ compile
@dataclass
class Selected:
    path: str  # canonical, e.g. Account.Name
    field: Field
    rel: Field | None  # the lookup field when the path goes through a parent
    label: str


@dataclass
class Plan:
    obj: SObject
    count_only: bool
    rows: Select  # without paging
    count: Select
    selected: list[Selected]
    rel_ids: dict[str, tuple[str, SObject]]  # relationship name -> (label of the parent's Id column, parent object)
    limit: int | None
    offset: int


class _Resolver:
    def __init__(self, obj: SObject):
        self.obj = obj
        self.base = TABLES[obj.name]
        self.joins: dict[str, tuple[Field, Any, SObject]] = {}  # relationship name -> (lookup field, alias, parent)

    def resolve(self, path: str, pos: int) -> tuple[Field, ColumnElement, Field | None, str]:
        parts = path.split(".")
        if len(parts) == 2 and parts[0].lower() == self.obj.name.lower():
            parts = parts[1:]
        if len(parts) == 1:
            f = self.obj.get(parts[0])
            if not f:
                raise SoqlError(
                    "INVALID_FIELD",
                    f"ERROR at Row:1:Column:{pos + 1}\nNo such column '{parts[0]}' on entity '{self.obj.name}'. If you are "
                    "attempting to use a custom field, be sure to append the '__c' after the custom field name.",
                )
            return f, self.base.c[f.name], None, f.name
        if len(parts) > 2:
            raise SoqlError("INVALID_FIELD", f"Relationship paths deeper than one level are not supported by this mock: {path}")
        lookup = self.obj.relationship(parts[0])
        if not lookup:
            raise SoqlError(
                "INVALID_FIELD",
                f"ERROR at Row:1:Column:{pos + 1}\nDidn't understand relationship '{parts[0]}' in field path. If you are "
                "attempting to use a custom relationship, be sure to append the '__r' after the custom relationship name.",
            )
        parent = OBJECTS[lookup.ref[0]]
        f = parent.get(parts[1])
        if not f:
            raise SoqlError(
                "INVALID_FIELD", f"ERROR at Row:1:Column:{pos + 1}\nNo such column '{parts[1]}' on entity '{parent.name}'."
            )
        if lookup.rel not in self.joins:
            self.joins[lookup.rel] = (lookup, TABLES[parent.name].alias(f"rel_{lookup.rel.lower()}"), parent)
        alias = self.joins[lookup.rel][1]
        return f, alias.c[f.name], lookup, f"{lookup.rel}.{f.name}"

    def from_(self):
        out = self.base
        for lookup, alias, _ in self.joins.values():
            out = out.outerjoin(alias, self.base.c[lookup.name] == alias.c.Id)
        return out


_NUMERIC = ("int", "double", "currency", "percent")


def _type_error(f: Field, quoted: bool) -> SoqlError:
    sf = {"datetime": "dateTime"}.get(f.type, f.type)
    if f.type in _NUMERIC:
        sf = "number"
    tail = "should be enclosed in quotes" if quoted else "should not be enclosed in quotes"
    return SoqlError("INVALID_FIELD", f"value of filter criterion for field '{f.name}' must be of type {sf} and {tail}")


def _value(f: Field, lit: Lit, today: date) -> Any:
    """The Python value to bind for `lit` against field `f`, or (start, end) for a date function."""
    if lit.kind == "null":
        return None
    if f.type in ("id", "reference"):
        if lit.kind != "string":
            raise _type_error(f, True)
        return normalise_id(lit.value) or lit.value
    if f.textual:
        if lit.kind != "string":
            raise _type_error(f, True)
        return lit.value
    if f.type in _NUMERIC:
        if lit.kind != "number":
            raise _type_error(f, False)
        return lit.value
    if f.type == "boolean":
        if lit.kind != "bool":
            raise _type_error(f, False)
        return lit.value
    if f.type in ("date", "datetime"):
        if lit.kind == "datefn":
            word, n = lit.value
            start, end = {
                "TODAY": (today, today + timedelta(days=1)),
                "YESTERDAY": (today - timedelta(days=1), today),
                "TOMORROW": (today + timedelta(days=1), today + timedelta(days=2)),
                "LAST_N_DAYS": (today - timedelta(days=n), today + timedelta(days=1)),
                "NEXT_N_DAYS": (today + timedelta(days=1), today + timedelta(days=n + 1)),
            }[word]
            if f.type == "datetime":
                start, end = (datetime.combine(d, time(), UTC) for d in (start, end))
            return ("range", start, end)
        if lit.kind != ("date" if f.type == "date" else "datetime"):
            raise _type_error(f, False)
        return lit.value
    raise _type_error(f, False)


def _compare(col: ColumnElement, f: Field, op: str, v: Any) -> ColumnElement:
    if isinstance(v, tuple) and v and v[0] == "range":
        _, s, e = v
        return {
            "=": lambda: and_(col >= s, col < e),
            "!=": lambda: or_(col < s, col >= e),
            "<": lambda: col < s,
            "<=": lambda: col < e,
            ">": lambda: col >= e,
            ">=": lambda: col >= s,
        }[op]()
    if v is None:
        if op == "=":
            return col.is_(None)
        if op == "!=":
            return col.is_not(None)
        raise SoqlError("MALFORMED_QUERY", f"null can only be compared with = or != (field '{f.name}')")
    if f.textual and op in ("=", "!="):
        expr = func.lower(col) == v.lower()
        return expr if op == "=" else or_(col.is_(None), not_(expr))
    if op == "!=":
        return or_(col.is_(None), col != v)
    return {"=": col.__eq__, "<": col.__lt__, ">": col.__gt__, "<=": col.__le__, ">=": col.__ge__}[op](v)


def compile_query(q: Query, today: date | None = None) -> Plan:
    obj = BY_LOWER.get(q.obj.lower())
    if not obj:
        raise SoqlError(
            "INVALID_TYPE",
            f"sObject type '{q.obj}' is not supported. If you are attempting to use a custom object, be sure to append "
            "the '__c' after the entity name. Please reference your WSDL or the describe call for the appropriate names.",
        )
    if q.offset > MAX_OFFSET:
        raise SoqlError("NUMBER_OUTSIDE_VALID_RANGE", f"Maximum SOQL offset allowed is {MAX_OFFSET}")
    today = today or datetime.now(UTC).date()
    r = _Resolver(obj)

    selected: list[Selected] = []
    for i, (path, pos) in enumerate(q.fields):
        f, col, lookup, canonical = r.resolve(path, pos)
        if any(s.path.lower() == canonical.lower() for s in selected):
            raise SoqlError("MALFORMED_QUERY", f"duplicate field selected: {canonical}")
        selected.append(Selected(canonical, f, lookup, f"c{i}"))

    def cond(node) -> ColumnElement:
        if isinstance(node, Logic):
            parts = [cond(x) for x in node.items]
            return {"AND": and_, "OR": or_}[node.op](*parts) if node.op != "NOT" else not_(parts[0])
        f, col, _, _ = r.resolve(node.path, node.pos)
        if node.op in ("in", "notin"):
            vals = [_value(f, lit, today) for lit in node.value]
            if any(isinstance(v, tuple) for v in vals):
                raise SoqlError("MALFORMED_QUERY", "Date functions are not allowed in IN lists")
            vals = [v for v in vals if v is not None]
            if f.textual:
                col, vals = func.lower(col), [v.lower() for v in vals]
            expr = col.in_(vals)
            return expr if node.op == "in" else or_(col.is_(None), not_(expr))
        if node.op == "like":
            if not (f.textual or f.type in ("id", "reference")) or node.value.kind != "string":
                raise SoqlError("INVALID_FIELD", f"invalid operator on {f.type} field '{f.name}': LIKE")
            return col.ilike(node.value.value)
        return _compare(col, f, node.op, _value(f, node.value, today))

    where = cond(q.where) if q.where is not None else None
    order = []
    for path, desc, nulls_first, pos in q.order:
        _, col, _, _ = r.resolve(path, pos)
        expr = col.desc() if desc else col.asc()
        first = (not desc) if nulls_first is None else nulls_first
        order.append(expr.nulls_first() if first else expr.nulls_last())

    base = r.base
    rel_ids = {}
    cols = [base.c.Id.label("__id")]
    for s in selected:
        if s.rel:
            alias = r.joins[s.rel.rel][1]
            if s.rel.rel not in rel_ids:
                lab = f"__rel_{len(rel_ids)}"
                rel_ids[s.rel.rel] = (lab, r.joins[s.rel.rel][2])
                cols.append(alias.c.Id.label(lab))
            cols.append(alias.c[s.field.name].label(s.label))
        else:
            cols.append(base.c[s.field.name].label(s.label))
    from_ = r.from_()
    rows = select(*cols).select_from(from_)
    count = select(func.count()).select_from(from_)
    if where is not None:
        rows, count = rows.where(where), count.where(where)
    rows = rows.order_by(*order, base.c.Id)
    return Plan(obj, q.count, rows, count, selected, rel_ids, q.limit, q.offset)
