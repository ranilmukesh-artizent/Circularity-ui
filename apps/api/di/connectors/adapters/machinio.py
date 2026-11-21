"""Machinio (dlr): the Dealer API v1 (source-sim's full mock, sim/vendors/machinio). Read only.

API key in X-Api-Key; cursor paging (?limit=&cursor=, body data / meta.next_cursor); deltas by ?updated_since=.
- offers: one record per offer on our listings (GET /offers). Delta on updated_at, so an offer that expires (the
  vendor's 14-day validity window on the simulated clock), is countered or accepted is read again.
- listings: one record per own listing (GET /listings) with the other dealers' listings Machinio matches to it
  (GET /listings/{id}/similar: listing demand and time to sale). Delta on the own listing's updated_at.

Facts (dlr has authority over the dealer offer)
    market.<stock_number>   dealer_offer (USD), dealer_offer_ref, listing_ref, dealer_name, dealer_offer_status
                            (open, countered, accepted, declined, expired), dealer_offer_kind (firm, indicative),
                            dealer_offer_type, dealer_offer_qty, dealer_unit_offer, dealer_offer_expires,
                            dealer_fees (USD), dealer_fees_detail (freight and channel fee in USD, commission, lanes),
                            dealer_time_to_sell (days)
                            open_listings, listing_count_by_grade, listing_grade, listing_status,
                            listing_asking_price (median, USD), listing_time_to_sell (median listing age, days),
                            listing_fee
Fees are INR in the source; USD at 83.5 INR/USD.
The demo's mapping: offer_amount → market.dealer_offer (Currency); listing_age_days → time to sell (Integer). Its
example values ($9,400 offer, 12 days listed) are not in the seed: RT-1048's offer is $5,600.
"""

import statistics
from collections.abc import Iterator

import httpx

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import iso_z, keep, to_usd, utc
from di.connectors.http import ApiKey, SourceClient

GRADE = {"Excellent": "A", "Very good": "B", "Good": "C", "Fair": "D"}
LIMIT = 100


def to_utc(v: str) -> str:
    u = utc(v)
    if u is None:
        raise ValueError(f"not a timestamp: {v!r}")
    return u.replace("Z", "+00:00")


class MachinioAdapter(Adapter):
    source_id = "dlr"
    base_path = "/machinio/v1"

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return ApiKey("X-Api-Key", secret or "mch_demo_circularity_4f7b2e91")

    def resources(self):
        return [Resource("offers", self.read_offers), Resource("listings", self.read_listings)]

    # ------------------------------------------------------------- reading
    def pages(self, client: SourceClient, path: str, **params) -> Iterator[tuple[dict, str]]:
        """Every item of a list, following next_cursor. Yields (item, request URL)."""
        cursor = None
        while True:
            q = {**params, "limit": str(LIMIT)} | ({"cursor": cursor} if cursor else {})
            body = client.get_json(path, params=q)
            client.note_records(len(body["data"]))
            url = str(httpx.URL(client.url(path), params=q))
            for item in body["data"]:
                yield item, url
            cursor = body["meta"].get("next_cursor")
            if not body["meta"].get("has_more") or not cursor:
                return

    def _since(self, since: str | None) -> dict:
        return {"updated_since": iso_z(utc(since) or "")} if since else {}  # `or ""` never applies: `since` is non-empty

    def read_offers(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        for o, url in self.pages(client, "/offers", **self._since(since)):
            yield Record("offers", o["id"], o, url, to_utc(o["updated_at"]))

    def read_listings(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        for listing, url in self.pages(client, "/listings", **self._since(since)):
            similar = [s for s, _ in self.pages(client, f"/listings/{listing['id']}/similar")]
            yield Record(
                "listings", listing["stock_number"], {"listing": listing, "similar": similar}, url, to_utc(listing["updated_at"])
            )

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        if record.resource == "offers":
            return keep(self._offer(record.payload))
        return keep(self._listing(record.payload))

    def _offer(self, p: dict) -> list[Fact]:
        key = p["stock_number"]
        cur = p.get("offer_currency") or "USD"
        fees = p.get("fees") or {}

        def pt(name: str, field: str, transform: str = "Pass-through") -> Fact:
            return Fact("market", key, name, p.get(field), field, p.get(field), transform)

        facts = [
            Fact("market", key, "dealer_offer", to_usd(p["offer_amount"], cur), "offer_amount", p["offer_amount"], "Currency"),
            Fact("market", key, "dealer_offer_ref", p["id"], "id", p["id"], "Pass-through"),
            pt("listing_ref", "listing_id"),
            pt("dealer_name", "dealer_name"),
            pt("dealer_offer_status", "status"),
            pt("dealer_offer_kind", "offer_kind"),
            pt("dealer_offer_type", "offer_type"),
            pt("dealer_offer_qty", "quantity", "Integer"),
            Fact(
                "market",
                key,
                "dealer_unit_offer",
                to_usd(p["unit_amount"], cur) if p.get("unit_amount") is not None else None,
                "unit_amount",
                p.get("unit_amount"),
                "Currency",
            ),
            Fact(
                "market", key, "dealer_offer_expires", to_utc(p["expires_at"]), "expires_at", p["expires_at"], "Timestamp (UTC)"
            ),
            pt("dealer_time_to_sell", "estimated_days_to_sale", "Integer days"),
        ]
        if fees:
            facts += [
                Fact("market", key, "dealer_fees", fees.get("total_usd"), "fees.total_usd", fees.get("total_usd"), "Currency"),
                Fact(
                    "market",
                    key,
                    "dealer_fees_detail",
                    {
                        "freight": to_usd(fees.get("freight_inr") or 0, "INR"),
                        "channel_fee": to_usd(fees.get("channel_fee_inr") or 0, "INR"),
                        "commission_pct": fees.get("commission_pct"),
                        "freight_lanes": fees.get("freight_lanes") or [],
                    },
                    "fees.freight_inr / fees.channel_fee_inr",
                    {"freight_inr": fees.get("freight_inr"), "channel_fee_inr": fees.get("channel_fee_inr")},
                    "Currency at 83.5 INR/USD",
                ),
            ]
        return facts

    def _listing(self, p: dict) -> list[Fact]:
        own, similar = p["listing"], [s for s in p["similar"] if s.get("status") == "active"]
        key = own["stock_number"]
        same = [s for s in similar if s.get("condition") == own.get("condition")] or similar
        ages = [s["listing_age_days"] for s in same if s.get("listing_age_days") is not None]
        asks = [to_usd(s["price"]["amount"], s["price"].get("currency")) for s in same if s.get("price")]
        by_grade: dict[str, int] = {}
        for s in similar:
            g = GRADE.get(s.get("condition") or "", "?")
            by_grade[g] = by_grade.get(g, 0) + 1
        fee = own.get("listing_fee") or {}
        return [
            Fact(
                "market",
                key,
                "open_listings",
                len(similar),
                "similar.id",
                [s["id"] for s in similar],
                "Count of active similar listings",
            ),
            Fact(
                "market",
                key,
                "listing_count_by_grade",
                dict(sorted(by_grade.items())),
                "similar.condition",
                [s.get("condition") for s in similar],
                "Condition map; count",
            ),
            Fact(
                "market",
                key,
                "listing_grade",
                GRADE.get(own.get("condition") or ""),
                "condition",
                own.get("condition"),
                "Condition map",
            ),
            Fact("market", key, "listing_status", own.get("status"), "status", own.get("status"), "Pass-through"),
            Fact(
                "market",
                key,
                "listing_asking_price",
                round(statistics.median(asks), 2) if asks else None,
                "price.amount",
                [s["price"]["amount"] for s in same if s.get("price")],
                "Currency; median of similar listings in the same condition",
            ),
            Fact(
                "market",
                key,
                "listing_time_to_sell",
                int(round(statistics.median(ages))) if ages else None,
                "listing_age_days",
                ages,
                "Integer (median listing age, days)",
            ),
            Fact(
                "market",
                key,
                "listing_fee",
                to_usd(fee["amount"], fee.get("currency")) if fee.get("amount") is not None else None,
                "listing_fee.amount",
                fee.get("amount"),
                "Currency",
            ),
        ]


ADAPTER = MachinioAdapter()
