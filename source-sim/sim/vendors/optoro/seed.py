"""Optoro data in Postgres schema `optoro` and the seed (see the package docstring).

One table of documents per resource (the resource exactly as the API returns it), keyed by its identifier, with its
change time. One RMA, one inbound ASN and one inventory receipt per case; one disposition update per graded case.
Values are the ones the generic mock held (RMA, receipt scan time, carrier, load, freight)."""

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, delete, insert, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.seed.model import CaseFacts
from sim.vendors.optoro.demo import (
    FAC_LOC,
    LOCS,
    SCAC,
    as_hex,
    case_no,
    demand_order,
    facility_id,
    load_id,
    return_logistics,
)

SCHEMA = "optoro"
PROGRAM = "lease_returns"
CONCEPT = "Northfield Lease Returns"
EDT = timezone(timedelta(hours=-4))  # the returns centre's local time, as receipts report it
WAREHOUSE_NO = {"WH01": 101, "WH02": 102, "RC01": 201}  # Optoro's numeric warehouse ids (to.identifier)

# grade -> (Optoro condition code, disposition channel). Ungraded units wait in needs_testing.
GRADE = {"A": ("A", "rts"), "B": ("B", "rts"), "C": ("C", "refurbish"), "D": ("X", "recycle"), None: ("TT", "needs_testing")}

metadata = MetaData(schema=SCHEMA)


def _doc_table(name: str) -> Table:
    return Table(
        name,
        metadata,
        Column("id", String(60), primary_key=True),
        Column("doc", JSONB, nullable=False),
        Column("updated", DateTime(timezone=True), nullable=False, index=True),
        Column("seq", Integer, nullable=False),
    )


RESOURCES = ("rma", "asn", "receipt", "disposition", "final_disposition")
TABLES = {r: _doc_table(r) for r in RESOURCES}
COUNTERS = Table("counters", metadata, Column("name", String(40), primary_key=True), Column("value", Integer))


def z(d: datetime) -> str:
    """Optoro timestamps: ISO 8601 UTC with milliseconds and Z."""
    d = d.astimezone(UTC)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


def plain(d: datetime) -> str:
    """The webhook payload format "2018-03-20T00:00:00" (UTC, no zone)."""
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def local(d: datetime) -> str:
    return d.astimezone(EDT).isoformat(timespec="seconds")


def lp(case_id: str) -> str:
    """The OptiTurn license plate of a returned unit."""
    return f"LPNF{case_no(case_id):07d}"


def upc(f: CaseFacts) -> str:
    return f"{as_hex(f.id, '|rl|upc') % 10**12:012d}"


def tracking(f: CaseFacts, carrier: str) -> str:
    return f"{SCAC[carrier]}{as_hex(f.id, '|rl|trk') % 10**10:010d}"


def received_at(f: CaseFacts) -> datetime:
    """The receipt scan: the received date, 12:00-19:59 UTC."""
    return f.received + timedelta(minutes=720 + as_hex(f.id, "|rl|rcv") % 480)


def rma_numbers(s: Seed) -> dict[str, str]:
    """The demo's asRMA(); on a hash collision the later case takes the next free number (as the Sterling mock does)."""
    taken, out = set(), {}
    for cid in s.cases:
        n = 55800 + as_hex(cid, "rma") % 900
        while n in taken:
            n += 1
        taken.add(n)
        out[cid] = f"RMA-{n}"
    return out


def build(s: Seed) -> dict[str, list[tuple[str, dict, datetime]]]:
    out: dict[str, list] = {r: [] for r in RESOURCES}
    numbers = rma_numbers(s)
    for case in s.cases.values():
        f = case.facts
        L = return_logistics(f) | {"rma": numbers[f.id]}
        lane = L["lane"]
        fid = facility_id(f.location)
        rcv = received_at(f)
        n = case_no(f.id)
        cond, channel = GRADE[f.grade]
        order = demand_order(f)
        trk = tracking(f, L["carrier"])
        authorized = L["auth"] + timedelta(hours=14)
        item = {
            "order_line_item_identifier": "1",
            "order_identifier": L["lease"],
            "secondary_identifier": f.id,
            "return_reason": L["intent"],
            "is_exchange": order is not None,
            "sku": f.asset_id,
            "upc": upc(f),
            "quantity": f.qty,
            "tracking_number": trk,
            "package_tracking_status": "DELIVERED",
            "receiving_status": "RECEIVED",
            "refund_financials": {
                "estimated_refund_amount_cents": 0,
                "optoro_refund_amount_cents": 0,
                "shopper_refund_amount_cents": 0,
            },
            "refund_type": "STANDARD_EXCHANGE" if order else "REFUND",
            "warehouse_receipt_condition": cond,
        }
        if order:
            item["exchange_order_identifier"] = order
        rma = {
            "rma_identifier": L["rma"],
            "status": "CREATED",
            "created_at": z(authorized),
            "updated_at": z(rcv),
            "items": [item],
            "return_method": "home-pickup",
            "return_shipping_cost_cents": int(L["fee"] * 100),
            "bonus_credit_amount_cents": 0,
            "gift_refund_only": False,
            "warehouse_id": fid,
            "receiving_complete": True,
            "concept": CONCEPT,
            "customer": {"tags": [f.owner]},
        }
        out["rma"].append((L["rma"], rma, rcv))
        asn_no = f"SHP-{n}"
        origin = {"identifier": lane["from"], "type": "CustomerSite", "name": LOCS[lane["from"]]["site"]}
        asn = {
            "program_identifier": PROGRAM,
            "from": origin,
            "to": {"identifier": fid, "type": "Warehouse"},
            "asn_number": asn_no,
            "shipment_identifier": load_id(f),
            "tracking_number": trk,
            "carrier": L["carrier"],
            "carrier_scac": SCAC[L["carrier"]],
            "ship_date": f"{L['pickup'].date().isoformat()}T00:00:00Z",
            "estimated_arrival_date": L["eta"].date().isoformat(),
            "status": "delivered",
            "details_type": "unit",
            "cartons": [
                {
                    "identifier": f"CT{n:08d}",
                    "reference": {"type": "RMA", "identifier": L["rma"], "alternate_identifier": f.id},
                    "details": [
                        {
                            "line_identifier": "1",
                            "unit_identifier": lp(f.id),
                            "reference_line_identifier": "1",
                            "sku": f.asset_id,
                            "upc": upc(f),
                            "serial_number": f.asset_id,
                            "quantity": f.qty,
                            "return_reason": L["intent"],
                            "return_date": rcv.date().isoformat(),
                        }
                    ],
                }
            ],
            "messagetimestamp": plain(L["pickup"]),
            "delivered_at": local(rcv),
            "freight": {
                "amount_cents": int(L["freight_usd"] * 100),
                "currency": "USD",
                "local_amount_cents": int(lane["inr"] * 100),
                "local_currency": "INR",
            },
            "receptions": 1,
            "created_at": z(authorized),
            "updated_at": z(rcv),
        }
        out["asn"].append((asn_no, asn, rcv))
        receipt = {
            "program_identifier": PROGRAM,
            "asn_number": asn_no,
            "shipment_identifier": load_id(f),
            "from": origin,
            "to": {"identifier": WAREHOUSE_NO[fid], "type": "Warehouse", "original_identifier": fid},
            "carton_identifier": f"CT{n:08d}",
            "reference": {"type": "RMA", "identifier": L["rma"], "alternate_identifier": f.id},
            "line_identifier": "1",
            "unit_identifier": lp(f.id),
            "reference_line_identifier": "1",
            "sku": f.asset_id,
            "upc": upc(f),
            "serial_number": f.asset_id,
            "quantity": f.qty,
            "initial_condition": "TT",
            "initial_channel": "needs_testing",
            "return_reason": L["intent"],
            "ot_user_login": f"receiving.{fid.lower()}@northfield",
            "merchant": f.mfr,
            "concept": CONCEPT,
            "tracking_number": trk,
            "location_identifier": FAC_LOC[f.location],
            "client_unit_identifier": f.asset_id,
            "received_at": local(rcv),
            "created_at": z(rcv),
            "updated_at": z(rcv),
        }
        out["receipt"].append((lp(f.id), receipt, rcv))
        if f.grade:
            decided = rcv + timedelta(hours=2)
            out["disposition"].append(
                (
                    f"DSP-{n}",
                    {
                        "id": f"DSP-{n}",
                        "from_disposition": "needs_testing",
                        "to_disposition": channel,
                        "timestamp": plain(decided),
                        "location_identifier": FAC_LOC[f.location],
                        "warehouse_identifier": fid,
                        "optiturn_lp": lp(f.id),
                        "program_identifier": PROGRAM,
                        "upc": upc(f),
                        "from_condition": "TT",
                        "to_condition": cond,
                        "from_sku": f.asset_id,
                        "to_sku": f.asset_id,
                        "reference_unit_identifier": f.id,
                        "user_login": "rules_engine",
                        "updated_at": z(decided),
                    },
                    decided,
                )
            )
    return out


def create(conn: Connection) -> None:
    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    metadata.create_all(conn)


def load(conn: Connection, s: Seed) -> dict[str, int]:
    counts = {}
    for name, rows in build(s).items():
        if rows:
            conn.execute(
                insert(TABLES[name]), [{"id": i, "doc": d, "updated": at, "seq": k} for k, (i, d, at) in enumerate(rows, 1)]
            )
        counts[name] = len(rows)
    conn.execute(insert(COUNTERS), [{"name": n, "value": 0} for n in ("rma", "disposition", "final_disposition", "seq")])
    conn.execute(update(COUNTERS).where(COUNTERS.c.name == "seq").values(value=1000))
    return counts


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text(f"SELECT count(*) FROM {SCHEMA}.rma")).scalar_one() == 0:  # noqa: S608 - SCHEMA is a module constant
        load(conn, s)


# ------------------------------------------------------------------ storage helpers used by routes.py
def next_no(conn: Connection, name: str) -> int:
    v = conn.execute(select(COUNTERS.c.value).where(COUNTERS.c.name == name).with_for_update()).scalar_one() + 1
    conn.execute(update(COUNTERS).where(COUNTERS.c.name == name).values(value=v))
    return v


def rows(conn: Connection, name: str):
    t = TABLES[name]
    return conn.execute(select(t).order_by(t.c.seq, t.c.id)).all()


def get(conn: Connection, name: str, id_: str, lock: bool = False) -> dict | None:
    t = TABLES[name]
    q = select(t.c.doc).where(t.c.id == id_)
    if lock:
        q = q.with_for_update()
    r = conn.execute(q).first()
    return r.doc if r else None


def put(conn: Connection, name: str, id_: str, doc: dict, at: datetime) -> dict:
    t = TABLES[name]
    at = at.replace(microsecond=at.microsecond // 1000 * 1000)  # the API's precision (updated_at has milliseconds)
    seq = next_no(conn, "seq")
    conn.execute(delete(t).where(t.c.id == id_))
    conn.execute(insert(t).values(id=id_, doc=doc, updated=at, seq=seq))
    return doc
