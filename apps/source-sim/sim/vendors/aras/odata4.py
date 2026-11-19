"""A small OData v4 query engine over in-memory rows, used by the Aras and AssetWise mocks.

Supports what their clients send: $filter (eq ne gt ge lt le, and or not, parentheses, contains / startswith /
endswith / tolower / toupper, null, strings, numbers, booleans, date-time literals, paths such as
`created_by_id/keyed_name` and Aras's bracketed names such as `[Part BOM]/quantity`), $select, $expand with nested
options (`Part BOM($select=quantity;$expand=related_id)`), $orderby, $top, $skip, $count, and server-driven paging
(`Prefer: odata.maxpagesize=N` -> `@odata.nextLink` with `$skiptoken`).

Rows are plain dicts. Paths are resolved by a `resolve(row, name)` callable from the mock, so item properties and
relationships can be followed lazily.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode


class QueryError(ValueError):
    """A malformed query option (answered 400)."""


# ------------------------------------------------------------------ splitting
def split_top(text: str, sep: str) -> list[str]:
    """Split on `sep` outside parentheses, brackets and quotes."""
    out, depth, cur, quoted = [], 0, [], False
    for ch in text:
        if ch == "'":
            quoted = not quoted
        elif not quoted and ch in "([":
            depth += 1
        elif not quoted and ch in ")]":
            depth -= 1
        if ch == sep and depth == 0 and not quoted:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if depth != 0 or quoted:
        raise QueryError(f"Unbalanced expression: {text}")
    out.append("".join(cur))
    return [x.strip() for x in out if x.strip()]


def parse_expand(text: str | None) -> dict[str, dict[str, str]]:
    """'Part BOM($select=quantity;$expand=related_id),created_by_id' -> {'Part BOM': {'$select': ..}, 'created_by_id': {}}."""
    out: dict[str, dict[str, str]] = {}
    for part in split_top(text or "", ","):
        m = re.fullmatch(r"\[?([^()\[\]]+?)\]?\s*(?:\((.*)\))?", part, re.S)
        if not m:
            raise QueryError(f"Invalid $expand: {part}")
        opts: dict[str, str] = {}
        for o in split_top(m.group(2) or "", ";"):
            k, _, v = o.partition("=")
            if not k.startswith("$"):
                raise QueryError(f"Invalid $expand option: {o}")
            opts[k.strip()] = v.strip()
        out[m.group(1).strip()] = opts
    return out


def parse_select(text: str | None) -> list[str] | None:
    if not text or text.strip() == "*":
        return None
    return [s.strip().strip("[]") for s in split_top(text, ",")]


# ------------------------------------------------------------------ values
_DT = re.compile(r"^\d{4}-\d\d-\d\d(?:T\d\d:\d\d(?::\d\d(?:\.\d+)?)?)?(?:Z|[+-]\d\d:\d\d)?$")


def as_datetime(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    if isinstance(v, str) and _DT.match(v):
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    return None


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str) and re.fullmatch(r"-?\d+(\.\d+)?", v.strip()):
        return float(v)
    return None


def compare(a: Any, op: str, b: Any) -> bool:
    if op in ("eq", "ne"):
        if a is None or b is None:
            res = a is None and b is None
        else:
            da, db = as_datetime(a), as_datetime(b)
            na, nb = _num(a), _num(b)
            if da and db:
                res = da == db
            elif na is not None and nb is not None and not (isinstance(a, str) and isinstance(b, str)):
                res = na == nb
            else:
                res = str(a) == str(b) if not isinstance(a, bool) and not isinstance(b, bool) else a == b
        return res if op == "eq" else not res
    if a is None or b is None:
        return False
    da, db = as_datetime(a), as_datetime(b)
    if da and db:
        a, b = da, db
    else:
        na, nb = _num(a), _num(b)
        if na is not None and nb is not None:
            a, b = na, nb
        else:
            a, b = str(a), str(b)
    return {"gt": a > b, "ge": a >= b, "lt": a < b, "le": a <= b}[op]


# ------------------------------------------------------------------ $filter
_TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<dt>\d{4}-\d\d-\d\d(?:T\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)?)?(?![\w-]))"
    r"|(?P<num>-?\d+(?:\.\d+)?(?![\w-]))|(?P<br>\[[^\]]+\](?:/(?:\[[^\]]+\]|[\w\-@.]+))*)"
    r"|(?P<name>[A-Za-z_$][\w\-@.]*(?:/(?:\[[^\]]+\]|[\w\-@.]+))*)|(?P<p>[(),]))"
)
FUNCS = {"contains", "startswith", "endswith", "tolower", "toupper"}
OPS = {"eq", "ne", "gt", "ge", "lt", "le"}

Resolver = Callable[[dict, str], Any]


def _tokens(text: str) -> list[tuple[str, str]]:
    pos, out = 0, []
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise QueryError(f"Syntax error at position {pos} in $filter: {text}")
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        pos = m.end()
        while pos < len(text) and text[pos] == " ":
            pos += 1
    return out


class _Filter:
    def __init__(self, text: str):
        self.toks = _tokens(text)
        self.i = 0
        self.fn = self._or()
        if self.i != len(self.toks):
            raise QueryError(f"Unexpected '{self.toks[self.i][1]}' in $filter")

    def _peek(self, value: str | None = None) -> bool:
        if self.i >= len(self.toks):
            return False
        return value is None or self.toks[self.i][1] == value

    def _take(self, value: str | None = None) -> tuple[str, str]:
        if self.i >= len(self.toks) or (value is not None and self.toks[self.i][1] != value):
            raise QueryError(f"Expected '{value}' in $filter")
        self.i += 1
        return self.toks[self.i - 1]

    def _or(self):
        left = self._and()
        while self._peek("or"):
            self._take()
            right = self._and()
            left = (lambda a, b: lambda r, g: a(r, g) or b(r, g))(left, right)
        return left

    def _and(self):
        left = self._not()
        while self._peek("and"):
            self._take()
            right = self._not()
            left = (lambda a, b: lambda r, g: a(r, g) and b(r, g))(left, right)
        return left

    def _not(self):
        if self._peek("not"):
            self._take()
            inner = self._not()
            return lambda r, g: not inner(r, g)
        return self._cmp()

    def _cmp(self):
        left = self._value()
        if self.i < len(self.toks) and self.toks[self.i][1] in OPS:
            op = self._take()[1]
            right = self._value()

            def test(r, g, left=left, right=right, op=op):
                a, b = left(r, g), right(r, g)
                if isinstance(a, list):  # a path through a relationship: any related item matches
                    return any(compare(x, op, b) for x in a)
                return compare(a, op, b)

            return test
        return lambda r, g: bool(left(r, g))

    def _value(self):
        kind, tok = self._take()
        if tok == "(":
            inner = self._or()
            self._take(")")
            return inner
        if kind == "str":
            s = tok[1:-1].replace("''", "'")
            return lambda r, g: s
        if kind == "dt":
            d = as_datetime(tok)
            return lambda r, g: d
        if kind == "num":
            n = float(tok) if "." in tok else int(tok)
            return lambda r, g: n
        if kind == "name" and tok in ("null", "true", "false"):
            v = {"null": None, "true": True, "false": False}[tok]
            return lambda r, g: v
        if kind == "name" and tok in FUNCS and self._peek("("):
            self._take("(")
            args = [self._value()]
            while self._peek(","):
                self._take(",")
                args.append(self._value())
            self._take(")")
            return self._func(tok, args)
        if kind in ("name", "br"):
            path = tok
            return lambda r, g: g(r, path)
        raise QueryError(f"Unexpected '{tok}' in $filter")

    @staticmethod
    def _func(name, args):
        def call(r, g):
            vals = [a(r, g) for a in args]
            if name in ("tolower", "toupper"):
                v = vals[0]
                return None if v is None else (str(v).lower() if name == "tolower" else str(v).upper())
            if len(vals) != 2:
                raise QueryError(f"{name} takes two arguments")
            hay, needle = vals
            if hay is None or needle is None:
                return False
            hay, needle = str(hay), str(needle)
            return {"contains": needle in hay, "startswith": hay.startswith(needle), "endswith": hay.endswith(needle)}[name]

        return call


def parse_filter(text: str | None) -> Callable[[dict, Resolver], bool] | None:
    if not text or not text.strip():
        return None
    return _Filter(text).fn


def path_value(row: dict, path: str, resolve: Resolver) -> Any:
    """Follow 'a/b/c' (names may be bracketed) from a row; lists fan out."""
    parts = [p.strip("[]") for p in re.split(r"/(?![^\[]*\])", path)]
    cur: Any = [row]
    many = False
    for p in parts:
        nxt = []
        for c in cur:
            if c is None:
                continue
            v = resolve(c, p)
            if isinstance(v, list):
                many = True
                nxt.extend(v)
            else:
                nxt.append(v)
        cur = nxt
    if many:
        return cur
    return cur[0] if cur else None


# ------------------------------------------------------------------ $orderby, paging
def order(rows: list[dict], text: str | None, resolve: Resolver) -> list[dict]:
    if not text:
        return rows
    for part in reversed(split_top(text, ",")):
        name, _, direction = part.partition(" ")
        desc = direction.strip().lower() == "desc"

        def key(r, name=name):
            v = path_value(r, name, resolve)
            return (v is None, v if not isinstance(v, str) or _num(v) is None else float(v))

        try:
            rows = sorted(rows, key=key, reverse=desc)
        except TypeError:
            rows = sorted(rows, key=lambda r, name=name: str(path_value(r, name, resolve)), reverse=desc)
    return rows


def int_option(params, name: str) -> int | None:
    v = params.get(name)
    if v is None or v == "":
        return None
    if not re.fullmatch(r"\d+", v):
        raise QueryError(f"Invalid value '{v}' for {name}")
    return int(v)


def max_page_size(prefer: str | None) -> int | None:
    m = re.search(r"odata\.maxpagesize\s*=\s*(\d+)", prefer or "")
    return int(m.group(1)) if m else None


def window(rows: list, params, prefer: str | None, url_base: str) -> tuple[list, str | None, int | None]:
    """Apply $skip/$top and server-driven paging. Returns (page, nextLink or None, applied page size)."""
    skip = int_option(params, "$skip") or 0
    top = int_option(params, "$top")
    token = int_option(params, "$skiptoken") or 0
    rows = rows[skip:]
    if top is not None:
        rows = rows[:top]
    size = max_page_size(prefer)
    if size is None or size <= 0:
        return rows[token:], None, None
    page = rows[token : token + size]
    nxt = None
    if token + size < len(rows):
        q = [(k, v) for k, v in params.multi_items() if k != "$skiptoken"] + [("$skiptoken", str(token + size))]
        nxt = url_base + "?" + urlencode(q, quote_via=quote, safe="$(),;='/:")
    return page, nxt, size
