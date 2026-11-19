"""Ritchie Bros. Market Data: tables (Postgres schema `ritchie`) and the seed (docs/BACKEND_STEPS.md, B5b).

Tables
    comparables   one realised sale (a "price result"): JSONB record plus the match columns (make, model, condition,
                  region, qty, sold_date) and LAST_UPDATED, the time the feed published it
    subjects      the customer's registered subject assets (the units it wants comparables for), with their scenarios
    price_index   monthly price index per asset class
    feed          one row: the subscription feed's last refresh and its feed-token expiry

The seed keeps the generic mock's values (sim/generic/specs/ritchie.py, B5) in the vendor's shape:
- per resale route, a comparable set whose median is the route's sale proceeds (RT-1048: 48, median $5,600, top
  comparable SOLD_PRC "8.1 L INR" = $9,700, 17 days listed, VG; RT-1049: 31, median $241); a refurbish-then-sell
  route gets a set one condition higher around its proceeds
- every set shares the subject's make, model, region and lot-size band, so the vendor's match rule finds exactly it
- every served sale is before 6 Oct; the feed last refreshed 6 Oct 14:00 UTC, when its feed token expired
- two RT-1048 sales published after that (6 Oct 18:00, 7 Oct 06:00) are held back until the feed token is renewed
  (one either side of the median, inside the range, so the set's median and high do not move when they arrive)
"""

import math
import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Column, Date, DateTime, Integer, MetaData, String, Table, insert, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.seed.model import CaseFacts, RouteFacts

FX = 83.5  # INR per USD, dated 2026-10-06 (the demo's EX_FX)
FEED_TS = datetime(2026, 10, 6, 14, 0, tzinfo=UTC)  # last refresh; the feed token expired then
FIRST_SALE = date(2026, 7, 1)
CONDITIONS = {"EXC": "Excellent", "VG": "Very good", "G": "Good", "FR": "Fair", "PR": "Poor"}
DEALER_GRADE = {"A": "EXC", "B": "VG", "C": "G", "D": "FR"}
GRADE_UP = {"A": "A", "B": "A", "C": "B", "D": "C"}
CHANNELS = ["Timed online auction", "Live auction", "Marketplace", "Private treaty"]
REGION_OF = {"Warehouse 1": "IN-West", "Warehouse 2": "IN-South", "Repair centre": "IN-South"}
SALE_SITES = {"IN-West": "Pune", "IN-South": "Chennai", "IN-North": "Delhi NCR", "IN-East": "Kolkata"}

md = MetaData(schema="ritchie")
COMPARABLES = Table(
    "comparables",
    md,
    Column("comp_id", String(30), primary_key=True),
    Column("make", String(60), nullable=False),
    Column("model", String(80), nullable=False),
    Column("asset_class", String(20), nullable=False),
    Column("condition", String(4), nullable=False),
    Column("region", String(12), nullable=False),
    Column("qty", Integer, nullable=False),
    Column("sold_date", Date, nullable=False),
    Column("amount", Integer, nullable=False),  # SOLD_PRC_AMT, INR
    Column("last_updated", DateTime(timezone=True), nullable=False),
    Column("doc", JSONB, nullable=False),
)
SUBJECTS = Table(
    "subjects",
    md,
    Column("subject_ref", String(30), primary_key=True),
    Column("last_updated", DateTime(timezone=True), nullable=False),
    Column("doc", JSONB, nullable=False),
)
PRICE_INDEX = Table(
    "price_index",
    md,
    Column("index_id", String(30), primary_key=True),
    Column("asset_class", String(20), nullable=False),
    Column("period", String(7), nullable=False),
    Column("last_updated", DateTime(timezone=True), nullable=False),
    Column("doc", JSONB, nullable=False),
)
FEED = Table(
    "feed",
    md,
    Column("id", Integer, primary_key=True),
    Column("feed_id", String(40), nullable=False),
    Column("refresh_interval_min", Integer, nullable=False),
    Column("last_refresh_at", DateTime(timezone=True), nullable=False),
    Column("token_expires_at", DateTime(timezone=True), nullable=False),
)


# ------------------------------------------------------------------ helpers (the demo's hashing and rounding)
def jround(x: float) -> int:
    """JavaScript Math.round (half up), so derived numbers equal the demo's."""
    return math.floor(x + 0.5)


def as_hex(case_id: str, k: str) -> int:
    """The demo's hashId (FNV-1a 32-bit) of case id + key, as an int."""
    h = 2166136261
    for ch in case_id + k:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def case_no(case_id: str) -> int:
    return int(case_id[3:])  # RT-1048 -> 1048


def lakh(inr: int) -> str:
    """The vendor's INR notation: 810000 -> "8.1 L INR", 1.2 crore -> "1.2 Cr INR", small amounts in full."""
    if inr >= 10_000_000:
        return f"{inr / 10_000_000:.1f} Cr INR"
    return f"{inr / 100000:.1f} L INR" if inr >= 100000 else f"{inr:,} INR"


def lot_band(qty: int) -> str:
    """Lot-size band of the match rule: single unit, 2-10, 11-20, 21+."""
    return "1" if qty <= 1 else "2-10" if qty <= 10 else "11-20" if qty <= 20 else "21+"


def model_of(f: CaseFacts) -> str:
    return " ".join(str(v) for v in list(f.spec.values())[:2])


def sale_amount(r: RouteFacts) -> float | None:
    t = next((t for t in r.terms if t.kind == "sale" and t.amt > 0), None)
    return t.amt if t else None


def _count(f: CaseFacts, r: RouteFacts, refurb: bool) -> int:
    for note in r.gate_notes:
        m = re.search(r"(\d+) comparable sales", note)
        if m and not refurb:
            return int(m.group(1))
    return 3 + as_hex(f.id, "|mkt|nr") % 3 if refurb else 5 + as_hex(f.id, "|mkt|n") % 4


def _target(f: CaseFacts, sale: float, refurb: bool) -> float:
    if not refurb:
        for fact in f.facts:
            m = re.search(r"median \$([\d,]+)", fact)
            if m:
                return float(m.group(1).replace(",", ""))
    return sale


def _comp(f: CaseFacts, cid: str, usd: float, cond: str, h: int, sold: date, published: datetime) -> dict:
    inr = jround(usd * FX)
    age = max(0.3, round(f.age + ((h >> 8) % 41 - 20) / 10, 1))
    region = REGION_OF.get(f.location, "IN-West")
    channel = CHANNELS[(h >> 4) % len(CHANNELS)]
    return {
        "COMP_ID": cid,
        "LOT_NO": str(1000 + h % 8000),
        "SALE_EVENT": f"{SALE_SITES[region]} {channel.lower()} {sold:%d %b %Y}",
        "CHANNEL": channel,
        "ASSET_CLASS": f.cls.upper(),
        "CATEGORY": f.product,
        "MAKE": f.mfr,
        "MODEL": model_of(f),
        "MODEL_DESC": " · ".join([f.product] + [str(v) for v in list(f.spec.values())[:2]]),
        "YEAR_MFG": 2026 - int(age),
        "AGE_YRS": age,
        "CONDITION": cond,
        "CONDITION_DESC": CONDITIONS[cond],
        "QTY": f.qty,
        "LISTING_PRICE": lakh(jround(inr * (1.03 + (h >> 16) % 9 / 100))),
        "SOLD_PRC": lakh(inr),
        "SOLD_PRC_AMT": inr,
        "CURRENCY": "INR",
        "SOLD_DATE": f"{sold:%d/%m/%Y}",
        "DAYS_LISTED": 8 + h % 40,
        "BIDDERS": 2 + (h >> 20) % 18,
        "SELLER_NAME": f"Consignor {(h >> 6) % 9000 + 1000}",
        "REGION": region,
        "COUNTRY": "IN",
        "LAST_UPDATED": published.isoformat().replace("+00:00", "Z"),
    }


def comparables_for(f: CaseFacts, r: RouteFacts, refurb: bool) -> list[dict]:
    sale = sale_amount(r)
    if sale is None or not f.grade:
        return []
    n, target = _count(f, r, refurb), _target(f, sale, refurb)
    cond = DEALER_GRADE[GRADE_UP[f.grade] if refurb else f.grade]
    tag = "R" if refurb else "C"
    usd = [target] if n % 2 else []  # symmetric pairs around the target, so the set's median is the target
    for k in range(n // 2):
        spread = 0.22 * (k + 1) / max(1, n // 2) * (0.85 + (as_hex(f.id, f"|mkt|{tag}{k}") % 30) / 100)
        usd += [target * (1 - spread), target * (1 + spread)]
    usd.sort()
    out = []
    for i, v in enumerate(usd):
        h = as_hex(f.id, f"|mkt|{tag}|{i}")
        sold = FIRST_SALE + timedelta(days=h % 96)  # 1 Jul .. 4 Oct
        published = min(datetime(sold.year, sold.month, sold.day, 6, tzinfo=UTC) + timedelta(days=1), FEED_TS)
        out.append(_comp(f, f"RB{tag}-{case_no(f.id)}-{i + 1:02d}", v, cond, h, sold, published))
    if f.id == "RT-1048" and not refurb:
        # MAPPINGS.mkt: SOLD_PRC 8.1 L INR ($9,700), 17 days listed, condition VG. The top of the set (a younger
        # unit), so the median (the $5,600 sale term) does not move.
        out[-1].update(
            SOLD_PRC="8.1 L INR", SOLD_PRC_AMT=809950, LISTING_PRICE="8.4 L INR", DAYS_LISTED=17, AGE_YRS=1.2, YEAR_MFG=2025
        )
    return out


def held_back(f: CaseFacts) -> list[dict]:
    """RT-1048 sales published after the feed token expired (not served until the token is renewed)."""
    if f.id != "RT-1048":
        return []
    out = []
    for i, (usd, sold, pub) in enumerate(
        [
            (5600 * 0.9, date(2026, 10, 6), datetime(2026, 10, 6, 18, tzinfo=UTC)),
            (5600 * 1.1, date(2026, 10, 6), datetime(2026, 10, 7, 6, tzinfo=UTC)),
        ]
    ):
        out.append(_comp(f, f"RBC-{case_no(f.id)}-{49 + i}", usd, "VG", as_hex(f.id, f"|mkt|late|{i}"), sold, pub))
    return out


def _subject(f: CaseFacts, scenarios: list[dict]) -> dict:
    created = datetime(2026, 9, 1, 8, tzinfo=UTC) + timedelta(hours=as_hex(f.id, "|mkt|sub") % 600)
    return {
        "SUBJECT_REF": f.asset_id,
        "ASSET_CLASS": f.cls.upper(),
        "CATEGORY": f.product,
        "MAKE": f.mfr,
        "MODEL": model_of(f),
        "YEAR_MFG": 2026 - int(f.age),
        "QTY": f.qty,
        "LOT_SIZE_BAND": lot_band(f.qty),
        "CONDITION": DEALER_GRADE[f.grade],
        "REGION": REGION_OF.get(f.location, "IN-West"),
        "SCENARIOS": scenarios,
        "CREATED_AT": created.isoformat().replace("+00:00", "Z"),
        "LAST_UPDATED": created.isoformat().replace("+00:00", "Z"),
    }


def _price_index(s: Seed) -> list[dict]:
    out = []
    for cls, trend in (("motor", 0.4), ("pump", 0.2), ("control", -0.3), ("drill", -0.6), ("batch", -0.5), ("it", -1.1)):
        value, prev = 100.0, None
        for i, m in enumerate(s.world.months):  # 'Oct 25' .. 'Sep 26'
            d = datetime.strptime(m, "%b %y")
            if i:
                value = round(value * (1 + (trend + (as_hex(cls, m) % 21 - 10) / 10) / 100), 1)
            pub = (d.replace(day=28) + timedelta(days=6)).replace(day=2)
            ts = f"{pub:%Y-%m-%d}T06:00:00Z"
            out.append(
                {
                    "INDEX_ID": f"PI-{cls.upper()}-{d:%Y-%m}",
                    "ASSET_CLASS": cls.upper(),
                    "PERIOD": f"{d:%Y-%m}",
                    "INDEX_BASE": "2025-10 = 100",
                    "INDEX_VALUE": value,
                    "CHANGE_MOM_PCT": round((value / prev - 1) * 100, 2) if prev else None,
                    "SAMPLE_SIZE": 180 + as_hex(cls, m + "n") % 400,
                    "PUBLISHED_AT": ts,
                    "LAST_UPDATED": ts,
                }
            )
            prev = value
    return out


def build(s: Seed) -> dict[str, list[dict]]:
    comps, subjects = [], []
    for case in s.cases.values():
        f = case.facts
        scenarios = []
        for r in f.routes:
            if r.id != "resale" or not f.grade or sale_amount(r) is None:
                continue
            refurb = r.variant == "refurb"
            comps += comparables_for(f, r, refurb)
            if not refurb:
                comps += held_back(f)
            cond = DEALER_GRADE[GRADE_UP[f.grade] if refurb else f.grade]
            scenarios.append({"SCENARIO": "REFURBISHED" if refurb else "AS_IS", "CONDITION": cond})
        if scenarios:
            subjects.append(_subject(f, sorted(scenarios, key=lambda x: x["SCENARIO"])))
    return {"comparables": comps, "subjects": subjects, "price_index": _price_index(s)}


def _ts(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def create(conn: Connection) -> None:
    conn.execute(text('CREATE SCHEMA IF NOT EXISTS "ritchie"'))
    md.create_all(conn)


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    data = build(seed)
    conn.execute(
        insert(COMPARABLES),
        [
            {
                "comp_id": c["COMP_ID"],
                "make": c["MAKE"],
                "model": c["MODEL"],
                "asset_class": c["ASSET_CLASS"],
                "condition": c["CONDITION"],
                "region": c["REGION"],
                "qty": c["QTY"],
                "sold_date": datetime.strptime(c["SOLD_DATE"], "%d/%m/%Y").date(),
                "amount": c["SOLD_PRC_AMT"],
                "last_updated": _ts(c["LAST_UPDATED"]),
                "doc": c,
            }
            for c in data["comparables"]
        ],
    )
    conn.execute(
        insert(SUBJECTS),
        [{"subject_ref": x["SUBJECT_REF"], "last_updated": _ts(x["LAST_UPDATED"]), "doc": x} for x in data["subjects"]],
    )
    conn.execute(
        insert(PRICE_INDEX),
        [
            {
                "index_id": x["INDEX_ID"],
                "asset_class": x["ASSET_CLASS"],
                "period": x["PERIOD"],
                "last_updated": _ts(x["LAST_UPDATED"]),
                "doc": x,
            }
            for x in data["price_index"]
        ],
    )
    conn.execute(
        insert(FEED).values(
            id=1, feed_id="IN-INDUSTRIAL-EQUIP", refresh_interval_min=60, last_refresh_at=FEED_TS, token_expires_at=FEED_TS
        )
    )
    return {k: len(v) for k, v in data.items()} | {"feed": 1}


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    conn.execute(text('DROP TABLE IF EXISTS "ritchie".docs, "ritchie".counters'))  # the B5 generic mock's tables
    md.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(select(FEED.c.id)).first() is None:
        load(conn, seed)
