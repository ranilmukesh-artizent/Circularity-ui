"""B11: cases in the database and the stage machine (docs/backend-steps.md)."""

import pytest
from sqlalchemy import text

from di.core import golden
from di.core.db import SessionLocal
from di.services.actions.registry import ActionError
from di.services.cases import lifecycle, store

GOLDEN = {c["id"]: c for c in golden.load("cases")}


@pytest.fixture
def s():
    store.reset()
    with SessionLocal() as session:
        yield session
    store.reset()


def test_every_case_is_open_with_the_engines_evaluation(s):
    cases = store.all_cases(s)
    assert [c["id"] for c in cases] == sorted(GOLDEN)
    for c in cases:
        g = GOLDEN[c["id"]]
        assert (c["owner"], c["location"], c["stage"]) == (g["owner"], g["location"], g["stage"])
        assert c["routes"] == g["routes"] and c["recommendation"] == g.get("recommendation")
    rt = store.get(s, "RT-1048")
    assert rt["recommendation"] is rt["routes"][0] and rt["recommendation"]["net"] == 9600
    assert s.execute(text("SELECT count(*) FROM case_stage_log WHERE reason = 'Case opened'")).scalar() == 128


def test_scope_reads_owner_and_location(s):
    assert store.scope(s, "RT-1048") == ("Customer A", "Warehouse 1")
    assert store.scope(s, "RT-9999") is None


def test_a_move_is_saved_logged_and_published(s):
    c = store.get(s, "RT-1048", for_update=True)
    lifecycle.move(s, c, "approved", "Approved under APR-TEST", "approver")
    s.commit()
    again = store.get(s, "RT-1048")
    assert again["stage"] == "approved"
    assert s.execute(text("SELECT stage, version FROM case_record WHERE id = 'RT-1048'")).one() == ("approved", 2)
    h = lifecycle.history(s, "RT-1048")
    assert [(x["from_stage"], x["to_stage"], x["actor"]) for x in h] == [
        (None, "awaiting_approval", "system"),
        ("awaiting_approval", "approved", "approver"),
    ]
    ev = s.execute(
        text(
            "SELECT payload FROM domain_event WHERE type = 'case.stage_changed' AND case_id = 'RT-1048' ORDER BY id DESC LIMIT 1"
        )
    ).scalar()
    assert ev == {
        "case_id": "RT-1048",
        "from": "awaiting_approval",
        "to": "approved",
        "reason": "Approved under APR-TEST",
        "by": "approver",
    }


@pytest.mark.parametrize(
    ("frm", "to", "ok"),
    [
        ("none", "awaiting_approval", True),
        ("awaiting_approval", "approved", True),
        ("awaiting_approval", "reeval", True),
        ("approved", "executing", True),
        ("executing", "closed", True),
        ("reeval", "awaiting_approval", True),
        ("none", "approved", False),
        ("awaiting_approval", "executing", False),
        ("closed", "reeval", False),
        ("executing", "approved", False),
    ],
)
def test_allowed_moves(frm, to, ok):
    assert lifecycle.can_move(frm, to) is ok


def test_a_refused_move_changes_nothing(s):
    c = store.get(s, "RT-1048", for_update=True)
    with pytest.raises(ActionError) as e:
        lifecycle.move(s, c, "closed", "skip ahead", "ops")
    assert e.value.code == "conflict"
    s.rollback()
    assert store.get(s, "RT-1048")["stage"] == "awaiting_approval"
