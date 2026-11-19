"""Machinio (dlr): dealer offers and listings (the demo's SOURCES.dlr). Read only.

API key (X-Api-Key), page/per_page paging, `?updated_since=` deltas (see oracle_lease.GenericAdapter).
- offers: one record per dealer offer (one per asset with an as-is resale route). Delta.
- listings: one record per subject asset holding its open dealer listings (listing demand and time to sale); a delta
  re-reads the whole set of an asset with a change.

Facts (dlr has authority over the dealer offer)
    market.<asset_ref>   dealer_offer (USD), dealer_offer_ref, listing_ref, dealer_name, dealer_offer_status,
                         dealer_offer_type, dealer_offer_qty, dealer_unit_offer, dealer_offer_expires,
                         dealer_fees (USD), dealer_fees_detail (freight and channel fee in USD, commission, lanes),
                         dealer_time_to_sell (days)
    market.<subject_asset>   open_listings, listing_grade, listing_asking_price (median, USD), listing_time_to_sell
                         (median listing age, days), listing_fee
Fees are INR in the source; USD at 83.5 INR/USD.
The demo's mapping: offer_amount → market.dealer_offer (Currency); listing_age_days → time to sell (Integer). Its
example values ($9,400 offer, 12 days listed) are not in the seed (see the spec): RT-1048's offer is $5,600.
"""

import statistics

from di.canonical.store import Fact
from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep, to_usd


class MachinioAdapter(GenericAdapter):
    source_id = "dlr"
    base_path = "/machinio/v1"
    auth_kind, api_key_header = "api_key", "X-Api-Key"
    items_key, next_key, next_param, size_param, page_size = "data", "next_page", "page", "per_page", 200

    def resources(self):
        return [
            Resource("offers", lambda c, s: self.flat(c, "offers", "/offers", "offer_id", s)),
            Resource("listings", lambda c, s: self.grouped(c, "listings", "/listings", "subject_asset", s)),
        ]

    def map(self, record: Record) -> list[Fact]:
        if record.resource == "offers":
            return keep(self._offer(record.payload))
        return keep(self._listings(record.payload))

    def _offer(self, p: dict) -> list[Fact]:
        key = p["asset_ref"]
        cur = p.get("currency") or "USD"
        fees = p.get("fees") or {}
        facts = [
            Fact("market", key, "dealer_offer", to_usd(p["offer_amount"], cur), "offer_amount", p["offer_amount"], "Currency"),
            Fact("market", key, "dealer_offer_ref", p["offer_id"], "offer_id", p["offer_id"], "Pass-through"),
            Fact("market", key, "listing_ref", p.get("listing_ref"), "listing_ref", p.get("listing_ref"), "Pass-through"),
            Fact("market", key, "dealer_name", p.get("dealer_name"), "dealer_name", p.get("dealer_name"), "Pass-through"),
            Fact("market", key, "dealer_offer_status", p.get("status"), "status", p.get("status"), "Pass-through"),
            Fact("market", key, "dealer_offer_type", p.get("offer_type"), "offer_type", p.get("offer_type"), "Pass-through"),
            Fact("market", key, "dealer_offer_qty", p.get("quantity"), "quantity", p.get("quantity"), "Integer"),
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
                "market", key, "dealer_offer_expires", p.get("expires_at"), "expires_at", p.get("expires_at"), "Timestamp (UTC)"
            ),
            Fact(
                "market",
                key,
                "dealer_time_to_sell",
                p.get("estimated_days_to_sale"),
                "estimated_days_to_sale",
                p.get("estimated_days_to_sale"),
                "Integer days",
            ),
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

    def _listings(self, p: dict) -> list[Fact]:
        key = p["subject_asset"]
        rows = [r for r in p["items"] if (r.get("status") or "active") == "active"]
        if not rows:
            return [Fact("market", key, "open_listings", 0, "status", "active", "Count of active listings")]
        asis = [r for r in rows if r["listing_id"].rsplit("-", 1)[-1].startswith("L")] or rows  # Lnn as-is, Rnn refurbished
        ages = [r["listing_age_days"] for r in asis if r.get("listing_age_days") is not None]
        asks = [to_usd(r["asking_price"], r.get("currency") or "USD") for r in asis if r.get("asking_price") is not None]
        return [
            Fact(
                "market",
                key,
                "open_listings",
                len(rows),
                "listing_id",
                [r["listing_id"] for r in rows],
                "Count of active listings",
            ),
            Fact("market", key, "listing_grade", asis[0].get("grade"), "condition", asis[0].get("condition"), "Condition map"),
            Fact(
                "market",
                key,
                "listing_asking_price",
                round(statistics.median(asks), 2) if asks else None,
                "asking_price",
                [r.get("asking_price") for r in asis],
                "Currency; median of open listings",
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
                asis[0].get("listing_fee_usd"),
                "listing_fee_usd",
                asis[0].get("listing_fee_usd"),
                "Currency",
            ),
        ]


ADAPTER = MachinioAdapter()
