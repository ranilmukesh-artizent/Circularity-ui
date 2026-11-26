"""Reads of the device market the market adapter landed (plan 9 P9-6.3; tables device_price_point, device_launch,
device_listing, device_bid, device_sale and device_replacement_demand, migration 0047).

Owns: the row types and the as-of reads of the weekly price feed, launches, live listings, open bids, settled sales and
replacement demand. Every read takes the date it asks as of and never returns a row dated after it (listed, received,
settled or launched later): Phase 7's leakage test relies on this. Never writes: `di.connectors.adapters.device_market`
lands the rows. Synthetic data: an IMEI identifies a device, no person is stored.

Replacement demand has no raising date in its table, so `replacement_demand` takes `as_of` for symmetry and cannot filter
by it.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

STALE_DAYS = 14  # a feed price whose week is more than this many days before `as_of` is stale


@dataclass(frozen=True)
class PricePoint:
    price: float
    week: date
    stale: bool


@dataclass(frozen=True)
class PriceRow:
    sku_key: str
    grade: str
    week: date
    price: float
    currency: str


@dataclass(frozen=True)
class LaunchRow:
    model: str  # the model the launch replaces
    successor: str
    launched_on: date


@dataclass(frozen=True)
class ListingRow:
    listing_id: str
    org_unit_id: str | None
    imei: str
    case_id: str | None
    channel: str
    price: float
    listed_at: datetime
    offers: int
    status: str
    updated_at: datetime


@dataclass(frozen=True)
class BidRow:
    bid_id: str
    lot_ref: str
    buyer_code: str
    amount: float
    fees: float
    logistics: float
    received_at: datetime


@dataclass(frozen=True)
class SaleRow:
    sale_id: str
    listing_id: str | None
    lot_ref: str | None
    imeis: list[str]
    price: float
    fees: float
    buyer_returns: float
    settled_at: datetime
    case_ids: list[str]


_LISTING = "listing_id, org_unit_id, imei, case_id, channel, price, listed_at, offers, status, updated_at"
_SALE = "sale_id, listing_id, lot_ref, imeis, price, fees, buyer_returns, settled_at, case_ids"


def _f(v: Any) -> float:
    return float(v)


def feed_price(s: Session, sku_key: str, grade: str, as_of: date) -> PricePoint | None:
    """The latest weekly price of a SKU and grade on or before `as_of`; `stale` when its week is more than 14 days back."""
    r = s.execute(
        text(
            "SELECT price, week FROM device_price_point WHERE sku_key = :k AND grade = :g AND week <= :d "
            "ORDER BY week DESC LIMIT 1"
        ),
        {"k": sku_key, "g": grade, "d": as_of},
    ).first()
    if r is None:
        return None
    return PricePoint(_f(r[0]), r[1], (as_of - r[1]).days > STALE_DAYS)


def price_history(s: Session, sku_key: str | None, since: date, until: date) -> list[PriceRow]:
    """The weekly prices with `since <= week <= until`, of one SKU or (None) of all, by SKU, grade and week."""
    rows = s.execute(
        text(
            "SELECT sku_key, grade, week, price, currency FROM device_price_point "
            "WHERE week BETWEEN :a AND :b AND (CAST(:k AS text) IS NULL OR sku_key = :k) ORDER BY sku_key, grade, week"
        ),
        {"k": sku_key, "a": since, "b": until},
    )
    return [PriceRow(r[0], r[1], r[2], _f(r[3]), r[4]) for r in rows]


def sales(s: Session, since: date, until: date) -> list[SaleRow]:
    """The sales settled from the start of `since` to the end of `until`, oldest first."""
    rows = s.execute(
        text(
            f"SELECT {_SALE} FROM device_sale "  # noqa: S608 - fixed column list
            "WHERE settled_at >= CAST(:a AS date) AND settled_at < CAST(:b AS date) + 1 ORDER BY settled_at, sale_id"
        ),
        {"a": since, "b": until},
    )
    return [SaleRow(r[0], r[1], r[2], r[3], _f(r[4]), _f(r[5]), _f(r[6]), r[7], r[8]) for r in rows]


def sales_by_id(s: Session, ids: list[str]) -> list[SaleRow]:
    """The sales with these ids, oldest first (P9-6.12: the sales a sync just landed)."""
    rows = s.execute(
        text(f"SELECT {_SALE} FROM device_sale WHERE sale_id = ANY(:ids) ORDER BY settled_at, sale_id"),  # noqa: S608 - fixed column list
        {"ids": ids},
    )
    return [SaleRow(r[0], r[1], r[2], r[3], _f(r[4]), _f(r[5]), _f(r[6]), r[7], r[8]) for r in rows]


def launches(s: Session, as_of: date) -> list[LaunchRow]:
    """The launches on or before `as_of`, oldest first."""
    rows = s.execute(
        text("SELECT model, successor, launched_on FROM device_launch WHERE launched_on <= :d ORDER BY launched_on, model"),
        {"d": as_of},
    )
    return [LaunchRow(*r) for r in rows]


def _listing(r: Any) -> ListingRow:
    return ListingRow(r[0], r[1], r[2], r[3], r[4], _f(r[5]), r[6], r[7], r[8], r[9])


def live_listings(s: Session, as_of: date, channel: str | None = None) -> list[ListingRow]:
    """The live listings listed on or before `as_of` (of one channel, or all), by listing id."""
    rows = s.execute(
        text(
            f"SELECT {_LISTING} FROM device_listing "  # noqa: S608 - fixed column list
            "WHERE status = 'live' AND listed_at < CAST(:d AS date) + 1 AND (CAST(:c AS text) IS NULL OR channel = :c) "
            "ORDER BY listing_id"
        ),
        {"d": as_of, "c": channel},
    )
    return [_listing(r) for r in rows]


def listing_of(s: Session, imei: str) -> ListingRow | None:
    """The newest listing of a device, or None."""
    r = s.execute(
        text(f"SELECT {_LISTING} FROM device_listing WHERE imei = :i ORDER BY listed_at DESC, listing_id DESC LIMIT 1"),  # noqa: S608
        {"i": imei},
    ).first()
    return _listing(r) if r else None


def open_bids(s: Session, lot_ref: str, as_of: date) -> list[BidRow]:
    """The bids on a lot received on or before `as_of`, oldest first."""
    rows = s.execute(
        text(
            "SELECT bid_id, lot_ref, buyer_code, amount, fees, logistics, received_at FROM device_bid "
            "WHERE lot_ref = :l AND received_at < CAST(:d AS date) + 1 ORDER BY received_at, bid_id"
        ),
        {"l": lot_ref, "d": as_of},
    )
    return [BidRow(r[0], r[1], r[2], _f(r[3]), _f(r[4]), _f(r[5]), r[6]) for r in rows]


def replacement_demand(s: Session, sku_key: str, grade: str, as_of: date) -> int:  # noqa: ARG001 - no raising date stored
    """The units still wanted for a SKU that a device of `grade` can fill: the demand whose minimum grade it meets
    (A is the best, so a B meets a minimum of B or C), less what is reserved."""
    n = s.execute(
        text(
            "SELECT COALESCE(sum(GREATEST(qty - jsonb_array_length(reserved), 0)), 0) FROM device_replacement_demand "
            "WHERE sku_key = :k AND grade_min >= :g"
        ),
        {"k": sku_key, "g": grade},
    ).scalar_one()
    return int(n)
