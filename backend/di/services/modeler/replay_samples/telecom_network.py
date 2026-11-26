# ruff: noqa: E501 - long lines in the docstring
"""The telecom replay history (plan 9, P9-10.13; registry entry I-16; story TN-20): 1,260 decommissioned network units decided
over the 20 days from 5 to 24 Nov 2026, 63 a day, the data `replay.import` takes.

    rows()                  1,260 CSV-shaped rows (strings) from `mulberry32(1404)`: item, class, date, route taken, realised value,
                            costs, market and the facts the telecom gates and valuer read, each with the time it was known
    csv_text()              the same rows as the CSV file (`fixtures/replay/telecom_network.csv`); first line: the command
    resales_of_current_cards(rows)   the rows that resell a `market.generation == "current"` line card (TN-14 needs 14)

    python -m di.services.modeler.replay_samples.telecom_network > fixtures/replay/telecom_network.csv

Owns: the generator. Its shares are the knobs tuned until the replay (`di.services.replay.telecom`) gave the modelled figures of the
plan: straight through 84 % +- 1 point, approvals 6 +- 1 a business day, exceptions 4 +- 1, new spend avoided $1.1M +- 10 %. Never
does: decide or replay anything (pure, like the rest of `di.services.modeler`), read a clock or a database, or carry a personal
column: every value is invented, the item ids are `TN-H00001` and up.

Per day the replay counts business days (Monday to Friday): the 20 calendar days hold 14, so 6 approvals and 4 exceptions a
business day are 84 and 56 units; the rest of the 16 % that do not run straight through are units a guardrail holds without
asking anything of a person (covered equipment disposed of with its record on file).
Legal note: export and covered-equipment rules are the pack's data; Kinective's Legal team reviews them before reliance.
"""

import csv
import io
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from di.services.modeler.valuers.rng import mulberry32

PACK = "telecom_network"
SEED = 1404
START = date(2026, 11, 5)
DAYS = 20
PER_DAY = 63
UNITS = DAYS * PER_DAY  # 1,260
CURRENT_CARD_RESALES = 14  # TN-14: resales of current-generation line cards
PROGRAMME = "reimbursement_programme"
COVERED = ("MFR-COV-1", "MFR-COV-2")
OTHER_MAKERS = ("MFR-A", "MFR-B", "MFR-C")

# the shares the generator is tuned with (module docstring)
P_SITE = 0.24  # a unit with an open site demand for its model
P_SPARES = 0.38  # of the others: a region below its spares target
P_NEED = 0.30  # a region needs the model within 6 months (resale is not offered)
P_BID = 0.85  # a broker bid is open
P_BOARD = 0.06  # an open repair need for a board
P_NO_INVENTORY = 0.023  # serial not in the network inventory: an exception
P_WIPE_FAIL = 0.017  # wipe failed: an exception
P_EXPORT_CLEAR = 0.022  # controlled export class, bid screened clear: an approval of trade compliance
P_EXPORT_PENDING = 0.008  # controlled, screening not on file: an exception
P_COVERED = 0.084  # of US units: covered equipment under the programme, disposed of with its record on file

MODELS: tuple[tuple[str, str, int, float, float], ...] = (  # (class, model, new price, weight kg, share)
    ("radio", "RRU-4410", 5000, 14.0, 0.20),
    ("radio", "RRU-2200", 3000, 11.0, 0.10),
    ("baseband", "BBU-2200", 3800, 9.0, 0.14),
    ("router", "RTR-880", 2500, 8.0, 0.13),
    ("line_card", "LC-100", 1900, 3.0, 0.08),
    ("line_card", "LC-200", 3100, 3.0, 0.08),
    ("power_unit", "PSU-48", 560, 6.0, 0.13),
    ("microwave_link", "MWL-18", 2100, 5.0, 0.14),
)
GENERATION = {"LC-100": "previous", "LC-200": "current"}
FACTS = (
    "asset.model", "asset.revision", "asset.firmware", "asset.firmware_major_gap", "asset.site_kind", "asset.region",
    "asset.grade", "asset.weight_kg", "asset.manufacturer", "asset.export_class", "inventory.match",
    "config.wipe_fail_count", "removal.programme", "disposal.record", "bid.screening", "market.new_price",
    "market.generation", "market.broker_bid", "demand.open_site_demand", "demand.id", "demand.site",
    "demand.firmware_min_major", "demand.use_probability", "demand.need_6m", "demand.board_value",
    "spares.region_below_target",
)  # fmt: skip
REQUIRED_FACTS = ("asset.model", "asset.grade", "inventory.match", "config.wipe_fail_count")
HEAD = (
    "item_id", "class", "decided_at", "reason", "actual_route", "realised_value", "cost_logistics", "cost_refurb", "cost_test",
    "cost_fees", "market", *(c for f in FACTS for c in (f"fact.{f}", f"fact.{f}.at")),
)  # fmt: skip
COMMAND = "python -m di.services.modeler.replay_samples.telecom_network"


# ---------------------------------------------------------------- the generator
def _pick(draw: Callable[[], float], options: Sequence[Any], weights: Sequence[float]) -> Any:
    x, acc = draw() * sum(weights), 0.0
    for o, w in zip(options, weights, strict=True):
        acc += w
        if x < acc:
            return o
    return options[-1]


def _unit(draw: Callable[[], float], n: int) -> dict[str, Any]:
    """One unit: its facts (name -> value, '' for none) and the route its history took."""
    cls, model, price, weight, _ = _pick(draw, MODELS, [m[4] for m in MODELS])
    us = draw() < 0.7
    gap = _pick(draw, (0, 1, 2), (0.7, 0.2, 0.1))
    f: dict[str, Any] = {k: "" for k in FACTS}
    f |= {
        "asset.model": model, "asset.revision": _pick(draw, ("A1", "B2", "C1"), (1, 2, 1)),
        "asset.firmware": f"{9 - gap}.{int(draw() * 5)}", "asset.firmware_major_gap": gap,
        "asset.site_kind": _pick(draw, ("edge", "core"), (4, 1)), "asset.region": "US" if us else "EU",
        "asset.grade": _pick(draw, ("A", "B", "C", "D"), (0.55, 0.25, 0.15, 0.05)),
        "asset.weight_kg": round(weight * (0.9 + 0.2 * draw()), 1), "asset.manufacturer": _pick(draw, OTHER_MAKERS, (3, 2, 1)),
        "inventory.match": "yes", "config.wipe_fail_count": 0, "market.new_price": price,
        "demand.open_site_demand": "no", "demand.need_6m": 0,
    }  # fmt: skip
    if model in GENERATION:
        f["market.generation"] = GENERATION[model]
    site = draw() < P_SITE
    if site:
        region = _pick(draw, ("N", "S"), (1, 1))
        f |= {"demand.open_site_demand": "yes", "demand.id": f"SD-{n:05d}", "demand.firmware_min_major": 9,
              "demand.site": f"SITE-{region}-{1 + int(draw() * 40):03d}"}  # fmt: skip
    spares = draw() < P_SPARES
    region_below = _pick(draw, ("North", "South"), (1, 1))
    prob = round(0.25 + 0.45 * draw(), 2)
    if spares or site:
        f["demand.use_probability"] = prob
    if spares and not site:
        f["spares.region_below_target"] = region_below
    if draw() < P_NEED:
        f["demand.need_6m"] = 1 + int(draw() * 3)
    if draw() < P_BID:
        f["market.broker_bid"] = round(price * (0.25 + 0.25 * draw()), -1)
    if draw() < P_BOARD:
        f["demand.board_value"] = round(120 + 260 * draw())
    kind = draw()  # the one guardrail situation a unit may be in (they are exclusive here)
    covered = us and draw() < P_COVERED
    if covered:
        f |= {"asset.manufacturer": _pick(draw, COVERED, (1, 1)), "removal.programme": PROGRAMME, "disposal.record": "yes"}
    elif kind < P_NO_INVENTORY:
        f["inventory.match"] = "no"
    elif kind < P_NO_INVENTORY + P_WIPE_FAIL:
        f["config.wipe_fail_count"] = 1 + int(draw() * 2)
    elif kind < P_NO_INVENTORY + P_WIPE_FAIL + P_EXPORT_CLEAR:
        f |= {"asset.export_class": _pick(draw, ("5A002", "5A992"), (1, 1)), "bid.screening": "clear"}
    elif kind < P_NO_INVENTORY + P_WIPE_FAIL + P_EXPORT_CLEAR + P_EXPORT_PENDING:
        f |= {"asset.export_class": "5A002", "bid.screening": "pending"}
    return {"cls": cls, "facts": f, "route": _route(draw, f, covered)}


def _route(draw: Callable[[], float], f: Mapping[str, Any], covered: bool) -> str:
    """The route the unit's history took: people favour a named demand, then a spares gap, then a bid, then boards."""
    if covered:
        return "recycle"
    current_card = f["market.generation"] == "current"
    if f["demand.open_site_demand"] == "yes" and draw() < 0.82:
        return "redeploy"
    if f["spares.region_below_target"] and draw() < 0.75:
        return "spare"
    if f["market.broker_bid"] != "" and not current_card and f["demand.need_6m"] == 0 and draw() < 0.8:
        return "resell"
    if f["demand.board_value"] != "" and draw() < 0.5:
        return "harvest"
    return _pick(draw, ("recycle", "spare", "harvest"), (6, 3, 1)) if not current_card else "recycle"


def _realised(draw: Callable[[], float], route: str, f: Mapping[str, Any]) -> tuple[float, dict[str, float]]:
    """(the realised value, the costs) of the route taken."""
    price = float(f["market.new_price"])
    j = 0.9 + 0.2 * draw()
    if route == "redeploy":
        return round(price * j, 2), {"logistics": 60.0, "test": 85.0, "refurb": 0.0, "fees": 220.0}
    if route == "spare":
        prob = float(f["demand.use_probability"] or 0.3)
        return round(price * prob * j, 2), {"logistics": 60.0, "test": 0.0, "refurb": 180.0, "fees": 72.0}
    if route == "resell":
        bid = float(f["market.broker_bid"])
        return round(bid * j, 2), {"logistics": 60.0, "test": 0.0, "refurb": 0.0, "fees": round(bid * 0.08 + 150, 2)}
    if route == "harvest":
        return round(float(f["demand.board_value"] or 150) * j, 2), {"logistics": 0.0, "test": 25.0, "refurb": 0.0, "fees": 90.0}
    return round(float(f["asset.weight_kg"]) * 1.8 * j, 2), {"logistics": 60.0, "test": 0.0, "refurb": 0.0, "fees": 15.0}


def rows() -> list[dict[str, str]]:
    """The 1,260 history rows, in date order (module docstring). The same call always gives the same rows."""
    draw = mulberry32(SEED)
    units = [_unit(draw, n + 1) for n in range(UNITS)]
    cards = [i for i, u in enumerate(units) if u["facts"]["market.generation"] == "current" and u["route"] != "resell"]
    for _ in range(CURRENT_CARD_RESALES):  # TN-14: exactly these resell a current-generation line card
        i = cards.pop(int(draw() * len(cards)))
        f = units[i]["facts"]
        f["market.broker_bid"] = f["market.broker_bid"] or round(float(f["market.new_price"]) * 0.35, -1)
        f["demand.need_6m"] = 0
        units[i]["route"] = "resell"
    out: list[dict[str, str]] = []
    for n, u in enumerate(units):
        day = START + timedelta(days=n // PER_DAY)
        at = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=8 + int(draw() * 10), minutes=int(draw() * 60))
        known = (at - timedelta(days=1 + int(draw() * 3))).isoformat()
        value, cost = _realised(draw, u["route"], u["facts"])
        row = {
            "item_id": f"TN-H{n + 1:05d}", "class": u["cls"], "decided_at": at.isoformat(), "reason": "history",
            "actual_route": u["route"], "realised_value": f"{value:.2f}", "cost_logistics": f"{cost['logistics']:.2f}",
            "cost_refurb": f"{cost['refurb']:.2f}", "cost_test": f"{cost['test']:.2f}", "cost_fees": f"{cost['fees']:.2f}",
            "market": u["facts"]["asset.region"],
        }  # fmt: skip
        for name in FACTS:
            row[f"fact.{name}"] = str(u["facts"][name])
            row[f"fact.{name}.at"] = known
        out.append(row)
    return out


def resales_of_current_cards(data: Sequence[Mapping[str, str]]) -> int:
    """The rows that resell a line card of the current generation."""
    return sum(
        r["class"] == "line_card" and r["fact.market.generation"] == "current" and r["actual_route"] == "resell" for r in data
    )


def csv_text(data: Sequence[Mapping[str, str]] | None = None) -> str:
    """The rows as the fixture file: the first line is the command that makes it."""
    out = io.StringIO()
    out.write(f"# {COMMAND}\n")
    w = csv.DictWriter(out, fieldnames=HEAD, lineterminator="\n")
    w.writeheader()
    w.writerows(data if data is not None else rows())
    return out.getvalue()


if __name__ == "__main__":
    sys.stdout.write(csv_text())
