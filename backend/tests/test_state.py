"""B12: the workspace state store (di/core/state.py)."""

import pytest
from sqlalchemy import text

from di.core import state
from di.core.db import SessionLocal

state.register("test.things", lambda: [("T-1", {"id": "T-1", "n": 1}), ("T-2", {"id": "T-2", "n": 2})])


@pytest.fixture
def s():
    state.reset(["test.things"])
    with SessionLocal() as session:
        yield session
        session.rollback()
    state.reset(["test.things"])


def test_seeded_once_in_order(s):
    assert [x["id"] for x in state.items(s, "test.things")] == ["T-1", "T-2"]
    assert [x["id"] for x in state.items(s, "test.things", newest_first=True)] == ["T-2", "T-1"]
    state.delete(s, "test.things", "T-1")
    state.delete(s, "test.things", "T-2")
    s.commit()
    assert state.items(s, "test.things") == []  # an emptied collection is not reseeded


def test_add_put_get_and_numbering(s):
    n = state.next_number(s, "test.things", "T-", after=100)
    assert n == 101
    state.add(s, "test.things", f"T-{n}", {"id": f"T-{n}", "n": n})
    assert state.next_number(s, "test.things", "T-", after=100) == 102
    state.put(s, "test.things", "T-1", {"id": "T-1", "n": 10})
    assert [x["n"] for x in state.items(s, "test.things")] == [10, 2, 101]  # put keeps the position
    assert state.get(s, "test.things", "T-1") == {"id": "T-1", "n": 10} and state.get(s, "test.things", "nope") is None


def test_rollback_leaves_nothing(s):
    state.add(s, "test.things", "T-9", {"id": "T-9"})
    s.rollback()
    assert state.get(s, "test.things", "T-9") is None


def test_unknown_collection_is_an_error(s):
    with pytest.raises(KeyError):
        state.items(s, "nope")
    assert s.execute(text("SELECT count(*) FROM state_seed WHERE collection = 'nope'")).scalar() == 0
