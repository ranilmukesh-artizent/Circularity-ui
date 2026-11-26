"""Tool service, stock and trade demand (plan 9, P9-3.2): the open repair orders, the spare-parts catalogue, the
refurbished stock, certified pre-owned sales orders, tool pool requests and dealer trade bids that the tool-fleet pack
queues a returned tool against.

    GET {base}/repair-orders/open | /catalogue | /refurbished-units | /sales-orders | /pool-requests | /trade-bids

Synthetic, like every mock here. Not a demo source: it is in sim/core/registry.py EXTRA_SYSTEMS (source id `parts`).
API key in `x-api-key` (demo key `parts-demo-key`), offset paging (`items`, `next`, `total`), `?updated_since=` deltas.

Seed (deterministic, md5, anchored on 2026-10-07): 120 open repair orders, 90 catalogue rows (15 a class), 48
refurbished units (eight a class, remaining useful life 35 to 85%), 20 sales orders, 10 pool requests and 30 trade bids.
Part names are those of the pack's classes (tool_fleet.json `classes.<cls>.parts`); prices are synthetic.
Two resources take writes: an open repair order takes the part a harvest issues (P9-3.17, `parts.repair_order.updated`) and a
refurbished unit takes the reservation of an approved contract refresh (P9-5.5, PATCH `status` "reserved", `parts.stock.updated`).
"""

from datetime import timedelta

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs import fleet_contracts as fleet
from sim.seed import Seed

h, frac, AS_OF, TODAY = fleet.h, fleet.frac, fleet.AS_OF, fleet.TODAY
CLASSES, SITES, MARKETS, CUSTOMERS = fleet.CLASSES, fleet.SITES, fleet.MARKETS, fleet.CUSTOMERS
PARTS = {  # (part name, list price) as the pack's classes
    "CMH": (("Motor armature", 260), ("Gearbox", 180), ("Electronics module", 120), ("Piston and seal kit", 90)),
    "BRK": (("Motor", 380), ("Impact mechanism", 320), ("Chisel holder", 110), ("Handle and vibration damper", 70)),
    "DCD": (("Drill motor", 900), ("Gearbox", 420), ("Drill stand", 380), ("Control electronics", 210)),
    "CRH": (("Brushless motor", 160), ("Electronics module", 95), ("Chuck assembly", 45)),
    "AGR": (("Armature", 70), ("Gear set", 38), ("On/off switch", 22)),
    "LSR": (("Laser module", 320), ("Rotor head", 170), ("Receiver", 110)),
}  # fmt: skip
NEW_PRICE = {"CMH": 1450, "BRK": 1900, "DCD": 3200, "CRH": 620, "AGR": 260, "LSR": 1100}  # a new unit, as the pack's newP
REFURB_PRICE = {"CMH": 210, "BRK": 280, "DCD": 520, "CRH": 70, "AGR": 45, "LSR": 140}
DEALERS = (
    "Crestline Tool Traders", "Ironbridge Wholesale", "Northgate Equipment", "Baywater Tool Exchange", "Quarry Lane Supply",
    "Redfield Resale",
)  # fmt: skip
MARKET_FACTOR = {"US": 1.0, "UK": 1.08, "DE": 1.1, "FR": 1.1, "AU": 1.15}
EOL_SHARE = 0.1  # the end-of-life value of a new unit, as a share of its price


def _day(*parts: object, lo: int, span: int) -> str:
    return (TODAY + timedelta(days=lo + h(*parts) % span)).isoformat()


def build() -> dict[str, list[dict]]:
    repair_orders = []
    for i in range(1, 121):
        cls = CLASSES[h("roc", i) % 6]
        repair_orders.append(
            {"roId": f"RO-{60000 + i}", "customer": CUSTOMERS[h("rocu", i) % len(CUSTOMERS)],
             "partName": PARTS[cls][h("rop", i) % len(PARTS[cls])][0], "toolClass": cls, "backorder": h("rob", i) % 10 < 3,
             "needBy": _day("ron", i, lo=4, span=56)}
        )  # fmt: skip
    catalogue = []
    for i in range(90):
        cls, j = CLASSES[i % 6], i // 6
        name, price = PARTS[cls][j % len(PARTS[cls])]
        market = MARKETS[(j // len(PARTS[cls])) % 5]
        catalogue.append(
            {"partNo": f"PN-{1000 + i + 1}", "partName": name, "toolClass": cls,
             "price": round(price * MARKET_FACTOR[market], 2), "market": market}
        )  # fmt: skip
    stock = []
    for i in range(48):
        cls = CLASSES[i % 6]
        stock.append(
            {"unitId": f"RU-{7001 + i}", "serial": f"{cls}-{80000 + i}", "toolClass": cls,
             "grade": "ABC"[h("rug", i) % 3], "rulPct": 35 + h("rul", i) % 51, "site": SITES[h("rus", i) % 5],
             "status": "reserved" if h("rust", i) % 4 == 0 else "available",
             "refurbishedAt": (TODAY - timedelta(days=5 + h("ruf", i) % 120)).isoformat()}
        )  # fmt: skip
    sales = []
    for i in range(1, 21):
        cls = CLASSES[h("soc", i) % 6]
        sales.append(
            {"soId": f"SO-{80000 + i}", "customer": CUSTOMERS[h("socu", i) % len(CUSTOMERS)], "toolClass": cls,
             "site": SITES[h("sos", i) % 5], "needBy": _day("son", i, lo=3, span=45),
             "price": float(round(NEW_PRICE[cls] * (0.4 + frac("sop", i) * 0.2)))}
        )  # fmt: skip
    pool = []
    for i in range(1, 11):
        cls = CLASSES[h("tpc", i) % 6]
        pool.append(
            {"requestId": f"TPR-{i:04d}", "site": SITES[h("tps", i) % 5], "toolClass": cls,
             "needBy": _day("tpn", i, lo=7, span=50), "avoidedPurchase": float(round(NEW_PRICE[cls] * (1 - EOL_SHARE))),
             "quoteRef": f"PR-{1000 + i}"}
        )  # fmt: skip
    bids = []
    for i in range(1, 31):
        cls = CLASSES[h("bdc", i) % 6]
        bids.append(
            {"bidId": f"BID-{i:05d}", "dealer": DEALERS[h("bdd", i) % len(DEALERS)], "toolClass": cls,
             "gradeMin": "ABC"[h("bdg", i) % 3], "price": float(round(REFURB_PRICE[cls] * (0.9 + frac("bdp", i) * 0.8))),
             "expires": _day("bde", i, lo=2, span=40)}
        )  # fmt: skip
    return {"openRepairOrders": repair_orders, "catalogue": catalogue, "stock": stock, "salesOrders": sales,
            "poolRequests": pool, "bids": bids}  # fmt: skip


def seed(s: Seed) -> dict[str, list[dict]]:  # noqa: ARG001 - anchored on its own date, as the sandbox
    return build()


SPEC = Spec(
    source_id="parts",
    title="Tool service, stock and trade demand (synthetic)",
    schema="parts",
    base_path="/parts/api",
    auth=Auth("api_key", header="x-api-key"),
    paging=Paging("offset", limit_param="limit", offset_param="offset", items_key="items", next_key="next", total_key="total"),
    resources=(
        Resource("openRepairOrders", "/repair-orders/open", "roId", filters=("toolClass", "partName"), update=True,
                 event="parts.repair_order"),  # P9-3.17: a harvest posts its certified part here
        Resource("catalogue", "/catalogue", "partNo", filters=("toolClass", "market")),
        Resource("stock", "/refurbished-units", "unitId", filters=("toolClass", "status", "site"), update=True,
                 event="parts.stock"),  # P9-5.5: an approved refresh reserves its swap's unit here
        Resource("salesOrders", "/sales-orders", "soId", filters=("toolClass", "site")),
        Resource("poolRequests", "/pool-requests", "requestId", filters=("toolClass", "site")),
        Resource("bids", "/trade-bids", "bidId", filters=("toolClass", "dealer")),
    ),
    seed=seed,
)
