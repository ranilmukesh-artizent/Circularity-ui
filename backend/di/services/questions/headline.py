"""The headline of a pack in Analytics (plan 11, D1): up to five figures, a breakdown by route and the grades against the
routes, over the cases of one pack opened in a period.

Pure: typed rows in, a plain dict out (the screen service loads the cases, the stage times and the pack). Every figure is
counted, summed or taken as a median here, never by a model, and carries its count and what it rests on:
    modelled   the route's net at the decision (no realised value is stored), so the sum is what was expected
    estimated  carbon avoided, from the factor set named on each route (`co2Prov.set`: sample factors, synthetic)
    counted    a count or a share of counts, and a median of days from the asset's receipt to the case's close
A figure with no case behind it has `value: None` and `needs`, the plain sentence of what must exist for it to appear.

A case's route is the one it was approved on (`chosen`), else the one recommended (`recommendation`); a case no route
survived (a gate holds it) has none. `closed` is stage `closed`: every instruction acknowledged.
Never does: read a session, the clock or a pack file, or write anything.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median
from typing import Any

Case = Mapping[str, Any]

CLOSED = "closed"
LIVE = ("approved", "executing")  # approved, instructions not all acknowledged: a sale is live, not yet reported
NO_GRADE = "No grade"


@dataclass(frozen=True)
class Spec:
    """What differs between two packs: the labels, and which route classes count as the pack's success."""

    key: str
    rate_id: str
    rate_label: str
    rate_classes: frozenset[str]  # route classes that count toward the rate
    rate_closed_only: bool  # True: closed / routed on those classes (sell-through); False: routed on them / routed (reuse)
    days_label: str
    days_classes: frozenset[str] | None  # None: every closed case
    open_id: str
    open_label: str
    open_classes: frozenset[str] | None  # None: every case that is not closed
    open_live_only: bool  # True: only cases whose sale is live (approved or executing)
    route_word: str  # "route" or "channel"


def route_of(case: Case) -> Mapping[str, Any] | None:
    """The route the case is on: approved, else recommended (None: none survived)."""
    r = case.get("chosen") or case.get("recommendation")
    return r if isinstance(r, Mapping) and r.get("id") else None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def share(part: int, whole: int) -> float | None:
    """Percent, None when there is nothing to divide by."""
    return part / whole * 100 if whole else None


def received_at(case: Case, opened: datetime | None) -> datetime | None:
    """When the asset was received (the case's own `received` date), else when the case opened. Days of a case count from
    here, in the headline and in the rows behind it, so the two cannot differ."""
    v = case.get("received")
    if isinstance(v, str):
        try:
            t = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return opened
        return t if t.tzinfo else t.replace(tzinfo=UTC)
    return opened


def median_days(spans: Sequence[tuple[datetime, datetime]]) -> float | None:
    """The median of the days from each start to each closed time (None: no span; a close before the open counts 0)."""
    days = [max((b - a).total_seconds(), 0.0) / 86400 for a, b in spans]
    return float(median(days)) if days else None


def carbon_estimate(cases: Sequence[Case]) -> tuple[float | None, int, list[str]]:
    """(kg CO2e avoided, cases it rests on, factor sets) over the cases that carry a carbon figure on their route.
    None when no case does: a figure with no factor behind it is not shown."""
    kgs: list[float] = []
    sets: set[str] = set()
    for c in cases:
        r = route_of(c)
        kg = _num(r.get("co2")) if r else None
        if r is None or kg is None:
            continue
        kgs.append(kg)
        prov = r.get("co2Prov")
        if isinstance(prov, Mapping) and prov.get("set"):
            sets.add(str(prov["set"]))
    return (sum(kgs) if kgs else None), len(kgs), sorted(sets)


def _fig(
    fid: str, label: str, value: float | None, unit: str, n: int, of: int, basis: str, needs: str, note: str = ""
) -> dict[str, Any]:
    return {
        "id": fid,
        "label": label,
        "value": value,
        "unit": unit,
        "n": n,
        "of": of,
        "basis": basis,
        "needs": needs,
        "note": note,
    }


def route_table(cases: Sequence[Case], names: Mapping[str, str]) -> list[dict[str, Any]]:
    """One row per route used: its cases, how many closed, and the sum of the net they carry (modelled), largest first."""
    by: dict[str, dict[str, Any]] = {}
    for c in cases:
        r = route_of(c)
        if r is None:
            continue
        rid = str(r["id"])
        row = by.setdefault(rid, {"id": rid, "name": names.get(rid, rid), "n": 0, "closed": 0, "net": 0.0})
        row["n"] += 1
        row["closed"] += 1 if c.get("stage") == CLOSED else 0
        row["net"] += _num(r.get("net")) or 0.0
    return sorted(by.values(), key=lambda x: (-x["n"], -x["net"], x["id"]))


def grade_table(cases: Sequence[Case], scale: Sequence[str], names: Mapping[str, str]) -> dict[str, Any]:
    """Grades (the pack's scale first, then any other, then none) against the routes used: counts per cell."""
    routed = [(c, r) for c in cases if (r := route_of(c)) is not None]
    used = [str(x["id"]) for x in route_table(cases, names)]
    seen = {str(c.get("grade") or NO_GRADE) for c, _ in routed}
    other = sorted(g for g in seen if g not in scale and g != NO_GRADE)
    grades = [g for g in scale if g in seen] + other + ([NO_GRADE] if NO_GRADE in seen else [])
    rows = []
    for g in grades:
        cells = dict.fromkeys(used, 0)
        for c, r in routed:
            if str(c.get("grade") or NO_GRADE) == g:
                cells[str(r["id"])] += 1
        rows.append({"grade": g, "total": sum(cells.values()), "cells": cells})
    return {"routes": [{"id": rid, "name": names.get(rid, rid)} for rid in used], "rows": rows}


def headline(
    spec: Spec,
    pack_name: str,
    cases: Sequence[Case],
    classes: Mapping[str, Sequence[str]],
    names: Mapping[str, str],
    scale: Sequence[str],
    spans: Mapping[str, tuple[datetime, datetime | None]],
    since: datetime,
    until: datetime,
    days: int,
) -> dict[str, Any]:
    """The headline of one pack. `cases` are the pack's cases the caller may see, `classes` each route id's route classes,
    `spans` each case's (opened, closed); only the cases opened from `since` on count."""
    mine = [c for c in cases if c["id"] in spans and spans[c["id"]][0] >= since]
    routed = [c for c in mine if route_of(c) is not None]

    def cls(c: Case) -> set[str]:
        r = route_of(c)
        return set(classes.get(str(r["id"]), ())) if r else set()

    closed = [c for c in mine if c.get("stage") == CLOSED]
    n_all = len(mine)

    # 1 net recovered: the net the closed cases carry on their approved route
    nets = [v for c in closed if (r := route_of(c)) is not None and (v := _num(r.get("net"))) is not None]
    net = _fig("net", "Net recovered", sum(nets) if nets else None, "usd", len(nets), len(closed), "modelled",
               "At least one closed case with a route and a net.", "Expected at approval, not yet reconciled")  # fmt: skip

    # 2 the rate
    on = [c for c in routed if cls(c) & spec.rate_classes]
    if spec.rate_closed_only:
        done = [c for c in on if c.get("stage") == CLOSED]
        rate = _fig(spec.rate_id, spec.rate_label, share(len(done), len(on)), "pct", len(done), len(on), "counted",
                    "At least one case routed to a sale channel.", "Closed, of the cases routed to a sale channel")  # fmt: skip
    else:
        rate = _fig(spec.rate_id, spec.rate_label, share(len(on), len(routed)), "pct", len(on), len(routed), "counted",
                    "At least one case with a route.", "Routed to keep the tool in use, of the cases with a route")  # fmt: skip

    # 3 median days from received to closed (the rows' Days column: the same start, the same end)
    pool = [c for c in closed if spec.days_classes is None or cls(c) & spec.days_classes]
    done_spans = [
        (received_at(c, spans[c["id"]][0]) or spans[c["id"]][0], t) for c in pool if (t := spans[c["id"]][1]) is not None
    ]
    n_done = len(done_spans)
    how = f"Median days from received to closed, {n_done} {'case' if n_done == 1 else 'cases'}"
    dfig = _fig("days", spec.days_label, median_days(done_spans), "days", n_done, len(closed), "counted",
                "At least one closed case.", how)  # fmt: skip

    # 4 still open (or still listed)
    left = [c for c in mine if c.get("stage") != CLOSED]
    if spec.open_live_only:
        left = [c for c in left if c.get("stage") in LIVE]
    if spec.open_classes is not None:
        left = [c for c in left if cls(c) & spec.open_classes]
    base = len(on) if spec.open_live_only else n_all
    ofig = _fig(spec.open_id, spec.open_label, float(len(left)) if n_all else None, "count", len(left), base, "counted",
                "At least one case opened in the period.",
                "Approved, the sale not yet reported" if spec.open_live_only else "Opened and not yet closed")  # fmt: skip

    # 5 carbon avoided
    kg, n_kg, sets = carbon_estimate(closed)
    note = ("Factor set " + ", ".join(sets) + " (sample factors, synthetic)") if sets else ""
    cfig = _fig("carbon", "Carbon avoided, estimated", kg, "kg", n_kg, len(closed), "estimated",
                "At least one closed case whose route carries a carbon factor.", note)  # fmt: skip

    return {
        "pack": spec.key, "name": pack_name, "route_word": spec.route_word,
        "period": {"days": days, "since": since.date().isoformat(), "until": until.date().isoformat()},
        "cases": n_all, "closed": len(closed),
        "figures": [net, rate, dfig, ofig, cfig],
        "routes": route_table(routed, names),
        "grades": grade_table(routed, scale, names),
        "carbon_sets": sets,
    }  # fmt: skip
