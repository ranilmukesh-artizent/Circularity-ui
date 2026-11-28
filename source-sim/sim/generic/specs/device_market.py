"""Device market (`dvmkt`, P9-6.1): the weekly price feed per SKU and grade, launches, live listings, wholesale lots and
their bids, settled sales and replacement demand. A `skuKey` is `<model>|<storageGb>` (e.g. `iPhone 14|128`).
Read: GET /prices, /launches, /listings, /bids, /lots, /sales, /replacement-demand.
Write: POST and PATCH /listings (event `devicemarket.listing`), POST /bids (event `devicemarket.bid`), POST /lots.
Sales carry the `devicemarket.sale` event type for the lead's later settlement flow; the mock serves them read-only.
Synthetic; the data is sim/seed/devices.py (seed 4242), shared with the registry and the lab. Not a demo source:
registered in sim/core/registry.py EXTRA_SYSTEMS.
"""

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed
from sim.seed.devices import world


def seed(s: Seed) -> dict[str, list[dict]]:  # noqa: ARG001 - the world does not depend on the demo's seed
    w = world()
    return {
        "prices": w.prices,
        "launches": w.launches,
        "listings": w.listings,
        "bids": w.bids,
        "lots": w.lots,
        "sales": w.sales,
        "replacementDemand": w.replacement_demand,
    }


SPEC = Spec(
    source_id="dvmkt",
    title="Device Market",
    schema="device_market",
    base_path="/device-market/v1",
    auth=Auth("api_key", header="X-Api-Key"),
    paging=Paging("offset", items_key="items", next_key="next", total_key="total"),
    resources=(
        Resource("prices", "/prices", "priceId", filters=("skuKey", "grade", "week")),
        Resource("launches", "/launches", "launchId", filters=("replaces",)),
        Resource(
            "listings",
            "/listings",
            "listingId",
            filters=("imei", "channel", "status", "skuKey"),
            create=True,
            update=True,
            id_format="LST-{n:04d}",
            event="devicemarket.listing",
            stamps=("listedAt",),  # a listing the app posts is listed now (the app's body carries no listedAt)
        ),
        Resource(
            "bids",
            "/bids",
            "bidId",
            filters=("lotRef", "buyerCode"),
            create=True,
            id_format="BID-{n:04d}",
            event="devicemarket.bid",
        ),
        Resource("lots", "/lots", "lotRef", filters=("lotRef", "model", "grade"), create=True, id_format="LOT-W-{n:04d}"),
        Resource("sales", "/sales", "saleId", filters=("listingId", "lotRef", "skuKey", "model"), event="devicemarket.sale"),
        Resource("replacementDemand", "/replacement-demand", "demandId", filters=("skuKey",)),
    ),
    seed=seed,
)
