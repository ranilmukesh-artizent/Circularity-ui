"""The deterministic repair history of the Depot Repair mock (plan 9, P9-4.1): closed repairs over three years.

`generate(seed=26110)` returns the rows of the `repair_history` table as the query service shows them (upper-case EBS
names). It owns the count table (`COUNTS`), the fault-to-part map (`FAULT_PARTS`) and the age bands; it never reads a
database and draws only from `random.Random(seed)`, so the same seed gives the same rows.

Rows
    Repair and Return   closed 7 Oct 2023 - 6 Oct 2026, one per count in `COUNTS` for every (class, fault, age band);
                        ISSUED true (the repaired tool went back to its owner), RELEASE_TO_SERVICE null.
    Refurbishment       30 per class, released to service and not issued (the refurbished stock a swap can draw on);
                        no fault code, GRADE A or B, RELEASE_TO_SERVICE {STATUS, RELEASED_AT, CERTIFICATE}.

Two cells are pinned to the figures the research samples quote (A section 1.9.1): (`CRH`, `MOT`, `13-24`) has 186 rows
and (`DCD`, `ELE`, `37+`) has 37. The other cells follow `CLASS_VOLUME` x `FAULT_SHARE` x `BAND_SHARE`, about 5,900
repairs in all.

Part numbers are `<class>-<index>`, the index being the 0-based position in the class's `parts` list of the tool-fleet
valuer (`di.services.modeler.valuers.tool_fleet.CLS`; source-sim cannot import it, so `PARTS` repeats the list's prices
in USD). `FAULT_PARTS` maps each fault code to the part indexes it replaces (MOT motor, GBX gearbox or drive train, ELE
electronics, WEA wear parts); where a class has no such component the nearest one is used.

Money: ACTUAL_COST is in the market's CURRENCY: parts + labour hours x the market's rate + the test fee, converted from
USD at `FX` (units per USD, as the app's `fx_rate` table).
"""

import random
from datetime import UTC, date, datetime, timedelta

SEED = 26110
FIRST_DAY, LAST_DAY = date(2023, 10, 7), date(2026, 10, 6)
BANDS = ("0-12", "13-24", "25-36", "37+")
FAULTS = ("MOT", "GBX", "ELE", "WEA")
CLASSES = ("CMH", "BRK", "DCD", "CRH", "AGR", "LSR")
MARKETS = ("DE", "UK", "US", "AU", "FR")
MARKET_WEIGHT = (22, 14, 40, 10, 14)
CURRENCY = {"DE": "EUR", "FR": "EUR", "UK": "GBP", "US": "USD", "AU": "AUD"}
FX = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "AUD": 1.52}
LABOUR_RATE_USD = {"DE": 74.0, "UK": 70.0, "US": 78.0, "AU": 72.0, "FR": 71.0}
TEST_FEE_USD = 25.0

# tool_fleet CLS parts (name, price in USD), in list order
PARTS: dict[str, list[tuple[str, float]]] = {
    "CMH": [("Motor armature", 260), ("Gearbox", 180), ("Electronics module", 120), ("Piston and seal kit", 90)],
    "BRK": [("Motor", 380), ("Impact mechanism", 320), ("Chisel holder", 110), ("Handle and vibration damper", 70)],
    "DCD": [("Drill motor", 900), ("Gearbox", 420), ("Drill stand", 380), ("Control electronics", 210)],
    "CRH": [("Brushless motor", 160), ("Electronics module", 95), ("Chuck assembly", 45)],
    "AGR": [("Armature", 70), ("Gear set", 38), ("On/off switch", 22)],
    "LSR": [("Laser module", 320), ("Rotor head", 170), ("Receiver", 110)],
}
# fault code -> part indexes replaced (the first is the main part)
FAULT_PARTS: dict[str, dict[str, list[int]]] = {
    "CMH": {"MOT": [0], "GBX": [1], "ELE": [2], "WEA": [3]},
    "BRK": {"MOT": [0], "GBX": [1], "ELE": [0], "WEA": [2, 3]},
    "DCD": {"MOT": [0], "GBX": [1], "ELE": [3], "WEA": [2]},
    "CRH": {"MOT": [0], "GBX": [2], "ELE": [1], "WEA": [2]},
    "AGR": {"MOT": [0], "GBX": [1], "ELE": [2], "WEA": [1]},
    "LSR": {"MOT": [1], "GBX": [1], "ELE": [0], "WEA": [2]},
}
CLASS_VOLUME = {"CMH": 1300, "BRK": 900, "DCD": 700, "CRH": 1700, "AGR": 800, "LSR": 500}
FAULT_SHARE = {"MOT": 0.40, "GBX": 0.25, "ELE": 0.20, "WEA": 0.15}
BAND_SHARE = {"0-12": 0.15, "13-24": 0.35, "25-36": 0.30, "37+": 0.20}
PINNED = {("CRH", "MOT", "13-24"): 186, ("DCD", "ELE", "37+"): 37}  # the A 1.9.1 samples
BAND_MONTHS = {"0-12": (1, 12), "13-24": (13, 24), "25-36": (25, 36), "37+": (37, 72)}
REFURBISHED_PER_CLASS = 30

COUNTS: dict[tuple[str, str, str], int] = {
    (c, f, b): PINNED.get((c, f, b), round(CLASS_VOLUME[c] * FAULT_SHARE[f] * BAND_SHARE[b]))
    for c in CLASSES
    for f in FAULTS
    for b in BANDS
}


def age_band(months: int) -> str:
    return "0-12" if months <= 12 else "13-24" if months <= 24 else "25-36" if months <= 36 else "37+"


def fault_parts(model_class: str, fault_code: str) -> list[int]:
    return list(FAULT_PARTS[model_class][fault_code])


def _stamp(day: date, hour: int) -> str:
    return datetime(day.year, day.month, day.day, hour, 0, 0, tzinfo=UTC).isoformat()


def _day(rng: random.Random) -> date:
    return FIRST_DAY + timedelta(days=rng.randrange((LAST_DAY - FIRST_DAY).days + 1))


def _repair(rng: random.Random, cls: str, fault: str, band: str) -> dict:
    market = rng.choices(MARKETS, MARKET_WEIGHT)[0]
    idx = fault_parts(cls, fault)
    if rng.random() < 0.18:  # a second part, the class's cheapest wear item
        idx = idx + [len(PARTS[cls]) - 1] if idx[-1] != len(PARTS[cls]) - 1 else idx
    parts = [{"PART_NUMBER": f"{cls}-{i}", "QUANTITY": 1} for i in idx]
    hours = round(rng.randrange(4, 15) * 0.25, 2)
    fee = rng.random() < 0.25
    usd = sum(PARTS[cls][i][1] for i in idx) + hours * LABOUR_RATE_USD[market] + (TEST_FEE_USD if fee else 0.0)
    cur = CURRENCY[market]
    closed = _day(rng)
    lo, hi = BAND_MONTHS[band]
    return {
        "SERIAL_NUMBER": "",
        "MODEL_CLASS": cls,
        "AGE_MONTHS": rng.randint(lo, hi),
        "FAULT_CODE": fault,
        "MARKET": market,
        "PARTS": parts,
        "LABOUR_HOURS": hours,
        "TEST_FEE_APPLIED": fee,
        "TURNAROUND_DAYS": rng.randint(3, 14),
        "ACTUAL_COST": round(usd * FX[cur] * rng.uniform(0.95, 1.1), 2),
        "CURRENCY": cur,
        "DATE_CLOSED": _stamp(closed, 16),
        "REPAIR_TYPE": "Repair and Return",
        "GRADE": None,
        "RELEASE_TO_SERVICE": None,
        "ISSUED": True,
    }


def _refurbishment(rng: random.Random, cls: str) -> dict:
    market = rng.choices(MARKETS, MARKET_WEIGHT)[0]
    closed = _day(rng)
    cur = CURRENCY[market]
    cost = sum(p for _, p in PARTS[cls][:1]) * 0.5 + 3 * LABOUR_RATE_USD[market]
    return {
        "SERIAL_NUMBER": "",
        "MODEL_CLASS": cls,
        "AGE_MONTHS": rng.randint(13, 48),
        "FAULT_CODE": None,
        "MARKET": market,
        "PARTS": [{"PART_NUMBER": f"{cls}-0", "QUANTITY": 1}],
        "LABOUR_HOURS": 3.0,
        "TEST_FEE_APPLIED": True,
        "TURNAROUND_DAYS": rng.randint(5, 12),
        "ACTUAL_COST": round(cost * FX[cur], 2),
        "CURRENCY": cur,
        "DATE_CLOSED": _stamp(closed, 16),
        "REPAIR_TYPE": "Refurbishment",
        "GRADE": rng.choice("AAB"),
        "RELEASE_TO_SERVICE": {"STATUS": "RELEASED", "RELEASED_AT": _stamp(closed, 17), "CERTIFICATE": ""},
        "ISSUED": False,
    }


def generate(seed: int = SEED) -> list[dict]:
    """Every closed repair and released refurbishment, in the order they closed; REPAIR_NUMBER RH-1, RH-2 ... and the
    serial `<class>-H<nnnnn>` follow that order."""
    rng = random.Random(seed)
    rows: list[dict] = []
    for (cls, fault, band), n in COUNTS.items():
        rows += [_repair(rng, cls, fault, band) for _ in range(n)]
    for cls in CLASSES:
        rows += [_refurbishment(rng, cls) for _ in range(REFURBISHED_PER_CLASS)]
    rows.sort(key=lambda r: (r["DATE_CLOSED"], r["MODEL_CLASS"], r["REPAIR_TYPE"], r["AGE_MONTHS"], r["ACTUAL_COST"]))
    for n, r in enumerate(rows, 1):
        r["REPAIR_NUMBER"] = f"RH-{n}"
        r["SERIAL_NUMBER"] = f"{r['MODEL_CLASS']}-H{n:05d}"
        r["LAST_UPDATE_DATE"] = r["DATE_CLOSED"]
        if r["RELEASE_TO_SERVICE"]:
            r["RELEASE_TO_SERVICE"]["CERTIFICATE"] = f"RTS-RH-{n}"
    return rows
