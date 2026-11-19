"""Ritchie Bros. Market Data (the demo's SOURCES.mkt): comparable transactions, realised prices, time-to-sale.
Read: GET /comparables, /price-index. Read only.

The demo shows this feed as STALE: "Feed token expired 6 Oct; pricing falls back to the last fresh comparables".
The seed reflects that: the last successful pull (FEED_TS) is 6 Oct 14:00 UTC (19 h before AS_OF, the demo's
freshMin 1140), every comparable sold on or before 5 Oct, and the newest price-index period is Sep 2026.
B6 fault injection should start this system with its API key rejected (401, code "token_expired") until the fault
is cleared; the generic `expire_tokens` hook only clears OAuth tokens, so an API-key system needs a per-system
"reject credentials" fault for that.

Comparables are generated per resale route so they support the route's sale term: the as-is set has the case's
dealer grade and its median is the expected sale proceeds (or the median the case's facts quote, e.g. RT-1049
"31 comparable sales, median $241"); a refurbish-then-sell route gets a set one grade higher around its proceeds.
Set sizes follow the demo's gate notes where they give one (RT-1048: 48, RT-1049: 31). Prices are INR, with
SOLD_PRC in the vendor's lakh notation ("8.1 L INR"), as in MAPPINGS.mkt.
"""

import re
from datetime import datetime, timedelta

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs.shiplane import FX, as_hex, case_no, jround
from sim.seed import Seed
from sim.seed.model import CaseFacts, RouteFacts

FEED_TS = "2026-10-06T14:00:00Z"  # last fresh pull before the token expired
FIRST_SALE = datetime(2026, 7, 1)
DEALER_GRADE = {"A": "EXC", "B": "VG", "C": "G", "D": "FR"}
GRADE_UP = {"A": "A", "B": "A", "C": "B", "D": "C"}
CHANNELS = ["Timed online auction", "Live auction", "Marketplace", "Private treaty"]
REGIONS = ["IN-West", "IN-South", "IN-North", "IN-East"]


def sold_prc(inr: int) -> str:
    return f"{inr / 100000:.1f} L INR" if inr >= 100000 else f"{inr:,} INR"


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


def comparables_for(f: CaseFacts, r: RouteFacts, refurb: bool) -> list[dict]:
    sale = sale_amount(r)
    if sale is None or not f.grade:
        return []
    n, target = _count(f, r, refurb), _target(f, sale, refurb)
    grade = GRADE_UP[f.grade] if refurb else f.grade
    tag = "R" if refurb else "C"
    # symmetric pairs around the target, so the set's median is the target
    usd = [target] if n % 2 else []
    for k in range(n // 2):
        spread = 0.22 * (k + 1) / max(1, n // 2) * (0.85 + (as_hex(f.id, f"|mkt|{tag}{k}") % 30) / 100)
        usd += [target * (1 - spread), target * (1 + spread)]
    usd.sort()
    out = []
    for i, v in enumerate(usd):
        h = as_hex(f.id, f"|mkt|{tag}|{i}")
        inr = jround(v * FX)
        days = 8 + h % 40
        age = max(0.3, round(f.age + ((h >> 8) % 41 - 20) / 10, 1))
        out.append(
            {
                "COMP_ID": f"RB{tag}-{case_no(f.id)}-{i + 1:02d}",
                "SUBJECT_ASSET": f.asset_id,
                "ASSET_CLASS": f.cls.upper(),
                "CATEGORY": f.product,
                "MAKE": f.mfr,
                "MODEL_DESC": " · ".join([f.product] + [str(v) for v in list(f.spec.values())[:2]]),
                "YEAR_MFG": 2026 - int(age),
                "AGE_YRS": age,
                "CONDITION": DEALER_GRADE[grade],
                "QTY": 1,
                "SOLD_PRC": sold_prc(inr),
                "SOLD_PRC_AMT": inr,
                "CURRENCY": "INR",
                "SOLD_DT": (FIRST_SALE + timedelta(days=h % 96)).date().isoformat(),  # 1 Jul .. 4 Oct
                "DAYS_LISTED": days,
                "CHANNEL": CHANNELS[(h >> 4) % len(CHANNELS)],
                "REGION": REGIONS[(h >> 12) % len(REGIONS)],
                "FEED_TS": FEED_TS,
            }
        )
    if f.id == "RT-1048" and not refurb:
        # MAPPINGS.mkt: SOLD_PRC 8.1 L INR ($9,700), 17 days listed, condition VG. The top of the set, so the
        # median (the $5,600 sale term) does not move: a younger unit.
        top = out[-1]
        top.update(SOLD_PRC="8.1 L INR", SOLD_PRC_AMT=809950, DAYS_LISTED=17, CONDITION="VG", AGE_YRS=1.2, YEAR_MFG=2025)
    return out


def _price_index(s: Seed) -> list[dict]:
    out = []
    months = s.world.months  # 'Oct 25' .. 'Sep 26'
    for cls, trend in (("motor", 0.4), ("pump", 0.2), ("control", -0.3), ("drill", -0.6), ("batch", -0.5), ("it", -1.1)):
        value = 100.0
        for i, m in enumerate(months):
            d = datetime.strptime(m, "%b %y")
            if i:
                value = round(value * (1 + (trend + (as_hex(cls, m) % 21 - 10) / 10) / 100), 1)
            prev = out[-1]["INDEX_VALUE"] if i else None
            pub = (d.replace(day=28) + timedelta(days=6)).replace(day=2)
            out.append(
                {
                    "INDEX_ID": f"PI-{cls.upper()}-{d:%Y-%m}",
                    "ASSET_CLASS": cls.upper(),
                    "PERIOD": f"{d:%Y-%m}",
                    "INDEX_BASE": "2025-10 = 100",
                    "INDEX_VALUE": value,
                    "CHANGE_MOM_PCT": round((value / prev - 1) * 100, 2) if prev else None,
                    "SAMPLE_SIZE": 180 + as_hex(cls, m + "n") % 400,
                    "PUBLISHED_AT": f"{pub:%Y-%m-%d}T06:00:00Z",
                    "FEED_TS": FEED_TS,
                }
            )
    return out


def seed(s: Seed) -> dict[str, list[dict]]:
    comps = []
    for case in s.cases.values():
        f = case.facts
        for r in f.routes:
            if r.id == "resale":
                comps += comparables_for(f, r, refurb=r.variant == "refurb")
    return {"comparables": comps, "price_index": _price_index(s)}


SPEC = Spec(
    source_id="mkt",
    title="Ritchie Bros. Market Data",
    schema="ritchie",
    base_path="/ritchie/v2",
    auth=Auth("api_key", header="X-Api-Key"),
    paging=Paging(
        "page", page_param="page", size_param="pageSize", items_key="results", next_key="nextPage", total_key="totalResults"
    ),
    resources=(
        Resource(
            "comparables", "/comparables", "COMP_ID", filters=("SUBJECT_ASSET", "ASSET_CLASS", "MAKE", "CONDITION", "REGION")
        ),
        Resource("price_index", "/price-index", "INDEX_ID", filters=("ASSET_CLASS", "PERIOD")),
    ),
    updated_since_param="modifiedSince",
    seed=seed,
)
