"""Workspace state: the demo's in-memory lists as ordered collections in the database (table state_item; B12).

A collection is a list of JSON items in the demo's shape, each with a unique id, kept in insertion order. A module
that owns a collection registers its starting values with `register`; the collection is seeded from them the first
time it is read, and never again (an emptied collection stays empty) until `reset`.

All reads and writes use the caller's session, so they commit or roll back with the action that made them.
"""

import json
import re
from collections.abc import Callable
from typing import Any, cast

from sqlalchemy import Connection, CursorResult, text
from sqlalchemy.orm import Session

Item = dict[str, Any]
_SEEDS: dict[str, Callable[[], list[tuple[str, Item]]]] = {}


def register(collection: str, starting: Callable[[], list[tuple[str, Item]]]) -> None:
    """Declare a collection and its starting items, [(id, item)] in order (oldest first)."""
    _SEEDS[collection] = starting


def _ensure(s: Session, collection: str) -> None:
    """Seed the collection the first time it is read.

    The seed is written and committed in its own short transaction, not the caller's: if the caller's transaction held
    the seed lock and uncommitted rows, any other session the same request opens (store.ensure, load_context …) that
    reads the collection would wait on that lock forever (a request deadlocking itself; seen in B17 after test resets).
    """
    if collection not in _SEEDS:
        raise KeyError(f"unknown state collection {collection!r}")
    if s.execute(text("SELECT 1 FROM state_seed WHERE collection = :c"), {"c": collection}).first():
        return
    from di.core.db import engine

    with engine.begin() as conn:
        # one seeder at a time per collection; the loser of the race finds it seeded
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:c))"), {"c": "state:" + collection})
        if conn.execute(text("SELECT 1 FROM state_seed WHERE collection = :c"), {"c": collection}).first():
            return
        for item_id, item in _SEEDS[collection]():
            _insert(conn, collection, item_id, item)
        conn.execute(text("INSERT INTO state_seed (collection) VALUES (:c)"), {"c": collection})


def _insert(s: Session | Connection, collection: str, item_id: str, item: Item) -> None:
    s.execute(
        text("INSERT INTO state_item (collection, id, data) VALUES (:c, :i, CAST(:d AS jsonb))"),
        {"c": collection, "i": item_id, "d": json.dumps(item)},
    )


def items(s: Session, collection: str, newest_first: bool = False) -> list[Item]:
    _ensure(s, collection)
    order = "DESC" if newest_first else "ASC"
    return list(
        s.execute(text(f"SELECT data FROM state_item WHERE collection = :c ORDER BY seq {order}"), {"c": collection}).scalars()  # noqa: S608 - `order` is ASC or DESC; values are bound
    )


def get(s: Session, collection: str, item_id: str, for_update: bool = False) -> Item | None:
    _ensure(s, collection)
    q = "SELECT data FROM state_item WHERE collection = :c AND id = :i" + (" FOR UPDATE" if for_update else "")  # noqa: S608 - only the fixed FOR UPDATE suffix is appended; values are bound
    item: Item | None = s.execute(text(q), {"c": collection, "i": item_id}).scalar()
    return item


def need(s: Session, collection: str, item_id: str, for_update: bool = False) -> Item:
    """get() for an item the caller knows exists (an action's guard found it in the same transaction)."""
    item = get(s, collection, item_id, for_update)
    if item is None:
        raise LookupError(f"no {collection} item {item_id!r}")
    return item


def add(s: Session, collection: str, item_id: str, item: Item) -> Item:
    """Append a new item (it becomes the newest)."""
    _ensure(s, collection)
    _insert(s, collection, item_id, item)
    return item


def put(s: Session, collection: str, item_id: str, item: Item) -> Item:
    """Replace an item in place, keeping its position; adds it if it does not exist."""
    _ensure(s, collection)
    s.execute(
        text(
            "INSERT INTO state_item (collection, id, data) VALUES (:c, :i, CAST(:d AS jsonb)) "
            "ON CONFLICT (collection, id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()"
        ),
        {"c": collection, "i": item_id, "d": json.dumps(item)},
    )
    return item


def delete(s: Session, collection: str, item_id: str) -> bool:
    _ensure(s, collection)
    n = cast(
        CursorResult[Any],
        s.execute(text("DELETE FROM state_item WHERE collection = :c AND id = :i"), {"c": collection, "i": item_id}),
    )
    return n.rowcount > 0


def next_number(s: Session, collection: str, prefix: str, after: int) -> int:
    """The next number for ids like NTF-102: one more than the highest used with this prefix, or after + 1. Holds a
    lock for the rest of the transaction, so two writers cannot take the same number."""
    _ensure(s, collection)
    s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"num:{collection}:{prefix}"})
    ids = s.execute(
        text("SELECT id FROM state_item WHERE collection = :c AND id LIKE :p"), {"c": collection, "p": prefix + "%"}
    ).scalars()
    nums = [int(m.group(1)) for i in ids if (m := re.fullmatch(re.escape(prefix) + r"(\d+)", i))]
    return max([after, *nums]) + 1


def reset(collections: list[str] | None = None) -> None:
    """Forget the given collections (all by default); each is reseeded from its starting values on its next read."""
    from di.core.db import SessionLocal

    with SessionLocal() as s:
        names = collections or list(_SEEDS)
        s.execute(text("DELETE FROM state_item WHERE collection = ANY(:n)"), {"n": names})
        s.execute(text("DELETE FROM state_seed WHERE collection = ANY(:n)"), {"n": names})
        s.commit()
