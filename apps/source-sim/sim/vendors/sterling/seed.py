"""Load the seed (B2) into the Sterling tables, as Sterling would hold them at the demo's as-of time.

What Sterling owns here (the demo's SOURCES.oms: "sales orders and lines, ship-to locations, need-by dates, return
authorisations, fulfilment and proof of delivery"):

- sales orders (DocumentType 0001), one per case with internal demand (71). OrderNo is the demo's demandOrder():
  RT-1048 → SO-48102, any other case → SO-(48000 + (case number × 7) mod 997). The matched line is the demo's
  caseDemand().line: line 10 for RT-1048, else 10 × (1 + exH(case, 'ln') mod 4). It orders a new unit of the
  returned asset's spec (ItemID e.g. MTR-55KW, the 55 kW motor RT-1048 returns), accepts a certified refurbished unit
  (Extn.ExtnAcceptsRefurbished Y), is open (1100 Created), ships to the demand site (ShipToKey LOC-CHN-03 for Site 3,
  the demo's LOCS codes), and needs it by caseDemand().needBy (RT-1048: 2026-10-17, i.e. ReqDeliveryDate
  2026-10-17T00:00:00+05:30). Unit price = the avoided purchase (RT-1048: 12,000 USD); Extn.ExtnAvoidedPurchaseOrder
  = PO-(48000 + case number), the planned S/4 purchase. Lines numbered below the matched line are earlier contract
  lines for new equipment, already delivered, that do not accept refurbished units. Forecast (unconfirmed) demand
  is an order with Extn.ExtnDemandStatus FORECAST; confirmed demand has CONFIRMED.
- return orders (DocumentType 0003), one per returned case (128): the RMA that brought the asset back. OrderNo is
  the demo's asRMA() (RMA-(55800 + hash mod 900); RT-1048 → RMA-56509; on the four hash collisions the later case
  takes the next free number). One line: the unit's ItemID with SerialNo = asset id (MTR-2041), status 3900 Return
  Received at the received date, ReceivingNode = where it sits now (Manhattan codes WH01, WH02, RC01), the WMS
  receipt (asReceipt(): GR-570262 for RT-1048), the return reason and the customer's intent.

Keys are deterministic: OrderHeaderKey 20261007 + 6-digit case number + 01 (sales) or 03 (return),
OrderLineKey = OrderHeaderKey + 4-digit PrimeLineNo. All times are kept in UTC and rendered in IST.
"""

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.seed.model import CaseFacts
from sim.vendors.sterling import tables as t

ENTERPRISE = "NORTHFIELD"
SALES, RETURN = "0001", "0003"
NODES = {"Warehouse 1": "WH01", "Warehouse 2": "WH02", "Repair centre": "RC01"}  # as the Manhattan WMS mock
# the demo's LOCS: customer sites (index.html)
SITE_LOCS = {
    "Site 1": ("LOC-PNQ-01", "Pune (Pimpri)", "MH", "411018"),
    "Site 2": ("LOC-HSR-02", "Hosur", "TN", "635109"),
    "Site 3": ("LOC-CHN-03", "Chennai (Ambattur)", "TN", "600058"),
    "Site 4": ("LOC-NSK-04", "Nashik", "MH", "422007"),
    "Site 5": ("LOC-VTZ-05", "Visakhapatnam", "AP", "530035"),
    "Site 6": ("LOC-CBE-06", "Coimbatore", "TN", "641021"),
    "Site 7": ("LOC-STV-07", "Surat", "GJ", "395003"),
    "Site 8": ("LOC-IDR-08", "Indore", "MP", "452015"),
}
STATUS = {
    "1100": "Created",
    "1500": "Scheduled",
    "3200": "Released",
    "3700": "Shipped",
    "3700.7777": "Delivered",
    "3900": "Return Received",
    "9000": "Cancelled",
}
ITEM_SPEC = {"motor": "Rated power", "pump": "Pressure", "drill": "Voltage", "control": "Family", "it": "Device"}
EX_NEED = {"RT-1048": date(2026, 10, 17)}  # the demo's fixed need-by dates
RETURN_REASONS = (  # (ReturnReason, text, customer intent)
    ("REPLACED", "Replaced at site by a new unit", "Credit against the replacement"),
    ("SURPLUS", "Surplus to site requirements", "Credit"),
    ("FAULT", "Reported fault; returned for assessment", "Repair or replace"),
    ("UPGRADE", "Upgraded; previous unit returned", "Credit"),
)
LEASE_RETURN = ("END_OF_LEASE", "Returned at the end of the lease", "Lease return, no credit")
EXIT_RETURN = ("END_OF_LIFE", "Retired by the customer", "Certified disposal")


def fnv(s: str) -> int:
    """The demo's hashId (FNV-1a, 32 bit) as a number."""
    h = 2166136261
    for ch in s:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def case_no(f: CaseFacts) -> int:
    return int(f.id.split("-")[1])


def order_no(f: CaseFacts) -> str:
    return "SO-48102" if f.id == "RT-1048" else f"SO-{48000 + (case_no(f) * 7) % 997}"


def line_no(f: CaseFacts) -> int:
    return 10 if f.id == "RT-1048" else 10 * (1 + fnv(f.id + "|ex|ln") % 4)


def need_by(f: CaseFacts, as_of: datetime) -> date:
    return EX_NEED.get(f.id) or (as_of + timedelta(days=12 + fnv(f.id + "|ex|nb") % 28)).date()


def node(location: str) -> str:
    return NODES.get(location) or "ST" + location.split()[-1].zfill(2)


def org_code(tenant: str) -> str:
    return tenant.upper().replace(" ", "_")  # Customer A -> CUSTOMER_A


def item_of(f: CaseFacts, seed: Seed) -> tuple[str, str]:
    """(ItemID, short description) of a unit with the case's spec: MTR-55KW, 'Industrial motor 55 kW'."""
    cls = seed.world.classes[f.cls]
    value = str(f.spec.get(ITEM_SPEC.get(f.cls, ""), "")) or "STD"
    return f"{cls.pre}-{re.sub('[^A-Z0-9]', '', value.upper())[:12]}", f"{cls.label} {value}"


def header_key(f: CaseFacts, doc: str) -> str:
    return f"20261007{case_no(f):06d}{doc[-2:]}"


def line_key(hkey: str, prime: int) -> str:
    return f"{hkey}{prime:04d}"


def ship_to(site_id: str, site_name: str, tenant: str) -> dict:
    loc, city, state, zip_code = SITE_LOCS[site_id]
    return {
        "PersonInfoKey": loc,
        "Company": tenant,
        "AddressLine1": site_name,
        "AddressLine2": site_id,
        "City": city,
        "State": state,
        "ZipCode": zip_code,
        "Country": "IN",
    }


def _status(code: str, at: datetime, qty: Decimal) -> dict:
    return {"Status": code, "StatusDescription": STATUS[code], "StatusDate": at, "StatusQty": str(qty)}


def _rma_numbers(seed: Seed) -> dict[str, str]:
    taken, out = set(), {}
    for cid in seed.cases:
        n = 55800 + fnv(cid + "rma") % 900
        while n in taken:
            n += 1
        taken.add(n)
        out[cid] = f"RMA-{n}"
    return out


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    w = seed.world
    as_of = w.as_of
    changed = as_of - timedelta(days=1)
    site_names = {s.id: s.name for s in w.sites}
    classes = list(w.classes)
    headers: list[dict] = []
    lines: list[dict] = []
    rmas = _rma_numbers(seed)

    for case in seed.cases.values():
        f = case.facts
        n = case_no(f)
        item_id, item_desc = item_of(f, seed)
        qty = Decimal(f.qty)

        # ---- the return authorisation that brought the unit back
        rkey = header_key(f, RETURN)
        received = f.received
        opened = received - timedelta(days=2 + fnv(f.id + "|oms|ra") % 6, hours=-5)
        reason = (
            EXIT_RETURN
            if f.kind == "exit"
            else LEASE_RETURN
            if f.demand.lease and fnv(f.id + "|oms|lr") % 3 == 0
            else RETURN_REASONS[fnv(f.id + "|oms|rr") % len(RETURN_REASONS)]
        )
        headers.append(
            {
                "order_header_key": rkey,
                "order_no": rmas[f.id],
                "enterprise_code": ENTERPRISE,
                "document_type": RETURN,
                "order_type": "CUSTOMER_RETURN",
                "buyer_organization_code": org_code(f.owner),
                "order_date": opened,
                "req_delivery_date": None,
                "ship_to_key": None,
                "ship_to": None,
                "receiving_node": node(f.location),
                "currency": "USD",
                "extn": {
                    "ExtnCustomerIntent": reason[2],
                    "ExtnReceiptNo": f"GR-{100000 + fnv(f.id + 'gr') % 900000}",
                    "ExtnLeaseNo": f.demand.lease or "",
                },
                "createts": opened,
                "modifyts": changed,
            }
        )
        lines.append(
            {
                "order_line_key": line_key(rkey, 1),
                "order_header_key": rkey,
                "prime_line_no": 1,
                "sub_line_no": 1,
                "line_type": "RETURN",
                "item_id": item_id,
                "item_desc": f"{item_desc} · {f.mfr}",
                "product_class": "RETURN",
                "uom": "EACH",
                "ordered_qty": qty,
                "unit_price": None,
                "ship_node": None,
                "ship_to_key": None,
                "req_delivery_date": None,
                "status": "3900",
                "accepts_refurbished": False,
                "serial_no": f.asset_id,
                "return_reason": reason[0],
                "allocated_serial": None,
                "reservation": None,
                "shipment": None,
                "pod": None,
                "idempotency_key": None,
                "history": [_status("1100", opened, qty), _status("3900", received, qty)],
                "extn": {"ExtnReturnReasonText": reason[1], "ExtnReceivedDate": received},
                "createts": opened,
                "modifyts": changed,
            }
        )

        # ---- the sales (contract replacement) order that the unit can fill
        if not f.demand.internal or not f.demand.site:
            continue
        skey = header_key(f, SALES)
        ordered = as_of - timedelta(days=20 + fnv(f.id + "|oms|od") % 60, hours=4)
        need = need_by(f, as_of)
        loc = SITE_LOCS[f.demand.site][0]
        purchase = max((term.amt for r in f.routes for term in r.terms if term.kind == "purchase"), default=0)
        price = Decimal(str(purchase / f.qty if purchase > 0 else w.classes[f.cls].pnew)).quantize(Decimal("0.01"))
        headers.append(
            {
                "order_header_key": skey,
                "order_no": order_no(f),
                "enterprise_code": ENTERPRISE,
                "document_type": SALES,
                "order_type": "CONTRACT_REPLACEMENT",
                "buyer_organization_code": org_code(f.owner),
                "order_date": ordered,
                "req_delivery_date": need,
                "ship_to_key": loc,
                "ship_to": ship_to(f.demand.site, site_names[f.demand.site], f.owner),
                "receiving_node": None,
                "currency": "USD",
                "extn": {"ExtnDemandStatus": "CONFIRMED" if f.demand.confirmed else "FORECAST"},
                "createts": ordered,
                "modifyts": changed,
            }
        )
        matched = line_no(f)
        for prime in range(10, matched + 1, 10):
            base = {
                "order_line_key": line_key(skey, prime),
                "order_header_key": skey,
                "prime_line_no": prime,
                "sub_line_no": 1,
                "uom": "EACH",
                "ship_to_key": loc,
                "serial_no": None,
                "return_reason": None,
                "allocated_serial": None,
                "reservation": None,
                "pod": None,
                "idempotency_key": None,
                "createts": ordered,
                "modifyts": changed,
            }
            if prime == matched:
                lines.append(
                    base
                    | {
                        "line_type": "REPLACEMENT",
                        "item_id": item_id,
                        "item_desc": item_desc,
                        "product_class": "NEW",
                        "ordered_qty": qty,
                        "unit_price": price,
                        "ship_node": None,
                        "req_delivery_date": need,
                        "status": "1100",
                        "accepts_refurbished": True,
                        "shipment": None,
                        "history": [_status("1100", ordered, qty)],
                        "extn": {
                            "ExtnAcceptsRefurbished": "Y",
                            "ExtnMinCertifiedMonths": "24",
                            "ExtnAvoidedPurchaseOrder": f"PO-{48000 + n}",
                        },
                    }
                )
                continue
            # an earlier contract line: new equipment, already delivered
            other = w.classes[
                classes[(classes.index(f.cls) + 1 + fnv(f"{f.id}|oms|l{prime}") % (len(classes) - 1)) % len(classes)]
            ]
            shipped = ordered + timedelta(days=3 + prime // 10)
            delivered = shipped + timedelta(days=2)
            src = ("WH01", "WH02")[fnv(f"{f.id}|oms|n{prime}") % 2]
            lines.append(
                base
                | {
                    "line_type": "NEW_EQUIPMENT",
                    "item_id": f"{other.pre}-STD",
                    "item_desc": f"{other.label}, standard",
                    "product_class": "NEW",
                    "ordered_qty": Decimal(1),
                    "unit_price": Decimal(str(other.pnew)).quantize(Decimal("0.01")),
                    "ship_node": src,
                    "req_delivery_date": delivered.date(),
                    "status": "3700.7777",
                    "accepts_refurbished": False,
                    "shipment": {"ShipmentNo": f"SHP-{skey[-8:]}{prime:02d}", "SCAC": "NLTL", "ShipDate": shipped},
                    "pod": {"ReceivedBy": f"{f.owner} stores", "DeliveryDate": delivered},
                    "history": [
                        _status("1100", ordered, Decimal(1)),
                        _status("1500", ordered + timedelta(hours=2), Decimal(1)),
                        _status("3200", shipped - timedelta(hours=6), Decimal(1)),
                        _status("3700", shipped, Decimal(1)),
                        _status("3700.7777", delivered, Decimal(1)),
                    ],
                    "extn": {"ExtnAcceptsRefurbished": "N"},
                }
            )

    for row in headers + lines:  # JSON columns hold ISO strings
        for col in ("extn", "pod", "shipment"):
            if row.get(col):
                row[col] = {k: _iso(v) for k, v in row[col].items()}
        if row.get("history"):
            row["history"] = [{k: _iso(v) for k, v in h.items()} for h in row["history"]]
    conn.execute(insert(t.ORDER_HEADER), headers)
    conn.execute(insert(t.ORDER_LINE), lines)
    sales = sum(1 for h in headers if h["document_type"] == SALES)
    return {"sales_orders": sales, "return_orders": len(headers) - sales, "order_lines": len(lines)}


def _iso(v):
    return v.astimezone(UTC).isoformat() if isinstance(v, datetime) else v


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS sterling"))
    t.metadata.create_all(conn)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    t.metadata.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM sterling.yfs_order_header")).scalar_one() == 0:
        load(conn, seed)
