"""Dealer management system (uc_dms, plan 9 P9-9.2): trade-ins, the lots, what each lot sells and the cars on them. Read only.

Written against source-sim's synthetic dealer mock (source-sim/sim/vendors/dealer_dms): no real dealer system is
connected. API key in `x-api-key`; offset paging (`items`, `next`, `total`). The mock has no change stamps, so every
resource is read in full (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered, so every demo screen and count is unchanged.
di.connectors.extra registers it and source.reconnect connects it. It fills the canonical models `asset`, `condition` and
`market` for a car, keyed by the source's org unit (schema.vin_key). It implements no registry entry of its own. Nothing is
ever written to the source (its four write routes are for the actions of later tasks).

Resources and facts (snake case of the source's camelCase fields)
    trade_ins   asset.<vin key>      vin, return_kind (always `trade_in`), book_value (tradeAllowance), mileage_at_return
                                     (mileage), model_year, segment, powertrain
                condition.<vin key>  payoff_confirmed
    stock       asset.<vin key>      lot_id, days_on_lot (a car on a lot; a lease return keeps its lease facts)
    vin_market  market.<vin key>     per lot, an object keyed by lot id: lot_avg_price, lot_days_to_sale, lot_spread,
                                     lot_comparables (the sales count), lot_distance_miles; and dealer_bid, the highest
                                     partner bid
    lots        no fact: read for the distances, kept raw
A car's market facts need its segment and mileage band (the lots' sales history is per segment and band). For a
trade-in they come from the trade-in; for any other car from the car's `asset` facts of the same org unit already in the
store (the lease system's `segment` and `mileage_at_return`), so sync the lease system first. A car with neither gets no
market facts until it has them.
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import SHARED_ORG, vin_key
from di.services.canonical.store import Fact

TRADE_ASSET = {
    "vin": "vin", "tradeAllowance": "book_value", "mileage": "mileage_at_return", "modelYear": "model_year",
    "segment": "segment", "powertrain": "powertrain",
}  # fmt: skip
BANDS = (("0-40k", 40000), ("40-80k", 80000), ("80-120k", 120000))
LOT_FACTS = {  # market field -> the lot-sales cell's field (or the lot's distance)
    "lot_avg_price": "avgPrice", "lot_days_to_sale": "avgDaysToSale", "lot_spread": "spread", "lot_comparables": "count",
    "lot_distance_miles": "distanceMiles",
}  # fmt: skip


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


def mileage_band(miles: float) -> str:
    return next((name for name, top in BANDS if miles < top), "120k+")


class DealerDmsAdapter(GenericAdapter):
    source_id = "uc_dms"
    base_path = "/dealer-dms/api/v1"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Dealer management system (synthetic)"
    source_type = "dms"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        return [
            Resource("trade_ins", lambda c, _s: self._plain(c, "trade_ins", "/trade-ins", "tradeId"), delta=False),
            Resource("lots", lambda c, _s: self._plain(c, "lots", "/lots", "lotId"), delta=False),
            Resource("stock", lambda c, _s: self._plain(c, "stock", "/stock", "stockId"), delta=False),
            Resource("vin_market", self.read_market, delta=False),
        ]

    # ------------------------------------------------------------- reading
    def _plain(self, client: SourceClient, name: str, path: str, id_field: str) -> Iterator[Record]:
        org = _org(client)
        for row, url in self.pages(client, path):
            yield Record(name, str(row[id_field]), row | {"org_unit_id": org}, url)

    def _known_cars(self, client: SourceClient, org: str | None) -> dict[str, tuple[str, float]]:
        """vin -> (segment, mileage) of the cars of this org unit already in the store (the lease system's facts)."""
        rows = client.session.execute(
            text(
                "SELECT data ->> 'vin' AS vin, data ->> 'segment' AS segment, data -> 'mileage_at_return' AS miles "
                "FROM canonical WHERE model = 'asset' AND starts_with(key, :p) AND jsonb_exists(data, 'vin')"
            ),
            {"p": f"{org or SHARED_ORG}:"},
        )
        return {r.vin: (r.segment, float(r.miles)) for r in rows if r.segment and r.miles is not None}

    def read_market(self, client: SourceClient, since: str | None) -> Iterator[Record]:  # noqa: ARG002 - always in full
        org = _org(client)
        lots = {x["lotId"]: x for x in self.read_all(client, "/lots")}
        cells = {(x["lotId"], x["segment"], x["mileageBand"]): x for x in self.read_all(client, "/lot-sales")}
        cars = self._known_cars(client, org)
        cars |= {t["vin"]: (t["segment"], float(t["mileage"])) for t in self.read_all(client, "/trade-ins")}
        for vin, (segment, miles) in sorted(cars.items()):
            band = mileage_band(miles)
            per_lot = {
                lot: {
                    "distanceMiles": info["distanceMiles"],
                    **{k: cells[lot, segment, band][k] for k in LOT_FACTS.values() if k != "distanceMiles"},
                }
                for lot, info in lots.items()
                if (lot, segment, band) in cells
            }
            bids = self.read_all(client, "/partner-bids", vin=vin)
            payload = {"vin": vin, "segment": segment, "mileage": miles, "band": band, "lots": per_lot, "bids": bids}
            yield Record("vin_market", vin, payload | {"org_unit_id": org}, client.url("/lot-sales"))

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource == "trade_ins":
            return self._trade_in(p)
        if record.resource == "stock":
            key = vin_key(p.get("org_unit_id"), p["vin"])
            return [
                Fact("asset", key, "lot_id", p["lotId"], "lotId", p["lotId"], "Pass-through"),
                Fact("asset", key, "days_on_lot", p["daysOnLot"], "daysOnLot", p["daysOnLot"], "Pass-through"),
            ]
        if record.resource == "vin_market":
            return self._market(p)
        return []

    @staticmethod
    def _trade_in(p: dict[str, Any]) -> list[Fact]:
        key = vin_key(p.get("org_unit_id"), p["vin"])
        facts = [Fact("asset", key, "return_kind", "trade_in", "tradeId", p.get("tradeId"), "Trade-in: kind trade_in")]
        facts += [
            Fact("asset", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in TRADE_ASSET.items()
        ]
        confirmed = p.get("payoffConfirmed")
        facts.append(Fact("condition", key, "payoff_confirmed", confirmed, "payoffConfirmed", confirmed, "Pass-through"))
        return keep(facts)

    @staticmethod
    def _market(p: dict[str, Any]) -> list[Fact]:
        key = vin_key(p.get("org_unit_id"), p["vin"])
        facts: list[Fact] = []
        if p.get("lots"):
            for to, src in LOT_FACTS.items():
                by_lot = {lot: cell[src] for lot, cell in p["lots"].items() if cell.get(src) is not None}
                facts.append(Fact("market", key, to, by_lot, src, by_lot, "One value per lot, keyed by lot id"))
        amounts = [b["amount"] for b in p.get("bids") or [] if b.get("amount") is not None]
        if amounts:
            facts.append(Fact("market", key, "dealer_bid", max(amounts), "amount", amounts, "Highest partner bid"))
        return facts


ADAPTER = DealerDmsAdapter()
