"""ServiceNow encoded query (sysparm_query) → SQLAlchemy expression. User text never reaches SQL as SQL.

    state=3^assigned_to=<sys_id>                      ^ is AND
    state=1^ORstate=10                                ^OR binds to the condition before it: a^b^ORc = a AND (b OR c)
    location.u_site_code=Site 3^NQnumber=WO0010382    ^NQ starts a new query, OR-ed with the others
    numberSTARTSWITHWO00103^ORDERBYDESCnumber         ORDERBY / ORDERBYDESC (in order of appearance)
Operators: = != > >= < <= LIKE NOT LIKE STARTSWITH ENDSWITH IN NOT IN ISEMPTY ISNOTEMPTY ANYTHING BETWEEN (a@b).
Dot-walking through references works in conditions (parent.number=WO0010382, location.name=Chennai Foundry).
A reference compared with something that is not a sys_id matches on the referenced record's display value.
Dates take "YYYY-MM-DD HH:MM:SS" (UTC) or javascript:gs.dateGenerate('2026-10-07','09:00:00').
An unknown field makes its condition match no rows (glide.invalid_query.returns_no_rows), as on current releases.
"""

import re
from dataclasses import dataclass

from sqlalchemy import String, and_, cast, false, not_, or_, select, true
from sqlalchemy.sql import ColumnElement

from sim.vendors.servicenow.schema import SPECS, TABLES, Field, TableSpec
from sim.vendors.servicenow.values import SYS_ID, BadValue, to_db

_OPS = [
    "ISNOTEMPTY",
    "ISEMPTY",
    "NOT LIKE",
    "NOTLIKE",
    "NOT IN",
    "NOTIN",
    "STARTSWITH",
    "ENDSWITH",
    "BETWEEN",
    "ANYTHING",
    "LIKE",
    "IN",
    "!=",
    ">=",
    "<=",
    "=",
    ">",
    "<",
]
_TERM = re.compile(r"^([a-z0-9_.]+?)(" + "|".join(re.escape(o) for o in _OPS) + r")(.*)$", re.DOTALL)


class QueryError(ValueError):
    pass


@dataclass
class Parsed:
    where: ColumnElement
    order_by: list  # SQLAlchemy order expressions


def _value_expr(spec: TableSpec, f: Field, op: str, raw: str) -> ColumnElement:
    col = TABLES[spec.name].c[f.name]
    if op == "ANYTHING":
        return true()
    if op in ("ISEMPTY", "ISNOTEMPTY"):
        empty = or_(col.is_(None), col == "") if f.type == "string" else col.is_(None)
        return empty if op == "ISEMPTY" else not_(empty)
    if op in ("LIKE", "NOT LIKE", "NOTLIKE", "STARTSWITH", "ENDSWITH"):
        text_col = col if isinstance(col.type, String) or f.type == "string" else cast(col, String)
        e = {
            "STARTSWITH": lambda: text_col.istartswith(raw, autoescape=True),
            "ENDSWITH": lambda: text_col.iendswith(raw, autoescape=True),
        }.get(op, lambda: text_col.icontains(raw, autoescape=True))()
        return e if op in ("LIKE", "STARTSWITH", "ENDSWITH") else or_(col.is_(None), not_(e))
    if op in ("IN", "NOT IN", "NOTIN"):
        values = [to_db(f, v) for v in raw.split(",")]
        e = col.in_([v for v in values if v is not None])
        return e if op == "IN" else or_(col.is_(None), not_(e))
    if op == "BETWEEN":
        lo, _, hi = raw.partition("@")
        return and_(col >= to_db(f, lo), col <= to_db(f, hi))
    v = to_db(f, raw)
    if v is None:
        return col.is_(None) if op == "=" else col.is_not(None) if op == "!=" else false()
    return {
        "=": lambda: col == v,
        "!=": lambda: or_(col.is_(None), col != v),
        ">": lambda: col > v,
        ">=": lambda: col >= v,
        "<": lambda: col < v,
        "<=": lambda: col <= v,
    }[op]()


def _condition(spec: TableSpec, path: str, op: str, raw: str) -> ColumnElement:
    head, _, rest = path.partition(".")
    f = spec.by_name.get(head)
    if f is None:
        return false()
    col = TABLES[spec.name].c[f.name]
    if rest:
        if f.type != "reference":
            return false()
        sub = _condition(SPECS[f.ref], rest, op, raw)
        target = TABLES[f.ref]
        return col.in_(select(target.c.sys_id).where(sub))
    if f.type == "reference" and op not in ("ISEMPTY", "ISNOTEMPTY", "ANYTHING"):
        values = raw.split(",") if "IN" in op else [raw]
        by_display = op in ("LIKE", "NOT LIKE", "NOTLIKE", "STARTSWITH", "ENDSWITH") or not all(
            SYS_ID.match(v) for v in values if v
        )
        if by_display:
            target = SPECS[f.ref]
            tcol = TABLES[target.name].c[target.display]
            positive = op in ("=", "IN", "LIKE", "STARTSWITH", "ENDSWITH")
            match = {
                "STARTSWITH": lambda: tcol.istartswith(raw, autoescape=True),
                "ENDSWITH": lambda: tcol.iendswith(raw, autoescape=True),
                "LIKE": lambda: tcol.icontains(raw, autoescape=True),
                "NOT LIKE": lambda: tcol.icontains(raw, autoescape=True),
                "NOTLIKE": lambda: tcol.icontains(raw, autoescape=True),
            }.get(op, lambda: tcol.in_(values))()
            e = col.in_(select(TABLES[target.name].c.sys_id).where(match))
            return e if positive else or_(col.is_(None), not_(e))
    return _value_expr(spec, f, op, raw)


def parse_query(table: str, text: str | None) -> Parsed:
    spec = SPECS[table]
    t = TABLES[table]
    groups: list[ColumnElement] = []
    order_by: list = []
    for group in (text or "").replace("^^", "\x01").split("^NQ"):
        clauses: list[list[ColumnElement]] = []
        for term in group.split("^"):
            term = term.replace("\x01", "^").strip()
            if not term or term == "EQ":
                continue
            if term.startswith("ORDERBYDESC") or term.startswith("ORDERBY"):
                desc = term.startswith("ORDERBYDESC")
                name = term[len("ORDERBYDESC") :] if desc else term[len("ORDERBY") :]
                if name in spec.by_name:
                    order_by.append(t.c[name].desc() if desc else t.c[name].asc())
                continue
            is_or = term.startswith("OR")
            if is_or:
                term = term[2:]
            m = _TERM.match(term)
            if not m:
                raise QueryError(f"Invalid encoded query condition: {term}")
            try:
                cond = _condition(spec, m.group(1), m.group(2), m.group(3))
            except BadValue:
                cond = false()  # an unparseable value matches nothing, as on an instance
            if is_or and clauses:
                clauses[-1].append(cond)
            else:
                clauses.append([cond])
        if clauses:
            groups.append(and_(*[or_(*c) if len(c) > 1 else c[0] for c in clauses]))
    where = or_(*groups) if len(groups) > 1 else groups[0] if groups else true()
    return Parsed(where, order_by)
