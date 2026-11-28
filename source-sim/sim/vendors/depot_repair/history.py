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

Money: ACTUAL_COST is in the market's CURRENCY and follows the tool-fleet pack's service-desk rate cards (the cards the
app's estimate prices with): parts at the parts card (`PARTS` x `PARTS_CARD_UPLIFT` x `FX`, rounded half up to a whole
unit, as the card's values), labour hours x the labour card's `LABOUR_RATE`, and the terms card's `TEST_FEE` (a repair is
always tested), times a small noise of +-2 %. So the estimate's P10 to P90 has the actuals' own spread: held out on
7 Oct 2026 it holds 65 % (AGR, 20 repairs) to 89 % (CRH) of them; GR-S1's bar is 70 %. (Market labour rates and a random
test fee had put every family at 47-68 %.) The cards are repeated here because source-sim cannot read the pack.
"""

import random
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

SEED = 26110
FIRST_DAY, LAST_DAY = date(2023, 10, 7), date(2026, 10, 6)
BANDS = ("0-12", "13-24", "25-36", "37+")
FAULTS = ("MOT", "GBX", "ELE", "WEA")
CLASSES = ("CMH", "BRK", "DCD", "CRH", "AGR", "LSR")
MARKETS = ("DE", "UK", "US", "AU", "FR")
MARKET_WEIGHT = (22, 14, 40, 10, 14)
CURRENCY = {"DE": "EUR", "FR": "EUR", "UK": "GBP", "US": "USD", "AU": "AUD"}
FX = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "AUD": 1.52}
LABOUR_RATE_USD = {"DE": 74.0, "UK": 70.0, "US": 78.0, "AU": 72.0, "FR": 71.0}  # refurbishments only
# the tool-fleet pack's service-desk cards (market_tables), in the market's currency: labour per_hour, terms test_fee, and
# the parts card = list price x 1.05 x FX
LABOUR_RATE = {"DE": 42.0, "FR": 46.0, "UK": 40.0, "US": 58.0, "AU": 64.0}
TEST_FEE = {"DE": 12.0, "FR": 12.0, "UK": 11.0, "US": 14.0, "AU": 15.0}
PARTS_CARD_UPLIFT = Decimal("1.05")
NOISE = (0.98, 1.02)

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
TIGHT = {("CRH", "MOT", "13-24")}  # the sample ticket CS0010042's cell: labour 2.0 to 2.5 h (`_repair`)
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


def card_part(model_class: str, index: int, currency: str) -> float:
    """The parts card's price of a part in a currency: list price x `PARTS_CARD_UPLIFT` x `FX`, half up to a whole unit."""
    price = Decimal(str(PARTS[model_class][index][1])) * PARTS_CARD_UPLIFT * Decimal(str(FX[currency]))
    return float(price.quantize(Decimal(1), ROUND_HALF_UP))


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
    draw = rng.randrange(4, 15)
    # the sample ticket's cell is a well-known repair (2.0 to 2.5 h), so its estimate is priced without a technician (plan 9
    # P9-4 demo: "186 similar repairs", within GR-S1's 30 % range); the same draw keeps every other row as it was
    hours = 2.0 + 0.25 * (draw % 3) if (cls, fault, band) in TIGHT else round(draw * 0.25, 2)
    rng.random()  # was the test-fee draw; kept so every later draw (and so every other column) stays as it was
    cur = CURRENCY[market]
    cost = sum(card_part(cls, i, cur) for i in idx) + hours * LABOUR_RATE[market] + TEST_FEE[market]
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
        "TEST_FEE_APPLIED": True,
        "TURNAROUND_DAYS": rng.randint(3, 14),
        "ACTUAL_COST": round(cost * rng.uniform(*NOISE), 2),
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
