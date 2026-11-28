"""Plan 9, P9-6.3: the device market adapter (`dvmkt`) and the market reads (repositories/device_market.py), against
source-sim's synthetic market mock (P9-6.1). Story ids: DV-06 ... DV-09, DV-12, DV-13 (prices, listings, bids, sales and
replacement demand the device flow reads).

`dvmkt` is not a demo source: it starts unregistered. It lands six tables from its reader, in the sync's own session, so a
dry or sample run (rolled back) writes no `device_*` row; `map` makes no fact. Landing and read tests run on literal
pages through a stub client; the sync test needs source-sim running with the mock and is skipped, with the reason, when it
lacks it (restart it, R14). Nothing here posts to the shared source-sim.
"""

from datetime import date
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.connectors.sync import run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.repositories import device_market
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
API = SIM + "/device-market/v1"
TABLES = ("device_price_point", "device_launch", "device_listing", "device_bid", "device_sale", "device_replacement_demand")
KEY = "iPhone 14|128"
IMEI = "359990000000428"


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()
    _empty()


def _empty() -> None:
    with engine.begin() as conn:
        for t in (*TABLES, "device_tradein"):
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names


@pytest.fixture(autouse=True)
def _empty_tables():
    _empty()


def served() -> bool:
    try:
        return (
            httpx.get(API + "/prices", headers={"X-Api-Key": "dvmkt-demo-key"}, params={"limit": 1}, timeout=10).status_code
            == 200
        )
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the device market mock: restart it (R14)")


def count(table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608 - fixed names


class Stub:
    """A client over literal list pages: {path: [rows]}. Same calls as the generic paging makes."""

    source_id = "dvmkt"

    def __init__(self, session, data: dict[str, list[dict]]):
        self.session, self.data, self.noted = session, data, 0

    def get_json(self, path: str, params: dict | None = None) -> dict[str, Any]:
        return {"items": self.data.get(path, []), "next": None, "total": len(self.data.get(path, []))}

    def url(self, path: str) -> str:
        return "http://stub" + path

    def note_records(self, n: int) -> None:
        self.noted += n

    @property
    def http(self):
        raise httpx.ConnectError("no clock")


def read(session, name: str, rows: list[dict]) -> list[Record]:
    path = {
        "prices": "/prices", "launches": "/launches", "listings": "/listings", "bids": "/bids", "sales": "/sales",
        "replacementDemand": "/replacement-demand",
    }[name]  # fmt: skip
    res = {r.name: r for r in ADAPTERS["dvmkt"].resources()}[name]
    return list(res.read(Stub(session, {path: rows}), None))  # type: ignore[arg-type]


def price(week: str, p: float, key: str = KEY, grade: str = "B") -> dict:
    return {"priceId": f"{key}|{grade}|{week}", "skuKey": key, "grade": grade, "week": week, "price": p, "currency": "USD"}


def listing(n: int = 1, imei: str = IMEI, **kw) -> dict:
    return {
        "listingId": f"LST-{n:04d}", "imei": imei, "skuKey": KEY, "grade": "B", "channel": "Offers", "price": 300.0,
        "listedAt": "2026-08-20T10:00:00+00:00", "offers": 0, "status": "live",
    } | kw  # fmt: skip


def land(name: str, rows: list[dict]) -> None:
    with SessionLocal() as s:
        read(s, name, rows)
        s.commit()


# ------------------------------------------------------------------ registration and mapping
def test_dvmkt_starts_unregistered_and_makes_no_facts():
    a = ADAPTERS["dvmkt"]
    assert a.extra and a.source_type == "dvmkt" and a.provisioned is False and a.auth_kind == "api_key"
    with engine.connect() as conn:
        assert not conn.execute(text("SELECT 1 FROM source_system WHERE id = 'dvmkt'")).first()
    assert run_sync("dvmkt", "manual")["status"] == "skipped"
    assert a.map(Record("prices", "x", price("2026-08-24", 400.0))) == []
    assert {r.name for r in a.resources()} == {"prices", "launches", "listings", "bids", "sales", "replacementDemand"}


# ------------------------------------------------------------------ the sync against the mock
@needs_mock
def test_dvmkt_sync_lands_market_tables():
    r = call("source.reconnect", {"source_id": "dvmkt"}, "developer")
    assert r["ok"], r
    out = run_sync("dvmkt", "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    with engine.connect() as conn:
        weeks = conn.execute(
            text("SELECT count(*) FROM (SELECT sku_key, grade FROM device_price_point GROUP BY 1, 2 HAVING count(*) = 52) x")
        ).scalar_one()
        series = conn.execute(text("SELECT count(DISTINCT (sku_key, grade)) FROM device_price_point")).scalar_one()
    assert series > 0 and weeks == series  # 52 weeks for every SKU and grade
    assert count("device_listing") == 60 and count("device_sale") == 400 and count("device_launch") >= 1
    assert count("device_replacement_demand") == 3
    with SessionLocal() as s:
        assert len(device_market.open_bids(s, "LOT-W-0001", date(2026, 12, 31))) == 6
        assert len(device_market.live_listings(s, date(2026, 12, 31))) == 60
    n = {t: count(t) for t in TABLES}
    assert run_sync("dvmkt", "manual", full=True)["status"] == "ok"
    assert {t: count(t) for t in TABLES} == n  # idempotent


# ------------------------------------------------------------------ DV-12: prices as of a date
def test_feed_price_is_as_of():
    land(
        "prices", [price("2026-07-13", 300.0), price("2026-08-10", 310.0), price("2026-08-24", 320.0), price("2026-09-07", 999.0)]
    )
    land("prices", [price("2026-08-03", 50.0, "Pixel 8|256")])  # last priced 29 days before: stale
    with SessionLocal() as s:
        p = device_market.feed_price(s, KEY, "B", date(2026, 9, 1))
        assert p == device_market.PricePoint(320.0, date(2026, 8, 24), False)  # never the 2026-09-07 week
        assert device_market.feed_price(s, KEY, "B", date(2026, 8, 24)).week == date(2026, 8, 24)  # the as-of day itself counts
        assert device_market.feed_price(s, KEY, "B", date(2026, 7, 1)) is None
        assert device_market.feed_price(s, KEY, "A", date(2026, 9, 1)) is None
        late = device_market.feed_price(s, KEY, "B", date(2026, 9, 13))  # 2026-09-07 is 6 days back, fresh
        assert late is not None and late.price == 999.0 and late.stale is False
        old = device_market.feed_price(s, "Pixel 8|256", "B", date(2026, 9, 1))
        assert old is not None and old.stale is True and old.week == date(2026, 8, 3)
        edge = device_market.feed_price(s, KEY, "B", date(2026, 9, 7))  # the week itself, 0 days back
        assert edge is not None and edge.week == date(2026, 9, 7) and edge.stale is False
        fourteen = device_market.feed_price(s, KEY, "B", date(2026, 9, 6))  # 2026-08-24 is 13 days back: not stale
        assert fourteen is not None and fourteen.week == date(2026, 8, 24) and fourteen.stale is False
    land("prices", [price("2026-08-12", 70.0, "Galaxy S23|128")])
    with SessionLocal() as s:
        st = device_market.feed_price(s, "Galaxy S23|128", "B", date(2026, 9, 1))  # exactly 20 days
        assert st is not None and st.stale is True


def test_price_history_is_a_window():
    land("prices", [price("2026-08-10", 310.0), price("2026-08-17", 315.0), price("2026-08-24", 320.0)])
    land("prices", [price("2026-08-17", 60.0, "Pixel 8|256")])
    with SessionLocal() as s:
        both = device_market.price_history(s, None, date(2026, 8, 11), date(2026, 8, 24))
        assert [(r.sku_key, r.week) for r in both] == [
            ("Pixel 8|256", date(2026, 8, 17)),
            (KEY, date(2026, 8, 17)),
            (KEY, date(2026, 8, 24)),
        ]
        one = device_market.price_history(s, KEY, date(2026, 8, 1), date(2026, 8, 17))
        assert [r.price for r in one] == [310.0, 315.0]


# ------------------------------------------------------------------ DV-06: listings, case link by IMEI
def test_listing_links_case_by_imei():
    land("listings", [listing(1), listing(2, imei="359990000000001")])
    with SessionLocal() as s:
        assert device_market.listing_of(s, IMEI).case_id is None
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO device_tradein (trade_in_id, imei, sku, quote, partner, bulk, received_at, case_id, source) "
                "VALUES ('TI-1', :i, '{}', '{}', 'P01', false, now(), 'RT-9001', 'dvlab')"
            ),
            {"i": IMEI},
        )
    land("listings", [listing(1), listing(2, imei="359990000000001")])  # the next sync
    with SessionLocal() as s:
        mine = device_market.listing_of(s, IMEI)
        assert mine is not None and mine.listing_id == "LST-0001" and mine.case_id == "RT-9001"
        assert device_market.listing_of(s, "359990000000001").case_id is None  # no case, none linked
        assert device_market.listing_of(s, "000") is None
    land("listings", [listing(1, price=280.0)])  # a changed price keeps the link
    with SessionLocal() as s:
        row = device_market.listing_of(s, IMEI)
        assert row is not None and row.case_id == "RT-9001" and row.price == 280.0
    assert count("device_listing") == 2


def test_a_listing_without_listed_at_is_held_and_the_others_land():
    """A listing the market serves without `listedAt` (one the app posted before the mock stamped it) is held in
    `failed_record` with its payload; it does not fail the read, and the other listings land (P9-13.11)."""
    bare = {k: v for k, v in listing(2, imei="359990000000001").items() if k != "listedAt"}
    with SessionLocal() as s:
        got = read(s, "listings", [listing(1), bare])
        s.commit()
    assert [r.ext_id for r in got] == ["LST-0001"] and count("device_listing") == 1
    with engine.begin() as conn:
        held = conn.execute(
            text("SELECT field, rule, step, payload FROM failed_record WHERE source_id = 'dvmkt' AND ext_id = 'LST-0002'")
        ).all()
        conn.execute(text("DELETE FROM failed_record WHERE source_id = 'dvmkt' AND ext_id = 'LST-0002'"))
    got_held = [(h.field, h.rule, h.step, h.payload["imei"]) for h in held]
    assert got_held == [("listedAt", "required", "connector", "359990000000001")]


def test_live_listings_are_as_of_and_by_channel():
    land("listings", [listing(1), listing(2, channel="Buy Now", listedAt="2026-09-10T10:00:00+00:00"), listing(3, status="sold")])
    with SessionLocal() as s:
        assert [x.listing_id for x in device_market.live_listings(s, date(2026, 9, 1))] == ["LST-0001"]
        assert [x.listing_id for x in device_market.live_listings(s, date(2026, 9, 30))] == ["LST-0001", "LST-0002"]
        assert [x.listing_id for x in device_market.live_listings(s, date(2026, 9, 30), "Buy Now")] == ["LST-0002"]
        assert device_market.live_listings(s, date(2026, 8, 1)) == []


# ------------------------------------------------------------------ DV-08, DV-09, DV-13: bids, sales, launches, demand
def test_open_bids_are_as_of():
    bid = {"lotRef": "LOT-W-0001", "buyerCode": "B01", "units": 100, "amount": 316, "fees": 6, "logistics": 4, "currency": "USD"}
    land(
        "bids",
        [
            bid | {"bidId": "BID-0001", "receivedAt": "2026-10-06T10:00:00+00:00"},
            bid | {"bidId": "BID-0002", "buyerCode": "B02", "receivedAt": "2026-10-08T10:00:00+00:00"},
            bid | {"bidId": "BID-0003", "lotRef": "LOT-W-0002", "receivedAt": "2026-10-06T10:00:00+00:00"},
        ],
    )
    with SessionLocal() as s:
        assert [b.bid_id for b in device_market.open_bids(s, "LOT-W-0001", date(2026, 10, 7))] == ["BID-0001"]
        both = device_market.open_bids(s, "LOT-W-0001", date(2026, 10, 8))
        assert [b.bid_id for b in both] == ["BID-0001", "BID-0002"] and both[0].amount == 316.0 and both[0].buyer_code == "B01"


def test_sales_launches_and_demand():
    sale = {
        "imeis": [IMEI], "model": "iPhone 14", "skuKey": KEY, "grade": "B", "week": "2026-08-24", "price": 300.0, "fees": 36.0,
        "buyerReturns": 0,
    }  # fmt: skip
    land(
        "sales",
        [
            sale | {"saleId": "SALE-1", "listingId": "LST-1", "settledAt": "2026-08-26T12:00:00+00:00"},
            sale | {"saleId": "SALE-2", "lotRef": "LOT-W-S001", "settledAt": "2026-09-02T12:00:00+00:00"},
        ],
    )
    land(
        "launches",
        [
            {
                "launchId": "L1",
                "brand": "Samsung",
                "name": "Galaxy S24 successor",
                "replaces": "Galaxy S24",
                "launchDate": "2026-08-01",
            },
            {"launchId": "L2", "brand": "Apple", "name": "iPhone 16", "replaces": "iPhone 15", "launchDate": "2026-09-20"},
        ],
    )
    land(
        "replacementDemand",
        [
            {"demandId": "RD-1", "skuKey": KEY, "minGrade": "B", "units": 5, "price": 340, "currency": "USD"},
            {"demandId": "RD-2", "skuKey": KEY, "minGrade": "C", "units": 4, "price": 200, "currency": "USD"},
        ],
    )  # fmt: skip
    with engine.begin() as conn:
        conn.execute(text("UPDATE device_replacement_demand SET reserved = '[\"RT-1\", \"RT-2\"]' WHERE id = 'RD-1'"))
    land(
        "replacementDemand",
        [
            {
                "demandId": "RD-1",
                "skuKey": KEY,
                "minGrade": "B",
                "units": 5,
                "price": 340,
                "currency": "USD",
                "raisedAt": "2026-09-01T00:00:00+00:00",
            }
        ],
    )  # a sync keeps the reservations
    with SessionLocal() as s:
        got = device_market.sales(s, date(2026, 8, 25), date(2026, 9, 2))
        assert [x.sale_id for x in got] == ["SALE-1", "SALE-2"] and got[1].lot_ref == "LOT-W-S001" and got[0].imeis == [IMEI]
        assert [x.sale_id for x in device_market.sales(s, date(2026, 8, 27), date(2026, 9, 1))] == []
        assert [x.model for x in device_market.launches(s, date(2026, 9, 1))] == ["Galaxy S24"]
        assert [x.model for x in device_market.launches(s, date(2026, 9, 30))] == ["Galaxy S24", "iPhone 15"]
        assert device_market.replacement_demand(s, KEY, "B", date(2026, 9, 1)) == 3 + 4  # RD-1 has 2 reserved, RD-2 takes a B too
        assert device_market.replacement_demand(s, KEY, "C", date(2026, 9, 1)) == 4  # a C does not meet a minimum of B
        assert device_market.replacement_demand(s, KEY, "D", date(2026, 9, 1)) == 0
        assert device_market.replacement_demand(s, "Pixel 8|256", "A", date(2026, 9, 1)) == 0
    land("sales", [sale | {"saleId": "SALE-1", "listingId": "LST-1", "settledAt": "2026-08-26T12:00:00+00:00"}])
    assert count("device_sale") == 2  # idempotent


def test_sale_links_cases_by_imei():
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO device_tradein (trade_in_id, imei, sku, quote, partner, bulk, received_at, case_id, source) "
                "VALUES ('TI-1', :i, '{}', '{}', 'P01', false, now(), 'RT-9001', 'dvlab')"
            ),
            {"i": IMEI},
        )
    sale = {"saleId": "SALE-1", "imeis": [IMEI, "359990000000001"], "price": 300.0, "fees": 36.0, "buyerReturns": 0,
            "settledAt": "2026-08-26T12:00:00+00:00"}  # fmt: skip
    land("sales", [sale])
    with SessionLocal() as s:
        assert device_market.sales(s, date(2026, 8, 1), date(2026, 9, 1))[0].case_ids == ["RT-9001"]


# ------------------------------------------------------------------ a dry run changes nothing
def test_a_dry_or_sample_run_writes_no_device_row():
    rows = {
        "prices": [price("2026-08-24", 320.0)], "listings": [listing(1)],
        "bids": [{"bidId": "BID-1", "lotRef": "LOT-W-0001", "buyerCode": "B01", "amount": 1, "fees": 1, "logistics": 1,
                  "receivedAt": "2026-10-06T10:00:00+00:00"}],
        "sales": [
            {"saleId": "S-1", "imeis": [], "price": 1.0, "fees": 0.1, "buyerReturns": 0, "settledAt": "2026-08-26T12:00:00Z"}
        ],
        "launches": [{"launchId": "L1", "name": "X", "replaces": "Y", "launchDate": "2026-08-01"}],
        "replacementDemand": [{"demandId": "RD-1", "skuKey": KEY, "minGrade": "B", "units": 1, "price": 1}],
    }  # fmt: skip
    for name, data in rows.items():
        with SessionLocal() as s:  # the engine's dry run reads inside a transaction it rolls back
            recs = read(s, name, data)
            assert len(recs) == 1
            assert ADAPTERS["dvmkt"].map(recs[0]) == []  # map writes nothing either
            s.rollback()
    assert [count(t) for t in TABLES] == [0] * 6
    for name, data in rows.items():
        land(name, data)  # the same read, committed: the rows are there
    assert [count(t) for t in TABLES] == [1] * 6
