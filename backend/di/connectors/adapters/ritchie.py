"""Ritchie Bros. Market Data (mkt): the Comparables API v2 (source-sim's full mock, sim/vendors/ritchie). Read only.

API key in X-Api-Key; offset paging (?offset=&limit=, body totalCount / results / links.next); deltas by
?modifiedSince= on LAST_UPDATED (when the feed published a record).
- comparables: one record per registered subject (GET /subjects) holding the subject and, per scenario (AS_IS,
  REFURBISHED), the comparables the vendor's match rule gives it (GET /subjects/{ref}/comparables?scenario=). A delta
  reads the comparables and subjects changed since the cursor and re-reads every subject they touch (same make, model
  and region); nothing changed: no requests beyond those two, no records.
- price_index: one record per asset class with its monthly series; read in full (delta=False).
The demo starts this feed with an expired token (source-sim's demo fault): every call is refused with 401 and the
source goes to auth_expired; pricing then rests on the last comparables read, whose dataAsOf says how old they are.

Facts (mkt has authority over the market price)
    market.<SUBJECT_REF>     sale_price (USD, median of the as-is comparables), comparables_count, comparables (list),
                             comparable_high, comparable_low, time_to_sell (median days listed), grade (dealer grade
                             map), buyer_demand (median bidders), refurb_sale_price, refurb_comparables_count,
                             refurb_grade, latest_sale_date, feed_updated_at
    market.class:<cls>       price_index, price_index_period, price_index_change_pct, price_index_series,
                             feed_updated_at
Prices are INR in the vendor's lakh notation ("8.1 L INR"); USD at 83.5 INR/USD.
The demo's mapping: SOLD_PRC 8.1 L INR → $9,700 (Currency + Lakh unit expanded; RT-1048's top comparable, recorded as
market.comparable_high and in market.comparables); DAYS_LISTED 17 (that comparable); CONDITION VG → grade B (Dealer
grade map). RT-1048's sale price is the median of 48 comparables, $5,600.
"""

import re
import statistics
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

import httpx

from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import INR_PER_USD, iso_z, keep, utc
from di.connectors.http import ApiKey, SourceClient
from di.services.canonical.store import Fact

DEALER_GRADE = {"EXC": "A", "VG": "B", "G": "C", "FR": "D", "PR": "D"}
LAKH, CRORE = 100_000, 10_000_000
LIMIT = 500


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


def iso_date(ddmmyyyy: str | None) -> str | None:
    """The vendor's SOLD_DATE (DD/MM/YYYY) → ISO date."""
    return datetime.strptime(ddmmyyyy, "%d/%m/%Y").date().isoformat() if ddmmyyyy else None  # noqa: DTZ007 - a calendar date: only .date() is kept


def to_utc(v: str) -> str:
    return datetime.fromisoformat(v.replace("Z", "+00:00")).isoformat()


class RitchieAdapter(Adapter):
    source_id = "mkt"
    base_path = "/ritchie/v2"

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return ApiKey("X-Api-Key", secret or "mkt-demo-key")

    def resources(self):
        return [Resource("comparables", self.read_comparables), Resource("price_index", self.read_price_index, delta=False)]

    # ------------------------------------------------------------- reading
    def pages(self, client: SourceClient, path: str, **params) -> Iterator[tuple[dict, str, str]]:
        """Every row of a list, following the offset paging. Yields (row, request URL, dataAsOf)."""
        offset = 0
        while True:
            q = {**params, "offset": str(offset), "limit": str(LIMIT)}
            body = client.get_json(path, params=q)
            rows = body["results"]
            client.note_records(len(rows))
            url = str(httpx.URL(client.url(path), params=q))
            for row in rows:
                yield row, url, body.get("dataAsOf")
            offset += LIMIT
            if body.get("links", {}).get("next") is None or not rows or offset >= body["totalCount"]:
                return

    def read_comparables(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        subjects = [s for s, _, _ in self.pages(client, "/subjects")] if not since else []
        if since:
            stamp = iso_z(utc(since) or "")  # `or ""` never applies: `since` is a non-empty timestamp
            changed = [c for c, _, _ in self.pages(client, "/comparables", modifiedSince=stamp)]
            changed_subjects = {s["SUBJECT_REF"] for s, _, _ in self.pages(client, "/subjects", modifiedSince=stamp)}
            if not changed and not changed_subjects:
                return
            keys = {(c["MAKE"], c["MODEL"], c["REGION"]) for c in changed}
            subjects = [
                s
                for s, _, _ in self.pages(client, "/subjects")
                if s["SUBJECT_REF"] in changed_subjects or (s["MAKE"], s["MODEL"], s["REGION"]) in keys
            ]
        for s in subjects:
            ref = s["SUBJECT_REF"]
            path = f"/subjects/{ref}/comparables"
            payload: dict = {"SUBJECT_REF": ref, "subject": s, "dataAsOf": None}
            stamps = [s["LAST_UPDATED"]]
            urls = [client.url(path)]
            for sc in s.get("SCENARIOS") or []:
                read = list(self.pages(client, path, scenario=sc["SCENARIO"]))
                rows = [r for r, _, _ in read]
                if read:
                    urls.append(read[0][1])
                    payload["dataAsOf"] = read[-1][2]
                payload[sc["SCENARIO"]] = rows
                stamps += [r["LAST_UPDATED"] for r in rows]
            url = urls[-1]
            yield Record("comparables", ref, payload, url, to_utc(max(stamps, key=to_utc)))

    def read_price_index(self, client: SourceClient, since: str | None) -> Iterator[Record]:  # noqa: ARG002 - the adapter read interface; this read is always full
        read = list(self.pages(client, "/price-index"))
        rows = [r for r, _, _ in read]
        url, as_of = (read[0][1], read[-1][2]) if read else (client.url("/price-index"), None)
        for cls in sorted({r["ASSET_CLASS"] for r in rows}):
            items = [r for r in rows if r["ASSET_CLASS"] == cls]
            yield Record("price_index", cls, {"ASSET_CLASS": cls, "items": items, "dataAsOf": as_of}, url)

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        if record.resource == "price_index":
            return keep(self._index(record.payload))
        return keep(self._comparables(record.payload))

    def _set(self, key: str, rows: list[dict], refurb: bool) -> list[Fact]:
        rows = sorted(rows, key=inr_amount)
        if not rows:
            return []
        prices = [usd(inr_amount(c)) for c in rows]
        n = len(rows)
        grades = [DEALER_GRADE.get(c.get("CONDITION") or "") for c in rows]
        grade = max(set(grades), key=grades.count)
        f = "refurb_" if refurb else ""
        facts = [
            Fact(
                "market",
                key,
                f + "sale_price",
                float(round(statistics.median(prices))),
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
                sorted({c["CONDITION"] for c in rows if c.get("CONDITION")}),
                "Dealer grade map",
            ),
        ]
        if refurb:
            return facts
        days = [c["DAYS_LISTED"] for c in rows if c.get("DAYS_LISTED") is not None]
        bidders = [c["BIDDERS"] for c in rows if c.get("BIDDERS") is not None]
        hi, lo = rows[-1], rows[0]
        return [
            *facts,
            Fact(
                "market",
                key,
                "comparables",
                [
                    {
                        "ref": c["COMP_ID"],
                        "price": p,
                        "sold_prc": c["SOLD_PRC"],
                        "sold_on": iso_date(c.get("SOLD_DATE")),
                        "days_listed": c.get("DAYS_LISTED"),
                        "grade": DEALER_GRADE.get(c.get("CONDITION") or ""),
                        "age_years": c.get("AGE_YRS"),
                        "bidders": c.get("BIDDERS"),
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
            Fact(
                "market",
                key,
                "buyer_demand",
                float(statistics.median(bidders)) if bidders else None,
                "BIDDERS",
                bidders,
                "Median bidders per sale",
            ),
        ]

    def _comparables(self, p: dict) -> list[Fact]:
        key = p["SUBJECT_REF"]
        asis, refurb = p.get("AS_IS") or [], p.get("REFURBISHED") or []
        facts = self._set(key, asis, False) + self._set(key, refurb, True)
        sold = [c["SOLD_DATE"] for c in asis + refurb if c.get("SOLD_DATE")]
        if sold:
            newest = max(sold, key=lambda d: iso_date(d) or "")  # `or ""` never applies: sold dates are non-empty
            facts.append(
                Fact(
                    "market",
                    key,
                    "latest_sale_date",
                    iso_date(newest),
                    "SOLD_DATE",
                    newest,
                    "DD/MM/YYYY → ISO date (newest sale)",
                )
            )
        if p.get("dataAsOf"):
            facts.append(
                Fact("market", key, "feed_updated_at", to_utc(p["dataAsOf"]), "dataAsOf", p["dataAsOf"], "Timestamp (UTC)")
            )
        return facts

    def _index(self, p: dict) -> list[Fact]:
        key = f"class:{p['ASSET_CLASS'].lower()}"
        rows = sorted(p["items"], key=lambda r: r["PERIOD"])
        if not rows:
            return []
        last = rows[-1]
        facts = [
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
        ]
        if p.get("dataAsOf"):
            facts.append(
                Fact("market", key, "feed_updated_at", to_utc(p["dataAsOf"]), "dataAsOf", p["dataAsOf"], "Timestamp (UTC)")
            )
        return facts


ADAPTER = RitchieAdapter()
