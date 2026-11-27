"""Lot ageing flags, suggestions and alert of a used-car dealer (plan 9, P9-9.18, story UC-19).

    flagged(s, org, pack=None)         the cars on a lot more than `SR-UC-AGE45`'s days, each with its suggested move
    sync_alerts(s, org, by, pack=None) open or close the `AL-UC-AGEING` work items to match the flagged cars
    orgs(s)                            the org units with cars on a lot (the worker's `uc.ageing` job syncs each one)

Reads the dealer system's facts (`asset.lot_id`, `asset.days_on_lot`, `asset.segment`, and `market.lot_days_to_sale` per lot,
all under `vin_key(org, vin)`) and the two rules of the pack's `runtime.suggestion_rules`: `SR-UC-AGE45` (days) and
`AL-UC-AGEING` (`min_cars`, `days_on_lot_gt`, the owner role and the action). A car over the days is suggested a transfer to
the lot with the lowest days to sale for its segment; when no lot sells it under the days (or its own lot is the fastest) it
is suggested the auction. Ordered oldest first (days on the lot), then the larger value first (the car's lot average price).
Each transfer carries the draft `lot_transfer` instruction body (`{vin, fromLot, toLot}`, the dealer system's transfer) and
sends nothing. `min_cars` or more cars of one segment over the days at one lot open one work item `AL-UC-AGEING` for the
pack's `lot_manager` role, titled "<segment words> ageing at <lot name>" (My work shows it as an exception; no case).
Never does: send a transfer, move or sell a car (a person adopts a suggestion, R7), or use a model: every figure is a count
or a read fact. Implements the used-car half of the ageing suggestions of registry entry I-4; the device half is
`di.services.device.ageing`. In the caller's transaction.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.cases import process
from di.services.modeler.pack import Pack, load_pack

PACK_KEY = "used_cars"
RULE, ALERT = "SR-UC-AGE45", "AL-UC-AGEING"
AUCTION = "auction"
TRANSFER = "transfer"
CLOSED = "No longer ageing"


@dataclass(frozen=True)
class Car:
    key: str
    vin: str
    lot: str
    days_on_lot: int
    segment: str
    value: float  # the lot's average price for the car's kind: what it is worth on the lot
    days_to_sale: dict[str, float]  # per lot


def _rule(pack: Pack, rule_id: str) -> dict[str, Any]:
    r = next((x for x in pack.runtime.suggestion_rules if x.get("id") == rule_id), None)
    if r is None:
        raise KeyError(f"the pack has no rule {rule_id}")
    return r


def threshold(pack: Pack) -> int:
    """The days over which a car is flagged (`SR-UC-AGE45`)."""
    return int(_rule(pack, RULE)["params"]["days_on_lot_gt"])


def _lot_name(pack: Pack, lot: str) -> str:
    return str((pack.valuer.params["params"].get("lot_names") or {}).get(lot, lot))


def _segment_words(pack: Pack, segment: str) -> str:
    """The plural words of a segment, from the pack's wording phrase `segment`, else the id."""
    phrase = next((p for p in pack.wording.phrases if p.key == "segment"), None)
    return phrase.words.get(segment, segment) if phrase else segment


def cars(s: Session, org: str) -> list[Car]:
    """The cars of the org on a lot (those with a lot and days on it), from the canonical store."""
    rows = s.execute(
        text(
            "SELECT a.key, a.data AS asset, m.data AS market FROM canonical a LEFT JOIN canonical m "
            "ON m.model = 'market' AND m.key = a.key WHERE a.model = 'asset' AND a.key LIKE :p "
            "AND a.data ? 'lot_id' AND a.data ? 'days_on_lot' ORDER BY a.key"
        ),
        {"p": f"{org}:%"},
    ).mappings()
    out = []
    for r in rows:
        a, m = r["asset"], r["market"] or {}
        lot = str(a["lot_id"])
        prices = m.get("lot_avg_price") or {}
        out.append(
            Car(r["key"], r["key"].partition(":")[2], lot, int(a["days_on_lot"]), str(a.get("segment") or ""),
                float(prices.get(lot) or 0), {k: float(v) for k, v in (m.get("lot_days_to_sale") or {}).items()})
        )  # fmt: skip
    return out


def suggest(car: Car, pack: Pack) -> dict[str, Any]:
    """The move for one flagged car: the lot with the lowest days to sale (ties: the lot id), else the auction."""
    days = threshold(pack)
    best = min(car.days_to_sale.items(), key=lambda kv: (kv[1], kv[0]), default=None)
    here = _lot_name(pack, car.lot)
    out: dict[str, Any] = {
        "vin": car.vin, "key": car.key, "segment": car.segment, "lot": car.lot, "lot_name": here,
        "days_on_lot": car.days_on_lot, "value": car.value,
    }  # fmt: skip
    if best is None or best[1] >= days or best[0] == car.lot:
        return out | {
            "kind": AUCTION, "to_lot": None, "to_days": None, "instruction": None,
            "text": f"Send {car.vin} to auction: {car.days_on_lot} days on {here} and no lot sells it in under {days} days",
        }  # fmt: skip
    to, to_days = best
    return out | {
        "kind": TRANSFER, "to_lot": to, "to_days": to_days,
        "instruction": {"type": "lot_transfer", "vin": car.vin, "fromLot": car.lot, "toLot": to},
        "text": f"Move {car.vin} to {_lot_name(pack, to)}: {to_days:g} days to sale against {car.days_on_lot} days on {here}",
    }  # fmt: skip


def flagged(s: Session, org: str, pack: Pack | None = None) -> list[dict[str, Any]]:
    """The suggestions for the cars over the days, oldest first, then the larger value first."""
    pack = pack or load_pack(PACK_KEY)
    over = [c for c in cars(s, org) if c.days_on_lot > threshold(pack)]
    over.sort(key=lambda c: (-c.days_on_lot, -c.value, c.key))
    return [suggest(c, pack) for c in over]


def alert_groups(flags: list[dict[str, Any]], pack: Pack) -> list[dict[str, Any]]:
    """`AL-UC-AGEING`: the (segment, lot) pairs with `min_cars` or more flagged cars, the larger group first."""
    p = _rule(pack, ALERT)["params"]
    by: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for f in flags:
        if f["days_on_lot"] > int(p["days_on_lot_gt"]):
            by[f["segment"], f["lot"]].append(f)
    out = []
    for (seg, lot), group in by.items():
        if len(group) >= int(p["min_cars"]):
            oldest = max(g["days_on_lot"] for g in group)
            out.append({
                "segment": seg, "lot": lot, "n": len(group), "vins": [g["vin"] for g in group],
                "title": f"{_segment_words(pack, seg)} ageing at {_lot_name(pack, lot)}",
                "cause": f"{len(group)} cars over {p['days_on_lot_gt']} days on the lot, the oldest {oldest}",
            })  # fmt: skip
    return sorted(out, key=lambda g: (-g["n"], g["title"]))


def orgs(s: Session) -> list[str]:
    """The org units with a car on a lot (the dealer system wrote `lot_id` and `days_on_lot` under their keys)."""
    rows = s.execute(
        text(
            "SELECT DISTINCT split_part(key, ':', 1) AS org FROM canonical WHERE model = 'asset' "
            "AND data ? 'lot_id' AND data ? 'days_on_lot' ORDER BY 1"
        )
    ).scalars()
    return [r for r in rows if r]


def sync_alerts(s: Session, org: str, by: str, pack: Pack | None = None) -> list[dict[str, Any]]:
    """Open one `AL-UC-AGEING` item per group (none twice) and close the open ones whose group is gone. Answers the groups."""
    pack = pack or load_pack(PACK_KEY)
    rule = _rule(pack, ALERT)
    groups = alert_groups(flagged(s, org, pack), pack)
    want = {g["title"] for g in groups}
    rows = s.execute(
        text("SELECT id, title FROM work_item WHERE type = :t AND org_unit_id = :o AND status = 'open'"), {"t": ALERT, "o": org}
    ).mappings()
    open_ = {r["title"]: r["id"] for r in rows}
    for title, item in open_.items():
        if title not in want:
            process.close_item(s, item, CLOSED, by)
    for g in groups:
        if g["title"] not in open_:
            process.open_item(
                s, kind="exception", case_id=None, org_unit_id=org, type=ALERT, title=g["title"], cause=g["cause"],
                action=str(rule["action"]), owner_role=pack.roles.get(rule["owner"]) or "Planner", due_hours=None, by=by,
            )  # fmt: skip
    return groups
