"""The device-recommerce world the three device mocks share (P9-6.1): registry (`dvreg`), lab (`dvlab`), market (`dvmkt`).

One deterministic generator (seed 4242, md5 of the seed and a label; no `random`, no clock), so every mock serves
the same devices and two builds are byte-identical. Documents are the camelCase JSON the mocks serve.

Owns: the 600 trade-ins and everything said about them (registry checks, diagnostics, gradings, photos, wipes, parts
declarations, repair quotes, disputes) and the market (a weekly price feed, a launch, listings, a wholesale lot and its
bids, settled sales, replacement demand). Never: reads the database, the clock or `sim.seed.seed()`; names a real
vendor product. Models are the backend device valuer's `DMOD` (brand, model, reference value of grade A), copied here
because source-sim cannot import the backend. Synthetic data only.

Numbers fixed by the spec (docs/agents/plans/09-agentic-platform.md, P9-6.1): 600 trade-ins in the 60 days before
2026-10-07; sample device IMEI 359990000000428; 15 blacklisted, 24 activation-locked, 12 financed, 30 read mismatches
(the four sets are disjoint and never hold the sample); BATCH-0007 of 40 devices, 12 without a wipe certificate; 50
disputes, 29 of them by P02 and P04 about "Screen graded before power-on"; the Galaxy S24 successor launch on 2026-09-14
with realised prices 8-12% under the feed for 3 weeks; 60 live listings; lot LOT-W-0001 with bids B01-B06.
"""

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from urllib.parse import quote

SEED = 4242
AS_OF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
SAMPLE_IMEI = "359990000000428"
SAMPLE_INDEX = 428
BATCH = "BATCH-0007"
LOT = "LOT-W-0001"

# (brand, model, reference value of grade A, age band): the valuer's DMOD (backend/di/services/modeler/valuers/device.py)
DMOD: list[tuple[str, str, int, str]] = [
    ("Apple", "iPhone 15", 470, "0-24m"),
    ("Apple", "iPhone 14", 370, "25-48m"),
    ("Apple", "iPhone 13", 290, "25-48m"),
    ("Apple", "iPhone 12", 210, "49m+"),
    ("Samsung", "Galaxy S24", 400, "0-24m"),
    ("Samsung", "Galaxy S23", 300, "25-48m"),
    ("Samsung", "Galaxy S21", 170, "49m+"),
    ("Google", "Pixel 9", 360, "0-24m"),
    ("Google", "Pixel 8", 250, "25-48m"),
    ("Motorola", "Moto G Power 2024", 95, "0-24m"),
]
GRADE_MULT = {"A": 1.0, "B": 0.85, "C": 0.68, "D": 0.45}
WORSE = {"A": "B", "B": "C", "C": "D", "D": "D"}
STORAGE = (128, 256)
STORAGE_MULT = {128: 1.0, 256: 1.12}
COLOURS = ("Black", "Silver", "Blue", "Gold", "Green")
VIEWS = ("front", "back", "screen")
FAILS = ("speaker", "camera", "wifi", "face unlock", "charging port")
OTHER_DISPUTE_REASONS = ("Cosmetic wear understated", "Battery health below declared", "Back glass crack missed")
SCREEN_REASON = "Screen graded before power-on"
N = 600
WEEKS = 52
LAUNCH_DATE = date(2026, 9, 14)
MON_LAST = date(2026, 10, 5)  # the Monday of the week of AS_OF
SALES_START = date(2026, 7, 20)  # 12 weeks of Mondays up to MON_LAST


def _h(*parts: object) -> int:
    return int(hashlib.md5("|".join(str(p) for p in (SEED, *parts)).encode()).hexdigest()[:12], 16)


def _u(*parts: object) -> float:
    """A deterministic number in [0, 1)."""
    return (_h(*parts) % 1_000_000) / 1_000_000


def _iso(t: datetime) -> str:
    return min(t, AS_OF).isoformat()


def sku_key(model: str, storage: int) -> str:
    return f"{model}|{storage}"


@dataclass
class DeviceWorld:
    tradeins: list[dict]
    checks: list[dict]
    diagnostics: list[dict]
    gradings: list[dict]
    photos: list[dict]
    wipes: list[dict]
    parts_declarations: list[dict]
    repair_quotes: list[dict]
    disputes: list[dict]
    prices: list[dict]
    launches: list[dict]
    listings: list[dict]
    bids: list[dict]
    lots: list[dict]
    sales: list[dict]
    replacement_demand: list[dict]

    def mismatches(self) -> list[str]:
        """IMEIs whose diagnostic read (IMEI, model or storage) differs from the trade-in."""
        sku = {t["imei"]: t["sku"] for t in self.tradeins}
        return [
            d["imei"]
            for d in self.diagnostics
            if d["imeiRead"] != d["imei"]
            or d["modelRead"] != sku[d["imei"]]["model"]
            or d["storageReadGb"] != sku[d["imei"]]["storageGb"]
        ]

    def as_dict(self) -> dict:
        return asdict(self)


def _imei(i: int) -> str:
    return f"35999{i:010d}"


def _label(text: str) -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120" viewBox="0 0 160 120">'
        '<rect width="160" height="120" fill="#e5e7eb"/>'
        f'<text x="80" y="64" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#374151">{text}</text>'
        "</svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg, safe="")


def _weeks() -> list[date]:
    return [MON_LAST - timedelta(weeks=WEEKS - 1 - k) for k in range(WEEKS)]


def _feed(model: tuple[str, str, int, str], storage: int, grade: str, k: int) -> float:
    base = model[2] * GRADE_MULT[grade] * STORAGE_MULT[storage]
    trend = 1 + 0.004 * (WEEKS - 1 - k)  # older weeks were dearer: prices erode
    noise = 1 + (_u("feed", model[1], storage, grade, k) - 0.5) * 0.03
    return round(base * trend * noise, 2)


def build() -> DeviceWorld:
    """Build the world from scratch (two calls give equal worlds); `world()` caches one."""
    models = {m[1]: m for m in DMOD}
    start = AS_OF - timedelta(days=60)

    # ---- the trade-ins
    base: list[dict] = []
    for i in range(N):
        m = DMOD[_h("model", i) % len(DMOD)]
        storage = STORAGE[_h("storage", i) % 2]
        grade = "ABBCCD"[_h("grade", i) % 6]
        amount = round(m[2] * GRADE_MULT[grade] * STORAGE_MULT[storage])
        partner = f"P{_h('partner', i) % 8 + 1:02d}"
        if i == SAMPLE_INDEX:
            m, storage, grade, amount, partner = models["iPhone 14"], 128, "B", 410, "P01"
        base.append(
            {
                "i": i,
                "m": m,
                "storage": storage,
                "grade": grade,
                "amount": amount,
                "partner": partner,
                "received": start + timedelta(minutes=_h("recv", i) % (60 * 24 * 60 - 600)),
            }
        )

    # ---- disjoint anomaly sets, never the sample
    perm = sorted((i for i in range(N) if i != SAMPLE_INDEX), key=lambda i: _h("perm", i))
    blacklisted, locked, financed = perm[0:15], perm[15:39], perm[39:51]
    mismatched = perm[51:81]
    disputed = [i for i in perm[81:] if base[i]["grade"] != "D"][:50]
    for k, i in enumerate(disputed):
        if k < 29:
            base[i]["partner"] = "P02" if k % 2 == 0 else "P04"
        else:
            base[i]["partner"] = ("P01", "P03", "P05", "P06", "P07", "P08")[_h("dp", i) % 6]
    in_dispute = set(disputed)
    graded = {b["i"]: (WORSE[b["grade"]] if b["i"] in in_dispute else b["grade"]) for b in base}

    tradeins, checks, diagnostics, gradings, photos, parts, quotes = [], [], [], [], [], [], []
    for b in base:
        i, m, imei = b["i"], b["m"], _imei(b["i"])
        got = b["received"]
        batch = i // 40 + 1
        tradeins.append(
            {
                "tradeInId": f"TI-{i:05d}",
                "imei": imei,
                "sku": {
                    "brand": m[0],
                    "model": m[1],
                    "storageGb": b["storage"],
                    "colour": COLOURS[_h("colour", i) % len(COLOURS)],
                    "carrierLock": "locked" if _h("carrier", i) % 5 == 0 else "unlocked",
                },
                "quote": {"declaredGrade": b["grade"], "amount": b["amount"], "currency": "USD", "quotedAt": _iso(got)},
                "partner": b["partner"],
                "batchId": f"BATCH-{batch:04d}",
                "bulk": (batch - 1) % 3 == 0,
                "receivedAt": _iso(got),
                "payoutAmount": round(b["amount"] * GRADE_MULT[graded[i]] / GRADE_MULT[b["grade"]]),
            }
        )
        checks.append(
            {
                "imei": imei,
                "blacklist": ("reported_lost" if blacklisted.index(i) % 2 == 0 else "reported_stolen") if i in blacklisted else "clear",
                "activationLock": "on" if i in locked else "off",
                "finance": "balance_owed" if i in financed else "clear",
                "checkedAt": _iso(got + timedelta(hours=1)),
            }
        )
        imei_read, model_read, storage_read = imei, m[1], b["storage"]
        if i in mismatched:
            kind = mismatched.index(i) % 3
            if kind == 0:
                imei_read = imei[:-1] + str((int(imei[-1]) + 1) % 10)
            elif kind == 1:
                model_read = DMOD[(DMOD.index(m) + 1) % len(DMOD)][1]
            else:
                storage_read = 256 if b["storage"] == 128 else 128
        roll = _h("fail", i) % 100
        fails = [FAILS[_h("f1", i) % 5]] if roll < 12 else []
        if roll < 3:
            fails.append(FAILS[(_h("f1", i) + 1 + _h("f2", i) % 4) % 5])
        battery = 84 if i == SAMPLE_INDEX else 70 + _h("bat", i) % 31
        diagnostics.append(
            {
                "imei": imei,
                "imeiRead": imei_read,
                "modelRead": model_read,
                "storageReadGb": storage_read,
                "functionalFails": fails,
                "batteryHealthPct": battery,
                "testedAt": _iso(got + timedelta(hours=4)),
            }
        )
        pids = [f"PH-{i:05d}-{v}" for v in VIEWS]
        gradings.append({"imei": imei, "cosmeticGrade": graded[i], "photoIds": pids, "gradedAt": _iso(got + timedelta(days=1))})
        photos += [{"photoId": p, "imei": imei, "view": v, "image": _label(v)} for p, v in zip(pids, VIEWS, strict=True)]
        roll = _h("parts", i) % 100
        parts.append(
            {
                "imei": imei,
                "status": "genuine" if roll < 90 else "non_genuine" if roll < 96 else "unknown",
                "declaredAt": _iso(got + timedelta(hours=3)),
            }
        )
        if battery < 85:
            quotes.append(
                {
                    "quoteId": f"RQ-{i:05d}",
                    "imei": imei,
                    "repair": "Battery swap",
                    "cost": 24,
                    "priceUplift": 28,
                    "days": 5,
                    "currency": "USD",
                    "quotedAt": _iso(got + timedelta(hours=5)),
                }
            )

    # ---- wipes: every device but 12 of BATCH-0007
    in_batch = [b["i"] for b in base if tradeins[b["i"]]["batchId"] == BATCH]
    unwiped = set(sorted(in_batch, key=lambda i: _h("nowipe", i))[:12])
    wipes = [
        {
            "certificateId": f"WC-{i:05d}",
            "imei": _imei(i),
            "method": ("Clear", "Purge")[_h("wm", i) % 2],
            "toolVersion": "4.2.1",
            "verification": "pass",
            "operator": f"OP-{_h('op', i) % 9 + 1:02d}",
            "at": _iso(base[i]["received"] + timedelta(hours=6)),
        }
        for i in range(N)
        if i not in unwiped
    ]

    disputes = []
    for k, i in enumerate(disputed):
        b = base[i]
        disputes.append(
            {
                "disputeId": f"DSP-{k + 1:04d}",
                "imei": _imei(i),
                "partner": b["partner"],
                "reason": SCREEN_REASON if k < 29 else OTHER_DISPUTE_REASONS[k % 3],
                "declaredGrade": b["grade"],
                "gradedGrade": graded[i],
                "raisedAt": _iso(b["received"] + timedelta(days=2)),
                "status": "upheld" if _h("ds", i) % 3 == 0 else "open",
            }
        )

    # ---- the market
    weeks = _weeks()
    prices = []
    for m in DMOD:
        for storage in STORAGE:
            for grade in GRADE_MULT:
                for k, wk in enumerate(weeks):
                    key = sku_key(m[1], storage)
                    prices.append(
                        {
                            "priceId": f"{key}|{grade}|{wk.isoformat()}",
                            "skuKey": key,
                            "grade": grade,
                            "week": wk.isoformat(),
                            "price": _feed(m, storage, grade, k),
                            "currency": "USD",
                        }
                    )
    feed = {(p["skuKey"], p["grade"], p["week"]): p["price"] for p in prices}
    launches = [
        {
            "launchId": "LCH-0001",
            "brand": "Samsung",
            "name": "Galaxy S24 successor",
            "replaces": "Galaxy S24",
            "launchDate": LAUNCH_DATE.isoformat(),
        }
    ]

    # listings: 12 stale Offers, 9 stale Buy Now, and 39 that are neither
    special = set(blacklisted) | set(locked) | set(financed) | {SAMPLE_INDEX}
    pool = [i for i in perm if i not in special][:60]
    plan = (
        [("Offers", 14 + k % 30, 0) for k in range(12)]  # >= 14 days, no offer
        + [("Buy Now", 21 + k % 30, 0) for k in range(9)]  # unsold >= 21 days
        + [("Offers", 14 + k * 4, 1 + k % 4) for k in range(6)]  # old but has offers
        + [("Offers", 1 + k * 3, 0) for k in range(4)]  # young
        + [("Buy Now", 1 + k, 0) for k in range(15)]  # young (1..15 days)
        + [("Marketplace", 1 + (k * 4) % 60, k % 4) for k in range(7)]
        + [("Auction", 1 + (k * 5) % 60, k % 3) for k in range(7)]
    )
    listings = []
    for n, (i, (channel, age, offers)) in enumerate(zip(pool, plan, strict=True), start=1):
        b = base[i]
        key = sku_key(b["m"][1], b["storage"])
        ref = feed[(key, graded[i], weeks[-1].isoformat())]
        listings.append(
            {
                "listingId": f"LST-{n:04d}",
                "imei": _imei(i),
                "skuKey": key,
                "grade": graded[i],
                "channel": channel,
                "price": round(ref * (1 + 0.05 * _u("lp", i)), 2),
                "listedAt": (AS_OF - timedelta(days=age, hours=_h("lh", i) % 24)).isoformat(),
                "offers": offers,
                "status": "live",
            }
        )

    lots = [
        {"lotRef": LOT, "brand": "Samsung", "model": "Galaxy S23", "grade": "C", "units": 100, "status": "open", "currency": "USD"}
    ]
    # per unit: B05 bids the most gross, but is not an approved buyer; B02 is the best net among the others (310)
    terms = {
        "B01": (316, 6, 4, "approved"),
        "B02": (324, 8, 6, "approved"),
        "B03": (312, 6, 5, "approved"),
        "B04": (320, 9, 7, "approved"),
        "B05": (340, 12, 8, "unverified"),
        "B06": (310, 5, 6, "approved"),
    }
    bids = [
        {
            "bidId": f"BID-{n:04d}",
            "lotRef": LOT,
            "buyerCode": code,
            "buyerStatus": status,
            "units": 100,
            "amount": amount,
            "fees": fees,
            "logistics": logistics,
            "currency": "USD",
            "receivedAt": (AS_OF - timedelta(hours=6 * n)).isoformat(),
        }
        for n, (code, (amount, fees, logistics, status)) in enumerate(terms.items(), start=1)
    ]

    # sales per SKU (model and storage): each SKU sells 20 times, 19 single units and one lot of 5, each time devices of that SKU
    # not sold before (until its devices run out), so every SKU has at least 20 sold devices in the 90 days to AS_OF and clears
    # the device pack's GR-D8 (`min_sales_90d` 20; lead decision 28 Nov: the seed, never the guardrail)
    by_sku: dict[str, list[int]] = {}
    for b in base:
        by_sku.setdefault(sku_key(b["m"][1], b["storage"]), []).append(b["i"])
    sold: dict[str, int] = {}
    sales = []
    for n in range(400):
        m = DMOD[n % len(DMOD)]
        r = n // len(DMOD)
        w = r % 12
        wk = SALES_START + timedelta(weeks=w)
        storage = STORAGE[(r + r // 12) % 2]  # 20 rounds each, spread over the weeks
        grade = "ABBCCD"[_h("sg", n) % 6]
        key = sku_key(m[1], storage)
        settled = datetime.combine(wk + timedelta(days=_h("sd", n) % (2 if w == 11 else 7)), datetime.min.time(), UTC) + timedelta(hours=12)
        on = feed[(key, grade, wk.isoformat())]
        hit = m[1] == launches[0]["replaces"] and LAUNCH_DATE <= wk < LAUNCH_DATE + timedelta(days=21)
        price = round(on * (1 - (0.085 + 0.03 * _u("sl", n))), 2) if hit else round(on * (0.97 + 0.06 * _u("sp", n)), 2)
        pool_s = by_sku[key]
        lot_sale = n >= 380
        at = _h("si", key) % len(pool_s) + sold.get(key, 0)
        units = 5 if lot_sale else 1
        sold[key] = sold.get(key, 0) + units
        imeis = [_imei(pool_s[(at + j) % len(pool_s)]) for j in range(units)]
        sales.append(
            {
                "saleId": f"SALE-{n + 1:04d}",
                ("lotRef" if lot_sale else "listingId"): f"LOT-W-S{n - 379:03d}" if lot_sale else f"LST-S{n + 1:04d}",
                "imeis": imeis,
                "model": m[1],
                "skuKey": key,
                "grade": grade,
                "week": wk.isoformat(),
                "price": price,
                "fees": round(price * 0.12, 2),
                "buyerReturns": 1 if _h("sr", n) % 100 < 6 else 0,
                "settledAt": settled.isoformat(),
            }
        )

    demand = [
        ("iPhone 14|128", "B", 5, 340),
        ("Galaxy S23|128", "C", 8, 190),
        ("Pixel 8|256", "B", 3, 235),
    ]
    replacement_demand = [
        {
            "demandId": f"RD-{n:04d}",
            "skuKey": key,
            "minGrade": grade,
            "units": units,
            "price": price,
            "currency": "USD",
            "raisedAt": (AS_OF - timedelta(days=2 * n)).isoformat(),
        }
        for n, (key, grade, units, price) in enumerate(demand, start=1)
    ]
    return DeviceWorld(
        tradeins, checks, diagnostics, gradings, photos, wipes, parts, quotes, disputes, prices, launches, listings, bids, lots,
        sales, replacement_demand,
    )  # fmt: skip


@lru_cache(maxsize=1)
def world() -> DeviceWorld:
    return build()
