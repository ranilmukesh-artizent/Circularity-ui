"""Ritchie Bros. Market Data mock (demo source `mkt`, schema `ritchie`; docs/backend-steps.md, B5b).

The demo's SOURCES.mkt: "Comparables API v2" at https://api.rbauction.example/v2, API key, offset paging, 30 calls a
minute, reads GET /comparables and GET /price-index; inputs "comparable transactions, realised prices, time-to-sale,
buyer demand"; status stale: "Feed token expired 6 Oct; pricing falls back to the last fresh comparables".
Served under /ritchie/v2 (see routes.py for the surface, seed.py for the data).

NO PUBLIC API DOCUMENTATION EXISTS. RB Global (Ritchie Bros., IronPlanet, Rouse Services) publishes no developer
portal or API reference for its market data; its pricing data reaches customers through Rouse products (Rouse Fleet
Manager, Rouse Analytics, appraisals), the monthly Rouse Market Trends report and the public "price results" pages.
Consulted (19 Nov 2026):
    https://rbglobal.com/insights/                       Rouse Market Trends report, Rouse Services industry reports
    https://www.rouseservices.com/wp-content/uploads/2026/02/Rouse-Fleet-Manager-Terms-of-Use-021326.pdf  (title only)
    https://apify.com/crawloop/rbauction-scraper         third-party: what a Ritchie Bros. price result holds (sold lot,
                                                         hammer price, make, model, year, meter, location, sale date)
    index.html (the demo): SOURCES.mkt, MAPPINGS.mkt (SOLD_PRC, DAYS_LISTED, CONDITION), the unmapped fields
    LISTING_PRICE, SOLD_DATE "14/09/2026", SELLER_NAME, and the query GET /comparables?class=…
So the API follows the demo's own description of the vendor and Ritchie Bros.' published terminology (price results,
lots, sale events, timed online and live auctions, Marketplace, private treaty). Every design choice is an assumption:

ASSUMPTION: base path /v2 below the vendor host prefix /ritchie; resources /comparables, /price-index (the demo's) plus
    /subjects (the customer's registered units, modelled on Rouse Fleet Manager's customer fleet), /market-summary and
    /feed/status, /feed/token.
ASSUMPTION: auth is a static API key in the X-Api-Key header. Demo credential: X-Api-Key: mkt-demo-key
    (account CIRCULARITY-REMARKETING). Missing key: 401 missing_api_key; unknown key: 401 invalid_api_key.
ASSUMPTION: errors are {"error": {"code", "message", "requestId", "target"?}} (the same shape as source-sim's fault
    middleware, which answers 401 invalid_token while the demo fault "token_expired" is on).
ASSUMPTION: offset paging (the demo says "Offset"): ?offset=&limit= (default 100, max 500); the body is
    {"totalCount", "offset", "limit", "dataAsOf", "results", "links": {"next"}}. Rate-limit headers are sent
    (X-RateLimit-Limit: 30) but not enforced.
ASSUMPTION: field names are upper-case as in the demo's MAPPINGS (SOLD_PRC, DAYS_LISTED, CONDITION); prices are INR
    in the lakh/crore notation ("8.1 L INR") with the exact amount in SOLD_PRC_AMT; SOLD_DATE is DD/MM/YYYY (the
    demo's sample); LAST_UPDATED is when the feed published the record (UTC, the delta field for ?modifiedSince=).
ASSUMPTION: conditions are dealer codes EXC, VG, G, FR, PR; buyer demand is BIDDERS per sale; time-to-sale is DAYS_LISTED.
ASSUMPTION: the match rule for a subject's comparables: same MAKE, MODEL, REGION and lot-size band (1, 2-10, 11-20, 21+),
    and the condition of the requested scenario (AS_IS, or REFURBISHED one grade up). Regions are IN-West / IN-South
    (/IN-North / IN-East); a subject's region is where it is held (Warehouse 1: IN-West; Warehouse 2, Repair centre:
    IN-South). /comparables takes the same criteria as filters (make, model, condition, region, lotSize, class …).
ASSUMPTION: freshness. The subscription feed refreshes hourly while its feed token is valid; a record is served only
    when it was published at or before the last refresh. The seed's feed token expired at the last refresh, 6 Oct
    14:00 UTC (the demo's freshMin 1140 at AS_OF), so /feed/status reports "stale" and two RT-1048 sales published
    later are held back (pendingRecords). POST /feed/token {"validityDays": 1..365} renews it: the feed refreshes at
    clock.now(), the held-back sales are served, and the event com.rbglobal.marketdata.feed.refreshed is emitted.
    The demo's starting fault (POST /_sim/faults/demo) separately makes every call answer 401, as the demo shows.
ASSUMPTION: COMP_IDs keep the B5 identifiers (RBC-<case>-nn as-is, RBR-<case>-nn refurbished); LOT_NO, SALE_EVENT and
    SELLER_NAME (anonymised consignor) are synthetic.
"""

from sim.core.mock import Mock
from sim.vendors.ritchie.routes import router
from sim.vendors.ritchie.seed import ensure, reset

MOCK = Mock("mkt", router, ensure, reset, "Ritchie Bros. Market Data")
