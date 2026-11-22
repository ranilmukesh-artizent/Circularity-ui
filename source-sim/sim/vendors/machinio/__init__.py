"""Machinio mock (demo source `dlr`, schema `machinio`; docs/backend-steps.md, B5b).

The demo's SOURCES.dlr: "Dealer API v1" at https://api.machinio.com/v1, API key, cursor paging, "API + events",
reads GET /listings and GET /offers; inputs "dealer offers, listing demand, fees, time-to-sale"; MAPPINGS.dlr
offer_amount -> market.dealer_offer, listing_age_days -> time to sell; unmapped offer_currency, dealer_contact.
Served under /machinio/v1 (see routes.py for the surface, seed.py for the data).

NO PUBLIC API DOCUMENTATION EXISTS. Machinio (a Liquidity Services company) publishes no developer portal or API
reference; sellers manage inventory and buyer inquiries in its dealer software, "Machinio System".
Consulted (19 Nov 2026):
    https://liquidityservices.com/services/machinio      Machinio System: manage inventory, respond to buyer inquiries
    https://www.machinio.com/blog/speedtoquote           dealer quoting and response speed
    https://www.equipmentworld.com/dealers/article/15770001/machinio-adds-service-features-to-equipment-dealer-platform
    https://apify.com/crawloop/machinio-scraper          third-party: what a public listing holds (title, price,
                                                         condition, year, location, seller)
    index.html (the demo): SOURCES.dlr, MAPPINGS.dlr and its unmapped fields
(https://www.machinio.com itself refuses automated reads.) Every design choice below is an assumption:

ASSUMPTION: auth is a seller API key in the X-Api-Key header. Demo credential:
    X-Api-Key: mch_demo_circularity_4f7b2e91   (account acct_7Q2M4K, Northfield India Remarketing)
    Missing key: 401 api_key_missing; unknown key: 401 api_key_invalid.
ASSUMPTION: errors are {"error": {"type", "code", "message", "param"?}} (types invalid_request_error,
    authentication_error); 404 resource_missing; 409 offer_expired / offer_not_open / listing_status_transition.
ASSUMPTION: cursor paging (the demo says "Cursor"): ?limit= (1..100, default 25) &cursor=<opaque>; the body is
    {"data": [...], "meta": {"total", "has_more", "next_cursor"}}. Deltas: ?updated_since=<ISO 8601 with zone>.
ASSUMPTION: field names are snake_case as in the demo's MAPPINGS (offer_amount, listing_age_days, offer_currency,
    dealer_contact). Money in USD; an offer's fees carry the buyer's freight quote and the channel fee in INR
    (freight_inr, channel_fee_inr, freight_lanes between the seller's location codes) and their USD total.
ASSUMPTION: resources: own listings (stock_number = the seller's asset id), /listings/{id}/similar (other dealers'
    listings Machinio matches to one of ours: listing demand), offers on own listings, /account.
ASSUMPTION: listing status draft -> active -> pending_sale -> sold, or withdrawn (LISTING_FLOW in routes.py); a listing
    becomes pending_sale when an offer on it is accepted. Conditions: Excellent, Very good, Good, Fair.
ASSUMPTION: offers have offer_kind firm or indicative and status open -> accepted / declined / countered (a counter
    must be above the offer, in its currency; it gives the buyer 7 more days) or expired. Validity: 14 days from
    created_at; past expires_at on the simulated clock an open or countered offer is expired and cannot be accepted.
ASSUMPTION: events (webhooks via source-sim's outbox): machinio.offer.accepted|declined|countered|expired,
    machinio.listing.updated|sold.
ASSUMPTION: identifiers keep the B5 values: listings ML-9<case>-01 (own), ML-9<case>-Lnn / -Rnn (similar, as-is /
    refurbished), offers MO-9<case> (RT-1048: MO-91048, $5,600, fees $800).
"""

from sim.core.mock import Mock
from sim.vendors.machinio.routes import router
from sim.vendors.machinio.seed import ensure, reset

MOCK = Mock("dlr", router, ensure, reset, "Machinio")
