"""Vehicle auction platform (uc_auction, plan 9 P9-9.6): sale dates, fees, cleared prices, salvage bids and buyers.

Written against source-sim's synthetic auction mock (source-sim/sim/vendors/vehicle_auction): no real auction house is
connected. API key in `x-api-key`; offset paging (`items`, `next`, `total`). The mock has no change stamps, so every
resource is read in full (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered, so every demo screen and count is unchanged.
di.connectors.extra registers it and source.reconnect connects it. It fills the canonical models `market` (per car,
keyed by the source's org unit: schema.vin_key) and `vendor` (per buyer, keyed by the buyer id). It implements no
registry entry of its own. Nothing is ever written to the source here (its write routes are the instruction writers').

Resources and facts (snake case of the source's camelCase fields)
    vin_auction  market.<vin key>  auction_next_sale_days (days to the next sale of the site the car's return centre
                                   sends to, the lease system's `return_center` fact of the same org unit; none without
                                   one), auction_sell_fee, auction_transport, salvage_bid and salvage_buyer (the best
                                   bid and who made it)
    sold         outcome.<vin key> sale_price, sold_at, days_to_sale: a consignment that sold (P9-9.20; the sale a case is closed
                                   against, `di.services.cases.close_used_cars`)
    buyers       vendor.<buyer id> title_db_reporting (whether the buyer reports to the national title database)
    results      no fact: the cleared prices by segment and mileage band, kept raw
A car is a VIN of the org unit's `asset` facts already in the store or with a salvage bid; sync the lease system first
to get the return centres.
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import SHARED_ORG, vin_key
from di.services.canonical.store import Fact


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class VehicleAuctionAdapter(GenericAdapter):
    source_id = "uc_auction"
    base_path = "/vehicle-auction/v1"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Vehicle auction platform (synthetic)"
    source_type = "auction"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        return [
            Resource("vin_auction", self.read_cars, delta=False),
            Resource("buyers", lambda c, _s: self._plain(c, "buyers", "/buyers", "buyerId"), delta=False),
            Resource("results", lambda c, _s: self._results(c), delta=False),
            Resource("sold", self.read_sold, delta=False),
        ]

    # ------------------------------------------------------------- reading
    def _plain(self, client: SourceClient, name: str, path: str, id_field: str) -> Iterator[Record]:
        for row, url in self.pages(client, path):
            yield Record(name, str(row[id_field]), row, url)

    def _results(self, client: SourceClient) -> Iterator[Record]:
        for row, url in self.pages(client, "/results"):
            yield Record("results", f"{row['segment']}:{row['band']}", row, url)

    def read_sold(self, client: SourceClient, since: str | None) -> Iterator[Record]:  # noqa: ARG002 - always in full
        org = _org(client)
        for row, url in self.pages(client, "/sold"):
            yield Record("sold", str(row["consignmentId"]), row | {"org_unit_id": org}, url)

    @staticmethod
    def _store_cars(client: SourceClient, org: str | None) -> dict[str, str | None]:
        """vin -> return centre of the cars of this org unit already in the store."""
        rows = client.session.execute(
            text(
                "SELECT data ->> 'vin' AS vin, data ->> 'return_center' AS centre FROM canonical "
                "WHERE model = 'asset' AND starts_with(key, :p) AND jsonb_exists(data, 'vin')"
            ),
            {"p": f"{org or SHARED_ORG}:"},
        )
        return {r.vin: r.centre for r in rows}

    def read_cars(self, client: SourceClient, since: str | None) -> Iterator[Record]:  # noqa: ARG002 - always in full
        org = _org(client)
        fees = client.get_json("/fees")
        next_days: dict[str, int] = {}  # return centre -> days to the next sale of its site
        for sale in self.read_all(client, "/sales"):
            centre = sale["returnCenter"]
            next_days[centre] = min(next_days.get(centre, sale["daysAhead"]), sale["daysAhead"])
        best: dict[str, dict] = {}
        for bid in self.read_all(client, "/salvage-bids"):
            if bid["vin"] not in best or bid["amount"] > best[bid["vin"]]["amount"]:
                best[bid["vin"]] = bid
        cars = {v: None for v in best} | self._store_cars(client, org)
        for vin in sorted(cars):
            centre = cars[vin]
            site_days = next_days.get(centre) if centre else None
            payload = {
                "vin": vin, "org_unit_id": org, "returnCenter": centre, "nextSaleDays": site_days,
                "sellFee": fees.get("sellFee"), "transport": fees.get("transport"),
                "bestBid": {"amount": best[vin]["amount"], "buyerId": best[vin]["buyerId"]} if vin in best else None,
            }  # fmt: skip
            yield Record("vin_auction", vin, payload, client.url("/salvage-bids"))

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource == "buyers":
            reporting = p.get("titleDbReporting")
            fact = Fact("vendor", p["buyerId"], "title_db_reporting", reporting, "titleDbReporting", reporting, "Pass-through")
            return keep([fact])
        if record.resource == "sold":
            key = vin_key(p.get("org_unit_id"), p["vin"])
            sale = (("price", "sale_price"), ("soldAt", "sold_at"), ("daysToSale", "days_to_sale"))
            return keep([Fact("outcome", key, to, p.get(src), src, p.get(src), "Consignment sold") for src, to in sale])
        if record.resource != "vin_auction":
            return []
        key = vin_key(p.get("org_unit_id"), p["vin"])
        bid = p.get("bestBid") or {}
        pairs = [
            ("auction_next_sale_days", "nextSaleDays", p.get("nextSaleDays"), "Days to the next sale of the car's site"),
            ("auction_sell_fee", "sellFee", p.get("sellFee"), "Pass-through"),
            ("auction_transport", "transport", p.get("transport"), "Pass-through"),
            ("salvage_bid", "amount", bid.get("amount"), "Best salvage bid"),
            ("salvage_buyer", "buyerId", bid.get("buyerId"), "Buyer of the best salvage bid"),
        ]
        return keep([Fact("market", key, to, v, src, v, rule) for to, src, v, rule in pairs])


ADAPTER = VehicleAuctionAdapter()
