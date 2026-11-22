"""The instruction row update only writes known columns (refactor A3, F15)."""

import pytest

from di.services.instructions.send import _update


def test_update_refuses_an_unknown_column(session):
    with pytest.raises(ValueError, match="not an updatable instruction column"):
        _update(session, 0, **{"status = 'x'; --": "y"})
    with pytest.raises(ValueError, match="not an updatable instruction column"):
        _update(session, 0, approval_ref="x")
    session.rollback()


def test_update_accepts_the_columns_send_writes(session):
    _update(  # id 0 matches no row: the statement only has to be valid
        session, 0, status="failed", last_error="e", simulated=True, due_at=None, sent_at=None, request=[], waiting_for=None
    )
    session.rollback()
