"""A candidate rule set simulated against the published one on a queue of cases (Domain spec D9; the prototype's fSim).

The valuation is injected (`Decider`), so the simulation stays pure: each case is decided under both rule sets, and
the result lists the cases whose best path changes and the value difference.
- `tool_fleet` and `industrial` (equip style): `dv` = sum over the queue of (candidate best net - base best net).
- `device`: a decision's `net` is the expected cash per unit and `extra["days"]` its days to sell; values are per lot
  (x its units). Extras: `u` units, `cash` (candidate total), `dd` (change in unit-weighted days), `days` (candidate),
  `dl` (change in units sold after the service level of `DEVICE_SLA_DAYS` days on hand).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from di.services.modeler.compile import CompiledRule
from di.services.modeler.templates import Template

DEVICE_SLA_DAYS = 60  # the prototype's DG.sla


@dataclass(frozen=True)
class Decision:
    best: str | None
    net: float
    extra: dict[str, Any] = field(default_factory=dict)


Decider = Callable[[Mapping[str, Any], Sequence[CompiledRule]], Decision]


@dataclass(frozen=True)
class Flip:
    case_id: str
    from_path: str | None
    to_path: str | None
    dv: float


@dataclass(frozen=True)
class SimResult:
    kind: str
    n: int
    flips: list[Flip]
    dv: float
    extra: dict[str, float]


Row = tuple[Mapping[str, Any], Decision, Decision]  # a case, its base decision, its candidate decision


def _equip(xs: list[Row]) -> SimResult:
    flips = [Flip(c["id"], b.best, s.best, s.net - b.net) for c, b, s in xs if b.best != s.best]
    return SimResult("equip", len(xs), flips, sum(s.net - b.net for _, b, s in xs), {})


def _device(xs: list[Row]) -> SimResult:
    units = sum(c["qty"] for c, _, _ in xs)
    flips = [Flip(c["id"], b.best, s.best, (s.net - b.net) * c["qty"]) for c, b, s in xs if b.best != s.best]
    base = [(c, b) for c, b, _ in xs]
    cand = [(c, s) for c, _, s in xs]

    def total(ds: list[tuple[Mapping[str, Any], Decision]]) -> float:
        return sum(d.net * c["qty"] for c, d in ds)

    def days(ds: list[tuple[Mapping[str, Any], Decision]]) -> float:
        return sum(d.extra["days"] * c["qty"] for c, d in ds) / units if units else 0.0

    def late(ds: list[tuple[Mapping[str, Any], Decision]]) -> float:
        return sum(c["qty"] for c, d in ds if c["doh"] + d.extra["days"] > DEVICE_SLA_DAYS)

    extra = {"u": units, "cash": total(cand), "dd": days(cand) - days(base), "days": days(cand), "dl": late(cand) - late(base)}
    return SimResult("device", len(xs), flips, total(cand) - total(base), extra)


def simulate(
    t: Template,
    base: Sequence[CompiledRule],
    cand: Sequence[CompiledRule],
    queue: Sequence[Mapping[str, Any]],
    decide: Decider,
    decide_cand: Decider | None = None,
) -> SimResult:
    """`decide_cand` (default `decide`) decides the candidate side, so a what-if can value it under other parameters."""
    dc = decide_cand or decide
    xs = [(c, decide(c, base), dc(c, cand)) for c in queue]
    return _device(xs) if t.key == "device" else _equip(xs)
