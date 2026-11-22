# ruff: noqa: ARG001 - every step has the STEPS signature (records, cfg, ctx); not every step needs ctx
"""Transform steps (plan 6, task C4): currency, timestamps, units, code tables, filter, expression, aggregation,
join, enrichment.

Every step that replaces a value keeps the source value in meta.source; x_fx also records the rate it used in meta.fx,
so a figure can always be traced to the rate that produced it. A value a step cannot convert is rejected with a
reason, never guessed.
"""

import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import text

from di.connectors.generic import EUR_PER_USD, INR_PER_USD
from di.workflow.steps.core import (
    Rec,
    Reject,
    StepCtx,
    StepError,
    StepResult,
    as_list,
    clone,
    compile_expr,
    condition,
    get,
    iso_z,
    keep_source,
    num,
    opt,
    parse_ts,
    present,
    put,
    zone,
)

# the settings each step reads (keys of di/workflow/blocks.py; the ones marked * are not in the catalogue: steps
# take them when a caller passes them, with these defaults)
KEYS = {
    "x_fx": {
        "currency": "currency", "rate_date": "rate_date", "rate_table": "rate_table",
        "fields": "fields",  # Amount fields, default ["amount"]
        "currency_field": "currency_field",  # default "currency"; "" none
        "source_currency": "source_currency",  # default "": USD
        "date_field": "date_field",  # default "date"; "" the run's date
    },
    "x_utc": {"fields": "fields", "zone": "source_zone"},
    "x_units": {"units": "units"},
    "x_lookup": {"tables": "tables", "on_missing": "on_missing"},  # * on_missing reject | keep, default reject
    "x_filter": {"condition": "condition"},
    "x_expr": {"target": "target", "expression": "expression"},
    "x_agg": {"group_by": "group_by", "totals": "totals"},
    "x_join": {"input": "input", "key": "key", "how": "how", "into": "into"},  # * how inner | left; into = input
    "x_enrich": {"model": "model", "key": "key", "fields": "fields", "into": "into", "table": "table"},  # * the last 3
}  # fmt: skip


# ------------------------------------------------------------------ x_fx
FIXED_RATE_DATE = date(2026, 10, 6)  # the demo's rate date ("Currency at 83.5 (rate dated 2026-10-06)")
FIXED_RATES = {"USD": Decimal(1), "INR": INR_PER_USD, "EUR": EUR_PER_USD}  # currency per USD, as migration 0017 seeds
CENT = Decimal("0.01")


def _rates(ctx: StepCtx, table: str, currencies: set[str]) -> dict[str, list[tuple[date, Decimal]]]:
    """Each currency's dated rates (units per USD), oldest first: from fx_rate, or the fixed demo rates without a
    session."""
    if table != "fx_rate":
        raise StepError(f"unknown rate table {table}")
    if ctx.s is None:
        return {c: [(FIXED_RATE_DATE, r)] for c, r in FIXED_RATES.items() if c in currencies}
    rows = ctx.s.execute(
        text("SELECT currency, date, usd_rate FROM fx_rate WHERE currency = ANY(:c) ORDER BY currency, date"),
        {"c": sorted(currencies)},
    ).all()
    out: dict[str, list[tuple[date, Decimal]]] = {}
    for cur, d, rate in rows:
        out.setdefault(cur, []).append((d, Decimal(str(rate))))
    return out


def _pick(rates: list[tuple[date, Decimal]], on: date) -> tuple[date, Decimal]:
    """The newest rate dated on or before `on`; before the first rate, the first one."""
    best = rates[0]
    for d, r in rates:
        if d <= on:
            best = (d, r)
    return best


def _named(cfg: dict, key: str, default: str) -> str:
    """A setting that names a field: missing → its default; set empty → "" (no such field)."""
    v = (cfg or {}).get(key, default)
    return default if v is None else str(v).strip()


def x_fx(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Each Amount field (`fields`, default amount) to the target currency at a dated rate: the rate of the record's
    Date field (`rate_date` record; Date field empty or no date: the run's) or the run's date (`run`). The currency
    an amount is in is the record's Currency field, else the Source currency, else USD (Currency field empty: the
    Source currency for every record). The amount goes source → USD → target; meta.fx[field] = {from, to, rate,
    rate_date, source_value} (plus target_rate when the target is not USD), and the Currency field (when there is
    one) becomes the target. A currency without a rate is rejected (rule `fx`)."""
    k = KEYS["x_fx"]
    target = str(opt(cfg, k["currency"], "USD")).upper()
    by_run = opt(cfg, k["rate_date"], "record") == "run"
    fields = as_list(opt(cfg, k["fields"], ["amount"]))
    cur_f, date_f = _named(cfg, k["currency_field"], "currency"), _named(cfg, k["date_field"], "date")
    fallback = str(opt(cfg, k["source_currency"], "USD")).upper()

    def source_of(r: Rec) -> str:
        return str((get(r, cur_f) if cur_f else None) or fallback).upper()

    wanted = {target} | {source_of(r) for r in recs}
    rates = _rates(ctx, opt(cfg, k["rate_table"], "fx_rate"), wanted)
    if target not in rates:
        raise StepError(f"no rate for the target currency {target}")
    out, rejected = [], []
    for r in recs:
        src = source_of(r)
        rd = parse_ts(get(r, date_f)) if date_f else None
        on = ctx.now.date() if by_run or rd is None else rd.date()
        if src not in rates:
            rejected.append(Reject(r, cur_f or None, "fx", src, f"no rate for {src} on {on.isoformat()}"))
            continue
        c, bad = clone(r), None
        for f in fields:
            v = get(r, f)
            if v is None:
                continue
            try:
                a = Decimal(str(v))
            except InvalidOperation:
                bad = Reject(r, f, "fx", v, f"{f} {v!r} is not an amount")
                break
            sd, sr = _pick(rates[src], on)
            td, tr = _pick(rates[target], on)
            put(c, f, float((a / sr * tr).quantize(CENT)) if src != target else v)
            note = {"from": src, "to": target, "rate": float(sr), "rate_date": sd.isoformat(), "source_value": v}
            if target != "USD":
                note |= {"target_rate": float(tr), "target_rate_date": td.isoformat()}
            c.meta.setdefault("fx", {})[f] = note
        if bad:
            rejected.append(bad)
            continue
        if cur_f and (get(r, cur_f) is not None or src != target):
            put(c, cur_f, target)
        out.append(c)
    return StepResult(out, rejected, {})


# ------------------------------------------------------------------ x_utc
def _looks_like_time(v) -> bool:
    return isinstance(v, str) and len(v) >= 16 and v[10:11] in ("T", " ") and parse_ts(v) is not None


def x_utc(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Timestamps to UTC ("…Z"). A value with an offset keeps its instant; a local one is read in the source zone
    (`record`: it is taken as UTC). Fields empty: every top-level field that holds a date and time."""
    k = KEYS["x_utc"]
    fields = as_list(opt(cfg, k["fields"], []))
    zname = opt(cfg, k["zone"], "record")
    tz = zone(None if zname == "record" else zname)
    out, rejected = [], []
    for r in recs:
        c, bad = clone(r), None
        for f in fields or [f for f, v in r.data.items() if _looks_like_time(v)]:
            v = get(r, f)
            if v is None or v == "":
                continue
            d = parse_ts(v) if isinstance(v, str) else None
            if d is None:
                bad = Reject(r, f, "utc", v, f"{f} {v!r} is not a timestamp")
                break
            if isinstance(v, str) and not _has_offset(v):
                d = d.replace(tzinfo=tz)
            new = iso_z(d)
            if new != v:
                keep_source(c, f, v)
                put(c, f, new)
        if bad:
            rejected.append(bad)
        else:
            out.append(c)
    return StepResult(out, rejected, {})


def _has_offset(v: str) -> bool:
    return v.endswith("Z") or bool(re.search(r"[+-]\d{2}:?\d{2}$", v[10:]))


# ------------------------------------------------------------------ x_units
_DIM = {  # unit -> (dimension, factor to the dimension's base unit)
    "w": ("power", 1.0), "kw": ("power", 1e3), "mw": ("power", 1e6),
    "wh": ("energy", 1.0), "kwh": ("energy", 1e3), "mwh": ("energy", 1e6),
    "g": ("mass", 1e-3), "kg": ("mass", 1.0), "t": ("mass", 1e3), "lb": ("mass", 0.45359237),
    "mm": ("length", 1e-3), "cm": ("length", 1e-2), "m": ("length", 1.0), "km": ("length", 1e3),
    "mi": ("length", 1609.344), "ft": ("length", 0.3048), "in": ("length", 0.0254),
    "min": ("time", 1 / 60), "h": ("time", 1.0), "days": ("time", 24.0), "months": ("time", 730.5),
    "years": ("time", 8766.0),
    "ea": ("count", 1.0), "pcs": ("count", 1.0), "dozen": ("count", 12.0),
}  # fmt: skip
_ALIAS = {"hr": "h", "hrs": "h", "hours": "h", "hour": "h", "day": "days", "d": "days", "month": "months",
          "mo": "months", "year": "years", "yr": "years", "y": "years", "each": "ea", "pc": "pcs", "piece": "pcs",
          "mins": "min", "minutes": "min", "tonne": "t", "tonnes": "t", "lbs": "lb", "kgs": "kg"}  # fmt: skip
_QTY = re.compile(r"\s*(-?\d[\d,]*(?:\.\d+)?)\s*([A-Za-z]+)\s*")


def _unit(u: str | None) -> str | None:
    if not u:
        return None
    u = u.strip().lower()
    u = _ALIAS.get(u, u)
    return u if u in _DIM else None


def convert(value: float, frm: str, to: str) -> float:
    a, b = _unit(frm), _unit(to)
    if a is None or b is None or _DIM[a][0] != _DIM[b][0]:
        raise ValueError(f"cannot convert {frm} to {to}")
    return round(value * _DIM[a][1] / _DIM[b][1], 6)


def _pairs(units) -> list[tuple[str, str | None, str]]:
    """The units setting -> (field, from or None, to): blocks.py's {field: to unit}, or rows {field, from, to}, or
    {field: "W>kW"}."""
    if isinstance(units, dict):
        out: list[tuple[str, str | None, str]] = []
        for f, to in units.items():
            frm, sep, t = str(to).replace("->", ">").partition(">")
            out.append((f, frm.strip(), t.strip()) if sep else (f, None, str(to)))
        return out
    return [(u["field"], u.get("from"), u["to"]) for u in units or []]


def x_units(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Values to the canonical unit; the source value is kept. The unit a value is in: the setting's `from`, else the
    value's own suffix ("7500 W"), else a `<field>_unit` field, else meta.units[field]. A value with no unit, or one
    that does not convert to the target, is rejected (rule `units`)."""
    pairs = _pairs(opt(cfg, KEYS["x_units"]["units"], {}))
    out, rejected = [], []
    for r in recs:
        c, bad = clone(r), None
        for f, frm, to in pairs:
            v = get(r, f)
            if v is None or v == "":
                continue
            n, unit = num(v), frm
            if n is None and isinstance(v, str) and (m := _QTY.fullmatch(v)):
                n, unit = float(m.group(1).replace(",", "")), unit or m.group(2)
                n = int(n) if n == int(n) else n
            elif isinstance(v, int | float) and not isinstance(v, bool):
                n = v
            unit = unit or get(r, f"{f}_unit") or (r.meta.get("units") or {}).get(f)
            if n is None or not unit:
                bad = Reject(r, f, "units", v, f"{f} {v!r} has no unit to convert from")
                break
            try:
                new = convert(n, unit, to)
            except ValueError as e:
                bad = Reject(r, f, "units", v, str(e))
                break
            keep_source(c, f, v)
            put(c, f, new)
        if bad:
            rejected.append(bad)
        else:
            out.append(c)
    return StepResult(out, rejected, {})


# ------------------------------------------------------------------ x_lookup
def grade_v3(v: str) -> str | None:
    """Grade table v3: "Grade B" → B, "B+" → B, "C-" → C."""
    letter = str(v).strip().removeprefix("Grade").strip()[:1].upper()
    return letter if letter in ("A", "B", "C", "D", "E") else None


def location(v: str) -> str | None:
    """Plant codes as the SAP adapter decodes them (2010 → Warehouse 1, 1030 → Site 3); a decoded name is kept."""
    s = str(v).strip()
    plants = {"2010": "Warehouse 1", "2020": "Warehouse 2", "2030": "Repair centre"}
    if s in plants:
        return plants[s]
    if m := re.fullmatch(r"10(\d)0", s):
        return f"Site {m[1]}"
    return s if s in plants.values() or re.fullmatch(r"Site \d.*", s) else None


STATUS = {"BOOKED": "active", "EXPIRED": "expired", "EVERGREEN": "evergreen", "TERMINATED": "terminated",
          "CONFIRMED": "confirmed", "FORECAST": "forecast", "CLOSED WON": "confirmed", "CLOSED LOST": "lost"}  # fmt: skip
REASON = {"DEF": "defect", "EOL": "end of lease", "EXC": "excess", "UPG": "upgrade", "RET": "return"}


def _table(t) -> Callable[[str], str | None]:
    if isinstance(t, dict):
        low = {str(k).lower(): v for k, v in t.items()}
        return lambda v: t.get(v, low.get(str(v).lower()))
    named: dict[str, Callable[[str], str | None]] = {
        "grade": grade_v3, "grade_v3": grade_v3, "condition": grade_v3, "location": location,
        "status": lambda v: STATUS.get(str(v).strip().upper()),
        "reason": lambda v: REASON.get(str(v).strip().upper()),
    }  # fmt: skip
    if t not in named:
        raise StepError(f"unknown code table {t}")
    return named[t]


def x_lookup(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Codes through a code table ({field: table}: grade, status, location, condition, reason, or an inline
    {code: value}); the source value is kept. An unknown code is rejected (rule `lookup`)."""
    k = KEYS["x_lookup"]
    tables = {f: _table(t) for f, t in (opt(cfg, k["tables"], {}) or {}).items()}
    keep_unknown = opt(cfg, k["on_missing"], "reject") == "keep"
    out, rejected = [], []
    for r in recs:
        c, bad = clone(r), None
        for f, look in tables.items():
            v = get(r, f)
            if v is None or v == "":
                continue
            new = look(v)
            if new is None:
                if keep_unknown:
                    continue
                bad = Reject(r, f, "lookup", v, f"no code {v!r} in the {f} table")
                break
            if new != v:
                keep_source(c, f, v)
                put(c, f, new)
        if bad:
            rejected.append(bad)
        else:
            out.append(c)
    return StepResult(out, rejected, {})


# ------------------------------------------------------------------ x_filter, x_expr
def x_filter(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Records that meet the condition go on; the rest are counted (side.filtered), not rejected."""
    test = condition(opt(cfg, KEYS["x_filter"]["condition"], []))
    out = [clone(r) for r in recs if test(r)]
    return StepResult(out, [], {"filtered": len(recs) - len(out)})


def x_expr(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """target = expression (see core.compile_expr), recorded in meta.expr[target]. Both empty: pass-through."""
    k = KEYS["x_expr"]
    target, src = opt(cfg, k["target"], ""), opt(cfg, k["expression"], "")
    if not target and not src:
        return StepResult([clone(r) for r in recs], [], {})
    if not target or not src:
        raise StepError("an expression needs both a target field and an expression")
    e = compile_expr(src)
    out = []
    for r in recs:
        c = clone(r)
        old = get(r, target)
        if old is not None:
            keep_source(c, target, old)
        put(c, target, e(r))
        c.meta.setdefault("expr", {})[target] = src
        out.append(c)
    return StepResult(out, [], {})


# ------------------------------------------------------------------ x_agg
def _total(fn: str, vals: list):
    if fn == "count":
        return len([v for v in vals if v is not None])
    ns = [n for n in (num(v) for v in vals) if n is not None]
    if not ns:
        return None
    r = {"sum": sum(ns), "min": min(ns), "max": max(ns), "avg": sum(ns) / len(ns)}.get(fn)
    if r is None:
        raise StepError(f"unknown total {fn} (sum, count, min, max, avg)")
    total = round(r, 6)
    return int(total) if total == int(total) else total


def x_agg(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """One record per group: the group-by fields, each total and `count`. A total is a field name (summed under its
    own name) or {field, fn: sum|count|min|max|avg, as}. Neither set: pass-through."""
    k = KEYS["x_agg"]
    by, totals = as_list(opt(cfg, k["group_by"], [])), list(opt(cfg, k["totals"], []))
    if not by and not totals:
        return StepResult([clone(r) for r in recs], [], {})
    specs = [(t, "sum", t) if isinstance(t, str) else (t["field"], t.get("fn", "sum"), t.get("as") or t["field"]) for t in totals]
    groups: dict[tuple, list[Rec]] = {}
    for r in recs:
        groups.setdefault(tuple(get(r, f) for f in by), []).append(r)
    out = []
    for key, members in groups.items():
        data = dict(zip(by, key, strict=True))
        for f, fn, name in specs:
            data[name] = _total(fn, [get(m, f) for m in members])
        data.setdefault("count", len(members))
        ext = "|".join(str(v) for v in key) if by else "all"
        out.append(
            Rec(ext, members[0].resource, data, None, {"group_size": len(members), "members": [m.ext_id for m in members[:100]]})
        )
    return StepResult(out, [], {"groups": len(out)})


# ------------------------------------------------------------------ x_join, x_enrich
def x_join(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Joins the main input with a second one on a key, inside one tenant: a record of the second input is one the
    engine tagged with that step (meta.node == input) or whose resource is `input`. A matched record gets the other's
    data under data[into] (default: the input's name). `how` inner (default; unmatched records are counted and do not
    go on) or left. Input empty: pass-through."""
    k = KEYS["x_join"]
    other, key = opt(cfg, k["input"], ""), opt(cfg, k["key"], "")
    if not other:
        return StepResult([clone(r) for r in recs], [], {})
    if not key:
        raise StepError("a join needs a key")
    how, into = opt(cfg, k["how"], "inner"), opt(cfg, k["into"], other)
    is_right = lambda r: r.meta.get("node") == other or r.resource == other  # noqa: E731
    right: dict[tuple, Rec] = {}
    for r in recs:
        if is_right(r) and present(get(r, key)):
            right.setdefault((str(get(r, "tenant")), str(get(r, key))), r)
    out, unmatched = [], 0
    for r in recs:
        if is_right(r):
            continue
        m = right.get((str(get(r, "tenant")), str(get(r, key))))
        if m is None:
            unmatched += 1
            if how == "left":
                out.append(clone(r))
            continue
        c = clone(r)
        put(c, into, dict(m.data))
        out.append(c)
    return StepResult(out, [], {"unmatched": unmatched})


MODEL_NAMES = {"Asset & component": "asset", "Condition & eligibility": "condition", "Demand opportunity": "demand",
               "Outcome": "outcome"}  # fmt: skip


def x_enrich(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Adds the canonical record of `model` whose key is the record's `key` field under data[into] (default: the
    model), optionally only some fields; the record's own fields are untouched. A key with no canonical record goes
    on unenriched (side.missing). Model or key empty: pass-through."""
    k = KEYS["x_enrich"]
    model, key = opt(cfg, k["model"], ""), opt(cfg, k["key"], "")
    if not model or not key:
        return StepResult([clone(r) for r in recs], [], {})
    model = MODEL_NAMES.get(model, model)
    fields, into = as_list(opt(cfg, k["fields"], [])), opt(cfg, k["into"], model)
    keys = sorted({str(get(r, key)) for r in recs if present(get(r, key))})
    table = opt(cfg, k["table"], None)
    if table is None:
        if ctx.s is None:
            raise StepError("enrichment needs the canonical store")
        rows = ctx.s.execute(
            text("SELECT key, data FROM canonical WHERE model = :m AND key = ANY(:k)"), {"m": model, "k": keys}
        ).all()
        table = {kk: d for kk, d in rows}  # noqa: C416 - Row objects, not 2-tuples
    out, missing = [], 0
    for r in recs:
        c = clone(r)
        found = table.get(str(get(r, key))) if present(get(r, key)) else None
        if found is None:
            missing += 1
        else:
            put(c, into, {f: found.get(f) for f in fields} if fields else dict(found))
            c.meta.setdefault("enrich", {})[into] = {"model": model, "key": str(get(r, key))}
        out.append(c)
    return StepResult(out, [], {"missing": missing})


STEPS = {
    "x_fx": x_fx, "x_utc": x_utc, "x_units": x_units, "x_lookup": x_lookup, "x_filter": x_filter,
    "x_expr": x_expr, "x_agg": x_agg, "x_join": x_join, "x_enrich": x_enrich,
}  # fmt: skip
