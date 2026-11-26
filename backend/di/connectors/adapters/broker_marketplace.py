"""Broker marketplace (tn_broker, plan 9 P9-10.5): buyers' bids and cleared prices for used telecom equipment. Read only.

Written against source-sim's synthetic marketplace mock (source-sim/sim/vendors/broker_marketplace): no real marketplace is
connected. API key in `x-api-key`; the two lists are not paged and have no change stamps (Resource.delta False). Nothing is
ever written to the source here (its listing route is for later tasks).

Not one of the demo's 21 sources: it starts unregistered, so every demo screen and count is unchanged.
di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own.

Resources and facts (keyed by the model number; no org unit in the key, a market is not one org's)
    bids     market.<model>   broker_bids: the model's bids as the source serves them (a list, best price first)
    cleared  market.<model>   cleared_price: the unit price of the model's latest cleared sale (soldAt, then sale id)
"""

from collections.abc import Iterator
from typing import Any

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter
from di.connectors.http import SourceClient
from di.services.canonical.store import Fact


class BrokerMarketplaceAdapter(GenericAdapter):
    source_id = "tn_broker"
    base_path = "/broker-market/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Broker marketplace (synthetic)"
    source_type = "broker_marketplace"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def bids(client: SourceClient, _since: str | None) -> Iterator[Record]:
            rows, url = client.get_json("/bids"), client.url("/bids")
            client.note_records(len(rows))
            by_model: dict[str, list[dict]] = {}
            for b in rows:
                by_model.setdefault(str(b["model"]), []).append(b)
            for model, group in by_model.items():
                yield Record("bids", model, {"model": model, "bids": group}, url)

        def cleared(client: SourceClient, _since: str | None) -> Iterator[Record]:
            rows, url = client.get_json("/cleared"), client.url("/cleared")
            client.note_records(len(rows))
            latest: dict[str, dict] = {}
            counts: dict[str, int] = {}
            for s in rows:
                model = str(s["model"])
                counts[model] = counts.get(model, 0) + 1
                if model not in latest or (s["soldAt"], s["saleId"]) > (latest[model]["soldAt"], latest[model]["saleId"]):
                    latest[model] = s
            for model, s in latest.items():
                payload = {"model": model, "price": s["unitPrice"], "soldAt": s["soldAt"], "sales": counts[model]}
                yield Record("cleared", model, payload, url)

        return [Resource("bids", bids, delta=False), Resource("cleared", cleared, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p: dict[str, Any] = record.payload
        if record.resource == "bids":
            return [Fact("market", str(p["model"]), "broker_bids", list(p["bids"]), "bids", p["bids"], "The model's bids, whole")]
        return [Fact("market", str(p["model"]), "cleared_price", p["price"], "unitPrice", p["price"], "Latest cleared sale")]


ADAPTER = BrokerMarketplaceAdapter()
