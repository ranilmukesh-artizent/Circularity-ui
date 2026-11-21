"""The field mapping a person edits is the one a sync applies (plan 6, task A4).

A source's mapping is versioned in table `field_mapping` (one row per saved version; Revert writes a new version equal
to an older one). A version holds `MapRow`s:

    MapRow(src="grade_text", model="condition", field="grade", rule="upper")

- `src` is a dotted path into the source record's payload ("audit_data.status", "items.0.label"); a key that itself
  contains dots or dashes ("EKPO-NETPR") is found as it is first.
- `rule`: copy | upper | lower | number | int | date | utc | units:<from>><to> | fx:<currency> | code:<table>, and
  the internal rule `code`: "keep what the adapter's own code maps for this canonical field".

How a sync uses it (sync.run_sync, at the adapter.map call):
- **No version** (every demo source at the start): the adapter's code mapping runs unchanged.
- **Python adapters** (the 21 demo sources): their code mapping stays the default and `overlay()` changes it per
  canonical field. The fields the Data Mapping tab shows (the demo's MAPPINGS rows, `builtin`) are the ones a person
  controls: a row whose rule is `code` keeps the code's fact; an edited row (any other rule) replaces the fact for its
  (model, field); an added row adds one; a builtin field with no row any more is dropped. Facts the tab does not show
  are never touched.
- **Configured sources** (no Python adapter, plan 6 A3): `map()` is `apply_rows()`.
- A row whose `src` is missing in a record fails only that record, with `MissingField("missing field {src}")`. For a
  Python adapter that is checked where the code mapping produced the row's field for that record (so a row is only
  required of the records, and resources, that feed it); an added row is applied where its `src` is present.

How the Data Mapping tab's rows (source field, sample, canonical field, normalised, rule text) become MapRows:
`rows_from_maps()`. A row equal to the demo's starting row (same source field, canonical field and rule text) is
`code` (it may name a display namespace such as movement.ts that is not a store model: the code's facts are kept). A
rule text that names a rule ("upper", "fx:INR", "units:kg>t", "Timestamp to UTC", "Integer" ...) is that
rule; any other text is a label: `code` on a starting row's source and canonical field, else `copy`.
"""

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di import golden
from di.canonical.schema import MODELS
from di.canonical.store import Fact
from di.connectors.generic import FX_NOTE, to_usd, utc

CODE = "code"  # keep the adapter's own mapping for this canonical field
SIMPLE = ("copy", "upper", "lower", "number", "int", "date", "utc")
LABEL = {
    "copy": "Pass-through",
    "upper": "Upper case",
    "lower": "Lower case",
    "number": "Number",
    "int": "Integer",
    "date": "Date",
    "utc": "Timestamp to UTC",
}
ALIASES = {
    "pass-through": "copy", "passthrough": "copy", "copy": "copy", "upper": "upper", "uppercase": "upper",
    "upper case": "upper", "lower": "lower", "lowercase": "lower", "lower case": "lower", "number": "number",
    "decimal": "number", "int": "int", "integer": "int", "date": "date", "utc": "utc", "timestamp to utc": "utc",
}  # fmt: skip
# units: factor to a base unit per dimension
UNITS: dict[str, tuple[str, float]] = {
    "mg": ("mass", 1e-6), "g": ("mass", 1e-3), "kg": ("mass", 1.0), "t": ("mass", 1000.0), "lb": ("mass", 0.45359237),
    "mm": ("length", 1e-3), "cm": ("length", 1e-2), "m": ("length", 1.0), "km": ("length", 1000.0),
    "in": ("length", 0.0254), "ft": ("length", 0.3048),
    "s": ("time", 1.0), "min": ("time", 60.0), "h": ("time", 3600.0), "d": ("time", 86400.0),
    "wh": ("energy", 1.0), "kwh": ("energy", 1e3), "mwh": ("energy", 1e6),
    "l": ("volume", 1.0), "m3": ("volume", 1000.0), "gal": ("volume", 3.785411784),
    "kgco2e": ("co2", 1.0), "tco2e": ("co2", 1000.0),
}  # fmt: skip
TEMPS = {"c", "f", "k"}


def _grade(v: Any) -> str | None:
    """Grade table: 'Grade B' / 'b' → 'B'."""
    s = str(v).strip()
    letter = s[5:].strip()[:1] if s.lower().startswith("grade") else s[:1]
    return letter.upper() if letter.isalpha() else None


def _bool(v: Any) -> bool | None:
    s = str(v).strip().lower()
    if s in ("y", "yes", "true", "1", "x", "on"):
        return True
    if s in ("n", "no", "false", "0", "", "off"):
        return False
    return None


CODE_TABLES: dict[str, Callable[[Any], Any]] = {"grade": _grade, "bool": _bool}


class MissingField(ValueError):
    """A row's source field is not in the record: that record fails (counted, not fatal)."""

    def __init__(self, src: str):
        super().__init__(f"missing field {src}")
        self.src = src


@dataclass(frozen=True)
class MapRow:
    src: str  # dotted path into the payload
    model: str
    field: str
    rule: str
    resource: str | None = None  # only records of this resource (None: every resource)


# ---------------------------------------------------------------- rules
def parse_rule(t: str | None) -> str | None:
    """A rule text → the rule ("Upper case" → upper, "fx:inr" → fx:INR, "units:kg>t"), or None when it names none."""
    s = re.sub(r"\s+", " ", str(t or "").strip())
    low = s.lower()
    if low in ALIASES:
        return ALIASES[low]
    if low == CODE:
        return CODE
    if m := re.fullmatch(r"fx:\s*([a-z]{3})", low):
        return f"fx:{m.group(1).upper()}"
    if m := re.fullmatch(r"units:\s*([a-z0-9]+)\s*>\s*([a-z0-9]+)", low):
        a, b = m.groups()
        if (a in TEMPS and b in TEMPS) or (a in UNITS and b in UNITS and UNITS[a][0] == UNITS[b][0]):
            return f"units:{a}>{b}"
        return None
    if m := re.fullmatch(r"code:\s*([a-z0-9_]+)", low):
        return f"code:{m.group(1)}" if m.group(1) in CODE_TABLES else None
    return None


def rule_label(rule: str) -> str:
    """What provenance shows as the transform."""
    if rule in LABEL:
        return LABEL[rule]
    kind, _, arg = rule.partition(":")
    if kind == "units":
        a, b = arg.split(">")
        return f"Units {a} → {b}"
    if kind == "fx":
        return f"Currency at {FX_NOTE[arg]}" if arg in FX_NOTE else f"Currency {arg} to USD"
    if kind == "code":
        return f"Code table {arg}"
    return rule


def _number(v: Any) -> float | int:
    if isinstance(v, bool):
        raise ValueError(f"not a number: {v!r}")
    if isinstance(v, int | float):
        n = float(v)
    else:
        s = re.sub(r"[^0-9.\-eE]", "", str(v).replace(",", ""))
        if not re.search(r"\d", s):
            raise ValueError(f"not a number: {v!r}")
        n = float(s)
    return int(n) if n.is_integer() and abs(n) < 2**53 else n


def _units(n: float, a: str, b: str) -> float:
    if a in TEMPS:
        c = n if a == "c" else (n - 32) * 5 / 9 if a == "f" else n - 273.15
        n = c if b == "c" else c * 9 / 5 + 32 if b == "f" else c + 273.15
        return round(n, 6)
    return round(n * UNITS[a][1] / UNITS[b][1], 6)


def apply_rule(rule: str, v: Any) -> Any:
    """One rule on one value (None stays None)."""
    if v is None:
        return None
    if rule in ("copy", CODE):
        return v
    if rule == "upper":
        return str(v).upper()
    if rule == "lower":
        return str(v).lower()
    if rule == "number":
        return _number(v)
    if rule == "int":
        return int(round(_number(v)))
    if rule == "utc":
        return utc(str(v))
    if rule == "date":
        s = str(v).strip()
        return s if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else (utc(s) or "")[:10] or None
    kind, _, arg = rule.partition(":")
    if kind == "units":
        a, b = arg.split(">")
        return _units(float(_number(v)), a, b)
    if kind == "fx":
        return to_usd(_number(v), arg)
    if kind == "code":
        return CODE_TABLES[arg](v)
    raise ValueError(f"unknown rule {rule}")


# ---------------------------------------------------------------- reading a record
_MISSING = object()


def lookup(payload: Any, path: str) -> Any:
    """The value at a dotted path, or _MISSING. A key that contains dots is found as it is first."""
    if isinstance(payload, dict) and path in payload:
        return payload[path]
    cur = payload
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return _MISSING
    return cur


def _payload(rec: Any) -> dict:
    return rec.payload if hasattr(rec, "payload") else rec


def _fact(r: MapRow, rec: Any, key: str, raw: Any) -> Fact | None:
    value = apply_rule(r.rule, raw)
    if value is None:
        return None
    return Fact(
        r.model, str(key), r.field, value, r.src, raw if not isinstance(raw, dict | list) else None, rule_label(r.rule),
        getattr(rec, "resource", None), getattr(rec, "ext_id", None),
    )  # fmt: skip


def _for(r: MapRow, rec: Any) -> bool:
    return r.resource is None or r.resource == getattr(rec, "resource", None)


def apply_rows(rows: Iterable[MapRow], rec: Any) -> list[Fact]:
    """Facts from the rows alone (configured sources). The key of a model is the value of its row with field `key`
    (not written as a fact), else the record's ext_id. A missing src fails the record (MissingField)."""
    rows = [r for r in rows if _for(r, rec)]
    p = _payload(rec)
    keys: dict[str, str] = {}
    for r in rows:
        if r.field == "key":
            v = lookup(p, r.src)
            if v is _MISSING or v is None:
                raise MissingField(r.src)
            keys[r.model] = str(apply_rule("copy" if r.rule == CODE else r.rule, v))
    out: list[Fact] = []
    for r in rows:
        if r.field == "key":
            continue
        raw = lookup(p, r.src)
        if raw is _MISSING:
            raise MissingField(r.src)
        key = keys.get(r.model) or getattr(rec, "ext_id", None)
        if key is None:
            continue
        rule = "copy" if r.rule == CODE else r.rule
        if (f := _fact(MapRow(r.src, r.model, r.field, rule, r.resource), rec, key, raw)) is not None:
            out.append(f)
    return out


def overlay(facts: list[Fact], rec: Any, rows: Iterable[MapRow], builtin: set[tuple[str, str]]) -> list[Fact]:
    """A Python adapter's facts with the person's rows over them (see the module docstring)."""
    rows = [r for r in rows if _for(r, rec)]
    kept = {(r.model, r.field) for r in rows if r.rule == CODE}
    edits = [r for r in rows if r.rule != CODE]
    replaced = {(r.model, r.field) for r in edits}
    produced = {(f.model, f.field) for f in facts}
    key_of: dict[str, str] = {}
    for f in facts:
        key_of.setdefault(f.model, f.key)
    out = [
        f
        for f in facts
        if (f.model, f.field) not in replaced and ((f.model, f.field) not in builtin or (f.model, f.field) in kept)
    ]
    p = _payload(rec)
    for r in edits:
        key = key_of.get(r.model)
        if key is None:  # this record feeds no fact of that model
            continue
        raw = lookup(p, r.src)
        if raw is _MISSING:
            if (r.model, r.field) in produced:
                raise MissingField(r.src)
            continue
        if (f := _fact(r, rec, key, raw)) is not None:
            out.append(f)
    return out


# ---------------------------------------------------------------- the Data Mapping tab's rows
def starting_maps(source_id: str) -> list[list[str]]:
    """The demo's starting rows for the source (MAPPINGS), [] for a source created here."""
    return [list(m) for m in golden.load("canonical")["mappings"].get(source_id, [])]


def builtin(source_id: str) -> set[tuple[str, str]]:
    """The canonical fields the Data Mapping tab shows for a demo source: the ones a person controls."""
    out = set()
    for m in starting_maps(source_id):
        if (t := _target(m[2] if len(m) > 2 else "")) is not None:
            out.add(t)
    return out


def _target(t: str) -> tuple[str, str] | None:
    model, dot, field = str(t).strip().partition(".")
    field = field.strip().removesuffix("[]")
    return (model.strip(), field) if dot and model.strip() and field else None


def rows_from_maps(source_id: str, maps: list[list[str]], strict: bool = True) -> list[dict]:
    """The tab's rows → stored rows (MapRow fields plus `show`, the row as displayed). Raises ValueError naming the
    first row that has no canonical model.field or a model that does not exist; not `strict`, such rows are left out
    (the catalogue's suggestions)."""
    start = {(str(m[0]).strip(), str(m[2]).strip()): str(m[4]).strip() for m in starting_maps(source_id) if len(m) >= 5}
    out = []
    for i, m in enumerate(maps):
        m = [str(x).strip() for x in m] + [""] * (5 - len(m))
        src, tgt, txt = m[0], m[2], m[4]
        t = _target(tgt)
        bad = None
        if not src or t is None:
            bad = f"Row {i + 1}: enter a source field and a canonical field as model.field."
        else:
            on_start = (src, tgt) in start
            unchanged = on_start and start[(src, tgt)] == txt
            rule = CODE if unchanged else parse_rule(txt) or (CODE if on_start else "copy")
            if rule != CODE and t[0] not in MODELS:  # the demo's own rows may name a display namespace (movement.ts)
                bad = f"Row {i + 1}: no canonical model {t[0]}."
        if bad:
            if strict:
                raise ValueError(bad)
            continue
        assert t is not None  # noqa: S101 - checked above
        out.append({"src": src, "model": t[0], "field": t[1], "rule": rule, "show": m[:5]})
    return out


def to_rows(stored: list[dict]) -> list[MapRow]:
    return [MapRow(r["src"], r["model"], r["field"], r["rule"], r.get("resource")) for r in stored]


# ---------------------------------------------------------------- versions
def _latest(s: Session, source_id: str):
    return s.execute(
        text(
            "SELECT version, rows, note, created_by, created_at FROM field_mapping WHERE source_id = :s "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"s": source_id},
    ).first()


def active_version(s: Session, source_id: str) -> int | None:
    r = _latest(s, source_id)
    return int(r.version) if r else None


def active_rows(s: Session, source_id: str) -> list[MapRow]:
    """The rows of the source's newest version ([] when it has none)."""
    r = _latest(s, source_id)
    return to_rows(r.rows) if r else []


def versions(s: Session, source_id: str) -> list[dict]:
    """Every saved version, newest first: {version, by, at (ISO), note, rows}."""
    rows = s.execute(
        text("SELECT version, rows, note, created_by, created_at FROM field_mapping WHERE source_id = :s ORDER BY version DESC"),
        {"s": source_id},
    ).all()
    return [
        {"version": r.version, "by": r.created_by, "at": r.created_at.astimezone(UTC).isoformat(), "note": r.note,
         "rows": len(r.rows)}
        for r in rows
    ]  # fmt: skip


def _insert(s: Session, source_id: str, version: int, rows: list[dict], by: str, note: str | None, at: datetime | None):
    s.execute(
        text(
            "INSERT INTO field_mapping (source_id, version, rows, note, created_by, created_at) "
            "VALUES (:s, :v, CAST(:r AS jsonb), :n, :b, coalesce(:at, now()))"
        ),
        {"s": source_id, "v": version, "r": json.dumps(rows), "n": note, "b": by, "at": at},
    )


def save_version(
    s: Session,
    source_id: str,
    maps: list[list[str]],
    by: str,
    note: str | None = None,
    at: datetime | None = None,
    strict: bool = True,
) -> int:
    """A new version from the tab's rows (in the caller's transaction). The first save of a demo source first records
    its default mapping as v1, so Revert can go back to it. Rows equal to the newest version add nothing."""
    rows = rows_from_maps(source_id, maps, strict)
    s.execute(text("SELECT pg_advisory_xact_lock(hashtext('field_mapping:' || :s))"), {"s": source_id})
    cur = _latest(s, source_id)
    if cur is None:
        v = 0
        if starting_maps(source_id):
            default = rows_from_maps(source_id, starting_maps(source_id))
            if default == rows:
                _insert(s, source_id, 1, rows, by, note or "Default mapping", at)
                return 1
            _insert(s, source_id, 1, default, "Circularity", "Default mapping", at)
            v = 1
        _insert(s, source_id, v + 1, rows, by, note, at)
        return v + 1
    if cur.rows == rows:
        return int(cur.version)
    _insert(s, source_id, cur.version + 1, rows, by, note, at)
    return int(cur.version) + 1


def revert(s: Session, source_id: str, version: int, by: str, at: datetime | None = None) -> tuple[int, list[list[str]]]:
    """A new version equal to an older one. Returns (new version, the tab's rows). KeyError: no such version."""
    old = s.execute(
        text("SELECT rows FROM field_mapping WHERE source_id = :s AND version = :v"), {"s": source_id, "v": version}
    ).scalar()
    if old is None:
        raise KeyError(f"No mapping version {version} for {source_id}.")
    s.execute(text("SELECT pg_advisory_xact_lock(hashtext('field_mapping:' || :s))"), {"s": source_id})
    cur = _latest(s, source_id)
    new = int(cur.version) + 1
    _insert(s, source_id, new, old, by, f"Reverted to v{version}", at)
    return new, [list(r.get("show") or [r["src"], "", f"{r['model']}.{r['field']}", "", r["rule"]]) for r in old]


def mapper(s: Session, source_id: str, builtin_adapter: bool) -> Callable[[Any, list[Fact]], list[Fact]] | None:
    """What sync.run_sync applies over a Python adapter's map() for one run, or None when nothing changes it (no
    saved version, or a configured source whose map() already is apply_rows)."""
    if not builtin_adapter:
        return None
    r = _latest(s, source_id)
    if r is None:
        return None
    rows, base = to_rows(r.rows), builtin(source_id)
    return lambda rec, facts: overlay(facts, rec, rows, base)
