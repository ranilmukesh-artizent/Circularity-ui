"""Device market (dvmkt, plan 9 P9-6.3): the weekly price feed per SKU and grade, launches, live listings, wholesale bids,
settled sales and replacement demand of the device-recommerce flow. Read only.

Written against source-sim's synthetic market mock (source-sim/sim/generic/specs/device_market.py): no real marketplace
or price feed is connected. API key in `X-Api-Key`; offset paging (`items`, `next`, `total`); `?updated_since=` delta
reads (on the source's change stamp, `updatedAt`). Nothing is ever written to the source (the mock's POST and PATCH
are for other tasks).

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own;
it lands plain tables, not canonical facts (`map` makes none; the sync still keeps every record raw). The rows are landed
by the reader, in the sync's own session, a page at a time, so a failed, dry or sample run undoes them with it (a dry run
changes nothing). They are upserts on the source's key, so a sync twice is a sync once:
    prices             device_price_point            (sku_key, grade, week) -> price, currency
    launches           device_launch                 model (= replaces), successor (= name), launched_on
    listings           device_listing                case_id linked by IMEI from the trade-in that has a case (device_tradein),
                                                     kept when a later read finds none
    bids               device_bid                    lot_ref, buyer_code, amount, fees, logistics, received_at
    sales              device_sale                   imeis; case_ids linked by IMEI the same way
    replacementDemand  device_replacement_demand     sku_key, grade_min, qty (units), unit_cost (price); `reserved` is kept
    lots               not read: the bids name their lot
Only listings carry an org unit (the source's; None: shared).

The reads change nothing at the source. The one write to it is a received device's listing (`POST /listings`, the `list`
step of an approved case, `di.services.instructions.writers.list_device`). A sale new to us settles the cases it names
(`di.services.device.settle.on_sale`), in the same session as the landing.
"""

import json
from collections.abc import Callable, Iterator
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter
from di.connectors.http import SourceClient
from di.services.canonical.store import Fact

SOURCE = "dvmkt"
PATHS = {  # resource: (path, id field)
    "prices": ("/prices", "priceId"),
    "launches": ("/launches", "launchId"),
    "listings": ("/listings", "listingId"),
    "bids": ("/bids", "bidId"),
    "sales": ("/sales", "saleId"),
    "replacementDemand": ("/replacement-demand", "demandId"),
}  # fmt: skip
BATCH = 200

UPSERT = {
    "prices": text(
        "INSERT INTO device_price_point (sku_key, grade, week, price, currency, source) "
        "VALUES (:sku, :grade, CAST(:week AS date), :price, :cur, :src) "
        "ON CONFLICT (sku_key, grade, week) DO UPDATE SET price = EXCLUDED.price, currency = EXCLUDED.currency, "
        "source = EXCLUDED.source"
    ),
    "launches": text(
        "INSERT INTO device_launch (model, successor, launched_on) VALUES (:model, :successor, CAST(:on AS date)) "
        "ON CONFLICT (model, launched_on) DO UPDATE SET successor = EXCLUDED.successor"
    ),
    "listings": text(
        "INSERT INTO device_listing (listing_id, org_unit_id, imei, case_id, channel, price, listed_at, offers, status, "
        "updated_at) VALUES (:id, :org, :imei, "
        "(SELECT t.case_id FROM device_tradein t WHERE t.imei = :imei AND t.case_id IS NOT NULL "
        "ORDER BY t.received_at DESC LIMIT 1), :channel, :price, "
        "CAST(:listed AS timestamptz), :offers, :status, CAST(:updated AS timestamptz)) "
        "ON CONFLICT (listing_id) DO UPDATE SET org_unit_id = EXCLUDED.org_unit_id, imei = EXCLUDED.imei, "
        "case_id = COALESCE(EXCLUDED.case_id, device_listing.case_id), channel = EXCLUDED.channel, "
        "price = EXCLUDED.price, listed_at = EXCLUDED.listed_at, offers = EXCLUDED.offers, status = EXCLUDED.status, "
        "updated_at = EXCLUDED.updated_at"
    ),
    "bids": text(
        "INSERT INTO device_bid (bid_id, lot_ref, buyer_code, amount, fees, logistics, received_at) "
        "VALUES (:id, :lot, :buyer, :amount, :fees, :logistics, CAST(:at AS timestamptz)) "
        "ON CONFLICT (bid_id) DO UPDATE SET lot_ref = EXCLUDED.lot_ref, buyer_code = EXCLUDED.buyer_code, "
        "amount = EXCLUDED.amount, fees = EXCLUDED.fees, logistics = EXCLUDED.logistics, received_at = EXCLUDED.received_at"
    ),
    "sales": text(
        "INSERT INTO device_sale (sale_id, listing_id, lot_ref, imeis, price, fees, buyer_returns, settled_at, case_ids) "
        "VALUES (:id, :listing, :lot, CAST(:imeis AS jsonb), :price, :fees, :returns, CAST(:at AS timestamptz), "
        "COALESCE((SELECT jsonb_agg(DISTINCT t.case_id) FROM device_tradein t WHERE t.case_id IS NOT NULL "
        "AND t.imei IN (SELECT jsonb_array_elements_text(CAST(:imeis AS jsonb)))), '[]'::jsonb)) "
        "ON CONFLICT (sale_id) DO UPDATE SET listing_id = EXCLUDED.listing_id, lot_ref = EXCLUDED.lot_ref, "
        "imeis = EXCLUDED.imeis, price = EXCLUDED.price, fees = EXCLUDED.fees, buyer_returns = EXCLUDED.buyer_returns, "
        "settled_at = EXCLUDED.settled_at, case_ids = EXCLUDED.case_ids"
    ),
    "replacementDemand": text(
        "INSERT INTO device_replacement_demand (id, sku_key, grade_min, qty, unit_cost, needed_by) "
        "VALUES (:id, :sku, :grade, :qty, :cost, CAST(:needed AS date)) "
        "ON CONFLICT (id) DO UPDATE SET sku_key = EXCLUDED.sku_key, grade_min = EXCLUDED.grade_min, qty = EXCLUDED.qty, "
        "unit_cost = EXCLUDED.unit_cost, needed_by = EXCLUDED.needed_by"
    ),
}  # the demand's `reserved` is never in the update: a sync keeps the reservations


def params(name: str, p: dict[str, Any], org: str | None) -> dict[str, Any]:
    """The bind values of one document of resource `name`."""
    if name == "prices":
        return {"sku": p["skuKey"], "grade": p["grade"], "week": p["week"], "price": p["price"],
                "cur": p.get("currency", "USD"), "src": SOURCE}  # fmt: skip
    if name == "launches":
        return {"model": p["replaces"], "successor": p["name"], "on": p["launchDate"]}
    if name == "listings":
        return {
            "id": p["listingId"], "org": org, "imei": p["imei"], "channel": p["channel"], "price": p["price"],
            "listed": p["listedAt"], "offers": p.get("offers", 0), "status": p["status"],
            "updated": p.get("updatedAt") or p["listedAt"],
        }  # fmt: skip
    if name == "bids":
        return {
            "id": p["bidId"], "lot": p["lotRef"], "buyer": p["buyerCode"], "amount": p["amount"], "fees": p["fees"],
            "logistics": p["logistics"], "at": p["receivedAt"],
        }  # fmt: skip
    if name == "sales":
        return {
            "id": p["saleId"], "listing": p.get("listingId"), "lot": p.get("lotRef"), "imeis": json.dumps(p["imeis"]),
            "price": p["price"], "fees": p["fees"], "returns": p.get("buyerReturns", 0), "at": p["settledAt"],
        }  # fmt: skip
    return {
        "id": p["demandId"], "sku": p["skuKey"], "grade": p["minGrade"], "qty": p["units"], "cost": p["price"],
        "needed": p.get("neededBy"),
    }  # fmt: skip


def _org(s: Session, source_id: str) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return s.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": source_id}).scalar()


class DeviceMarketAdapter(GenericAdapter):
    source_id = SOURCE
    base_path = "/device-market/v1"
    auth_kind = "api_key"
    api_key_header = "X-Api-Key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Device market (synthetic)"
    source_type = "dvmkt"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        return [Resource(name, self.read(name, path, id_field)) for name, (path, id_field) in PATHS.items()]

    def read(self, name: str, path: str, id_field: str) -> Callable[[SourceClient, str | None], Iterator[Record]]:
        def reader(client: SourceClient, since: str | None) -> Iterator[Record]:
            org = _org(client.session, client.source_id)
            now = self.source_now(client)
            batch: list[Record] = []
            for row, url in self.pages(client, path, since):
                batch.append(Record(name, str(row[id_field]), row, url, now))
                if len(batch) >= BATCH:
                    yield from self.land(client.session, name, batch, org)
                    batch = []
            yield from self.land(client.session, name, batch, org)

        return reader

    @staticmethod
    def land(s: Session, name: str, batch: list[Record], org: str | None) -> list[Record]:
        """Upsert a batch in the sync's session (a rolled-back run undoes it), then hand its records on."""
        if batch:
            ids = [r.ext_id for r in batch]
            known = (
                set(s.execute(text("SELECT sale_id FROM device_sale WHERE sale_id = ANY(:i)"), {"i": ids}).scalars())
                if name == "sales"
                else set()
            )
            s.execute(UPSERT[name], [params(name, r.payload, org) for r in batch])
            if name == "sales":  # a sale new to us settles its cases (P9-6.12); one we had does not settle again
                from di.repositories import device_market
                from di.services.device import settle

                for sale in device_market.sales_by_id(s, [i for i in ids if i not in known]):
                    settle.on_sale(s, sale)
        return batch

    def map(self, record: Record) -> list[Fact]:  # noqa: ARG002 - the rows are landed as they are read
        return []


ADAPTER = DeviceMarketAdapter()
