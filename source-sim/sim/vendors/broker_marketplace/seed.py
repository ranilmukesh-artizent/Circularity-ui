"""The broker marketplace mock's seed: bids and cleared sales for three models, synthetic and fixed (no randomness)."""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.broker_marketplace.models import BID, CLEARED, metadata


def _bid(bid_id: str, model: str, qty: int, price: int, country: str, screening: str, ref: str | None) -> dict:
    return {
        "bidId": bid_id, "model": model, "qty": qty, "unitPrice": price, "buyerCountry": country,
        "domestic": country == "US", "endUserScreening": {"result": screening, "ref": ref},
    }  # fmt: skip


def bids() -> list[dict]:
    return [
        _bid("BID-4410-A", "RRU-4410", 25, 3400, "US", "clear", "EUS-0101"),
        _bid("BID-4410-B", "RRU-4410", 60, 3250, "US", "clear", "EUS-0102"),
        _bid("BID-4410-OS", "RRU-4410", 100, 3300, "VN", "refer", "EUS-0103"),
        _bid("BID-2200-A", "BBU-2200", 80, 1450, "US", "clear", "EUS-0104"),
        _bid("BID-2200-B", "BBU-2200", 40, 1300, "US", "clear", "EUS-0105"),
        _bid("BID-7700-OS", "RAD-7700", 40, 1900, "AE", "none", None),
    ]


def _sale(sale_id: str, model: str, qty: int, price: int, sold_at: str) -> dict:
    return {"saleId": sale_id, "model": model, "qty": qty, "unitPrice": price, "soldAt": sold_at}


def cleared() -> list[dict]:
    return [
        _sale("CL-4410-1", "RRU-4410", 30, 3350, "2026-09-20"),
        _sale("CL-4410-2", "RRU-4410", 45, 3280, "2026-08-28"),
        _sale("CL-2200-1", "BBU-2200", 60, 1420, "2026-09-15"),
        _sale("CL-2200-2", "BBU-2200", 50, 1390, "2026-08-20"),
        _sale("CL-7700-1", "RAD-7700", 20, 1850, "2026-09-02"),
    ]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    conn.execute(insert(BID), [{"bid_id": d["bidId"], "model": d["model"], "doc": d} for d in bids()])
    conn.execute(insert(CLEARED), [{"sale_id": d["saleId"], "model": d["model"], "doc": d} for d in cleared()])
    return {"bid": len(bids()), "cleared": len(cleared())}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS broker_marketplace"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM broker_marketplace.bid")).scalar_one() == 0:
        load(conn, s)
