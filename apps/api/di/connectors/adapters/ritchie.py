"""Ritchie Bros. Market Data (mkt): comparable sales and the price index (the demo's SOURCES.mkt). Read only.

API key (X-Api-Key), page/pageSize paging, `?modifiedSince=` deltas (see oracle_lease.GenericAdapter).
- comparables: one record per subject asset holding all of its comparable sales: the as-is set (RBC-…) and the
  refurbish-then-sell set (RBR-…). A delta re-reads the whole set of an asset with a change.
- price_index: one record per asset class with its monthly series; read in full (delta=False).
The demo starts this feed with an expired token (source-sim's demo fault): every call is refused with 401 and the
source goes to auth_expired; pricing then rests on the last comparables read, whose dates say how old they are.

Facts (mkt has authority over the market price)
    market.<SUBJECT_ASSET>   sale_price (USD, median of the as-is comparables), comparables_count, comparables (list),
                             comparable_high, comparable_low, time_to_sell (median days listed), grade (dealer grade
                             map), refurb_sale_price, refurb_comparables_count, refurb_grade, latest_sale_date,
                             feed_updated_at
    market.class:<cls>       price_index, price_index_period, price_index_change_pct, price_index_series,
                             feed_updated_at
Prices are INR in the vendor's lakh notation ("8.1 L INR"); USD at 83.5 INR/USD.
The demo's mapping: SOLD_PRC 8.1 L INR → $9,700 (Currency + Lakh unit expanded; RT-1048's top comparable, recorded as
market.comparable_high and in market.comparables); DAYS_LISTED 17 (that comparable); CONDITION VG → grade B (Dealer
grade map). RT-1048's sale price is the median of 48 comparables, $5,600.
"""

import re
import statistics
from decimal import Decimal

from di.canonical.store import Fact
from di.connectors.base import Record, Resource
from di.connectors.generic import INR_PER_USD, GenericAdapter, keep

DEALER_GRADE = {"EXC": "A", "VG": "B", "G": "C", "FR": "D", "PR": "D"}
LAKH, CRORE = 100_000, 10_000_000


def inr_amount(c: dict) -> Decimal:
    """The sale price in INR: the vendor's amount, else its notation expanded ("8.1 L INR" → 810000)."""
    if c.get("SOLD_PRC_AMT") is not None:
        return Decimal(str(c["SOLD_PRC_AMT"]))
    m = re.match(r"\s*([\d.,]+)\s*(L|Cr)?\s*INR", c["SOLD_PRC"])
    if not m:
        raise ValueError(f"unreadable SOLD_PRC {c['SOLD_PRC']!r}")
    n = Decimal(m[1].replace(",", ""))
    return n * {"L": LAKH, "Cr": CRORE}.get(m[2] or "", 1)


def usd(inr: Decimal) -> float:
    return float((inr / INR_PER_USD).quantize(Decimal("1")))


class RitchieAdapter(GenericAdapter):
    source_id = "mkt"
    base_path = "/ritchie/v2"
    auth_kind, api_key_header = "api_key", "X-Api-Key"
    items_key, next_key, next_param, size_param, page_size = "results", "nextPage", "page", "pageSize", 200
    since_param = "modifiedSince"

    def resources(self):
        return [
            Resource("comparables", lambda c, s: self.grouped(c, "comparables", "/comparables", "SUBJECT_ASSET", s)),
            Resource("price_index", self.read_price_index, delta=False),
        ]

    def read_price_index(self, client, since):
        rows = self.read_all(client, "/price-index")
        url = client.url("/price-index")
        for cls in sorted({r["ASSET_CLASS"] for r in rows}):
            yield Record("price_index", cls, {"ASSET_CLASS": cls, "items": [r for r in rows if r["ASSET_CLASS"] == cls]}, url)

    def map(self, record: Record) -> list[Fact]:
        if record.resource == "price_index":
            return keep(self._index(record.payload))
        return keep(self._comparables(record.payload))

    def _set(self, key: str, rows: list[dict], prefix: str) -> list[Fact]:
        rows = sorted(rows, key=inr_amount)
        if not rows:
            return []
        prices = [usd(inr_amount(c)) for c in rows]
        median = float(round(statistics.median(prices)))
        n = len(rows)
        grades = [DEALER_GRADE.get(c.get("CONDITION") or "", None) for c in rows]
        grade = max(set(grades), key=grades.count) if grades else None
        days = [c["DAYS_LISTED"] for c in rows if c.get("DAYS_LISTED") is not None]
        f = "refurb_" if prefix == "refurb" else ""
        facts = [
            Fact(
                "market",
                key,
                f + "sale_price",
                median,
                "SOLD_PRC",
                [c["SOLD_PRC"] for c in rows],
                f"Currency + Lakh unit expanded; median of {n} comparables",
            ),
            Fact("market", key, f + "comparables_count", n, "COMP_ID", n, "Count"),
            Fact(
                "market",
                key,
                f + "grade",
                grade,
                "CONDITION",
                sorted({c.get("CONDITION") for c in rows if c.get("CONDITION")}),
                "Dealer grade map",
            ),
        ]
        if not f:
            hi, lo = rows[-1], rows[0]
            facts += [
                Fact(
                    "market",
                    key,
                    "comparables",
                    [
                        {
                            "ref": c["COMP_ID"],
                            "price": p,
                            "sold_prc": c["SOLD_PRC"],
                            "sold_on": c.get("SOLD_DT"),
                            "days_listed": c.get("DAYS_LISTED"),
                            "grade": DEALER_GRADE.get(c.get("CONDITION") or ""),
                            "age_years": c.get("AGE_YRS"),
                            "channel": c.get("CHANNEL"),
                            "region": c.get("REGION"),
                        }
                        for c, p in zip(rows, prices, strict=True)
                    ],
                    "SOLD_PRC",
                    [c["SOLD_PRC"] for c in rows],
                    "Currency + Lakh unit expanded",
                ),
                Fact("market", key, "comparable_high", prices[-1], "SOLD_PRC", hi["SOLD_PRC"], "Currency + Lakh unit expanded"),
                Fact("market", key, "comparable_low", prices[0], "SOLD_PRC", lo["SOLD_PRC"], "Currency + Lakh unit expanded"),
                Fact(
                    "market",
                    key,
                    "time_to_sell",
                    int(round(statistics.median(days))) if days else None,
                    "DAYS_LISTED",
                    days,
                    "Integer (median days listed)",
                ),
            ]
        return facts

    def _comparables(self, p: dict) -> list[Fact]:
        key = p["SUBJECT_ASSET"]
        rows = p["items"]
        asis = [c for c in rows if not c["COMP_ID"].startswith("RBR-")]
        refurb = [c for c in rows if c["COMP_ID"].startswith("RBR-")]
        facts = self._set(key, asis, "") + self._set(key, refurb, "refurb")
        sold = [c["SOLD_DT"] for c in rows if c.get("SOLD_DT")]
        feed = [c["FEED_TS"] for c in rows if c.get("FEED_TS")]
        if sold:
            facts.append(Fact("market", key, "latest_sale_date", max(sold), "SOLD_DT", max(sold), "ISO date (newest sale)"))
        if feed:
            ts = max(feed).replace("Z", "+00:00")
            facts.append(Fact("market", key, "feed_updated_at", ts, "FEED_TS", max(feed), "Timestamp (UTC)"))
        return facts

    def _index(self, p: dict) -> list[Fact]:
        key = f"class:{p['ASSET_CLASS'].lower()}"
        rows = sorted(p["items"], key=lambda r: r["PERIOD"])
        if not rows:
            return []
        last = rows[-1]
        return [
            Fact(
                "market",
                key,
                "price_index",
                last["INDEX_VALUE"],
                "INDEX_VALUE",
                last["INDEX_VALUE"],
                f"Index ({last.get('INDEX_BASE')})",
            ),
            Fact("market", key, "price_index_period", last["PERIOD"], "PERIOD", last["PERIOD"], "Pass-through"),
            Fact(
                "market",
                key,
                "price_index_change_pct",
                last.get("CHANGE_MOM_PCT"),
                "CHANGE_MOM_PCT",
                last.get("CHANGE_MOM_PCT"),
                "Percent month on month",
            ),
            Fact(
                "market",
                key,
                "price_index_series",
                {r["PERIOD"]: r["INDEX_VALUE"] for r in rows},
                "INDEX_VALUE",
                [r["INDEX_VALUE"] for r in rows],
                "Pass-through",
            ),
            Fact(
                "market",
                key,
                "feed_updated_at",
                max(r["FEED_TS"] for r in rows).replace("Z", "+00:00"),
                "FEED_TS",
                max(r["FEED_TS"] for r in rows),
                "Timestamp (UTC)",
            ),
        ]


ADAPTER = RitchieAdapter()
