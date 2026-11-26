"""Synthetic used-car history for the replay (plan 9, P9-9.15; story UC-22; registry entry I-16, the input of `import_history`).

    rows() -> list[dict]         2,140 past cars decided over the 32 days 24 Oct to 24 Nov 2026 (about 67 a day)
    history_rows(rows) -> list   the same cars as the string rows `replay.import` reads (`history.parse_csv` shape)
    make_csv(n) -> str           the CSV text of the first n cars; its first line holds the command that made it

Owns: the seeded generator (`mulberry32(1909)`, so the same rows on every run and machine) and the shares it draws: the lien,
odometer, recall and reconditioning shares below are tuned so the replay of the rows under the published used-car flow gives the
pack's modelled figures (79 % straight through, about 9 approvals and 5 exceptions a business day, about +$410 a car). The replay
code is never tuned. Exactly 31 rows are an auction sale under 40,000 miles (the count UC-13's plain-words guardrail needs).
Never does: read a clock, a database or a source, or value a channel (the past channel is picked from simple, fixed shares, and
`realised_net` is an invented figure near the sale); every value is invented, nothing is personal: a car is its code and VIN
(`SYNUC...`), and no column names a person, a lessee or an address. All figures are *modelled*, never measured.

The market inputs that are the same for every car (the three lots' prices, days and distances) are the pack's `replay.example
["defaults"]`; the facts that differ per car are the columns here (`asset.*`, `condition.*`, `market.*` as the canonical store
names them). Every fact is dated the day before the decision, so no future fact is ever read.
"""

import csv
import io
from datetime import UTC, date, datetime, timedelta
from typing import Any

from di.services.modeler.valuers.rng import mulberry32

SEED = 1909
CARS = 2140
FIRST_DAY = date(2026, 10, 24)
DAYS = 32  # 24 Oct to 24 Nov 2026; 2,140 cars over 32 days is about 67 a day, 22 of the days are business days
LOW_MILEAGE_AUCTIONS = 31  # auction sales under 40,000 miles (UC-13)
COMMAND = "python -m di.services.replay.sample used_cars"

# the shares the generator draws (tuned: never the replay code, see the module docstring)
P_LIEN = 0.025  # a lien still open at check-in
P_ODOMETER = 0.024  # the odometer photo disagrees with the lease record by more than the pack's tolerance
P_RECALL = 0.07  # an open recall
P_TRADE_IN = 0.12  # a dealer trade-in rather than a lease return
P_NO_PAYOFF = 0.01  # a trade-in whose loan payoff is not confirmed
SEGMENTS = (("compact", 0.22), ("midsize", 0.25), ("suv", 0.28), ("ev_crossover", 0.13), ("truck", 0.12))
SCORES = ((5, 0.29), (4, 0.43), (3, 0.2), (2, 0.05), (1, 0.03))
RECON = {5: (300, 900), 4: (600, 1800), 3: (1100, 2450), 2: (2600, 6000), 1: (7000, 17000)}  # estimate by condition score
REGIONS = (("RC-East", 0.5), ("RC-West", 0.5))
DEALER_SHARE = 0.3  # of the wholesale sales the past process made of cars retail would have paid more for
MISROUTED = 0.167  # the share of such cars (tuned to the modelled gross a car)
SALVAGE_RECON = 14000  # a car in the worst condition whose repair costs more than this was sold for salvage
AUCTION_RECON = 5000  # above this reconditioning the past process went to auction


def _pick(u: float, options: tuple[tuple[Any, float], ...]) -> Any:
    acc = 0.0
    for value, w in options:
        acc += w
        if u < acc:
            return value
    return options[-1][0]


def _between(u: float, lo: float, hi: float) -> float:
    return lo + (hi - lo) * u


def _per_day() -> list[int]:
    base, extra = divmod(CARS, DAYS)
    return [base + (d < extra) for d in range(DAYS)]


def _car(u: Any, n: int, day: date) -> dict[str, Any]:
    """One car: a fixed number of draws, so the order of the draws never depends on the car."""
    seg = _pick(u(), SEGMENTS)
    year = _pick(u(), ((2020, 0.1), (2021, 0.25), (2022, 0.35), (2023, 0.22), (2024, 0.08)))
    miles = int(round(((2026 - year) * 8500 + 14000) * _between(u(), 0.7, 1.35), -2))
    score = _pick(u(), SCORES)
    recon = int(round(_between(u(), *RECON[score]), -1))
    book = int(round(_between(u(), 16500, 24500) + (1500 if seg in ("suv", "truck") else 0), -2))
    wholesale = int(round(book * _between(u(), 0.68, 0.78), -1))
    bid = int(round(wholesale * _between(u(), 0.60, 0.70), -1))
    salvage = int(round(book * _between(u(), 0.12, 0.2), -1))
    fee, transport = int(_between(u(), 420, 640)), int(_between(u(), 120, 300))
    next_sale = int(_between(u(), 6, 21))
    lien, odo, recall = u() < P_LIEN, u() < P_ODOMETER, u() < P_RECALL
    trade = u() < P_TRADE_IN
    no_payoff = u() < P_NO_PAYOFF
    region = _pick(u(), REGIONS)
    route_u, noise_u, days_u = u(), u(), u()
    checked = datetime.combine(day - timedelta(days=1), datetime.min.time(), UTC) + timedelta(hours=9)
    lease_record = miles - (int(_between(u(), 10, 40) * 100) if not odo else 0)
    photo = miles if not odo else lease_record + int(_between(u(), 1500, 9000))
    return {
        "case_ref": f"UC-H{n:05d}", "decided_on": day.isoformat(), "vin": f"SYNUC{900000 + n:012d}",
        "asset.model_year": year, "asset.segment": seg, "asset.powertrain": "ev" if seg == "ev_crossover" else "petrol",
        "asset.return_kind": "trade_in" if trade else "lease_end", "asset.mileage_at_return": miles,
        "asset.mileage_lease_record": lease_record if odo else miles, "asset.book_value": book,
        "condition.condition_score": score, "condition.recon_estimate": recon,
        "condition.title_status": "lien" if lien else "clear", "condition.lien_open": lien, "condition.recall_open": recall,
        "condition.title_checked_at": checked.isoformat(), "condition.recall_checked_at": checked.isoformat(),
        "condition.odometer_statement_ref": f"OS-H{n:05d}", "condition.odometer_photo_reading": photo,
        **({"condition.payoff_confirmed": not no_payoff} if trade else {}),
        "market.wholesale_guide_price": wholesale, "market.retail_guide_price": int(round(book * 1.2, -1)),
        "market.auction_sell_fee": fee, "market.auction_transport": transport, "market.auction_next_sale_days": next_sale,
        "market.dealer_bid": bid, "market.salvage_bid": salvage, "market.salvage_buyer_reports": True,
        "region": region, "_route_u": route_u, "_noise_u": noise_u, "_days_u": days_u,
    }  # fmt: skip


def _past_route(c: dict[str, Any]) -> str:
    """The channel the past process took: fixed shares from the car's own facts, not the replay's valuation."""
    recon, score, u = c["condition.recon_estimate"], c["condition.condition_score"], c["_route_u"]
    if score == 1 and recon > SALVAGE_RECON:
        return "salvage"
    if c["condition.recall_open"] or recon > AUCTION_RECON:  # a retail listing is not allowed, or not worth the repair
        return "auction" if u < 0.95 else "dealer_trade"
    if u < MISROUTED:  # the past process sold a car that retail would have paid more for, to a wholesale channel
        return "auction" if u < MISROUTED * (1 - DEALER_SHARE) else "dealer_trade"
    return "retail"


def _realised(c: dict[str, Any], route: str) -> tuple[float, int]:
    """(realised net, days to sell) near the sale: an invented figure around a plain estimate of the channel."""
    noise = _between(c["_noise_u"], 0.93, 1.06)
    wholesale, recon = c["market.wholesale_guide_price"], c["condition.recon_estimate"]
    base = {
        "retail": 23800 - recon - 1300,
        "auction": wholesale * (1.0 if c["condition.condition_score"] >= 4 else 0.9) - 900,
        "dealer_trade": c["market.dealer_bid"] - 235,
        "salvage": c["market.salvage_bid"] - 180,
    }[route]
    days = {"retail": 28, "auction": 14, "dealer_trade": 7, "salvage": 5}[route]
    return round(base * noise, 2), max(1, int(days * _between(c["_days_u"], 0.6, 1.5)))


def rows() -> list[dict[str, Any]]:
    """The 2,140 cars, decided 24 Oct to 24 Nov 2026, in date order (module docstring); the same list on every call."""
    u = mulberry32(SEED)
    cars: list[dict[str, Any]] = []
    n = 0
    for d, count in enumerate(_per_day()):
        day = FIRST_DAY + timedelta(days=d)
        for _ in range(count):
            n += 1
            cars.append(_car(u, n, day))
    low = 0
    for c in cars:
        c["actual_route"] = _past_route(c)
    for c in cars:  # exactly LOW_MILEAGE_AUCTIONS auction sales under 40,000 miles: the rest of them retailed
        if c["actual_route"] == "auction" and c["asset.mileage_at_return"] < 40000:
            low += 1
            if low > LOW_MILEAGE_AUCTIONS:
                c["actual_route"] = "retail" if not c["condition.recall_open"] else "dealer_trade"
    for c in cars:
        cheap = c["asset.mileage_at_return"] < 40000 and c["actual_route"] == "retail"
        if low < LOW_MILEAGE_AUCTIONS and cheap and c["condition.condition_score"] >= 4 and not c["condition.recall_open"]:
            c["actual_route"] = "auction"
            low += 1
    out = []
    for c in cars:
        net, days = _realised(c, c["actual_route"])
        out.append({k: v for k, v in c.items() if not k.startswith("_")} | {"realised_net": net, "realised_days": days})
    return out


def _text(v: Any) -> str:
    return str(v).lower() if isinstance(v, bool) else str(v)


def history_rows(cars: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    """The cars as `replay.import` reads them: `item_id`, `class`, `decided_at`, `actual_route`, `realised_value`, `market` (the
    return centre), the costs left empty, and `fact.<name>` with `fact.<name>.at` for every fact the pack's gates and valuer
    read. The extra `vin` and `realised_days` columns carry no fact."""
    out: list[dict[str, str]] = []
    for c in cars if cars is not None else rows():
        decided = datetime.fromisoformat(c["decided_on"]).replace(hour=10, tzinfo=UTC)
        at = (decided - timedelta(days=1)).isoformat()
        r = {
            "item_id": c["case_ref"], "class": "car_ev" if c["asset.powertrain"] == "ev" else "car_ice",
            "decided_at": decided.isoformat(), "reason": "sample decision", "actual_route": c["actual_route"],
            "realised_value": _text(c["realised_net"]), "market": c["region"], "vin": c["vin"],
            "realised_days": _text(c["realised_days"]),
        }  # fmt: skip
        for k, v in c.items():
            if k.startswith(("asset.", "condition.", "market.")):
                r[f"fact.{k}"] = _text(v)
                r[f"fact.{k}.at"] = at
        out.append(r)
    return out


def make_csv(n: int = CARS) -> str:
    """The history CSV of the first n cars; the first line is the command that made it (the sample CLI writes it)."""
    hist = history_rows(rows()[:n])
    head = list(dict.fromkeys(k for r in hist for k in r))
    out = io.StringIO()
    out.write(f"# {COMMAND} {n}\n")
    w = csv.DictWriter(out, fieldnames=head, lineterminator="\n", restval="")
    w.writeheader()
    w.writerows(hist)
    return out.getvalue()
