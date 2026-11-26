"""Worked analytics questions of the telecom_network pack (plan 9, P9-10.17, stories TN-21, TN-22; the shape of P9-6.17, DV-13).

    power_units_idle(units, reqs, idle_days_gt)   `wq_tn_1` WQ-TN-1 "Why are we still buying new power units when returns are coming
                                                  in?": the model idle in one region while another raised open requisitions for it
    idle_spares_by_region(units, prices)          `wq_tn_2` WQ-TN-2 "Where are our idle spares?": count and value (catalogue price)
                                                  per region, most first

Each question is a pure function of typed rows returning `di.services.device.analytics.Answer`, wrapped in a `WorkedQuestion`
whose compute loads only the rows its `Scope` allows (R21: the org unit is the first part of the canonical key; `shared` rows
are allowed) and registered with `analytics.register`. Imported by `di.services.questions`, so the action `device.question` and
Ask's `device_question` tool answer them by id. Every number is counted here, never by a model; the sentence goes through
`analytics.word`. Idle means more than the pack's `AL-TN-XREGION` `idle_days_gt` for WQ-TN-1. Read only; synthetic data.
"""

# ruff: noqa: E501 - long sentence and SQL lines

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical.schema import SHARED_ORG
from di.services.cases import tn_cross_region as xr
from di.services.device.analytics import Answer, Scope, WorkedQuestion, register
from di.services.modeler.pack import load_pack

EXAMPLES = 3
TAIL = "spares targets are set per region, so one region's surplus is never offered to another."


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def power_units_idle(units: Sequence[xr.Unit], reqs: Sequence[xr.Req], idle_days_gt: int) -> Answer:
    """WQ-TN-1: the (model, idle region, other region) with the most idle units that the other region is buying new."""
    idle = [u for u in units if u.idle_days > idle_days_gt]
    cells = Counter(
        {(m, a, b): sum(1 for u in idle if u.model == m and u.region == a)
         for m, a, b in {(r.model, u.region, r.region) for r in reqs for u in idle if u.model == r.model and u.region != r.region}}
    )  # fmt: skip
    order = sorted(cells.items(), key=lambda kv: (-kv[1], kv[0]))
    points = [{"x": f"{m} {a} to {b}", "y": n} for (m, a, b), n in order]
    chart = {"kind": "bar", "series": [{"name": "Idle units", "points": points}]}
    if not order:
        return Answer("wq_tn_1", "No idle units sit in one region while another region buys the same model new.", chart, [])
    (model, here, there), n = order[0]
    asked = sorted((r for r in reqs if r.model == model and r.region == there), key=lambda r: r.req_id)
    sentence = f"{n} returned {model} units sat idle in {here} while {there} raised {_plural(len(asked), 'purchase requisition')}: {TAIL}"
    mine = sorted((u for u in idle if u.model == model and u.region == here), key=lambda u: (-u.idle_days, u.serial))
    examples = [
        {"serial": u.serial, "model": u.model, "region": here, "idle_days": u.idle_days, "req_id": asked[0].req_id,
         "requisition_region": there}
        for u in mine[:EXAMPLES]
    ]  # fmt: skip
    return Answer("wq_tn_1", sentence, chart, examples)


def idle_spares_by_region(units: Sequence[xr.Unit], prices: Mapping[str, float]) -> Answer:
    """WQ-TN-2: idle pool units per region, count and value at the catalogue price, most units first (ties: region)."""
    count = Counter(u.region for u in units)
    value = {r: sum(prices.get(u.model, 0.0) for u in units if u.region == r) for r in count}
    order = sorted(count, key=lambda r: (-count[r], r))
    points = [{"x": r, "y": count[r], "value": value[r]} for r in order]
    chart = {"kind": "bar", "series": [{"name": "Idle spares", "points": points}]}
    if not order:
        return Answer("wq_tn_2", "No idle spares on record.", chart, [])
    top = order[0]
    sentence = f"{top} holds the most idle spares: {_plural(count[top], 'unit')} worth {value[top]:,.0f}"
    if len(order) > 1:
        sentence += f", against {_plural(count[order[1]], 'unit')} worth {value[order[1]]:,.0f} in {order[1]}"
    mine = sorted((u for u in units if u.region == top), key=lambda u: (-u.idle_days, u.serial))
    examples = [{"serial": u.serial, "model": u.model, "region": top, "idle_days": u.idle_days} for u in mine[:EXAMPLES]]
    return Answer("wq_tn_2", sentence, chart, examples)


def _orgs(s: Session, scope: Scope | None) -> list[str]:
    """The org units the scope allows (`shared` is always read), among those that hold asset or demand records."""
    rows = s.execute(text("SELECT DISTINCT split_part(key, ':', 1) FROM canonical WHERE model IN ('asset', 'demand')")).scalars()
    return [o for o in rows if o != SHARED_ORG and (scope or Scope()).allows(o)]


def _prices(s: Session, orgs: Sequence[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    rows = s.execute(
        text("SELECT key, data -> 'new_price' FROM canonical WHERE model = 'market' AND data ? 'new_price' ORDER BY key")
    )
    for key, price in rows:
        org, _, model = str(key).rpartition(":")
        if (org in orgs or org == SHARED_ORG) and isinstance(price, int | float):
            out.setdefault(model, float(price))
    return out


def _idle_days() -> int:
    al = next((r for r in load_pack("telecom_network").runtime.suggestion_rules if r.get("id") == xr.ALERT_ID), {})
    return int((al.get("params") or {}).get("idle_days_gt", 30))


def _wq1(s: Session, scope: Scope | None, _as_of: date) -> Answer:
    return power_units_idle(*xr.read(s, _orgs(s, scope)), _idle_days())


def _wq2(s: Session, scope: Scope | None, _as_of: date) -> Answer:
    orgs = _orgs(s, scope)
    return idle_spares_by_region(xr.read(s, orgs)[0], _prices(s, orgs))


register(WorkedQuestion("wq_tn_1", "Why are we still buying new power units when returns are coming in?", "bar", _wq1))
register(WorkedQuestion("wq_tn_2", "Where are our idle spares?", "bar", _wq2))
