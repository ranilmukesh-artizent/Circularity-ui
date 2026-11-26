"""The like-life assignment of a contract refresh (plan 9, P9-5.3, story CR-03; a companion of the queue planner, I-5). Pure.

    target(actions) -> int                                   the median remaining life of the tools kept (A section 1.10.2)
    match(needs, units, reserved) -> MatchResult             which unit replaces which tool, each unit once

A swap should return a unit whose remaining life is as near the fleet's median as possible, so the customer's fleet ages evenly.
`match` is an exact minimum-cost assignment of `abs(unit.rul - need.target)` within one tool class (SciPy
`optimize.linear_sum_assignment`), over the needs of every open contract together, so a unit is promised once. A unit in
`reserved` is never offered. Ties are decided the same way for everyone: by the source (refurbished stock before returns), then
the unit id, and the needs in the order given (callers pass them in case-id order, as the returns queue is read, so each
caller sees the same winner). The costs are whole numbers built as distance, then source, then unit order, then need order, so
a nearer unit always beats a better-ranked one.

An unmatched need gets a reason in `why`: no unit of the class, every unit reserved, or the nearest unit going to another
contract's case (named, so the person sees who has it).

Never does: read the database or the clock, write text with a model, or reserve anything (reservations are written on a
person's approval, `di.repositories.unit_reservations`).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median_low
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment  # type: ignore[import-untyped]

SOURCES = ("stock", "return")  # in the order they are offered
_K_DIST, _K_SOURCE, _K_UNIT = 10**13, 10**10, 10**7


@dataclass(frozen=True)
class Need:
    id: str
    case_id: str
    cls: str
    target: int


@dataclass(frozen=True)
class Unit:
    id: str
    cls: str
    rul: int
    source: str  # "stock" or "return"


@dataclass(frozen=True)
class MatchResult:
    assign: dict[str, str] = field(default_factory=dict)  # need id -> unit id
    unmatched: list[str] = field(default_factory=list)
    why: dict[str, str] = field(default_factory=dict)  # need id -> why it has no unit


def target(actions: Sequence[Any]) -> int:
    """The median remaining life of the tools kept (the lower middle for an even count); 100 when none is kept."""
    kept = [int(a.rul_pct) for a in actions if a.action == "keep"]
    return int(median_low(kept)) if kept else 100


def _rank(u: Unit) -> tuple[int, str]:
    return (SOURCES.index(u.source) if u.source in SOURCES else len(SOURCES), u.id)


def match(needs: Sequence[Need], units: Sequence[Unit], reserved: frozenset[str]) -> MatchResult:
    """The assignment (module docstring)."""
    offered = sorted((u for u in units if u.id not in reserved), key=_rank)
    case_of = {n.id: n.case_id for n in needs}
    assign: dict[str, str] = {}
    for cls in sorted({n.cls for n in needs}):
        ns = [n for n in needs if n.cls == cls]
        us = [u for u in offered if u.cls == cls]
        if not ns or not us:
            continue
        cost = np.zeros((len(ns), len(us)), dtype=np.float64)
        for i, n in enumerate(ns):
            for j, u in enumerate(us):
                src = SOURCES.index(u.source) if u.source in SOURCES else len(SOURCES)
                cost[i, j] = abs(u.rul - n.target) * _K_DIST + src * _K_SOURCE + j * _K_UNIT - i * j
        rows, cols = linear_sum_assignment(cost)
        for i, j in zip(rows, cols, strict=True):
            assign[ns[i].id] = us[j].id
    taken = {u: n for n, u in assign.items()}
    unmatched: list[str] = []
    why: dict[str, str] = {}
    for n in needs:
        if n.id in assign:
            continue
        unmatched.append(n.id)
        same = [u for u in offered if u.cls == n.cls]
        if same:
            near = min(same, key=lambda u: (abs(u.rul - n.target), *_rank(u)))
            winner = case_of[taken[near.id]]
            why[n.id] = f"{near.id} ({near.rul}%) goes to {winner}, which it fits better"
        elif any(u.cls == n.cls for u in units):
            why[n.id] = f"every {n.cls} unit is reserved"
        else:
            why[n.id] = f"no {n.cls} unit in refurbished stock or planned from returns"
    return MatchResult(assign, unmatched, why)
