"""Worked analytics questions of the used_cars pack (plan 9, P9-9.19, stories UC-20 and UC-21; the shape of P9-6.17, DV-13).

    ev_crossover_lots(cars, names)   WQ-UC-1 `wq_uc_1`: where the EV crossovers go and how many days they take there
    lease_return_lots(cars, names)   WQ-UC-2 `wq_uc_2`: the lots that sell lease returns fastest, quickest first

Each question is a pure function of typed rows returning `di.services.device.analytics.Answer`, wrapped in a `WorkedQuestion`
whose compute loads only the cars of the org units its `Scope` allows (R21: the tenant is the first part of the canonical
key) and registered with `analytics.register`. Imported by `di.services.questions`, so the action `device.question` and Ask's
`device_question` tool answer them by id. Every number is counted or averaged here, never by a model; the sentence goes
through `analytics.word`. Days are the market facts' `lot_days_to_sale` per lot (the dealer system's average days to sale),
and a car's own days in stock (`asset.days_on_lot`, P9-9.18) orders the example records.
Never does: write anything, or build saved views and alerts (DV-13 has none to reuse; the ageing alert is P9-9.18's).
"""

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from statistics import mean

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.device.analytics import Answer, Scope, WorkedQuestion, register
from di.services.modeler.pack import load_pack

SEGMENT = "ev_crossover"
LEASE_END = "lease_end"
EXAMPLES = 3


@dataclass(frozen=True)
class StockCar:
    key: str
    vin: str
    lot: str
    days_in_stock: int
    segment: str
    return_kind: str
    days_to_sale: dict[str, float]  # per lot, from the dealer's market facts


def _name(names: dict[str, str], lot: str) -> str:
    return names.get(lot, lot)


def _avg(cars: Sequence[StockCar]) -> dict[str, float]:
    """The average days to sale per lot over the cars' market facts (a lot with no fact is absent)."""
    by: dict[str, list[float]] = defaultdict(list)
    for c in cars:
        for lot, d in c.days_to_sale.items():
            by[lot].append(d)
    return {lot: round(mean(v), 1) for lot, v in by.items()}


def _example(c: StockCar, names: dict[str, str]) -> dict[str, object]:
    return {"vin": c.vin, "lot": c.lot, "lot_name": _name(names, c.lot), "days_in_stock": c.days_in_stock,
            "segment": c.segment, "return_kind": c.return_kind}  # fmt: skip


def _g(x: float) -> str:
    return f"{x:g}"


def ev_crossover_lots(cars: Sequence[StockCar], names: dict[str, str]) -> Answer:
    """WQ-UC-1: of the EV crossovers, the lot most of them are at (ties: lot id) and the days to sale per lot."""
    ev = [c for c in cars if c.segment == SEGMENT]
    days = _avg(ev)
    points = [{"x": _name(names, lot), "y": d} for lot, d in sorted(days.items(), key=lambda kv: (-kv[1], kv[0]))]
    chart = {"kind": "bar", "series": [{"name": "Days to sale", "points": points}]}
    if not ev or not days:
        return Answer("wq_uc_1", "No EV crossovers on a lot with sales history yet.", chart, [])
    per = Counter(c.lot for c in ev)
    top = sorted(per.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    best = min(days.items(), key=lambda kv: (kv[1], kv[0]))
    here = days.get(top)
    sentence = f"Most returned EV crossovers go to {_name(names, top)}, nearest the return centre"
    if here is not None and best[0] != top:
        sentence += f", where they take {_g(here)} days on average against {_g(best[1])} at {_name(names, best[0])}"
    picked = sorted((c for c in ev if c.lot == top), key=lambda c: (-c.days_in_stock, c.vin))[:EXAMPLES]
    return Answer("wq_uc_1", sentence, chart, [_example(c, names) for c in picked])


def lease_return_lots(cars: Sequence[StockCar], names: dict[str, str]) -> Answer:
    """WQ-UC-2: the average days to sale per lot over the lease returns, quickest lot first (ties: lot id)."""
    lease = [c for c in cars if c.return_kind == LEASE_END]
    order = sorted(_avg(lease).items(), key=lambda kv: (kv[1], kv[0]))
    points = [{"x": _name(names, lot), "y": d} for lot, d in order]
    chart = {"kind": "bar", "series": [{"name": "Days to sale", "points": points}]}
    if not order:
        return Answer("wq_uc_2", "No lease returns on a lot with sales history yet.", chart, [])
    first, last = order[0], order[-1]
    sentence = f"Lease returns sell fastest at {_name(names, first[0])}, in {_g(first[1])} days on average"
    if len(order) > 1:
        sentence += f", against {_g(last[1])} days at {_name(names, last[0])}"
    picked = sorted((c for c in lease if c.lot == first[0]), key=lambda c: (-c.days_in_stock, c.vin))[:EXAMPLES]
    return Answer("wq_uc_2", sentence, chart, [_example(c, names) for c in picked])


def load_cars(s: Session, scope: Scope | None) -> list[StockCar]:
    """The cars on a lot of the org units `scope` allows: asset facts and the dealer's market facts, from the canonical store."""
    rows = s.execute(
        text(
            "SELECT a.key, a.data AS asset, m.data AS market FROM canonical a LEFT JOIN canonical m "
            "ON m.model = 'market' AND m.key = a.key WHERE a.model = 'asset' AND a.data ? 'lot_id' AND a.data ? 'days_on_lot' "
            "ORDER BY a.key"
        )
    ).mappings()
    out = []
    for r in rows:
        org, _, vin = r["key"].partition(":")
        if not (scope or Scope()).allows(org):
            continue
        a, m = r["asset"], r["market"] or {}
        sale = {k: float(v) for k, v in (m.get("lot_days_to_sale") or {}).items()}
        out.append(StockCar(r["key"], vin, str(a["lot_id"]), int(a["days_on_lot"]), str(a.get("segment") or ""),
                            str(a.get("return_kind") or ""), sale))  # fmt: skip
    return out


def _names() -> dict[str, str]:
    return {k: str(v) for k, v in (load_pack("used_cars").valuer.params["params"].get("lot_names") or {}).items()}


def _ev(s: Session, scope: Scope | None, _as_of: date) -> Answer:
    return ev_crossover_lots(load_cars(s, scope), _names())


def _lease(s: Session, scope: Scope | None, _as_of: date) -> Answer:
    return lease_return_lots(load_cars(s, scope), _names())


register(WorkedQuestion("wq_uc_1", "Where do returned EV crossovers sell fastest?", "bar", _ev))
register(WorkedQuestion("wq_uc_2", "Which lots sell lease returns fastest?", "bar", _lease))
