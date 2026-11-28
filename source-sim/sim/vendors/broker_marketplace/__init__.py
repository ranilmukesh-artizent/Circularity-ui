"""Broker marketplace mock (plan 9, P9-10.5): buyers' bids and cleared prices for used telecom equipment, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `tn_broker`, schema
`broker_marketplace`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its
adapter (backend/di/connectors/adapters/broker_marketplace.py), which maps the bids of a model to a `market.broker_bids`
fact and its latest cleared sale to `market.cleared_price`, both keyed by the model. No real marketplace, no real company.

    GET  /broker-market/api/bids?model=      [{bidId, model, qty, unitPrice, buyerCountry, domestic,
                                               endUserScreening: {result: "clear" | "refer" | "none", ref}}]
    GET  /broker-market/api/cleared?model=   [{saleId, model, qty, unitPrice, soldAt}]
    POST /broker-market/api/listings         {serials, unitPrice, bidId}  idempotent on the bid and the set of serials

Bids come best price first (then bid id), cleared sales newest first; without `model` every model is listed. Auth: API key
in `x-api-key` (demo key `tn_broker-demo-key`); 401 with an error body otherwise. Errors are `{"error": {"code",
"message"}}`. A listing answers 201 with the new document, or 200 with the first one for a repeat; an unknown bid is 404, a
bad body 422 (invalid JSON 400). A listing is a ledger entry: it does not change the bids.

Data in Postgres schema `broker_marketplace` (models.py, seed.py): fixed, no randomness. `RRU-4410`: the best bid is 3,400,
domestic (an overseas bid, screening `refer`, is lower); `BBU-2200`: best 1,450, domestic; `RAD-7700`: one bid,
`BID-7700-OS`, 40 units at 1,900 from an overseas buyer, end-user screening `clear` (ref EUS-0106): the export gate asks
trade compliance to approve (TN-08; the smoke p9-10 demo). An unscreened bid (TN-07) is covered by the api tests.

ASSUMPTION: `domestic` is true when `buyerCountry` is "US"; an unscreened bid has `ref` null.
ASSUMPTION: the spec names no cleared-sale fields; `{saleId, model, qty, unitPrice, soldAt}` is the guess.
"""

from sim.core.mock import Mock
from sim.vendors.broker_marketplace import routes, seed

MOCK = Mock("tn_broker", routes.router, seed.ensure, seed.reset, "Broker marketplace (synthetic)")
