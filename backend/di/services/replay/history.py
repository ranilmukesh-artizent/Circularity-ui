"""History batch checks (plan 9, P9-7.1; registry entry I-16; story X-06): the pure part of `replay.import`.

Owns: reading a CSV of past decisions (A section 3.1 columns) and checking every row against the pack with pandera
(`DataFrameSchema`, `lazy=True`); a failing row is held with exactly one reason, a good row becomes an item.
Never does: store anything (di.repositories.replay), read the clock (`now` is passed in), read or interpret free text, or
accept a personal column. A header that looks personal refuses the whole import. Implements the pure half of I-16's
`import_history`; the repository write is the other half.

Columns: `item_id, class, decided_at, reason, actual_route, realised_value, cost_logistics, cost_refurb, cost_test,
cost_fees, market`, then `fact.<name>` each with `fact.<name>.at` (the ISO time the fact was known). A fact the pack's
replay part lists as required (`replay.example["required_facts"]`; none of the packs lists one yet) must have its column.

Demand at the time (P9-7.5): `import_demand` checks a second file, `demand_id, route, opens_at, closes_at, value, capacity`
(a renewal, requisition, bid or repair slot window), the same way: a row failing a check is held with one reason.
"""

import csv
import io
from collections import Counter
from collections.abc import Collection, Iterable
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd  # type: ignore[import-untyped]  # no pandas-stubs in the locks
import pandera.pandas as pa

from di.services.modeler.pack import Pack

MAX_ROWS = 25_000
PERSONAL = ("name", "email", "phone", "address", "account", "card", "iban", "ssn", "birth")
REQUIRED = ("item_id", "decided_at", "actual_route", "realised_value")
COSTS = ("cost_logistics", "cost_refurb", "cost_test", "cost_fees")
COLUMNS = ("item_id", "class", "decided_at", "reason", *REQUIRED[2:], *COSTS, "market")
FACT = "fact."

R_DUP = "Duplicate item_id."
R_DATE = "No valid decision date."
R_VALUE = "No realised value."
R_COST = "Costs cannot be negative."
R_NO_ID = "No item_id."
# the order a row's one reason is picked in when several checks fail
ORDER = ("route", "dup", "date", "value", "cost", "fact", "id")


class HistoryRefused(ValueError):
    """The whole import is refused (a personal column, a missing column, too many rows): nothing is stored."""


def personal_column(headers: Iterable[str]) -> str | None:
    """The first header that looks like personal data (case-insensitive contains), or None."""
    for h in headers:
        if any(p in h.lower() for p in PERSONAL):
            return h
    return None


def parse_csv(text: str) -> list[dict[str, str]]:
    """The rows of a CSV; leading `#` comment lines (the command that made a sample) are skipped."""
    lines = text.lstrip("﻿").splitlines()
    while lines and lines[0].lstrip().startswith("#"):
        lines.pop(0)
    rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None} for r in rows]


def required_facts(pack: Pack) -> list[str]:
    """The facts the pack's replay part (part 10) requires; empty when it lists none."""
    return [str(f) for f in ((pack.replay.example or {}).get("required_facts") or [])]


def fact_names(headers: Iterable[str]) -> list[str]:
    return [h[len(FACT) :] for h in headers if h.startswith(FACT) and not h.endswith(".at")]


def when(raw: str) -> datetime | None:
    """An ISO date or time as an aware datetime (a date: midnight UTC; no zone: UTC); None if it does not parse."""
    try:
        d = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def number(raw: str) -> float | None:
    try:
        return float(raw) if raw.strip() else None
    except ValueError:
        return None


def _fact_problem(row: dict[str, str], names: list[str], required: list[str]) -> str:
    """The first fact of the row that has a value but no valid time (or a required one with no value), else ''."""
    for n in names:
        value, at = row.get(f"{FACT}{n}", ""), row.get(f"{FACT}{n}.at", "")
        if (value or n in required) and when(at) is None:
            return n
    return ""


def _schema(pack: Pack, now: datetime) -> pa.DataFrameSchema:
    routes = {r.id for r in pack.routes}

    def check(name: str, fn: Any, element_wise: bool = True) -> pa.Check:
        return pa.Check(fn, element_wise=element_wise, name=name)

    def date_ok(v: str) -> bool:
        d = when(v)
        return d is not None and d <= now

    def cost_ok(v: str) -> bool:
        n = number(v)
        return v == "" or (n is not None and n >= 0)  # a cost that is not a number is held too

    cols: dict[str, pa.Column] = {
        "item_id": pa.Column(
            str, [check("id", lambda v: v != ""), check("dup", lambda s: ~(s.duplicated() & (s != "")), element_wise=False)]
        ),
        "decided_at": pa.Column(str, check("date", date_ok)),
        "actual_route": pa.Column(str, check("route", lambda v: v in routes)),
        "realised_value": pa.Column(str, check("value", lambda v: number(v) is not None)),
        "_fact_problem": pa.Column(str, check("fact", lambda v: v == "")),
    }
    for c in COSTS:
        cols[c] = pa.Column(str, check("cost", cost_ok))
    return pa.DataFrameSchema(cols, strict=False)


def _reason(code: str, row: dict[str, str], pack: Pack, fact: str) -> str:
    return {
        "route": f"Route '{row.get('actual_route', '')}' is not a route of {pack.key}.",
        "dup": R_DUP,
        "date": R_DATE,
        "value": R_VALUE,
        "cost": R_COST,
        "fact": f"Fact {fact} has no date.",
        "id": R_NO_ID,
    }[code]


def _item(n: int, row: dict[str, str], names: list[str]) -> dict[str, Any]:
    decided = when(row.get("decided_at", ""))
    value = number(row.get("realised_value", ""))
    return {
        "n": n,
        "item_id": row.get("item_id", ""),
        "decided_at": decided,
        "cls": row.get("class") or None,
        "market": row.get("market") or None,
        "reason": row.get("reason") or None,
        "actual_route": row.get("actual_route") or None,
        "realised_value": value,
        "costs": {c: number(row.get(c, "")) or 0.0 for c in COSTS if c in row},
        "facts": {
            k: {"value": row.get(f"{FACT}{k}", ""), "at": (when(row.get(f"{FACT}{k}.at", "")) or None)}
            for k in names
            if row.get(f"{FACT}{k}", "") != ""
        },
    }


def check_header(headers: Collection[str], pack: Pack) -> None:
    """Refuse the import for a personal column, a missing mandatory column or a missing required fact column."""
    if bad := personal_column(headers):
        raise HistoryRefused(f"Column {bad} looks like personal data. Send de-identified extracts only.")
    for c in (*REQUIRED, *(f"{FACT}{f}" for f in required_facts(pack))):
        if c not in headers:
            raise HistoryRefused(f"Column {c} is missing.")
    for f in fact_names(headers):
        if f"{FACT}{f}.at" not in headers:
            raise HistoryRefused(f"Column {FACT}{f}.at is missing: every fact needs the time it was known.")


def import_history(
    rows: list[dict[str, str]], pack: Pack, *, now: datetime, seen: Collection[str] = ()
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(ok items, held items with `held_reason`) of the rows, checked with pandera (lazy). `seen` are item ids already in
    the batch being appended to: a row repeating one is a duplicate. Raises HistoryRefused for a bad header or row count."""
    if len(rows) > MAX_ROWS:
        raise HistoryRefused(f"At most {MAX_ROWS:,} rows per import.")
    if not rows:
        raise HistoryRefused("The file has no rows.")
    headers = {k for r in rows for k in r}
    check_header(headers, pack)
    names, required = fact_names(headers), required_facts(pack)
    norm = [{k: str(r.get(k) or "").strip() for k in headers} for r in rows]
    frame = pd.DataFrame(
        [
            {
                **{c: r.get(c, "") for c in (*REQUIRED, *COSTS)},
                "_fact_problem": _fact_problem(r, names, required),
            }
            for r in norm
        ],
        dtype=object,
    )
    if seen:
        frame = pd.concat([pd.DataFrame({"item_id": sorted(seen)}, dtype=object), frame], ignore_index=True)
    offset = len(frame) - len(norm)
    failed: dict[int, set[str]] = {}
    try:
        _schema(pack, now).validate(frame.fillna(""), lazy=True)
    except pa.errors.SchemaErrors as err:
        for _, f in err.failure_cases.iterrows():
            if pd.notna(f["index"]) and int(f["index"]) >= offset:
                failed.setdefault(int(f["index"]) - offset, set()).add(str(f["check"]))
    ok, held = [], []
    for k, row in enumerate(norm):
        item = _item(k + 1, row, names)
        codes = failed.get(k)
        if codes:
            code = next(c for c in ORDER if c in codes)
            item["held_reason"] = _reason(code, row, pack, frame["_fact_problem"].iloc[k + offset])
            held.append(item)
        else:
            ok.append(item)
    return ok, held


def held_reasons(held: Iterable[dict[str, Any]]) -> dict[str, int]:
    """How many held rows each reason holds."""
    return dict(Counter(h["held_reason"] for h in held))


def period(items: Iterable[dict[str, Any]]) -> tuple[date, date] | None:
    days = [i["decided_at"].date() for i in items if i.get("decided_at")]
    return (min(days), max(days)) if days else None


# ---------------------------------------------------------------- demand at the time (P9-7.5)
DEMAND_COLUMNS = ("demand_id", "route", "opens_at", "closes_at", "value", "capacity")
# the routes a demand window can be for, and what the window is for the queue planner: a fleet contract (`lease`), a firm bid
# (`bid`) or repair slots (`slot`). A route not listed takes no named order and no slot, so a window for it is held.
DEMAND_ROUTES = {"release": "lease", "resell": "bid", "refurb": "slot"}
R_DEM_DUP = "Duplicate demand_id."
R_DEM_ORDER = "Demand closes before it opens."
R_DEM_DATE = "No valid window date."
R_DEM_VALUE = "No demand value."
R_DEM_CAP = "Capacity is a whole number of at least 1."
R_DEM_ID = "No demand_id."


def check_demand_header(headers: Collection[str]) -> None:
    """Refuse the file for a personal column or a missing demand column."""
    if bad := personal_column(headers):
        raise HistoryRefused(f"Column {bad} looks like personal data. Send de-identified extracts only.")
    for c in DEMAND_COLUMNS:
        if c not in headers:
            raise HistoryRefused(f"Column {c} is missing.")


def _day(raw: str) -> date | None:
    d = when(raw) if raw.strip() else None
    return d.date() if d else None


def import_demand(
    rows: list[dict[str, str]], pack: Pack, *, seen: Collection[str] = ()
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(ok rows, held rows with `held_reason`) of a demand file, checked like history items: one reason per row, the first
    that fails of an unknown route, a route with no demand window, a repeated id (`seen` are the ids already stored), a
    window that does not parse or closes before it opens, no value, a capacity that is not a whole number of at least 1.
    Raises HistoryRefused for a bad header, no rows or too many."""
    if len(rows) > MAX_ROWS:
        raise HistoryRefused(f"At most {MAX_ROWS:,} rows per import.")
    if not rows:
        raise HistoryRefused("The file has no rows.")
    check_demand_header({k for r in rows for k in r})
    routes, taken = {r.id for r in pack.routes}, set(seen)
    ok, held = [], []
    for k, r in enumerate(rows):
        did, route = r.get("demand_id", "").strip(), r.get("route", "").strip()
        opens, closes = _day(r.get("opens_at", "")), _day(r.get("closes_at", ""))
        value, cap = number(r.get("value", "")), number(r.get("capacity", ""))
        why = ""
        if not did:
            why = R_DEM_ID
        elif route not in routes:
            why = f"Route '{route}' is not a route of {pack.key}."
        elif route not in DEMAND_ROUTES:
            why = f"Route '{route}' takes no demand window."
        elif did in taken:
            why = R_DEM_DUP
        elif opens is None or closes is None:
            why = R_DEM_DATE
        elif closes <= opens:
            why = R_DEM_ORDER
        elif value is None or value < 0:
            why = R_DEM_VALUE
        elif cap is None or cap < 1 or cap != int(cap):
            why = R_DEM_CAP
        row = {"n": k + 1, "demand_id": did, "route": route or None, "opens_at": opens, "closes_at": closes,
               "value": value, "capacity": int(cap) if cap is not None and cap == int(cap) else None}  # fmt: skip
        if why:
            held.append(row | {"held_reason": why})
        else:
            taken.add(did)
            ok.append(row)
    return ok, held
